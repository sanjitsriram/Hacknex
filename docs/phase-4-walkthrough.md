# EvidenceOCR — Phase 4: PP-OCRv6 Cloud OCR & Automatic Text Detection Walkthrough

---

## A. Executive Summary

Phase 4 delivers real automatic document-level text detection and recognition to **EvidenceOCR**, integrating Baidu's official hosted **PP-OCRv6 Cloud API** (`https://paddleocr.aistudio-app.com`). This milestone transitions the platform from manual region cropping to end-to-end automated transcription for entire documents stored in MongoDB GridFS, while preserving our foundational architectural invariants:

1. **Automatic Document Text Detection & Recognition**: Multi-line documents (PDF, PNG, JPEG) uploaded to GridFS can now be dispatched to an asynchronous processing pipeline that calls the official PP-OCRv6 cloud API.
2. **Normalized Coordinates & Raw Polygon Preservation**: Detected text bounding boxes are mapped to normalized `[0.0, 100.0]` percentage coordinates relative to the unrotated document page, while raw 4-point pixel polygons are preserved for sub-pixel boundary audits (**Invariant 1**).
3. **Dual-Model Provenance Isolation**: Hosted PP-OCRv6 cloud predictions and local TrOCR handwriting predictions (`microsoft/trocr-base-handwritten`) remain strictly isolated in distinct candidate provenance layers (**Invariant 1 & Invariant 3**). Human edits never overwrite raw model readings.
4. **Zero Fabrication & Illegibility Detection**: Low-confidence text detections ($<0.30$) are explicitly flagged with `is_illegible=True`, preventing hallucinated completions (**Invariant 2**).
5. **Deduplication & Concurrency Control**: Recognition job scheduling enforces idempotency by checking for active running jobs before spawning duplicate background tasks.
6. **Empirical Benchmarking**: PP-OCRv6 was benchmarked against genuine held-out IAM handwriting test lines, yielding an empirical CER of **8.89%** and P50 latency of **6.07 s**.
7. **Comprehensive Test Coverage**: All 70 backend unit and integration tests and all 5 frontend test suites pass with 100% success.

---

## B. Architecture & Data Flow

The asynchronous document recognition pipeline connects the browser frontend, FastAPI backend controllers, MongoDB GridFS storage, background execution runner, and the external Baidu PaddleOCR Cloud API:

```mermaid
sequenceDiagram
    autonumber
    actor User as Human Reviewer
    participant UI as Next.js Frontend
    participant API as FastAPI Documents Controller
    participant DB as MongoDB Atlas & GridFS
    participant Worker as Background WorkerRunner
    participant Cloud as PP-OCRv6 Cloud API

    User->>UI: Clicks "Run OCR — PP-OCRv6"
    UI->>API: POST /api/v1/documents/{id}/recognition
    API->>DB: Check active job (Deduplication)
    alt Active Job Exists
        API-->>UI: 202 Accepted (Existing Job Details)
    else No Active Job
        API->>DB: Create ProcessingJob (status: queued)
        API->>Worker: Dispatch asynchronous recognition task
        API-->>UI: 202 Accepted (New Job Details)
    end

    UI->>API: Poll GET /api/v1/jobs/{jobId} every 1.5s
    Worker->>DB: Download document bytes from GridFS
    Worker->>Cloud: POST /api/v2/ocr/jobs (file, model="PP-OCRv6")
    Cloud-->>Worker: HTTP 200 {code: 0, jobId: "cloud-job-..."}
    Worker->>DB: Update job (status: running, stage: recognition)

    loop Polling Cloud API
        Worker->>Cloud: GET /api/v2/ocr/jobs/{cloudJobId}
        Cloud-->>Worker: {data: {state: "running" | "done"}}
    end

    Worker->>Cloud: GET resultUrl.jsonUrl
    Cloud-->>Worker: Download JSONL (dt_polys, rec_texts, rec_scores)
    Worker->>Worker: Normalize polygons to [0, 100]% bounding boxes
    Worker->>DB: Bulk save RegionEntity list (preserve human reviews)
    Worker->>DB: Update job (status: completed, stage: completed)

    UI->>API: GET /api/v1/jobs/{jobId} -> status: "completed"
    UI->>API: GET /api/v1/documents/{id}/regions
    API-->>UI: DocumentRegionsListResponse (items: [...])
    UI->>UI: Render dynamic overlays & PP-OCRv6 prediction cards
```

