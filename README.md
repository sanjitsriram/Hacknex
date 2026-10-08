# EvidenceOCR

Evidence-first handwriting recognition and human review for HACKNEX 2026, PS04.

EvidenceOCR converts difficult handwritten documents into auditable text without hiding uncertainty. Every automated reading remains linked to normalized source coordinates, raw provider output is preserved, and human decisions are stored separately. If the visual evidence is insufficient, the system records uncertainty or `[illegible]` instead of guessing.

> **Status:** Document persistence, three recognition layers, the review workspace, evidence fusion, disagreement analysis, and bounded recovery are implemented. Combined fusion CER/WER evaluation, production authentication, durable distributed jobs, and formal accessibility/security audits remain production-readiness work.

## Principles

- **Evidence before certainty:** every proposal references visible source pixels and a normalized bounding box.
- **No fabricated text:** unsupported completions are prohibited and ambiguity remains explicit.
- **Immutable provenance:** raw OCR/VLM output, fusion proposals, and human edits stay separate.
- **Reproducible inference:** provider, model version, parameters, latency, and input SHA-256 are retained.
- **Human authority:** automated consensus is a proposal, never a human verification.
- **Bounded recovery:** difficult regions receive limited, deduplicated attempts rather than unbounded retries.
- **Environment-only secrets:** credentials are loaded through typed settings and never committed or logged.

See [`AGENTS.md`](AGENTS.md) for the governing architecture invariants.

## Architecture

```text
Validated upload → SHA-256 + immutable GridFS original
        ↓
Independent evidence
  ├─ PP-OCRv6: full-page lines
  ├─ TrOCR Base: handwriting region recheck
  └─ PaddleOCR-VL-1.6: layout, reading order, tables
        ↓
Evidence fusion
  ├─ normalized spatial alignment
  ├─ text disagreement analysis
  ├─ conservative candidate selection
  └─ bounded contrast/padding/deskew recovery
        ↓
Human review → verify, correct, or mark illegible → audit record
```

Backend boundaries:

1. `api/v1/endpoints/` translates HTTP requests and responses.
2. `api/dependencies.py` wires services, providers, and repositories.
3. Domain services enforce evidence, review, and audit rules.
4. `db/repositories/` owns MongoDB access.
5. One application-scoped PyMongo `AsyncMongoClient` is managed by FastAPI lifespan events.

## Implemented capabilities

### Review workspace

- Single API-backed evidence-review workspace with no mounted sample document.
- Direct PNG, JPEG, WebP, and PDF upload.
- Backend document discovery and GridFS source streaming.
- Source preview with zoom, rotation, OCR overlays, and layout-block overlays.
- Transcription, comparison, fusion, tables, Markdown, and activity views.
- Human verification and explicit illegibility decisions.
- Keyboard-operable tabs, visible focus styles, accessible dialogs, and live status messages.

### Backend

- FastAPI modular monolith with typed Pydantic contracts.
- MongoDB Atlas repositories and `AsyncGridFSBucket` document storage.
- Liveness and dependency-readiness probes.
- Correlation IDs, timing middleware, structured logging, and security headers.
- Optimistic revisions for review changes.
- Pluggable OCR, VLM, and storage provider interfaces.

### Phase 6 fusion and recovery

- Spatial matching across normalized evidence regions.
- ROVER-inspired text-hypothesis alignment.
- Typed numeric, date, unit, geometry, confidence, and missing-text disagreements.
- Conservative, explicitly uncalibrated proposals.
- Bounded padded, CLAHE, and deskewed recovery variants.
- SHA-256 variant deduplication and per-region recovery budgets.
- Persisted transform parameters, model version, latency, output, confidence, and outcome.
- A recovery is “improved” only when it corroborates existing independent evidence. Confidence alone cannot promote novel text.

## Technology

| Layer | Stack |
|---|---|
| Frontend | Next.js 16, React 19, TypeScript 5, Lucide React |
| API | FastAPI, Pydantic v2, Uvicorn |
| Persistence | MongoDB Atlas, PyMongo Async, Async GridFS |
| Recognition | PP-OCRv6, Microsoft TrOCR Base Handwritten, PaddleOCR-VL-1.6 |
| Verification | pytest, Node test runner, TypeScript, Next.js production build |

## Repository layout

```text
backend/src/evidence_ocr/
  api/                 controllers and dependency injection
  core/                configuration, errors, logging, middleware
  db/repositories/     MongoDB data access
  ingestion/           validated upload and registration
  recognition/         OCR orchestration
  fusion/              alignment, disagreement, selection, recovery
  review/              human decisions and concurrency controls
  evaluation/          benchmark contracts and services
  providers/           OCR, VLM, and storage abstractions
backend/tests/          unit, integration, provider, and contract tests
frontend/src/           Next.js workspace and typed API client
frontend/tests/         frontend regression tests
docs/                   walkthroughs and benchmark reports
scripts/                benchmark and inspection utilities
```

## Local development

### Prerequisites

- Python 3.11+
- Node.js compatible with Next.js 16
- MongoDB Atlas or a compatible MongoDB deployment
- PaddleOCR access token for cloud-provider paths
- Local TrOCR model files for offline inference

### Backend

```powershell
Copy-Item backend\.env.example backend\.env
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
uvicorn evidence_ocr.main:app --host 127.0.0.1 --port 8000 --reload
```

