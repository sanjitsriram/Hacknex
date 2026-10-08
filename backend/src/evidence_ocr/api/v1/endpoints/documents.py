"""Document management and ingestion endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_ingestion_service,
    get_job_repository,
    get_storage_provider,
    get_worker_runner,
)
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.providers.storage import BaseStorageProvider
from evidence_ocr.schemas.documents import (
    DocumentDetailResponse,
    DocumentItemResponse,
    DocumentListResponse,
    DocumentUploadResponse,
)
from evidence_ocr.schemas.jobs import JobCreateRequest, JobResponse
from evidence_ocr.workers.runner import WorkerRunner

router = APIRouter(prefix="/documents", tags=["Documents"])


@router.post(
    "",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a document",
    description="Ingests a new document, verifies constraints (PDF/PNG/JPEG, <=10MB, <=20 pages), and stores in MongoDB GridFS.",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document binary file (PDF, PNG, JPEG)")],
    title: Annotated[str, Form(description="Document title")] = "Untitled document",
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
    description="Enqueues asynchronous OCR recognition pipeline for the specified document.",
)
async def schedule_recognition(
    id: str,
    payload: JobCreateRequest,
    doc_repo: Annotated[DocumentRepository, Depends(get_document_repository)],
    job_repo: Annotated[JobRepository, Depends(get_job_repository)],
    worker_runner: Annotated[WorkerRunner, Depends(get_worker_runner)],
) -> JobResponse:
    """Create and dispatch asynchronous recognition job."""
    doc = await doc_repo.get_by_id(id)
    if not doc:
        raise EntityNotFoundError("Document", id)

    now = datetime.now(timezone.utc).isoformat()
    job_id = f"job-{uuid.uuid4().hex[:8]}"

    job = ProcessingJob(
        id=job_id,
        document_id=id,
        pipeline_version=payload.pipeline_version,
        idempotency_key=payload.idempotency_key,
        status=JobStatus.QUEUED,
        stage=JobStage.INGESTION,
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
        created_at=job.created_at,
    )
