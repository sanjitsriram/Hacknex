"""Document management and ingestion endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, List, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_ingestion_service,
    get_job_repository,
    get_parsing_repository,
    get_recognition_service,
    get_region_repository,
    get_storage_provider,
    get_worker_runner,
)
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.db.repositories.parsing import DocumentParsingRepository
from evidence_ocr.db.repositories.regions import RegionRepository
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.models.parsing import DocumentParsingRun, LayoutBlock, ParsedPage
from evidence_ocr.models.region import BoundingBox
from evidence_ocr.providers.storage import BaseStorageProvider
from evidence_ocr.recognition.service import RecognitionService
from evidence_ocr.schemas.documents import (
    DocumentDetailResponse,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)
from evidence_ocr.schemas.jobs import JobCreateRequest, JobResponse, JobStatusResponse
from evidence_ocr.schemas.parsing import (
    DocumentIntelligenceRequest,
    DocumentParsingRunResponse,
    LayoutBlockResponse,
    ParsedPageResponse,
)
from evidence_ocr.schemas.recognition import (
    DocumentRegionDetail,
    DocumentRegionsListResponse,
    RegionRecognitionRequest,
    RegionRecognitionResponse,
)
from evidence_ocr.workers.runner import WorkerRunner

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document",
    description="Ingests a new document, verifies configured file/page limits, and stores it in MongoDB GridFS.",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document binary file (PDF, PNG, JPEG)")],
    title: Annotated[str, Form(min_length=1, max_length=120, description="Document title")] = "Untitled document",
    kind: Annotated[str, Form(description="Document category")] = "Field notes",
    expected_language: Annotated[str, Form(description="Expected language")] = "English",
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)] = None,
) -> DocumentUploadResponse:
    """Handle multipart document upload and incremental ingestion into GridFS."""
    entity = await ingestion_service.ingest_upload(
        file=file,
        title=title,
        kind=kind,
        language=expected_language,
    )
    return DocumentUploadResponse(
        document_id=entity.id,
        name=entity.name,
        original_filename=entity.original_filename,
        content_type=entity.content_type,
        file_size_bytes=entity.file_size_bytes,
        sha256=entity.sha256,
        gridfs_file_id=entity.gridfs_file_id,
        page_count=entity.page_count,
        source_url=entity.source_url,
        status=entity.status,
        revision=entity.revision,
        created_at=entity.created_at,
    )


@router.get(
    "",
    response_model=DocumentListResponse,
    summary="List documents",
    description="Query documents with optional search string and status filter.",
)
async def list_documents(
    search: Annotated[Optional[str], Query(description="Search by document name")] = None,
    status_filter: Annotated[Optional[str], Query(alias="status", description="Filter by status")] = None,
    limit: Annotated[int, Query(ge=1, le=100, description="Items limit")] = 20,
    skip: Annotated[int, Query(ge=0, description="Offset")] = 0,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)] = None,
) -> DocumentListResponse:
    """List documents with pagination."""
    entities, total = await doc_repo.list_documents(
        status_filter=status_filter,
        search_query=search,
        skip=skip,
        limit=limit,
    )

    items = [
        DocumentItemResponse(
            id=d.id,
            name=d.name,
            kind=d.kind,
            language=d.language,
            pages=d.pages,
            status=d.status.value if hasattr(d.status, "value") else str(d.status),
            added=d.added,
            size=d.size,
            sample=d.sample,
            url=d.source_url,
            mime=d.mime or d.content_type,
            revision=d.revision,
            sha256=d.sha256,
            gridfs_file_id=d.gridfs_file_id,
            file_size_bytes=d.file_size_bytes,
        )
        for d in entities
    ]

    return DocumentListResponse(
        items=items,
        next_cursor=str(skip + limit) if (skip + limit) < total else None,
        total=total,
    )


@router.get(
    "/{document_id}",
    response_model=DocumentDetailResponse,
    summary="Get document details",
    description="Retrieve full metadata for a specific document.",
)
async def get_document(
    document_id: str,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)] = None,
) -> DocumentDetailResponse:
    """Retrieve complete metadata for a document."""
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise EntityNotFoundError("Document", document_id)

    status_str = doc.status.value if hasattr(doc.status, "value") else str(doc.status)
    return DocumentDetailResponse(
        id=doc.id,
        document_id=doc.document_id or doc.id,
        name=doc.name,
        original_filename=doc.original_filename,
        content_type=doc.content_type or doc.mime,
        file_size_bytes=doc.file_size_bytes,
        sha256=doc.sha256,
        gridfs_file_id=doc.gridfs_file_id,
        page_count=doc.page_count or doc.pages,
        pages=doc.pages,
        kind=doc.kind,
        language=doc.language,
        status=status_str,
        processing_status=doc.processing_status or status_str,
        sample=doc.sample,
        source_url=doc.source_url,
        revision=doc.revision,
        schema_version=doc.schema_version,
        created_at=doc.created_at,
        updated_at=doc.updated_at,
    )


@router.get(
    "/{document_id}/file",
    summary="Stream original document binary",
    description="Stream bit-for-bit identical original file from MongoDB GridFS.",
)
async def stream_document_file(
    document_id: str,
    download: Annotated[bool, Query(description="Force download attachment")] = False,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)] = None,
    storage: Annotated[BaseStorageProvider, Depends(get_storage_provider)] = None,
):
    """Stream stored original file bytes from GridFS."""
    doc = await doc_repo.get_by_id(document_id)
    if not doc:
        raise EntityNotFoundError("Document", document_id)

    file_key = doc.gridfs_file_id or doc.file_key or doc.id
    if not file_key:
        raise EntityNotFoundError("FileKey", document_id)

    grid_out = await storage.open_download_stream(file_key)
    content_type = (
        doc.content_type
        or doc.mime
        or getattr(grid_out, "metadata", {}).get("content_type", "application/octet-stream")
    )
    safe_filename = doc.original_filename or f"{document_id}.bin"
    disposition_type = "attachment" if download else "inline"

    async def file_stream_generator():
        while True:
            chunk = await grid_out.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    headers = {
        "Content-Disposition": f'{disposition_type}; filename="{safe_filename}"',
    }
    if doc.file_size_bytes:
        headers["Content-Length"] = str(doc.file_size_bytes)
    elif hasattr(grid_out, "length") and grid_out.length:
        headers["Content-Length"] = str(grid_out.length)
    if doc.sha256:
        headers["ETag"] = f'"{doc.sha256}"'

    return StreamingResponse(
        file_stream_generator(),
        media_type=content_type,
        headers=headers,
    )


@router.post(
    "/{id}/recognition",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Schedule recognition job",
    description="Enqueues asynchronous OCR recognition pipeline for the specified document with duplicate prevention.",
)
async def schedule_recognition(
    id: str,
    payload: JobCreateRequest,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    worker_runner: Annotated[WorkerRunner, Depends(get_worker_runner)],
) -> JobResponse:
    """Create and dispatch asynchronous recognition job or return active job."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    # Check for active existing job with zombie recovery and force re-run support
    active_job: Optional[ProcessingJob] = None
    if hasattr(job_repo, "find_active_by_document"):
        res = await job_repo.find_active_by_document(id, task_type="recognition")
        if isinstance(res, ProcessingJob):
            active_job = res
    if not active_job and hasattr(job_repo, "list_by_document"):
        job_list = await job_repo.list_by_document(id)
        if isinstance(job_list, list):
            for candidate in job_list:
                if (
                    isinstance(candidate, ProcessingJob)
                    and candidate.status in (JobStatus.QUEUED, JobStatus.SUBMITTED, JobStatus.RUNNING)
                    and getattr(candidate, "task_type", None) in ("recognition", None)
                ):
                    active_job = candidate
                    break

    if active_job:
        if getattr(payload, "force", False):
            await worker_runner.cancel_job(active_job.id, reason="Force re-run requested by user")
        else:
            return JobResponse(
                job_id=active_job.id,
                document_id=active_job.document_id,
                status=active_job.status,
                stage=active_job.stage,
                provider=getattr(active_job, "provider", "paddleocr-cloud") or "paddleocr-cloud",
                model=getattr(active_job, "model", "PP-OCRv6") or "PP-OCRv6",
                created_at=active_job.created_at,
            )

    now = datetime.now(timezone.utc).isoformat()
    job_id = f"job-{uuid.uuid4().hex[:8]}"

    job = ProcessingJob(
        id=job_id,
        document_id=id,
        pipeline_version=payload.pipeline_version,
        idempotency_key=payload.idempotency_key,
        status=JobStatus.QUEUED,
        stage=JobStage.INGESTION,
        provider="paddleocr-cloud",
        model="PP-OCRv6",
        created_at=now,
        updated_at=now,
    )

    await job_repo.create(job)
    await worker_runner.dispatch_document_recognition(job_id, id, payload.pipeline_version)

    return JobResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        provider=job.provider,
        model=job.model,
        created_at=job.created_at,
    )


