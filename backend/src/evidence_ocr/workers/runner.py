"""Asynchronous in-process task runner boundary for background recognition jobs."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.db.repositories.regions import RegionRepository
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus
from evidence_ocr.models.region import (
    BoundingBox,
    CandidateSuggestion,
    RegionEntity,
    RegionReviewStatus,
)
from evidence_ocr.providers.ocr import BaseOCRProvider
from evidence_ocr.providers.storage import BaseStorageProvider

logger = get_logger("evidence_ocr.workers")


class WorkerRunner:
    """In-process asynchronous job execution coordinator."""

    def __init__(
        self,
        job_repo: JobRepository,
        cloud_ocr_provider: Optional[BaseOCRProvider] = None,
        storage_provider: Optional[BaseStorageProvider] = None,
        doc_repo: Optional[DocumentRepository] = None,
        region_repo: Optional[RegionRepository] = None,
        recognition_service: Optional[Any] = None,
    ) -> None:
        self.job_repo = job_repo
        self.cloud_ocr_provider = cloud_ocr_provider
        self.storage_provider = storage_provider
        self.doc_repo = doc_repo
        self.region_repo = region_repo
        self.recognition_service = recognition_service

    async def dispatch_document_recognition(
        self, job_id: str, document_id: str, pipeline_version: str = "v1.0.0"
    ) -> None:
        """Enqueue and execute recognition pipeline steps asynchronously."""
        asyncio.create_task(self._run_job_pipeline(job_id, document_id))

    async def _run_job_pipeline(self, job_id: str, document_id: str) -> None:
        """Execute multi-stage pipeline flow connecting GridFS, PP-OCRv6 cloud API, and MongoDB."""
        logger.info("Starting background processing for job %s (doc: %s)", job_id, document_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            # 1. Update status to SUBMITTED / RUNNING
            await self.job_repo.update_metadata(job_id, started_at=now_iso)
            await self.job_repo.update_stage(job_id, JobStage.INGESTION, JobStatus.SUBMITTED)

            doc = None
            if self.doc_repo:
                doc = await self.doc_repo.get_by_id(document_id)

            # Handle demo documents gracefully without making cloud API calls (Invariant 5)
            if doc and doc.sample:
                logger.info("Skipping cloud API for sample document %s", document_id)
                await self.job_repo.update_stage(job_id, JobStage.PREPROCESSING, JobStatus.RUNNING)
                await asyncio.sleep(0.05)
                await self.job_repo.update_stage(job_id, JobStage.LAYOUT_INTELLIGENCE, JobStatus.RUNNING)
                await asyncio.sleep(0.05)
                await self.job_repo.update_stage(job_id, JobStage.RECOGNITION, JobStatus.RUNNING)
                await asyncio.sleep(0.05)
                await self.job_repo.update_stage(job_id, JobStage.COMPLETED, JobStatus.COMPLETED)
                await self.job_repo.mark_completed(job_id, processed_page_count=1, execution_time_ms=10.0)
                return

            if not self.storage_provider:
                raise RuntimeError("Storage provider not configured on WorkerRunner.")

            # Stage 1: Preprocessing & Retrieval
            await self.job_repo.update_stage(job_id, JobStage.PREPROCESSING, JobStatus.RUNNING)
            file_key = (doc.gridfs_file_id if doc else None) or document_id
            doc_bytes = await self.storage_provider.download(file_key)
            if not doc_bytes:
                raise RuntimeError(f"Could not retrieve file bytes for document {document_id}")

            mime_type = (doc.content_type if doc else None) or "application/pdf"
            filename = (doc.original_filename if doc else None) or f"{document_id}.bin"

            # Stage 2: Layout / Automatic text detection & PP-OCRv6 inference
            await self.job_repo.update_stage(job_id, JobStage.LAYOUT_INTELLIGENCE, JobStatus.RUNNING)

            if not self.cloud_ocr_provider:
                raise RuntimeError("Cloud OCR provider not configured on WorkerRunner.")

            # Stage 3: Recognition execution
            await self.job_repo.update_stage(job_id, JobStage.RECOGNITION, JobStatus.RUNNING)
            ocr_result = await self.cloud_ocr_provider.recognize_document(
                document_bytes=doc_bytes,
                mime_type=mime_type,
                filename=filename,
            )

            # Record remote cloud job ID and execution metadata
            cloud_job_id = ocr_result.metadata.parameters.get("cloud_job_id")
            await self.job_repo.update_metadata(
                job_id=job_id,
                provider_job_id=str(cloud_job_id) if cloud_job_id else None,
                execution_time_ms=ocr_result.execution_time_ms,
            )

            # Normalize and construct RegionEntity records
            regions_to_save = []
            now_str = datetime.now(timezone.utc).isoformat()
            detected_items = ocr_result.detected_regions

            for idx, item in enumerate(detected_items):
                reg_id = f"reg-p{item.page_index}-{idx + 1:03d}"
                bbox = BoundingBox(
                    x=item.bounding_box["x"],
                    y=item.bounding_box["y"],
                    w=item.bounding_box["w"],
                    h=item.bounding_box["h"],
                )
                candidate = CandidateSuggestion(
                    text=item.text,
                    confidence=round(item.confidence, 4),
                    calibrated_score=round(item.confidence, 4),
                    provider_id=ocr_result.metadata.provider_name,
                    model_version=ocr_result.metadata.model_version,
                )
                reason_codes = ["AUTO_DETECTED"]
                if item.is_illegible:
                    reason_codes.append("LOW_CONFIDENCE")

                entity = RegionEntity(
                    id=reg_id,
                    document_id=document_id,
                    page_index=item.page_index,
                    line=item.text,
                    original=item.text,
                    alternatives=[item.text],
                    candidates_detail=[candidate],
                    reason=f"Automatic text line detected by {ocr_result.metadata.model_version} ({item.confidence * 100:.1f}% conf)",
                    reason_codes=reason_codes,
                    bounding_box=bbox,
                    polygon=item.polygon,
                    confidence=item.confidence,
                    provider_id=ocr_result.metadata.provider_name,
                    model_version=ocr_result.metadata.model_version,
                    provider_job_id=str(cloud_job_id) if cloud_job_id else None,
                    source_sha256=doc.sha256 if doc else None,
                    status=RegionReviewStatus.PENDING,
                    is_illegible=item.is_illegible,
                    created_at=now_str,
                    updated_at=now_str,
                )
                regions_to_save.append(entity)

            # Persist detected regions into MongoDB
            if self.region_repo and regions_to_save:
                saved = await self.region_repo.bulk_save_regions(document_id, regions_to_save)
                logger.info("Persisted %s detected text regions for document %s", saved, document_id)

            # Stage 4: Evidence Fusion
            await self.job_repo.update_stage(job_id, JobStage.EVIDENCE_FUSION, JobStatus.RUNNING)
            await asyncio.sleep(0.02)

            # Stage 5: Trust Decision
            await self.job_repo.update_stage(job_id, JobStage.TRUST_DECISION, JobStatus.RUNNING)
            await asyncio.sleep(0.02)

            # Mark Completed
            page_count = (doc.pages if doc else None) or (doc.page_count if doc else 1) or 1
            await self.job_repo.mark_completed(
                job_id=job_id,
                processed_page_count=page_count,
                execution_time_ms=ocr_result.execution_time_ms,
            )

            # Update document status to Needs review
            if self.doc_repo:
                await self.doc_repo.update_status(document_id, DocumentStatus.NEEDS_REVIEW)

            logger.info("Job %s completed successfully (%s regions detected)", job_id, len(regions_to_save))

        except Exception as exc:
            logger.exception("Job %s failed with exception: %s", job_id, str(exc))
            await self.job_repo.mark_failed(job_id, error_message=str(exc))
