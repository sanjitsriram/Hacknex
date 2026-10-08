"""Document management and ingestion endpoints."""

import uuid
from datetime import datetime, timezone
from typing import Annotated, Optional
from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, status
from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_ingestion_service,
    get_job_repository,
    get_worker_runner,
)
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.db.repositories.jobs import JobRepository
from evidence_ocr.ingestion.service import IngestionService
from evidence_ocr.models.document import DocumentStatus
from evidence_ocr.models.job import JobStage, JobStatus, ProcessingJob
from evidence_ocr.schemas.documents import (
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
    description="Ingests a new document, verifies constraints (PNG/JPG/WebP/PDF, <=20MB), and stores original.",
)
async def upload_document(
    file: Annotated[UploadFile, File(description="Document binary file")],
    title: Annotated[str, Form(description="Document title")] = "Untitled document",
    kind: Annotated[str, Form(description="Document category")] = "Field notes",
    expected_language: Annotated[str, Form(description="Expected language")] = "English",
    ingestion_service: Annotated[IngestionService, Depends(get_ingestion_service)] = None,
) -> DocumentUploadResponse:
    """Handle multipart document intake."""
    file_bytes = await file.read()
    entity = await ingestion_service.ingest_document(
        title=title,
        kind=kind,
        language=expected_language,
        filename=file.filename,
        content_type=file.content_type,
        file_bytes=file_bytes,
    )
    return DocumentUploadResponse(
        document_id=entity.id,
        source_url=entity.source_url,
        status=entity.status,
        revision=entity.revision,
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
            status=d.status.value,
            added=d.added,
            size=d.size,
            sample=d.sample,
            url=d.source_url,
            mime=d.mime,
            revision=d.revision,
        )
        for d in entities
    ]

    return DocumentListResponse(
        items=items,
        next_cursor=str(skip + limit) if (skip + limit) < total else None,
        total=total,
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