@router.get(
    "/{id}/regions",
    response_model=DocumentRegionsListResponse,
    summary="List detected document regions",
    description="Retrieves all detected regions, visual bounding boxes, original polygons, and candidate recognition proposals.",
)
async def list_document_regions(
    id: str,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    region_repo: Annotated[Optional[RegionRepository], Depends(get_region_repository)] = None,
) -> DocumentRegionsListResponse:
    """Retrieve persisted detected regions for a document from MongoDB."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    entities = []
    if hasattr(region_repo, "get_by_document_id"):
        res = await region_repo.get_by_document_id(id)
        if isinstance(res, list):
            entities = res
    if not entities and hasattr(region_repo, "list_by_document"):
        res = await region_repo.list_by_document(id)
        if isinstance(res, list):
            entities = res
    items = [
        DocumentRegionDetail(
            id=r.id,
            document_id=r.document_id,
            page_index=r.page_index,
            line=r.line,
            original=r.original,
            bounding_box=r.bounding_box,
            polygon=r.polygon,
            confidence=r.confidence,
            provider_id=r.provider_id,
            model_version=r.model_version,
            candidates_detail=r.candidates_detail,
            status=r.status.value if hasattr(r.status, "value") else str(r.status),
            reviewer_decision=r.reviewer_decision,
            is_illegible=r.is_illegible,
        )
        for r in entities
    ]

    return DocumentRegionsListResponse(
        document_id=id,
        total=len(items),
        items=items,
    )


@router.get(
    "/{id}/jobs",
    response_model=list[JobStatusResponse],
    summary="List document processing jobs",
    description="Retrieves execution history and statuses of all recognition jobs for the document.",
)
async def list_document_jobs(
    id: str,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
) -> list[JobStatusResponse]:
    """Retrieve all jobs recorded for this document."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    jobs = await job_repo.list_by_document(id)
    return [
        JobStatusResponse(
            job_id=j.id,
            document_id=j.document_id,
            status=j.status,
            stage=j.stage,
            provider=getattr(j, "provider", "paddleocr-cloud") or "paddleocr-cloud",
            model=getattr(j, "model", "PP-OCRv6") or "PP-OCRv6",
            provider_job_id=j.provider_job_id,
            processed_page_count=j.processed_page_count,
            execution_time_ms=j.execution_time_ms,
            error=j.error_message,
            retry_count=j.retry_count,
            started_at=j.started_at,
            created_at=j.created_at,
            updated_at=j.updated_at,
            completed_at=j.completed_at,
        )
        for j in jobs
    ]


