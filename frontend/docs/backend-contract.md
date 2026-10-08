# Backend integration contract

The current UI is standalone. Proposed API operations for the next phase:

| Operation | Request | Response |
|---|---|---|
| POST /documents | multipart file, title, type, expectedLanguage | documentId, sourceUrl, status |
| GET /documents | search, status, cursor | items, nextCursor |
| POST /documents/{id}/recognition | pipelineVersion, idempotencyKey | jobId, queued status |
| GET /jobs/{id} | none | queued/running/failed/completed, stage, error |
| GET /documents/{id}/review | none | transcript, source regions, candidates, decisions, revision |
| PATCH /documents/{id}/regions/{regionId} | decision, expectedRevision | updated region, revision, audit event |
| PATCH /documents/{id}/transcript | text, expectedRevision | text, revision, audit event |
| POST /documents/{id}/complete | expectedRevision | status; reject unresolved required regions |
| GET /documents/{id}/export | format, revision | streamed TXT/JSON with provenance |
| GET /evaluations | dataset, subset, metric | real runs with dataset/model hashes and denominators |

Store bounding boxes normalized to the original unrotated page. Rotation and zoom are view transforms, not source mutations. Each region needs pageIndex, boundingBox, originalText, candidates, reasonCodes, reviewStatus and reviewer decision. Separate OCR output and human modifications. Do not infer probabilities from uncalibrated scores.

Use immutable originals, server-side type/size/content validation, authorization at every document boundary, safe file handling, persisted jobs with bounded retries and structured errors. Issue source URLs with appropriately scoped access; keep credentials server-side. Use optimistic concurrency for edits. Backend and browser must distinguish pending, retryable failure, terminal failure, partial success and completed states.

The UI currently stores demo state in `hacknex:workspace:v1` (with fallback to `inkproof:workspace:v1`). Replace the demo state adapter with API-backed state; do not send demo fixtures as genuine evaluations. Do not upload browser-local files without an explicit processing action.