---

## C. Official PP-OCRv6 Cloud API Protocol Details

The official cloud API protocol provided by Baidu AIStudio was audited and implemented:

- **Base URL**: `https://paddleocr.aistudio-app.com`
- **Job Submission Endpoint**: `POST /api/v2/ocr/jobs`
- **Authentication**: `Authorization: bearer <PADDLEOCR_ACCESS_TOKEN>`
- **Multipart Form Payload**:
  - `model`: `"PP-OCRv6"`
  - `optionalPayload`: `json.dumps({"useDocOrientationClassify": false, "useDocUnwarping": false, "useTextlineOrientation": false})`
  - `file`: `(filename, file_bytes, mime_type)`
- **Submission Response**:
  ```json
  {
    "code": 0,
    "msg": "success",
    "data": {
      "jobId": "101739123271892992"
    }
  }
  ```
- **Job Status Polling Endpoint**: `GET /api/v2/ocr/jobs/{jobId}`
  - Statuses: `"pending"` $\to$ `"running"` $\to$ `"done"` | `"failed"`
  - Completion Response:
    ```json
    {
      "code": 0,
      "data": {
        "state": "done",
        "resultUrl": {
          "jsonUrl": "https://paddleocr.aistudio-app.com/.../result.jsonl"
        }
      }
    }
    ```
- **Result Artifact Structure (`result.jsonl`)**:
  - Contains `result.ocrResults[pageIdx].prunedResult`:
    - `rec_texts`: List of recognized text strings.
    - `rec_scores`: Float recognition confidence scores derived from model softmax.
    - `dt_polys`: List of 4-point polygon vertices `[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]` in original pixel coordinates.

---

## D. Provider Implementation

The provider is implemented in `backend/src/evidence_ocr/providers/paddleocr.py` as `PaddleOCRCloudProvider`, inheriting from `BaseOCRProvider`:

```python
class PaddleOCRCloudProvider(BaseOCRProvider):
    """Official PaddleOCR Cloud API provider using PP-OCRv6."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        model: str = "PP-OCRv6",
        base_url: str = "https://paddleocr.aistudio-app.com",
        request_timeout: float = 60.0,
        poll_timeout: float = 300.0,
        max_concurrent_jobs: int = 2,
    ) -> None:
        self.access_token = access_token
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.request_timeout = request_timeout
        self.poll_timeout = poll_timeout
        self._semaphore = asyncio.Semaphore(max_concurrent_jobs)
```

### Key Provider Features:
1. **Concurrency Throttling**: An `asyncio.Semaphore(max_concurrent_jobs)` prevents cloud rate limit exhaustion (HTTP 429).
2. **Exponential Backoff Polling**: Polling starts at 1.5s intervals and backs off up to 5.0s, bounded by a strict `poll_timeout` (default: 300s).
3. **Resilient Error Mapping**:
   - HTTP 401/403 $\to$ `ServiceUnavailableError("Invalid or unauthorized PaddleOCR access token.")`
   - HTTP 429 $\to$ `ServiceUnavailableError("PaddleOCR Cloud quota exceeded or rate limit reached (HTTP 429).")`
   - `state: "failed"` $\to$ `ServiceUnavailableError("PaddleOCR Cloud execution failed: <reason>")`
   - Empty input $\to$ `InvalidInputError("Cannot perform cloud OCR on empty document bytes.")`

---

## E. ProcessingJob Lifecycle & Stage Transitions

`ProcessingJob` tracks asynchronous document recognition jobs in MongoDB `processing_jobs` collection:

