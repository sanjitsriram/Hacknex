"""Asynchronous in-process task runner boundary for background jobs."""

import asyncio
from typing import Optional
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob

logger = get_logger("evidence_ocr.workers")


class WorkerRunner:
    """In-process asynchronous job execution coordinator.
    
    Adheres to Phase 1 invariant: does not introduce Celery or Redis prematurely
    while establishing clear boundaries and asynchronous execution contracts.
    """

    def __init__(self, job_repo: JobRepository) -> None:
        self.job_repo = job_repo

    async def dispatch_document_recognition(
        self, job_id: str, document_id: str, pipeline_version: str
    ) -> None:
        """Enqueue and execute recognition pipeline steps asynchronously."""
        asyncio.create_task(self._run_job_pipeline(job_id, document_id))

    async def _run_job_pipeline(self, job_id: str, document_id: str) -> None:
        """Execute simulated multi-stage pipeline flow updating job states."""
        logger.info("Starting background processing for job %s (doc: %s)", job_id, document_id)
        try:
            # Advance to running
            await self.job_repo.update_stage(job_id, JobStage.PREPROCESSING, JobStatus.RUNNING)
            await asyncio.sleep(0.05)

            await self.job_repo.update_stage(job_id, JobStage.LAYOUT_INTELLIGENCE, JobStatus.RUNNING)
            await asyncio.sleep(0.05)

            await self.job_repo.update_stage(job_id, JobStage.RECOGNITION, JobStatus.RUNNING)
            await asyncio.sleep(0.05)

            await self.job_repo.update_stage(job_id, JobStage.EVIDENCE_FUSION, JobStatus.RUNNING)
            await asyncio.sleep(0.05)

            await self.job_repo.update_stage(job_id, JobStage.TRUST_DECISION, JobStatus.RUNNING)
            await asyncio.sleep(0.05)

            await self.job_repo.mark_completed(job_id)
            logger.info("Job %s completed successfully", job_id)
        except Exception as exc:
            logger.exception("Job %s failed with exception: %s", job_id, str(exc))
            await self.job_repo.mark_failed(job_id, error_message=str(exc))
