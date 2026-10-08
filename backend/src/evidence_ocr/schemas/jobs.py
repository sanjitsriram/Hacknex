"""API schemas for asynchronous jobs."""

from typing import Optional
from pydantic import BaseModel, Field
from evidence_ocr.models.job import JobStage, JobStatus


class JobCreateRequest(BaseModel):
    """Request payload to schedule document recognition."""

    pipeline_version: str = Field(default="v1.0.0", description="Reproducible pipeline version tag")
    idempotency_key: Optional[str] = Field(default=None, description="Optional idempotency key")


class JobResponse(BaseModel):
    """Response returned upon scheduling a job."""

    job_id: str = Field(description="Unique job identifier")
    document_id: str = Field(description="Target document ID")
    status: JobStatus = Field(description="Initial job status (queued)")
    stage: JobStage = Field(description="Initial job stage")
    provider: str = Field(default="paddleocr-cloud", description="Cloud or local OCR provider")
    model: str = Field(default="PP-OCRv6", description="Target OCR model")
    created_at: str = Field(description="Creation timestamp")


class JobStatusResponse(BaseModel):
    """Response returned when polling job status."""

    job_id: str = Field(description="Job ID")
    document_id: str = Field(description="Associated document ID")
    status: JobStatus = Field(description="Current job status")
    stage: JobStage = Field(description="Current pipeline stage")
    provider: str = Field(default="paddleocr-cloud", description="Cloud or local OCR provider")
    model: str = Field(default="PP-OCRv6", description="OCR model identifier")
    provider_job_id: Optional[str] = Field(default=None, description="External provider job ID")
    processed_page_count: int = Field(default=0, description="Pages processed")
    execution_time_ms: Optional[float] = Field(default=None, description="Execution duration in ms")
    error: Optional[str] = Field(default=None, description="Error message if failed")
    retry_count: int = Field(default=0, description="Retry count")
    started_at: Optional[str] = Field(default=None, description="Execution start timestamp")
    created_at: str = Field(description="Creation timestamp")
    updated_at: str = Field(description="Last update timestamp")
    completed_at: Optional[str] = Field(default=None, description="Completion timestamp")