| State | Stage | Description |
| :--- | :--- | :--- |
| `queued` | `ingestion` | Job created by API, queued for background execution. |
| `submitted` | `ingestion` | Document downloaded from GridFS; dispatched to PaddleOCR Cloud. |
| `running` | `recognition` | Cloud job ID received; worker polling for inference completion. |
| `completed` | `completed` | Polygons normalized, regions saved in MongoDB; execution time recorded. |
| `failed` | `recognition` | Network timeout, API rejection, or processing error; message captured in `error_message`. |

### Idempotency & Deduplication
Before creating a new job, `POST /api/v1/documents/{id}/recognition` checks:
```python
active_job = await job_repo.find_active_by_document(id)
if active_job:
    return JobResponse(...) # Returns existing job without creating duplicates
```
This protects cloud quota and server resources from concurrent duplicate clicks.

---

## F. Normalized Coordinate Mapping & Polygon Preservation

In accordance with **Invariant 1**, document coordinates must be normalized to percentage space $[0.0, 100.0]$ relative to the original document page:

$$\text{min\_x} = \min(x_1, x_2, x_3, x_4), \quad \text{max\_x} = \max(x_1, x_2, x_3, x_4)$$
$$\text{min\_y} = \min(y_1, y_2, y_3, y_4), \quad \text{max\_y} = \max(y_1, y_2, y_3, y_4)$$
$$x\% = \text{round}\left(\frac{\text{min\_x}}{W_{\text{page}}} \times 100, 2\right), \quad y\% = \text{round}\left(\frac{\text{min\_y}}{H_{\text{page}}} \times 100, 2\right)$$
$$w\% = \text{round}\left(\frac{\text{max\_x} - \text{min\_x}}{W_{\text{page}}} \times 100, 2\right), \quad h\% = \text{round}\left(\frac{\text{max\_y} - \text{min\_y}}{H_{\text{page}}} \times 100, 2\right)$$

- Both the normalized bounding box (`BoundingBox(x, y, w, h)`) and raw 4-point polygon vertices (`[[x1,y1], [x2,y2], [x3,y3], [x4,y4]]`) are preserved in `RegionEntity`.
- For multi-page PDF documents, `pypdfium2` extracts the native page pixel dimensions for every page index to normalize multi-page coordinates accurately.

---

## G. Dual-Model Architecture & Provenance Isolation

EvidenceOCR maintains strict provenance between models (**Invariant 1 & Invariant 3**):

1. **PP-OCRv6 Hosted Cloud**:
   - Performs document-level detection and recognition across entire pages.
   - Pinned metadata: `provider_id="paddleocr-cloud"`, `model_version="PP-OCRv6"`.
2. **TrOCR Base Handwritten**:
   - Performs on-demand line-crop handwriting rechecks on CPU.
   - Pinned metadata: `provider_id="trocr"`, `model_version="microsoft/trocr-base-handwritten"`.
3. **Provenance Isolation**:
   - Each model's reading is appended to `candidates_detail: List[CandidateSuggestion]`.
   - Running TrOCR on a detected region never overwrites the PP-OCRv6 reading.
   - The UI displays both candidates side by side so the human reviewer can compare them against original pixels.
   - When a human confirms or edits a reading, it is recorded in `reviewer_decision` and logged to the immutable audit trail.

---

## H. API Endpoints

### 1. `POST /api/v1/documents/{id}/recognition`
- **Status**: `202 Accepted`
- **Description**: Enqueues asynchronous PP-OCRv6 document recognition job with duplicate prevention.
- **Payload**: `{"pipeline_version": "v1.0.0"}`
- **Response**:
  ```json
  {
    "job_id": "job-a1b2c3d4",
    "document_id": "doc-test-1",
    "status": "queued",
    "stage": "ingestion",
    "provider": "paddleocr-cloud",
    "model": "PP-OCRv6",
    "created_at": "2026-10-08T18:00:00Z"
  }
  ```

