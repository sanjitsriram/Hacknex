# EvidenceOCR — Phase 5: PaddleOCR-VL-1.6 Document Intelligence Walkthrough

## Section A: Executive Summary & Objective Realization

Phase 5 of **EvidenceOCR (HackNex 2026)** integrates **PaddleOCR-VL-1.6** as the platform's third artificial intelligence model, elevating the system from isolated text-line and document-level recognition to **hierarchical document layout intelligence, topological reading-order sequencing, tabular structure isolation, and sanitized Markdown extraction**.

```mermaid
graph TD
    A[Original Document in MongoDB GridFS] --> B[ProcessingJob Lifecycle Engine]
    B --> C[Model 1: PP-OCRv6 Cloud Line Detection]
    B --> D[Model 2: TrOCR Base Local CPU Crop OCR]
    B --> E[Model 3: PaddleOCR-VL-1.6 Document Intelligence]
    
    E --> F[Hierarchical Layout Blocks]
    E --> G[Topological Reading-Order Badges]
    E --> H[Isolated Tabular Structures]
    E --> I[Sanitized Prettified Markdown]
    
    F --> J[Tri-Model Comparison & Human Verification]
    G --> J
    H --> J
    I --> J
    C --> J
    D --> J
    J --> K[Immutable MongoDB Atlas Collections & Audit Trail]
```

### Key Milestones Delivered in Phase 5:
1. **Third Model Integration**: Integrated `PaddleOCR-VL-1.6` via hosted cloud inference (`https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`) without adding local C++ dependencies, heavy VLM weights, or GPU hosting burdens.
2. **Normalized Hierarchical Layouts**: Extracted structural blocks (`paragraph_title`, `text`, `table`, `formula`, `seal`, `figure`) with coordinate bounding boxes normalized strictly to `[0.0, 100.0]%` of the original unrotated document page (Invariant 1).
3. **Reading-Order Sequencing**: Extracted and displayed topological reading sequence (`reading_order` badges `[1]`, `[2]`, `[3]`, etc.) directly on document preview overlays and transcription outlines.
4. **Isolated Table Parsing & Prettified Markdown**: Generated clean Markdown representations and isolated structured tabular blocks with HTML formatting.
5. **Phase 4 Defect Resolution**: Decoupled recognition uncertainty (`LOW_CONFIDENCE`) from permanent illegibility (`is_illegible`), eliminating false illegibility classifications when raw model confidence was $< 0.30$.
6. **Tri-Model Provenance Layering**: Enabled side-by-side verification of all three models (PP-OCRv6 Cloud, TrOCR Base Local CPU, PaddleOCR-VL-1.6 Cloud) in distinct, non-destructive provenance layers.
7. **Production Verification & Test Suite**: 81 backend pytest tests (100% passing rate) and 5 frontend contract tests passing cleanly.

---

## Section B: Architectural Invariants Compliance Matrix (Invariants 1-8)

| Invariant | Title | Phase 5 Technical Implementation & Proof | Compliance Status |
| :--- | :--- | :--- | :---: |
| **Invariant 1** | **Evidence-First OCR** | Coordinates from PaddleOCR-VL are normalized strictly to unrotated percentage space `[0.0, 100.0]`: $x = \frac{x_{\min}}{W} \times 100$, $y = \frac{y_{\min}}{H} \times 100$, $w = \frac{x_{\max} - x_{\min}}{W} \times 100$, $h = \frac{y_{\max} - y_{\min}}{H} \times 100$. Viewport zoom/rotation are client-side SVG transforms. | **STRICTLY ENFORCED** |
| **Invariant 2** | **No Fabricated Characters** | PaddleOCR-VL predictions are presented as unverified automated proposals. When handwriting strokes are ambiguous, low confidence is preserved (`LOW_CONFIDENCE`), never injecting synthetic completions or hallucinated words. | **STRICTLY ENFORCED** |
| **Invariant 3** | **Reproducible Cloud-Model Versions** | Metadata records `provider_id="paddleocr-vl-cloud"`, `model_version="PaddleOCR-VL-1.6"`, `temperature=0.0`, SHA-256 hash of input image, and cloud Job ID. No unversioned aliases (e.g. `latest`) are permitted. | **STRICTLY ENFORCED** |
| **Invariant 4** | **Credentials Exclusively from Environment** | `PADDLEOCR_ACCESS_TOKEN` is loaded dynamically via typed `Settings` (`pydantic-settings`). Excluded from `.git`, logs, client bundles, and API responses. | **STRICTLY ENFORCED** |
| **Invariant 5** | **No Fake Production Data** | Sample fixtures in frontend are explicitly flagged (`sample=True`, `demo-1`). Genuine held-out IAM lines evaluated honestly without mock numbers or fabricated metrics. | **STRICTLY ENFORCED** |
| **Invariant 6** | **No Bypassing Tests** | All 81 backend pytest tests and 5 frontend contract tests pass cleanly. Zero skipped or disabled tests. | **STRICTLY ENFORCED** |
| **Invariant 7** | **Changes Only Within Approved Scope** | Confined strictly to Phase 5 boundaries. No Phase 6 Bayesian evidence fusion, confidence calibration, or final export workflows implemented. | **STRICTLY ENFORCED** |
| **Invariant 8** | **Pluggable Provider Abstractions** | `PaddleOCRVLCloudProvider` implements `BaseVLMProvider` and `BaseOCRProvider` protocols, communicating via standard `httpx.AsyncClient` with mock adapters for automated test suites. | **STRICTLY ENFORCED** |

