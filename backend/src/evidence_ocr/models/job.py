"""Domain models for asynchronous processing jobs and execution stages."""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class JobStatus(str, Enum):
    """Processing job status lifecycle."""

    QUEUED = "queued"
    SUBMITTED = "submitted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class JobStage(str, Enum):
    """Pipeline processing stages reflecting the platform architecture."""

    INGESTION = "ingestion"
    PREPROCESSING = "preprocessing"
    LAYOUT_INTELLIGENCE = "layout_intelligence"
    RECOGNITION = "recognition"
    EVIDENCE_FUSION = "evidence_fusion"
    TRUST_DECISION = "trust_decision"
    COMPLETED = "completed"


class ProcessingJob(BaseModel):
    """Asynchronous recognition and pipeline job entity."""

    id: str = Field(description="Unique job identifier, e.g. job-xxxxxxxx")
    document_id: str = Field(description="Target document ID")
    pipeline_version: str = Field(default="v1.0.0", description="Reproducible pipeline version tag")
    idempotency_key: Optional[str] = Field(default=None, description="Client idempotency key")
    provider: str = Field(default="paddleocr-cloud", description="Cloud or local OCR provider")
    model: str = Field(default="PP-OCRv6", description="OCR model identifier")
    provider_job_id: Optional[str] = Field(default=None, description="Remote cloud provider job ID")
    status: JobStatus = Field(default=JobStatus.QUEUED)
    stage: JobStage = Field(default=JobStage.INGESTION)
    error_message: Optional[str] = Field(default=None, description="Diagnostic error details if failed")
    retry_count: int = Field(default=0, ge=0, description="Number of execution attempts")
    max_retries: int = Field(default=3, ge=0, description="Configured maximum retries")
    processed_page_count: int = Field(default=0, ge=0, description="Number of pages successfully processed")
    execution_time_ms: Optional[float] = Field(default=None, ge=0.0, description="Total pipeline latency in ms")
    started_at: Optional[str] = Field(default=None, description="UTC ISO-8601 start timestamp")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
    updated_at: str = Field(description="UTC ISO-8601 last update timestamp")
    completed_at: Optional[str] = Field(default=None, description="UTC ISO-8601 completion timestamp")
