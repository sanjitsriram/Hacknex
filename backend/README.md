# EvidenceOCR Backend

Accuracy-first handwriting digitization platform backend foundation (Phase 1).

## Architecture Pipeline Overview

```
[Evidence-Preserving Document Ingestion]
                   │
                   ▼
[Document Preprocessing & Layout Intelligence]
                   │
                   ▼
[Independent Cloud OCR Model Recognition]
                   │
                   ▼
[Evidence Fusion & Targeted Visual Recovery (VLM)]
                   │
                   ▼
[Calibrated Trust Decision & Triage]
                   │
                   ▼
[Editable Output, Human Verification & Evaluation]
```

## Phase 1 Scope & Foundation

Phase 1 provides the industry-standard, maintainable Python FastAPI modular-monolith backend:
- **Core Infrastructure**: Pydantic Settings (`core/config.py`), structured JSON/console logging (`core/logging.py`), unified error hierarchy (`core/errors.py`), correlation ID & timing middleware (`core/middleware.py`), and security headers (`core/security.py`).
- **Database**: Single managed asynchronous client for **MongoDB Atlas** via PyMongo Async (`db/client.py`) with connection lifecycle and health ping.
- **Data Access**: Typed abstract and concrete repositories (`db/repositories/`) separating persistence from business logic.
- **Domain Models & Contracts**: Normalized bounding-box coordinates on unrotated pages, candidate suggestions with model provenance, optimistic concurrency revisions, and auditable correction logs.
- **Provider Interfaces**: Pluggable abstract interfaces for Cloud OCR (`providers/ocr.py`), VLM Visual Recovery (`providers/vlm.py`), and Object Storage (`providers/storage.py`) without locking into unapproved vendors.
- **Typed Modular Packages**: `ingestion/`, `preprocessing/`, `layout/`, `recognition/`, `fusion/`, `trust/`, `review/`, `evaluation/`, and `workers/`.
- **Health Endpoints**: Liveness (`GET /api/v1/health/live`) and accurate dependency readiness (`GET /api/v1/health/ready`).

---

## Getting Started

### Prerequisites
- Python 3.11+
- [uv](https://github.com/astral-sh/uv) or standard `pip`
- MongoDB Atlas cluster connection string

### Setup & Installation

1. Navigate to the backend directory:
   ```bash
   cd backend
   ```

2. Configure environment variables:
   ```bash
   copy .env.example .env
   ```
   Edit `.env` to configure your MongoDB Atlas connection string (`MONGODB_URI`).

3. Install dependencies:
   ```bash
   pip install -r requirements-dev.txt
   ```
   Or with `uv`:
   ```bash
   uv pip install -r requirements-dev.txt
   ```

---

## Running the Server

Start the development server with hot reload:
```bash
uvicorn evidence_ocr.main:app --host 0.0.0.0 --port 8000 --reload
```

The interactive OpenAPI documentation is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

---

## Running Tests

Execute the automated test suite with pytest:
```bash
pytest -v
```

---

## Container Build (Docker)

Build the production image:
```bash
docker build -t evidence-ocr-backend .
```

Run the container:
```bash
docker run -p 8000:8000 --env-file .env evidence-ocr-backend
```

---

## API Endpoints (Phase 1)

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health/live` | Process liveness probe (200 OK) |
| `GET` | `/api/v1/health/ready` | Dependency readiness probe (checks MongoDB Atlas ping) |
| `POST` | `/api/v1/documents` | Multipart document intake (PNG/JPG/WebP/PDF, <=20MB) |
| `GET` | `/api/v1/documents` | Query paginated documents with status/search filters |
| `POST` | `/api/v1/documents/{id}/recognition` | Enqueue asynchronous recognition job |
| `GET` | `/api/v1/jobs/{id}` | Poll job processing status and current stage |
| `GET` | `/api/v1/documents/{id}/review` | Fetch transcript, normalized regions, and candidates |
| `PATCH` | `/api/v1/documents/{id}/regions/{regionId}` | Apply reviewer decision with optimistic revision |
| `PATCH` | `/api/v1/documents/{id}/transcript` | Update transcript text with optimistic revision |
| `POST` | `/api/v1/documents/{id}/complete` | Finalize review (rejects if unresolved regions remain) |
| `GET` | `/api/v1/evaluations` | Query benchmark runs with dataset hashes and denominators |