@router.post(
    "/{id}/regions/{region_id}/recognize",
    response_model=RegionRecognitionResponse,
    summary="Execute on-demand TrOCR handwriting recognition",
    description="Extracts the specified region crop from the document in GridFS, executes TrOCR, and saves the candidate proposal.",
)
async def recognize_region(
    id: str,
    region_id: str,
    payload: Optional[RegionRecognitionRequest] = None,
    recognition_service: Annotated[RecognitionService, Depends(get_recognition_service)] = None,
) -> RegionRecognitionResponse:
    """Execute real TrOCR inference on document region crop."""
    bbox = payload.bounding_box if payload else None
    page_idx = payload.page_index if payload else 0
    return await recognition_service.recognize_region(
        document_id=id,
        region_id=region_id,
        bounding_box=bbox,
        page_index=page_idx,
    )


@router.post(
    "/{id}/document-intelligence",
    response_model=JobResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Schedule PaddleOCR-VL Document Intelligence job",
    description="Enqueues asynchronous PaddleOCR-VL-1.6 document parsing and layout intelligence with duplicate prevention.",
)
async def schedule_document_intelligence(
    id: str,
    payload: DocumentIntelligenceRequest,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    worker_runner: Annotated[WorkerRunner, Depends(get_worker_runner)],
) -> JobResponse:
    """Create and dispatch asynchronous PaddleOCR-VL document intelligence job or return active job."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    # Check for active existing job with zombie recovery and force re-run support
    active_job: Optional[ProcessingJob] = None
    if hasattr(job_repo, "find_active_by_document"):
        res = await job_repo.find_active_by_document(id, task_type="document_intelligence")
        if isinstance(res, ProcessingJob):
            active_job = res
    if not active_job and hasattr(job_repo, "list_by_document"):
        job_list = await job_repo.list_by_document(id)
        if isinstance(job_list, list):
            for candidate in job_list:
                if (
                    isinstance(candidate, ProcessingJob)
                    and candidate.status in (JobStatus.QUEUED, JobStatus.SUBMITTED, JobStatus.RUNNING)
                    and getattr(candidate, "task_type", None) in ("document_intelligence", None)
                ):
                    active_job = candidate
                    break

    if active_job:
        if getattr(payload, "force", False):
            await worker_runner.cancel_job(active_job.id, reason="Force re-run requested by user")
        else:
            return JobResponse(
                job_id=active_job.id,
                document_id=active_job.document_id,
                status=active_job.status,
                stage=active_job.stage,
                provider=getattr(active_job, "provider", "paddleocr-cloud") or "paddleocr-cloud",
                model=getattr(active_job, "model", "PaddleOCR-VL-1.6") or "PaddleOCR-VL-1.6",
                created_at=active_job.created_at,
            )

    now = datetime.now(timezone.utc).isoformat()
    job_id = f"job-{uuid.uuid4().hex[:8]}"

    job = ProcessingJob(
        id=job_id,
        document_id=id,
        pipeline_version=payload.pipeline_version,
        idempotency_key=payload.idempotency_key,
        task_type="document_intelligence",
        status=JobStatus.QUEUED,
        stage=JobStage.INGESTION,
        provider="paddleocr-cloud",
        model="PaddleOCR-VL-1.6",
        created_at=now,
        updated_at=now,
    )

    await job_repo.create(job)
    await worker_runner.dispatch_document_intelligence(job_id, id, payload.pipeline_version)

    return JobResponse(
        job_id=job.id,
        document_id=job.document_id,
        status=job.status,
        stage=job.stage,
        provider=job.provider,
        model=job.model,
        created_at=job.created_at,
    )


@router.get(
    "/{id}/parsed-document",
    response_model=Optional[DocumentParsingRunResponse],
    summary="Get latest PaddleOCR-VL document intelligence parsing run",
    description="Retrieves the most recent document parsing run including layout blocks, reading orders, and Markdown.",
)
async def get_parsed_document(
    id: str,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    parsing_repo: Annotated[Optional[DocumentParsingRepository], Depends(get_parsing_repository)] = None,
) -> Optional[DocumentParsingRunResponse]:
    """Retrieve latest parsed document layout and Markdown from MongoDB."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    if parsing_repo is None:
        # Fallback for demo sample when db is mock/unconnected
        if doc.sample:
            return DocumentParsingRunResponse(
                id=f"run-sample-{doc.id}",
                document_id=doc.id,
                job_id="sample-job",
                provider_id="paddleocr-cloud",
                model_version="PaddleOCR-VL-1.6",
                page_count=1,
                markdown_text="# Site Inspection Report · Sample\n\nThe north wall measures 4.8 metres. Crack propagation observed.",
                pages=[
                    ParsedPageResponse(
                        page_index=0,
                        width=1000,
                        height=1414,
                        markdown_text="# Site Inspection Report · Sample\n\nThe north wall measures 4.8 metres.",
                        blocks=[
                            LayoutBlockResponse(
                                block_id="blk-p0-001",
                                page_index=0,
                                block_type="paragraph_title",
                                bounding_box=BoundingBox(x=5.0, y=5.0, w=85.0, h=10.0),
                                content="# Site Inspection Report · Sample",
                                reading_order=1,
                                confidence=0.98,
                            ),
                            LayoutBlockResponse(
                                block_id="blk-p0-002",
                                page_index=0,
                                block_type="text",
                                bounding_box=BoundingBox(x=5.0, y=18.0, w=85.0, h=25.0),
                                content="The north wall measures 4.8 metres. Crack propagation observed.",
                                reading_order=2,
                                confidence=0.94,
                            ),
                        ],
                        reading_order_sequence=["blk-p0-001", "blk-p0-002"],
                        tables_count=0,
                    )
                ],
                total_blocks=2,
                execution_time_ms=12.0,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        return None

    run = await parsing_repo.get_latest_by_document(id)
    if not run:
        if doc.sample:
            # Generate deterministic sample response for interactive sample fixture
            return DocumentParsingRunResponse(
                id=f"run-sample-{doc.id}",
                document_id=doc.id,
                job_id="sample-job",
                provider_id="paddleocr-cloud",
                model_version="PaddleOCR-VL-1.6",
                page_count=1,
                markdown_text="# Site Inspection Report · Sample\n\nThe north wall measures 4.8 metres. Crack propagation observed.",
                pages=[
                    ParsedPageResponse(
                        page_index=0,
                        width=1000,
                        height=1414,
                        markdown_text="# Site Inspection Report · Sample\n\nThe north wall measures 4.8 metres.",
                        blocks=[
                            LayoutBlockResponse(
                                block_id="blk-p0-001",
                                page_index=0,
                                block_type="paragraph_title",
                                bounding_box=BoundingBox(x=5.0, y=5.0, w=85.0, h=10.0),
                                content="# Site Inspection Report · Sample",
                                reading_order=1,
                                confidence=0.98,
                            ),
                            LayoutBlockResponse(
                                block_id="blk-p0-002",
                                page_index=0,
                                block_type="text",
                                bounding_box=BoundingBox(x=5.0, y=18.0, w=85.0, h=25.0),
                                content="The north wall measures 4.8 metres. Crack propagation observed.",
                                reading_order=2,
                                confidence=0.94,
                            ),
                        ],
                        reading_order_sequence=["blk-p0-001", "blk-p0-002"],
                        tables_count=0,
                    )
                ],
                total_blocks=2,
                execution_time_ms=12.0,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
        return None

    pages_resp = [
        ParsedPageResponse(
            page_index=p.page_index,
            width=p.width,
            height=p.height,
            markdown_text=p.markdown_text,
            blocks=[
                LayoutBlockResponse(
                    block_id=b.block_id,
                    page_index=b.page_index,
                    block_type=b.block_type,
                    bounding_box=b.bounding_box,
                    polygon=b.polygon,
                    raw_bbox=b.raw_bbox,
                    content=b.content,
                    reading_order=b.reading_order,
                    confidence=b.confidence,
                )
                for b in p.blocks
            ],
            reading_order_sequence=p.reading_order_sequence,
            tables_count=p.tables_count,
        )
        for p in run.pages
    ]

    return DocumentParsingRunResponse(
        id=run.id,
        document_id=run.document_id,
        job_id=run.job_id,
        provider_id=run.provider_id,
        model_version=run.model_version,
        provider_job_id=run.provider_job_id,
        input_sha256=run.input_sha256,
        page_count=run.page_count,
        markdown_text=run.markdown_text,
        pages=pages_resp,
        total_blocks=run.total_blocks,
        execution_time_ms=run.execution_time_ms,
        created_at=run.created_at,
    )


@router.get(
    "/{id}/parsing-history",
    response_model=List[DocumentParsingRunResponse],
    summary="List document intelligence parsing history",
    description="Retrieves historical parsing runs for the document.",
)
async def list_parsing_history(
    id: str,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    parsing_repo: Annotated[Optional[DocumentParsingRepository], Depends(get_parsing_repository)] = None,
) -> List[DocumentParsingRunResponse]:
    """Retrieve history of parsing runs for a document."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    if parsing_repo is None:
        return []

    runs = await parsing_repo.list_by_document(id)
    return [
        DocumentParsingRunResponse(
            id=r.id,
            document_id=r.document_id,
            job_id=r.job_id,
            provider_id=r.provider_id,
            model_version=r.model_version,
            provider_job_id=r.provider_job_id,
            input_sha256=r.input_sha256,
            page_count=r.page_count,
            markdown_text=r.markdown_text,
            pages=[
                ParsedPageResponse(
                    page_index=p.page_index,
                    width=p.width,
                    height=p.height,
                    markdown_text=p.markdown_text,
                    blocks=[
                        LayoutBlockResponse(
                            block_id=b.block_id,
                            page_index=b.page_index,
                            block_type=b.block_type,
                            bounding_box=b.bounding_box,
                            polygon=b.polygon,
                            raw_bbox=b.raw_bbox,
                            content=b.content,
                            reading_order=b.reading_order,
                            confidence=b.confidence,
                        )
                        for b in p.blocks
                    ],
                    reading_order_sequence=p.reading_order_sequence,
                    tables_count=p.tables_count,
                )
                for p in r.pages
            ],
            total_blocks=r.total_blocks,
            execution_time_ms=r.execution_time_ms,
            created_at=r.created_at,
        )
        for r in runs
    ]

