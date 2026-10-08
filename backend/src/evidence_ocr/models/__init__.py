"""Domain models package."""

from evidence_ocr.models.audit import AuditEvent, ProvenanceRecord
from evidence_ocr.models.document import DocumentEntity, DocumentStatus, PageMetadata
from evidence_ocr.models.evaluation import EvaluationRun
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.models.region import (
    BoundingBox,
    CandidateSuggestion,
    RegionEntity,
    RegionReviewStatus,
)

__all__ = [
    "AuditEvent",
    "ProvenanceRecord",
    "DocumentEntity",
    "DocumentStatus",
    "PageMetadata",
    "EvaluationRun",
    "JobStage",
    "JobStatus",
    "ProcessingJob",
    "BoundingBox",
    "CandidateSuggestion",
    "RegionEntity",
    "RegionReviewStatus",
]