Required environment configuration includes:

```dotenv
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>/?retryWrites=true&w=majority
MONGODB_DB_NAME=evidence_ocr
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
PADDLEOCR_ACCESS_TOKEN=<token>
FUSION_STRATEGY=evidence_aware
FUSION_MAX_TROCR_VARIANTS=2
FUSION_RECOVERY_BUDGET_SECONDS=120
FUSION_MAX_CLOUD_ESCALATIONS=0
```

Never commit `.env`; repository rules exclude it.

Development endpoints:

- Swagger UI: `http://127.0.0.1:8000/docs`
- ReDoc: `http://127.0.0.1:8000/redoc`
- Liveness: `http://127.0.0.1:8000/api/v1/health/live`
- Readiness: `http://127.0.0.1:8000/api/v1/health/ready`

### Frontend

In a second terminal:

```powershell
cd frontend
npm ci
npm run dev
```

Open `http://127.0.0.1:3000`. Next.js rewrites `/api/v1/*` to the local API at `127.0.0.1:8000`. Set `NEXT_PUBLIC_API_URL` when the API is hosted elsewhere.

## Review workflow

1. Upload an original document.
2. Confirm its SHA-256 and GridFS identity.
3. Run PP-OCRv6 for full-page line detection.
4. Run PaddleOCR-VL for layout and reading-order evidence.
5. Use TrOCR to recheck selected handwriting regions.
6. Run evidence fusion after independent evidence exists.
7. Inspect disagreements against the original pixels.
8. Optionally run bounded recovery for eligible regions.
9. Verify the supported reading or mark the region illegible.

Model agreement is not proof. Human verification must be grounded in the source image.

## API surface

All routes are versioned under `/api/v1`.

| Area | Operations |
|---|---|
| Health | process liveness and MongoDB readiness |
| Documents | upload, list, inspect, and stream originals |
| Recognition | schedule document OCR and recognize regions |
| Parsing | schedule PaddleOCR-VL and fetch parsed output/history |
| Jobs | poll asynchronous processing state |
| Fusion | create/list runs, fetch proposals, list disagreements |
| Recovery | execute bounded recovery and retrieve evidence history |
| Review | read state, update regions/transcript, complete review |
| Evaluation | query reproducible benchmark records |

Route handlers contain no direct database access or business rules.

## Verification

Frontend:

```powershell
cd frontend
npm test
npm run typecheck
npm run build
```

Backend:

```powershell
cd backend
python -m pytest -v
```

Do not skip, weaken, or comment out failing tests. Deployment should require both suites and the production frontend build to pass.

## Security and operational standards

- Allowlist MIME types and validate signatures, size, and PDF page limits server-side.
- Store secrets in environment variables or a managed vault; redact credentials and document content from logs.
- Restrict CORS to explicit deployment origins and terminate TLS at a trusted ingress.
- Apply least-privilege MongoDB roles and network controls.
- Run dependency, secret, and container vulnerability scans in CI.
- Define retention, deletion, backup, restoration, and incident-response procedures.
- Use durable distributed jobs before scaling across API replicas; in-process tasks are not a production queue.
- Add authentication, authorization, tenant isolation, rate limits, malware scanning, and signed document access before public deployment.
- Monitor provider failures, latency, queue depth, recovery exhaustion, review backlog, and audit-write failures.

The design uses PyMongo’s native asynchronous API and `AsyncGridFSBucket`, matching MongoDB’s current guidance for asynchronous applications. File-upload controls follow the OWASP pattern of allowlisting, server-side validation, size limits, controlled storage, and safe serving.

## Benchmarking and claims

Benchmark artifacts live under `backend/tests/fixtures/benchmark_dataset/`. Report metrics only with the dataset hash, sample count, model snapshot, frozen parameters, exact metric implementation, and raw outputs.

Individual model benchmarks exist. Phase 6 fusion is implemented, but combined fusion CER/WER must remain labeled **not yet evaluated** until a reproducible benchmark is completed. Demo or synthetic data must never be reported as production accuracy.

## Production-readiness boundary

This repository is not a claim of production certification. Before production use, complete authentication and authorization, durable queue infrastructure, malware scanning, encrypted backup/restore testing, retention/deletion workflows, penetration testing, formal accessibility testing, confidence calibration, Phase 6 fusion benchmarking, load testing, and disaster-recovery exercises.

## Documentation

- [`backend/README.md`](backend/README.md) — backend setup and endpoints
- [`docs/phase-2-walkthrough.md`](docs/phase-2-walkthrough.md) — ingestion and persistence
- [`docs/phase-4-walkthrough.md`](docs/phase-4-walkthrough.md) — PP-OCRv6 and TrOCR
- [`docs/phase-5-walkthrough.md`](docs/phase-5-walkthrough.md) — PaddleOCR-VL
- [`docs/trocr_baseline_benchmark_report.md`](docs/trocr_baseline_benchmark_report.md) — TrOCR benchmark
- [`frontend/docs/backend-contract.md`](frontend/docs/backend-contract.md) — frontend/backend contract
- [`frontend/docs/validation.md`](frontend/docs/validation.md) — frontend validation

## License

The backend package currently declares a proprietary license. Confirm repository-level licensing and third-party model/provider terms before distribution.
