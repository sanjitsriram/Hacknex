"""API v1 endpoint handlers."""

from evidence_ocr.api.v1.endpoints.documents import router as documents_router
from evidence_ocr.api.v1.endpoints.evaluations import router as evaluations_router
from evidence_ocr.api.v1.endpoints.health import router as health_router
from evidence_ocr.api.v1.endpoints.jobs import router as jobs_router
from evidence_ocr.api.v1.endpoints.review import router as review_router

__all__ = [
    "documents_router",
    "evaluations_router",
    "health_router",
    "jobs_router",
    "review_router",
]
