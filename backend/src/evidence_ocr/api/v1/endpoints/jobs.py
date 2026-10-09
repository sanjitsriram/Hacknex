"""Job status polling and lifecycle management endpoints."""

from datetime import datetime, timezone, timedelta
from typing import Annotated
from fastapi import APIRouter, Depends, status
from evidence_ocr.api.dependencies import get_job_repository
from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.models.job import JobStatus
from evidence_ocr.schemas.jobs import JobStatusResponse
from evidence_ocr.workers.runner import WorkerRunner

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
    settings: Annotated[Settings, Depends(get_settings)],
) -> JobStatusResponse:
    """Fetch job status by ID with active zombie detection and watchdog verification."""
    job = await job_repo.get_by_id(id)
    if not job:
        raise EntityNotFoundError("Job", id)

    # Enterprise Watchdog: If job is marked running but has no heartbeat and worker is not running in memory
    if job.status in (JobStatus.QUEUED, JobStatus.SUBMITTED, JobStatus.RUNNING):
        if not WorkerRunner.is_active(id):
            cutoff_dt = datetime.now(timezone.utc) - timedelta(seconds=settings.job_stale_threshold_seconds)
            last_pulse = getattr(job, "heartbeat_at", None) or job.updated_at or job.created_at
            if last_pulse:
                try:
                    clean_str = last_pulse.replace("Z", "+00:00")
                    pulse_dt = datetime.fromisoformat(clean_str)
                    if pulse_dt.tzinfo is None:
                        pulse_dt = pulse_dt.replace(tzinfo=timezone.utc)
                    if pulse_dt < cutoff_dt:
                        # Auto-expire zombie job
                        reaped = await job_repo.mark_failed(
                            id,
                            error_message=f"Job exceeded {settings.job_stale_threshold_seconds}s timeout without worker heartbeat (zombie worker recovered).",
                        )
                        if reaped:
                            job = reaped
                except Exception:
                    pass

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
        heartbeat_at=getattr(job, "heartbeat_at", None),
        created_at=job.created_at,
        updated_at=job.updated_at,
        completed_at=getattr(job, "completed_at", None),
    )


@router.post(
    "/{id}/cancel",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel processing job",
    description="Explicitly aborts an in-progress or queued processing job.",
)
@router.delete(
    "/{id}",
    response_model=JobStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Cancel or abort processing job",
    description="Explicitly cancels an active or queued processing job.",
)
async def cancel_job(
    id: str,
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> JobStatusResponse:
    """Abort a running or stuck job immediately."""
    job = await job_repo.get_by_id(id)
    if not job:
        raise EntityNotFoundError("Job", id)

    WorkerRunner.cancel_active_task(id)
    await job_repo.cancel_job(id, reason="Job cancelled by user request")
    updated = await job_repo.get_by_id(id)
    target = updated or job

    return JobStatusResponse(
        job_id=target.id,
        document_id=target.document_id,
        status=target.status,
        stage=target.stage,
        provider=getattr(target, "provider", "paddleocr-cloud") or "paddleocr-cloud",
        model=getattr(target, "model", "PP-OCRv6") or "PP-OCRv6",
        provider_job_id=getattr(target, "provider_job_id", None),
        processed_page_count=getattr(target, "processed_page_count", 0),
        execution_time_ms=getattr(target, "execution_time_ms", None),
        error=target.error_message,
        retry_count=target.retry_count,
        started_at=getattr(target, "started_at", None),
        heartbeat_at=getattr(target, "heartbeat_at", None),
        created_at=target.created_at,
        updated_at=target.updated_at,
        completed_at=getattr(target, "completed_at", None),
    )
