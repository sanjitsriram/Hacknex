"""Typed repository for ProcessingJob entities."""

from datetime import datetime, timezone
from typing import Optional
from pymongo.asynchronous.database import AsyncDatabase
from evidence_ocr.db.repositories.base import BaseRepository
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob


class JobRepository(BaseRepository):
    """Repository handling processing job records."""

    def __init__(self, db: AsyncDatabase) -> None:
        super().__init__(db, collection_name="jobs")

    async def get_by_id(self, job_id: str) -> Optional[ProcessingJob]:
        """Fetch job by ID."""
        doc = await self.find_by_id(job_id)
        if not doc:
            return None
        return ProcessingJob(**doc)

    async def create(self, job: ProcessingJob) -> ProcessingJob:
        """Insert a newly scheduled job."""
        await self.insert_one(job.model_dump())
        return job

    async def update_stage(
        self, job_id: str, stage: JobStage, status: JobStatus = JobStatus.RUNNING
    ) -> Optional[ProcessingJob]:
        """Update job execution stage."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": job_id},
            {"$set": {"stage": stage.value, "status": status.value, "updated_at": now}},
        )
        if not res:
            return None
        return ProcessingJob(**res)

    async def mark_completed(self, job_id: str) -> Optional[ProcessingJob]:
        """Mark job as successfully completed."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": job_id},
            {
                "$set": {
                    "stage": JobStage.COMPLETED.value,
                    "status": JobStatus.COMPLETED.value,
                    "completed_at": now,
                    "updated_at": now,
                }
            },
        )
        if not res:
            return None
        return ProcessingJob(**res)

    async def mark_failed(self, job_id: str, error_message: str) -> Optional[ProcessingJob]:
        """Mark job as failed with error diagnostics."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": JobStatus.FAILED.value,
                    "error_message": error_message,
                    "updated_at": now,
                },
                "$inc": {"retry_count": 1},
            },
        )
        if not res:
            return None
        return ProcessingJob(**res)