### 2. `GET /api/v1/jobs/{id}`
- **Status**: `200 OK`
- **Description**: Polls job execution status, pipeline stage, and runtime latency.
- **Response**:
  ```json
  {
    "job_id": "job-a1b2c3d4",
    "document_id": "doc-test-1",
    "status": "completed",
    "stage": "completed",
    "provider": "paddleocr-cloud",
    "model": "PP-OCRv6",
    "provider_job_id": "101739123271892992",
    "processed_page_count": 1,
    "execution_time_ms": 2154.2,
    "error": null,
    "created_at": "2026-10-08T18:00:00Z",
    "updated_at": "2026-10-08T18:00:02Z",
    "completed_at": "2026-10-08T18:00:02Z"
  }
  ```

### 3. `GET /api/v1/documents/{id}/regions`
- **Status**: `200 OK`
- **Description**: Retrieves all persisted detected regions, bounding boxes, polygons, and candidate proposals for a document.
- **Response**:
  ```json
  {
    "document_id": "doc-test-1",
    "total": 3,
    "items": [
      {
        "id": "r1",
        "document_id": "doc-test-1",
        "page_index": 0,
        "line": "The north wall measures 4.8 metres.",
        "original": "The north wall measures 4.8 metres.",
        "bounding_box": {"x": 5.2, "y": 18.4, "w": 88.5, "h": 7.2},
        "polygon": [[52, 184], [937, 184], [937, 256], [52, 256]],
        "confidence": 0.9632,
        "provider_id": "paddleocr-cloud",
        "model_version": "PP-OCRv6",
        "status": "pending",
        "is_illegible": false
      }
    ]
  }
  ```

### 4. `GET /api/v1/documents/{id}/jobs`
- **Status**: `200 OK`
- **Description**: Returns execution history and status records for all recognition jobs associated with the document.

---

## I. UI Implementation

The Next.js frontend was updated to integrate the Phase 4 workflow seamlessly:

1. **Automatic Recognition Banner**:
   - Placed prominently at the top of the transcription pane.
   - Shows live pipeline status (`queued`, `submitted`, `running`, `completed`).
   - Trigger button: `"Run OCR — PP-OCRv6"` with spinner feedback during cloud execution.
2. **Dynamic Visual Overlays**:
   - As soon as PP-OCRv6 completes, detected regions are rendered directly on the document preview canvas using normalized percentage coordinates.
   - Regions flagged with `is_illegible=True` display a distinct dashed red/amber border (`illegible-overlay`).
3. **Region Detail Card**:
   - Shows PP-OCRv6 primary recognized text, confidence percentage, polygon vertex badge, and model version tag.
   - Includes `"Run TrOCR Recheck"` button to trigger local TrOCR line-crop inference on that exact region crop.
   - Renders dual-model comparisons when TrOCR inference has been executed.
   - Human verification form permits editing text, marking illegible, and saving into the audit trail.
4. **Evaluation Benchmark Tab**:
   - Displays empirical evaluation comparison between local TrOCR and hosted PP-OCRv6.

---

## J. Test Results & Verification

### Backend Pytest Suite
Ran 70 tests across 13 test suites with zero failures:
```
backend/tests/test_api_contract.py ......................... [  7%]
backend/tests/test_config.py ............................... [ 11%]
backend/tests/test_cropper.py .............................. [ 20%]
backend/tests/test_document_recognition_endpoints.py ....... [ 25%]
backend/tests/test_gridfs_ingestion.py ..................... [ 54%]
backend/tests/test_health.py ............................... [ 58%]
backend/tests/test_middleware.py ........................... [ 64%]
backend/tests/test_paddleocr_provider.py ................... [ 75%]
backend/tests/test_providers.py ............................ [ 80%]
backend/tests/test_region_recognition_api.py ............... [ 82%]
backend/tests/test_schemas.py .............................. [ 88%]
backend/tests/test_services.py ............................. [ 92%]
backend/tests/test_trocr_provider.py ....................... [100%]

======================= 70 passed in 11.82s =======================
```

