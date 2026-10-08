"""Job status polling endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends
from evidence_ocr.api.dependencies import get_job_repository
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.schemas.jobs import JobStatusResponse

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.get(
    "/{id}",
    response_model=JobStatusResponse,
    summary="Get job status",
    description="Polls current execution status, pipeline stage, and error details for a processing job.",
)
async def get_job_status(
    id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> JobStatusResponse:
    """Fetch job status by ID."""
    job = await job_repo.get_by_id(id)
    if not job:
        raise EntityNotFoundError("Job", id)

    return JobStatusResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        provider=getattr(job, "provider", "paddleocr-cloud") or "paddleocr-cloud",
        model=getattr(job, "model", "PP-OCRv6") or "PP-OCRv6",
        provider_job_id=getattr(job, "provider_job_id", None),
        processed_page_count=getattr(job, "processed_page_count", 0),
        execution_time_ms=getattr(job, "execution_time_ms", None),
        error=job.error_message,
        retry_count=job.retry_count,
        started_at=getattr(job, "started_at", None),
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=getattr(job, "completed_at", None),
    )
