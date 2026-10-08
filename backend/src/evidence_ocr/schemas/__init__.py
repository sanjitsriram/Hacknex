"""API schemas package."""

from evidence_ocr.schemas.common import APIError, ErrorResponse, HealthResponse, PaginationParams
from evidence_ocr.schemas.documents import (
    DocumentCreateRequest,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)
from evidence_ocr.schemas.evaluations import EvaluationItemResponse, EvaluationResponse
from evidence_ocr.schemas.jobs import JobCreateRequest, JobResponse, JobStatusResponse
from evidence_ocr.schemas.review import (
    AuditEventResponse,
    CompleteReviewRequest,
    CompleteReviewResponse,
    RegionItemResponse,
    RegionUpdateRequest,
    RegionUpdateResponse,
    ReviewSessionResponse,
    TranscriptUpdateRequest,
    TranscriptUpdateResponse,
)

__all__ = [
    "HealthResponse",
    "APIError",
    "ErrorResponse",
    "PaginationParams",
    "DocumentCreateRequest",
    "DocumentUploadResponse",
    "DocumentItemResponse",
    "DocumentListResponse",
    "JobCreateRequest",
    "JobResponse",
    "JobStatusResponse",
    "RegionItemResponse",
    "AuditEventResponse",
    "ReviewSessionResponse",
    "RegionUpdateRequest",
    "RegionUpdateResponse",
    "TranscriptUpdateRequest",
    "TranscriptUpdateResponse",
    "CompleteReviewRequest",
    "CompleteReviewResponse",
    "EvaluationItemResponse",
    "EvaluationResponse",
]
