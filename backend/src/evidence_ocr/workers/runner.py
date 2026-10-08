"""Asynchronous in-process task runner boundary for background recognition and document intelligence jobs."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Optional
import uuid
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.db.repositories.parsing import DocumentParsingRepository
from evidence_ocr.db.repositories.regions import RegionRepository
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus
from evidence_ocr.models.parsing import DocumentParsingRun, LayoutBlock, ParsedPage
from evidence_ocr.models.region import (
    BoundingBox,
    CandidateSuggestion,
    RegionEntity,
    RegionReviewStatus,
)
from evidence_ocr.providers.ocr import BaseOCRProvider
from evidence_ocr.providers.paddleocr_vl import PaddleOCRVLCloudProvider
from evidence_ocr.providers.storage import BaseStorageProvider

logger = get_logger("evidence_ocr.workers")


class WorkerRunner:
    """In-process asynchronous job execution coordinator."""

    def __init__(
        self,
        job_repo: JobRepository,
        cloud_ocr_provider: Optional[BaseOCRProvider] = None,
        paddle_vl_provider: Optional[PaddleOCRVLCloudProvider] = None,
        storage_provider: Optional[BaseStorageProvider] = None,
        doc_repo: Optional[DocumentRepository] = None,
        region_repo: Optional[RegionRepository] = None,
        parsing_repo: Optional[DocumentParsingRepository] = None,
        recognition_service: Optional[Any] = None,
    ) -> None:
        self.job_repo = job_repo
        self.cloud_ocr_provider = cloud_ocr_provider
        self.paddle_vl_provider = paddle_vl_provider
        self.storage_provider = storage_provider
        self.doc_repo = doc_repo
        self.region_repo = region_repo
        self.parsing_repo = parsing_repo
        self.recognition_service = recognition_service

    async def dispatch_document_recognition(
        self, job_id: str, document_id: str, pipeline_version: str = "v1.0.0"
    ) -> None:
        """Enqueue and execute PP-OCRv6 recognition pipeline steps asynchronously."""
        asyncio.create_task(self._run_job_pipeline(job_id, document_id))

    async def dispatch_document_intelligence(
        self, job_id: str, document_id: str, pipeline_version: str = "v1.0.0"
    ) -> None:
        """Enqueue and execute PaddleOCR-VL document intelligence pipeline steps asynchronously."""
        asyncio.create_task(self._run_document_intelligence_pipeline(job_id, document_id))

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
                if item.confidence < 0.30:
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

    async def _run_document_intelligence_pipeline(self, job_id: str, document_id: str) -> None:
        """Execute PaddleOCR-VL document intelligence flow connecting GridFS and MongoDB."""
        logger.info("Starting Document Intelligence for job %s (doc: %s)", job_id, document_id)
        now_iso = datetime.now(timezone.utc).isoformat()
        try:
            await self.job_repo.update_metadata(job_id, started_at=now_iso)
            await self.job_repo.update_stage(job_id, JobStage.INGESTION, JobStatus.SUBMITTED)

            doc = None
            if self.doc_repo:
                doc = await self.doc_repo.get_by_id(document_id)

            # Handle demo documents gracefully without making cloud API calls (Invariant 5)
            if doc and doc.sample:
                logger.info("Generating sample Document Intelligence for sample document %s", document_id)
                await self.job_repo.update_stage(job_id, JobStage.PREPROCESSING, JobStatus.RUNNING)
                await asyncio.sleep(0.05)
                await self.job_repo.update_stage(job_id, JobStage.LAYOUT_INTELLIGENCE, JobStatus.RUNNING)

                sample_blocks = [
                    LayoutBlock(
                        block_id="blk-p0-001",
                        page_index=0,
                        block_type="paragraph_title",
                        bounding_box=BoundingBox(x=5.0, y=5.0, w=85.0, h=10.0),
                        content="# Structural Inspection Report · Section A",
                        reading_order=1,
                        confidence=0.98,
                    ),
                    LayoutBlock(
                        block_id="blk-p0-002",
                        page_index=0,
                        block_type="text",
                        bounding_box=BoundingBox(x=5.0, y=18.0, w=85.0, h=25.0),
                        content="The north wall measures 4.8 metres. Crack propagation observed along horizontal mortar joint. Replace bracket before inspection.",
                        reading_order=2,
                        confidence=0.92,
                    ),
                    LayoutBlock(
                        block_id="blk-p0-003",
                        page_index=0,
                        block_type="table",
                        bounding_box=BoundingBox(x=5.0, y=46.0, w=85.0, h=30.0),
                        content="| Element | Measurement | Status |\n|---|---|---|\n| North Wall | 4.8 m | Degraded |\n| Support Bracket | 12 mm | Pending |",
                        reading_order=3,
                        confidence=0.95,
                    ),
                ]

                sample_run = DocumentParsingRun(
                    id=f"run-{uuid.uuid4().hex[:8]}",
                    document_id=document_id,
                    job_id=job_id,
                    provider_id="paddleocr-cloud",
                    model_version="PaddleOCR-VL-1.6",
                    provider_job_id="sample-vl-job-001",
                    input_sha256=doc.sha256 if doc else None,
                    page_count=1,
                    markdown_text="# Structural Inspection Report · Section A\n\nThe north wall measures 4.8 metres. Crack propagation observed along horizontal mortar joint. Replace bracket before inspection.\n\n| Element | Measurement | Status |\n|---|---|---|\n| North Wall | 4.8 m | Degraded |\n| Support Bracket | 12 mm | Pending |",
                    pages=[
                        ParsedPage(
                            page_index=0,
                            width=1000,
                            height=1414,
                            markdown_text="# Structural Inspection Report · Section A\n\nThe north wall measures 4.8 metres.",
                            blocks=sample_blocks,
                            reading_order_sequence=["blk-p0-001", "blk-p0-002", "blk-p0-003"],
                            tables_count=1,
                        )
                    ],
                    total_blocks=len(sample_blocks),
                    execution_time_ms=15.0,
                    created_at=now_iso,
                )

                if self.parsing_repo:
                    await self.parsing_repo.save_run(sample_run)

                await self.job_repo.update_stage(job_id, JobStage.COMPLETED, JobStatus.COMPLETED)
                await self.job_repo.mark_completed(job_id, processed_page_count=1, execution_time_ms=15.0)
                return

            if not self.storage_provider:
                raise RuntimeError("Storage provider not configured on WorkerRunner.")

            # Stage 1: Download from GridFS
            await self.job_repo.update_stage(job_id, JobStage.PREPROCESSING, JobStatus.RUNNING)
            file_key = (doc.gridfs_file_id if doc else None) or document_id
            doc_bytes = await self.storage_provider.download(file_key)
            if not doc_bytes:
                raise RuntimeError(f"Could not retrieve file bytes for document {document_id}")

            mime_type = (doc.content_type if doc else None) or "application/pdf"
            filename = (doc.original_filename if doc else None) or f"{document_id}.bin"

            # Stage 2: Execute PaddleOCR-VL inference
            await self.job_repo.update_stage(job_id, JobStage.LAYOUT_INTELLIGENCE, JobStatus.RUNNING)
            if not self.paddle_vl_provider:
                raise RuntimeError("PaddleOCR-VL provider not configured on WorkerRunner.")

            parse_result = await self.paddle_vl_provider.parse_document(
                document_bytes=doc_bytes,
                mime_type=mime_type,
                filename=filename,
            )

            cloud_job_id = parse_result.metadata.parameters.get("cloud_job_id")
            await self.job_repo.update_metadata(
                job_id=job_id,
                provider_job_id=str(cloud_job_id) if cloud_job_id else None,
                execution_time_ms=parse_result.execution_time_ms,
            )

            # Stage 3: Construct and save DocumentParsingRun
            run_entity = DocumentParsingRun(
                id=f"run-{uuid.uuid4().hex[:8]}",
                document_id=document_id,
                job_id=job_id,
                provider_id=parse_result.metadata.provider_name,
                model_version=parse_result.metadata.model_version,
                provider_job_id=str(cloud_job_id) if cloud_job_id else None,
                input_sha256=doc.sha256 if doc else None,
                page_count=len(parse_result.pages),
                markdown_text=parse_result.markdown_text,
                pages=parse_result.pages,
                total_blocks=parse_result.total_blocks,
                execution_time_ms=parse_result.execution_time_ms,
                created_at=now_iso,
            )

            if self.parsing_repo:
                await self.parsing_repo.save_run(run_entity)
                logger.info(
                    "Persisted document parsing run %s (%s blocks across %s pages) for document %s",
                    run_entity.id,
                    run_entity.total_blocks,
                    run_entity.page_count,
                    document_id,
                )

            # Mark Completed
            page_count = len(parse_result.pages) or 1
            await self.job_repo.mark_completed(
                job_id=job_id,
                processed_page_count=page_count,
                execution_time_ms=parse_result.execution_time_ms,
            )

            if self.doc_repo:
                await self.doc_repo.update_status(document_id, DocumentStatus.NEEDS_REVIEW)

            logger.info("Document Intelligence job %s completed successfully", job_id)

        except Exception as exc:
            logger.exception("Document Intelligence job %s failed: %s", job_id, str(exc))
            await self.job_repo.mark_failed(job_id, error_message=str(exc))
