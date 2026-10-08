# EvidenceOCR Architecture Invariants & Agent Guidelines

This document governs all implementation decisions, code reviews, and automated agent modifications within the **EvidenceOCR** (HackNex) repository.

---

## 1. Architectural Invariants

### Invariant 1: Evidence-First OCR
- All transcription candidates, token predictions, and confidence evaluations must be strictly grounded in verifiable, normalized visual bounding boxes.
- Bounding box coordinates MUST be normalized to the original unrotated document page (`[0.0, 1.0]` or `[0, 100]` percentage space). Rotation, zoom, and distortion corrections in the viewport are client/presentation transforms, not source mutations.
- Raw OCR outputs, automated VLM proposals, and human edits MUST be kept strictly isolated in distinct provenance layers. Human modifications must never overwrite raw provider output in the audit trail.

### Invariant 2: No Fabricated Characters or Hallucinated Text
- When handwriting is illegible or visual evidence is insufficient, the system must produce an explicit illegibility marker or an uncertain confidence signal (`is_illegible=True`, reason code: `LOW_CONFIDENCE` or `ILLEGIBLE_STROKE`).
- Models, fusion algorithms, and backend services must NEVER extrapolate or hallucinate unrepresented characters to "complete" words or grammatical sentences without visual proof.

### Invariant 3: Reproducible Cloud-Model Versions
- Every automated extraction or model evaluation must record full provider metadata:
  - Provider identifier (e.g., `google-cloud-vision`, `azure-document-intelligence`, `aws-textract`)
  - Explicit model identifier and model version/snapshot tag (e.g., `gemini-1.5-pro-002`, `2024-02-29-preview`)
  - Request parameters: `temperature=0.0`, request seed, prompt version/hash
  - Input image content SHA-256 hash
- Unversioned API calls or dynamic model aliases (e.g. `latest`) are strictly prohibited in production inference paths.

### Invariant 4: Credentials Exclusively from Environment
- API keys, service account credentials, database connection strings, and cloud secrets must NEVER be hard-coded, checked into version control, or logged.
- All secrets must be loaded dynamically at runtime via typed Pydantic Settings from system environment variables or secure vault integrations.
- `.env` files must be excluded from version control via `.gitignore`.

### Invariant 5: No Fake Production Data
- Synthetic fixtures, mock data, and local browser demonstration states (e.g., `hacknex:workspace:v1`) must be explicitly labeled as demo/sample fixtures (`sample=True`, `is_demo=True`).
- Mock results must NEVER be saved to production database collections or submitted as genuine benchmark evaluation metrics.

### Invariant 6: No Bypassing Tests
- All production code must be accompanied by comprehensive unit, integration, and contract tests.
- Tests must not be skipped, commented out, or weakened to mask architectural flaws or broken assertions.
- The test suite must pass cleanly in CI/CD without unhandled exceptions or hidden side-effects.

### Invariant 7: Changes Only Within Approved Scope
- Agents must restrict modifications to the approved phase and task boundaries.
- Phase 1 is strictly limited to backend foundation, contracts, typed packages, PyMongo Async management, configuration, health endpoints, and provider interfaces.
- Do NOT prematurely implement concrete OCR models, pipeline processing queues, Celery, Redis, authentication infrastructure, or frontend modifications until explicitly authorized.

### Invariant 8: Pluggable Provider Abstractions
- External services (OCR engines, Vision-Language Models, Object Storage) must be defined as abstract provider interfaces (`BaseOCRProvider`, `BaseVLMProvider`, `BaseStorageProvider`).
- No concrete vendor dependency or proprietary SDK is locked in until specifically selected and approved. Mock adapters serve testing and architectural validation.

---

## 2. Code Organization & Modular-Monolith Standards

### Layer Boundaries
1. **Route Handlers (`api/v1/endpoints/`)**:
   - Act purely as protocol controllers.
   - Accept typed Pydantic schemas, invoke injected service methods, and return typed response schemas.
   - ZERO direct database access, queries, or business rules in route handlers.
2. **Dependency Injection (`api/dependencies.py`)**:
   - Manages object lifetimes and wires repositories and services into route handlers using FastAPI `Depends`.
3. **Domain Services (`ingestion/`, `review/`, `trust/`, etc.)**:
   - Enforce business logic, validation rules, audit logging, and coordinate domain operations across repositories.
4. **Repositories (`db/repositories/`)**:
   - Abstract data access. Communicate with MongoDB Atlas via PyMongo Async.
5. **Database Manager (`db/client.py`)**:
   - Manages a single application `AsyncMongoClient` tied to FastAPI lifespan events.

---

## 3. Auditability & Concurrency
- All modifications to document regions or transcripts must record:
  - Timestamp (UTC ISO 8601)
  - Action code
  - Reviewer identity / Actor ID
  - Pre-edit and post-edit diffs
  - Optimistic concurrency control (`revision` integer check) to prevent concurrent overwrites.