---

## Section C: Official PaddleOCR-VL Documentation & API Protocol Findings

Investigation of official PaddleOCR documentation and the `PaddlePaddle/PaddleOCR` repository revealed the exact REST API schema utilized by AI Studio for model `PaddleOCR-VL-1.6`:

1. **Job Submission**:
   - `POST https://paddleocr.aistudio-app.com/api/v2/ocr/jobs`
   - Headers: `Authorization: token <PADDLEOCR_ACCESS_TOKEN>`
   - Payload:
     ```json
     {
       "model": "PaddleOCR-VL-1.6",
       "file": "<base64_encoded_image_bytes>",
       "fileType": 1,
       "optionalPayload": {
         "useLayoutDetection": true,
         "prettifyMarkdown": true,
         "temperature": 0.0
       }
     }
     ```
2. **Job Polling & Results Retrieval**:
   - `GET https://paddleocr.aistudio-app.com/api/v2/ocr/jobs/{jobId}`
   - Header: `Authorization: token <PADDLEOCR_ACCESS_TOKEN>`
   - Terminal States: `done` (completed), `failed`, `timeout`.
3. **Response Parsing**:
   - The response contains `result.layoutParsingResults[page_idx]`.
   - `prunedResult`: Contains `width`, `height`, and `parsing_res_list` with `block_id`, `block_label` (`paragraph_title`, `text`, `table`, etc.), `block_order` (topological reading sequence), `block_bbox` (`[min_x, min_y, max_x, max_y]`), and `block_polygon_points`.
   - `markdown`: Clean full-page prettified text (`{"text": "# Title..."}`).
   - Detection scores are extracted from `prunedResult.layout_det_res.boxes`.

---

## Section D: Data Model & Schema Implementation

Phase 5 introduced typed domain models in `backend/src/evidence_ocr/models/parsing.py` and API schemas in `backend/src/evidence_ocr/schemas/parsing.py`:

```python
class LayoutBlock(BaseModel):
    block_id: str
    page_index: int = 0
    block_type: str = "text"  # paragraph_title, text, table, formula, figure, seal
    bounding_box: BoundingBox  # Normalized [0.0, 100.0]%
    polygon: Optional[List[List[float]]] = None
    raw_bbox: Optional[List[float]] = None
    content: str = ""
    reading_order: int = 0
    confidence: Optional[float] = None
    table_html: Optional[str] = None

class ParsedPage(BaseModel):
    page_index: int = 0
    width: int
    height: int
    markdown_text: str = ""
    blocks: List[LayoutBlock] = Field(default_factory=list)
    reading_order_sequence: List[str] = Field(default_factory=list)
    tables_count: int = 0

class DocumentParsingRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    document_id: str
    job_id: str
    provider_id: str = "paddleocr-vl-cloud"
    model_version: str = "PaddleOCR-VL-1.6"
    provider_job_id: Optional[str] = None
    input_sha256: Optional[str] = None
    page_count: int = 1
    markdown_text: str = ""
    pages: List[ParsedPage] = Field(default_factory=list)
    total_blocks: int = 0
    execution_time_ms: float = 0.0
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

---

## Section E: PaddleOCRVLCloudProvider Implementation & Security

The provider class `PaddleOCRVLCloudProvider` was implemented in `backend/src/evidence_ocr/providers/paddleocr_vl.py`.

### Resilient Polling with Exponential Backoff
- Base polling interval: 1.5s
- Growth factor: 1.5x up to maximum 5.0s
- Maximum poll timeout: configurable via `PADDLEOCR_VL_POLL_TIMEOUT` (default: 180s)
- Request timeout: 60s
- Concurrency limiting: `asyncio.Semaphore(settings.paddleocr_vl_concurrency)`

### Error Handling & Mapping
- HTTP 401 / 403: Translated to `AuthenticationError`
- Remote job failure: Translated to `OCRProviderError`
- Network timeouts: Translated to `ProviderTimeoutError` with automatic retry handling

---

## Section F: PyMongo Async & MongoDB Atlas Persistence

A dedicated repository `DocumentParsingRepository` was created in `backend/src/evidence_ocr/db/repositories/parsing.py`, operating on collection `document_parsing_runs`:

### Indexes Created:
1. `{"document_id": 1, "created_at": -1}` (Fast document history lookup)
2. `{"job_id": 1}` (Direct task correlation)
3. `{"provider_job_id": 1}` (Cloud job idempotency tracking)

---

## Section G: Document Intelligence Job Lifecycle & Polling Architecture

`ProcessingJob` in `backend/src/evidence_ocr/models/job.py` was extended with `task_type: JobTaskType = "document_intelligence"`:

1. Client dispatches `POST /api/v1/documents/{id}/document-intelligence`.
2. Worker runner creates job with `status="queued"`, `task_type="document_intelligence"`.
3. Background task retrieves raw document stream from GridFS, computes SHA-256 verification hash, transitions state to `status="running"`, `stage="layout_analysis"`.
4. Asynchronous polling queries AI Studio job until terminal completion.
5. Blocks are normalized to percentage space `[0.0, 100.0]%` and sorted by `block_order`.
6. Full `DocumentParsingRun` is persisted in `document_parsing_runs` collection.
7. Job updates to `status="completed"`, capturing duration in `execution_time_ms`.

---

## Section H: API Surface & Contract Verification

Phase 5 registered three dedicated endpoints under `backend/src/evidence_ocr/api/v1/endpoints/documents.py`:

| Method | Endpoint | Description | Response Status |
| :--- | :--- | :--- | :---: |
| `POST` | `/api/v1/documents/{id}/document-intelligence` | Schedule asynchronous PaddleOCR-VL pipeline | `202 Accepted` |
| `GET` | `/api/v1/documents/{id}/parsed-document` | Retrieve latest parsed document intelligence run | `200 OK` / `404 Not Found` |
| `GET` | `/api/v1/documents/{id}/parsing-history` | Retrieve chronological parsing runs for document | `200 OK` |

---

## Section I: Next.js Frontend Workspace Integration

The Next.js 16 frontend (`frontend/src/components/workspace.tsx`) was upgraded with state and polling hooks:

- State variables: `vlResults`, `vlJobState`, `overlayMode`, `activeBlockId`.
- LocalStorage caching: `hacknex:vl_results:v1` caches results locally, surviving browser page reloads.
- Dual action banner: Visibly displays status of PaddleOCR-VL-1.6 and PP-OCRv6 cloud pipelines.
- Responsive sub-navigation: Switch between `Layout & Reading Order`, `Sanitized Markdown`, `Parsed Tables`, and `Detected Text Lines`.

---

## Section J: Layout Overlays, Reading Order & Table Rendering

### Document Preview Overlays
- An overlay toggle bar (`All (PP-OCR + VL)`, `PP-OCR Lines`, `PaddleOCR-VL Blocks`) controls canvas layers.
- Bounding boxes are styled by layout type:
  - `paragraph_title`: Indigo border with `#order Title` badge.
  - `text`: Emerald border with `#order Text` badge.
  - `table`: Amber border with `#order Table` badge.
  - `formula` / other: Cyan/Rose border with `#order Block` badge.
- Clicking an overlay focuses the corresponding block in the transcription pane.

### Tabular Structure & Markdown View
- Structured tables are rendered in dedicated table cards.
- Prettified Markdown text is displayed with a one-click `Copy Markdown` button.

---

## Section K: 3-Model Provenance Comparison Architecture

The `Comparison` tab provides a side-by-side evaluation of all three models:

```
+----------------------------------------------------------------------------------------------------+
| MULTI-MODEL CANDIDATE PROVENANCE                                                  Tri-Model Stack  |
+---------+----------------------------+----------------------------+-----------------------+--------+
| Target  | Model 1: PP-OCRv6 (Line)   | Model 2: TrOCR Base (Crop) | Model 3: PaddleOCR-VL | Status |
+---------+----------------------------+----------------------------+-----------------------+--------+
| #1 Title| "SITE INSPECTION REPORT"   | "SITE INSPECTION REPORT"   | "SITE INSPECTION..."  | Verified
|         | Conf: 98.4% (PP-OCRv6)     | Conf: 97.2% (2,491ms)      | Order #1 (Title)      |        |
| #2 Text | "Crack detected on beam"   | "Crack detected on beam"   | "Crack detected on..."| Pending|
|         | Conf: 88.2% (PP-OCRv6)     | Conf: 91.5% (2,810ms)      | Order #2 (Text)       |        |
+---------+----------------------------+----------------------------+-----------------------+--------+
```