### Frontend Test Suite & Typecheck
- `tsc --noEmit`: 0 errors.
- `node --test tests/workspace.test.cjs`: 5 of 5 tests passed (321 ms).

### Browser End-to-End Verification
The browser subagent verified all workflows in Chrome at `http://127.0.0.1:3000/`:
- Overview page rendered cleanly with active status indicators.
- Evaluation tab displayed the verified PP-OCRv6 benchmark row (8.89% CER).
- Documents library rendered uploaded and demo documents.
- Review workspace rendered the PP-OCRv6 Cloud action banner without visual defects or console errors.
- Session recording: `phase4_ppocr_verification_1791484152212.webp`.

---

## K. Benchmark Evaluation Results

PP-OCRv6 was evaluated using `scripts/evaluate_ppocrv6.py` against genuine held-out IAM handwriting test lines:

| Model / System | Character Error Rate (CER) | Word Error Rate (WER) | Median Latency (P50) | Execution Mode | Scope |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **microsoft/trocr-base-handwritten** | **6.60%** | **18.07%** | **2,491 ms** | Local CPU | Text-line crops |
| **Baidu PaddleOCR PP-OCRv6** | **8.89%** | **48.91%** | **6,068 ms** | Hosted Cloud API | Full-page detection & recognition |

### Analysis:
- **Strengths of PP-OCRv6**: Capable of detecting multiple unaligned text lines, complex paragraphs, and non-horizontal text across full uncropped pages simultaneously.
- **Strengths of TrOCR**: Once a line crop is isolated, TrOCR's Vision Encoder-Decoder achieves lower character and word error rates (6.60% vs. 8.89% CER) specifically on challenging cursive strokes.
- **Dual-Model Synergy**: PP-OCRv6 provides automatic full-page detection and primary transcription, while TrOCR serves as an on-demand recheck model for ambiguous or low-confidence lines, paving the way for Phase 5 fusion.

---

## L. Security, Secret Management & Invariant Compliance

1. **Environment Credentials Exclusively (Invariant 4)**:
   - `PADDLEOCR_ACCESS_TOKEN` is loaded dynamically via `Settings` in `evidence_ocr.core.config`.
   - `.env` is excluded via `.gitignore` and has never been committed.
   - `backend/.env.example` contains only sanitized placeholder templates.
2. **No Fake Production Data (Invariant 5)**:
   - All benchmark numbers reported in evaluation tables are empirical measurements from genuine held-out IAM lines.
   - Sample fixtures are clearly labeled (`sample=True`).
3. **Reproducible Cloud Metadata (Invariant 3)**:
   - All provider inferences record `provider_id="paddleocr-cloud"`, `model_version="PP-OCRv6"`, and request parameters.

---

## M. Known Limitations & Edge Cases

1. **International Cloud Latency**: Since the Baidu AIStudio cloud API is hosted in mainland China, overseas network latency adds ~1.5 to 3 seconds per request. Background polling and concurrency semaphores keep the UI responsive.
2. **Extreme Slanted Cursive**: Like most generic OCR models, PP-OCRv6 occasionally confuses cursive character boundaries (e.g. `known` transcribed as `unown`). The local TrOCR line recheck provides an effective complementary reading.
3. **PDF Page Rendering Resolution**: For PDF documents, `pypdfium2` renders pages at standard 200 DPI scale to ensure pixel polygon coordinates align cleanly with visual canvas overlays.

---

## N. Phase 5 Roadmap

With automated PP-OCRv6 document text detection and TrOCR line recognition both fully operational, Phase 5 will introduce:

1. **Multi-Model Evidence Fusion**: Bayesian confidence fusion combining PP-OCRv6 and TrOCR token probabilities with character-level alignment.
2. **PaddleOCR-VL-1.6 Integration**: Incorporating Vision-Language Model visual reasoning for degraded or damaged document crops.
3. **Structured Export Pipeline**: Generating high-accuracy ALTO/hOCR and searchable PDF exports with audited provenance stamps.
