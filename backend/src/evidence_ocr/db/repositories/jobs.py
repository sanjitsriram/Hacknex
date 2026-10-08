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

    async def find_active_by_document(self, document_id: str) -> Optional[ProcessingJob]:
        """Find any currently pending, queued, submitted, or running job for this document."""
        doc = await self.find_one(
            {
                "document_id": document_id,
                "status": {"$in": [JobStatus.QUEUED.value, JobStatus.SUBMITTED.value, JobStatus.RUNNING.value]},
            }
        )
        if not doc:
            return None
        return ProcessingJob(**doc)

    async def list_by_document(self, document_id: str, limit: int = 50) -> list[ProcessingJob]:
        """List historical processing jobs for a document, newest first."""
        docs = await self.find_many(
            {"document_id": document_id},
            sort_field="created_at",
            sort_direction=-1,
            limit=limit,
        )
        return [ProcessingJob(**d) for d in docs]

    async def update_metadata(
        self,
        job_id: str,
        provider_job_id: Optional[str] = None,
        processed_page_count: Optional[int] = None,
        execution_time_ms: Optional[float] = None,
        started_at: Optional[str] = None,
    ) -> Optional[ProcessingJob]:
        """Update job provider metadata and execution metrics."""
        now = datetime.now(timezone.utc).isoformat()
        updates: dict = {"updated_at": now}
        if provider_job_id is not None:
            updates["provider_job_id"] = provider_job_id
        if processed_page_count is not None:
            updates["processed_page_count"] = processed_page_count
        if execution_time_ms is not None:
            updates["execution_time_ms"] = execution_time_ms
        if started_at is not None:
            updates["started_at"] = started_at

        res = await self.update_one({"id": job_id}, {"$set": updates})
        if not res:
            return None
        return ProcessingJob(**res)

    async def mark_completed(
        self,
        job_id: str,
        processed_page_count: Optional[int] = None,
        execution_time_ms: Optional[float] = None,
    ) -> Optional[ProcessingJob]:
        """Mark job as successfully completed."""
        now = datetime.now(timezone.utc).isoformat()
        updates: dict = {
            "stage": JobStage.COMPLETED.value,
            "status": JobStatus.COMPLETED.value,
            "completed_at": now,
            "updated_at": now,
        }
        if processed_page_count is not None:
            updates["processed_page_count"] = processed_page_count
        if execution_time_ms is not None:
            updates["execution_time_ms"] = execution_time_ms

        res = await self.update_one(
            {"id": job_id},
            {"$set": updates},
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