---

## Section L: Defect Resolution (Low Confidence vs Illegibility)

In Phase 4, detected lines with raw confidence $< 0.30$ were flagged as permanently illegible (`is_illegible=True`). 

### Defect Fix:
- In `backend/src/evidence_ocr/workers/runner.py`, low confidence is decoupled from illegibility:
  ```python
  # Confidence < 0.30 represents UNCERTAINTY, not permanent illegibility
  is_low_confidence = conf < 0.30
  region = DocumentRegion(
      ...
      is_illegible=False,  # Illegibility requires human reviewer confirmation or explicit illegible marker
      confidence=conf,
  )
  ```
- Regions with low confidence are highlighted with a distinct `LOW CONFIDENCE` warning badge rather than corrupting the ground truth illegibility state.

---

## Section M: Reproducible Accuracy Benchmark & Evaluation Metrics

The evaluation script `scripts/evaluate_paddleocr_vl.py` was executed against held-out handwritten lines from the Teklia/IAM dataset (`backend/tests/fixtures/benchmark_dataset/metadata.json`):

### Benchmark Results (`benchmark_results_paddleocr_vl.json`):
- **Dataset**: `IAM-Handwriting-Line-Test`
- **Dataset SHA-256**: `0f7270051136d5d2708ef1d2a0d276c7809847f0aada0799a572ea8a4d118f2d`
- **Evaluated Samples**: Held-out IAM lines
- **Median Cloud Latency (P50)**: 8.798s
- **Observations**: PaddleOCR-VL is optimized for whole-document structural parsing and layout comprehension. On narrow single-line crops, focused handwriting OCR (TrOCR Base) achieves superior CER (6.6%), while PaddleOCR-VL provides layout hierarchy, reading order, and table isolation.

---

## Section N: Test Suite Execution & Verification Evidence

### Backend Pytest Results:
```
============================= test session starts =============================
platform win32 -- Python 3.11.9, pytest-9.1.1, pluggy-1.6.0
rootdir: B:\Hackathon\hancknex\backend
collected 81 items

backend\tests\test_api_contract.py .....                                 [  6%]
backend\tests\test_config.py ...                                         [  9%]
backend\tests\test_cropper.py ......                                     [ 17%]
backend\tests\test_document_parsing_endpoints.py ....                    [ 22%]
backend\tests\test_document_recognition_endpoints.py ....                [ 27%]
backend\tests\test_gridfs_ingestion.py ....................              [ 51%]
backend\tests\test_health.py ...                                         [ 55%]
backend\tests\test_middleware.py ....                                    [ 60%]
backend\tests\test_paddleocr_provider.py ........                        [ 70%]
backend\tests\test_paddleocr_vl_provider.py .......                      [ 79%]
backend\tests\test_providers.py ...                                      [ 82%]
backend\tests\test_region_recognition_api.py ..                          [ 85%]
backend\tests\test_schemas.py ....                                       [ 90%]
backend\tests\test_services.py ...                                       [ 93%]
backend\tests\test_trocr_provider.py .....                               [100%]

======================== 81 passed, 1 warning in 9.94s ========================
```

### Frontend Test Results:
```
✔ upload boundaries and supported MIME types (0.6305ms)
✔ region decisions update the intended line, including duplicate illegibility markers (0.1603ms)
✔ manual text conflicts never change an unrelated occurrence (0.0876ms)
✔ malformed storage is rejected and invalid audit entries are ignored (1.9223ms)
✔ api module exports and document mapping contract (39.6445ms)
ℹ tests 5 | pass 5 | fail 0 | duration_ms 315.6706
```

### Browser E2E Verification Recording:
- Verification web recording saved to artifacts directory:
  `verify_phase5_ui_1791488093040.webp`

---

## Section O: Phase 6 Hand-Off & Boundary Governance

### Phase 5 Boundaries Maintained:
- No Phase 6 Bayesian evidence fusion, calibration, or final export workflows implemented.
- Model proposals remain isolated in distinct provenance layers.
- Raw provider outputs and human edits are kept strictly partitioned.

### Ready for Phase 6:
With Model 1 (PP-OCRv6), Model 2 (TrOCR Base), and Model 3 (PaddleOCR-VL-1.6) fully integrated, tested, and persisted in MongoDB Atlas, the platform is positioned for **Phase 6: Multi-Model Evidence Fusion, Confidence Calibration, and Auditable Export**.
