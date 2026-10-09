"""Typed repository for ProcessingJob entities."""

from datetime import datetime, timedelta, timezone
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
            {"$set": {"stage": stage.value, "status": status.value, "heartbeat_at": now, "updated_at": now}},
        )
        if not res:
            return None
        return ProcessingJob(**res)

    async def update_heartbeat(self, job_id: str) -> Optional[ProcessingJob]:
        """Update job heartbeat pulse to signal active execution to the watchdog."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": job_id},
            {"$set": {"heartbeat_at": now, "updated_at": now}},
        )
        if not res:
            return None
        return ProcessingJob(**res)

    async def cancel_job(
        self, job_id: str, reason: str = "Job cancelled by user"
    ) -> Optional[ProcessingJob]:
        """Explicitly transition an active or stuck job to CANCELLED state."""
        now = datetime.now(timezone.utc).isoformat()
        res = await self.update_one(
            {"id": job_id},
            {
                "$set": {
                    "status": JobStatus.CANCELLED.value,
                    "error_message": reason,
                    "completed_at": now,
                    "updated_at": now,
                }
            },
        )
        if not res:
            return None
        return ProcessingJob(**res)

    async def reap_stale_jobs(self, max_stale_seconds: int = 120) -> int:
        """Find and expire any active jobs that have missed heartbeats beyond max_stale_seconds.

        Enterprise zombie job cleanup pattern: transitions orphaned in-flight tasks to TIMED_OUT.
        """
        now_dt = datetime.now(timezone.utc)
        cutoff_dt = now_dt - timedelta(seconds=max_stale_seconds)
        cutoff_iso = cutoff_dt.isoformat()
        now_iso = now_dt.isoformat()

        active_statuses = [JobStatus.QUEUED.value, JobStatus.SUBMITTED.value, JobStatus.RUNNING.value]
        query = {
            "status": {"$in": active_statuses},
            "$or": [
                {"heartbeat_at": {"$lt": cutoff_iso}},
                {"$and": [{"heartbeat_at": None}, {"updated_at": {"$lt": cutoff_iso}}]},
                {"$and": [{"heartbeat_at": None}, {"updated_at": None}, {"created_at": {"$lt": cutoff_iso}}]},
            ],
        }

        try:
            cursor = self.collection.find(query)
            stale_docs = await cursor.to_list(100)
            reaped_count = 0
            for doc in stale_docs:
                job_id = doc.get("id")
                if job_id:
                    await self.update_one(
                        {"id": job_id},
                        {
                            "$set": {
                                "status": JobStatus.TIMED_OUT.value,
                                "error_message": f"Job execution timed out after exceeding {max_stale_seconds}s without worker heartbeat (zombie worker recovered).",
                                "completed_at": now_iso,
                                "updated_at": now_iso,
                            }
                        },
                    )
                    reaped_count += 1
            return reaped_count
        except Exception:
            return 0

    async def find_active_by_document(
        self,
        document_id: str,
        task_type: Optional[str] = None,
        max_stale_seconds: int = 120,
    ) -> Optional[ProcessingJob]:
        """Find any currently pending, queued, submitted, or running job for this document.

        Automatically detects and reaps stale/zombie jobs older than max_stale_seconds so
        documents are never locked indefinitely.
        """
        query: dict = {
            "document_id": document_id,
            "status": {"$in": [JobStatus.QUEUED.value, JobStatus.SUBMITTED.value, JobStatus.RUNNING.value]},
        }
        if task_type:
            query["task_type"] = task_type

        doc = await self.find_one(query)
        if not doc:
            return None

        # Check for staleness against cutoff
        now_dt = datetime.now(timezone.utc)
        cutoff_dt = now_dt - timedelta(seconds=max_stale_seconds)
        last_pulse_str = doc.get("heartbeat_at") or doc.get("updated_at") or doc.get("created_at")
        if last_pulse_str:
            try:
                clean_str = last_pulse_str.replace("Z", "+00:00")
                pulse_dt = datetime.fromisoformat(clean_str)
                if pulse_dt.tzinfo is None:
                    pulse_dt = pulse_dt.replace(tzinfo=timezone.utc)
                if pulse_dt < cutoff_dt:
                    # Stale zombie job detected! Auto-reap it and allow new execution
                    job_id = doc.get("id")
                    if job_id:
                        await self.update_one(
                            {"id": job_id},
                            {
                                "$set": {
                                    "status": JobStatus.TIMED_OUT.value,
                                    "error_message": f"Job automatically expired after exceeding {max_stale_seconds}s with no worker heartbeat.",
                                    "completed_at": now_dt.isoformat(),
                                    "updated_at": now_dt.isoformat(),
                                }
                            },
                        )
                    return None
            except Exception:
                pass

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
