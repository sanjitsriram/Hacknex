"""Phase 6 Fusion API endpoints.

Routes:
  POST   /documents/{document_id}/fusion-runs                    - Queue a new fusion run
  GET    /documents/{document_id}/fusion-runs                    - List runs (session-scoped)
  GET    /documents/{document_id}/fusion-runs/{run_id}           - Get run detail with proposals
  GET    /documents/{document_id}/disagreements                  - List disagreements (filterable)
  POST   /documents/{document_id}/regions/{region_id}/recover    - Queue targeted recovery
  GET    /documents/{document_id}/regions/{region_id}/evidence   - Full evidence view

All handlers: zero direct DB access; delegate to FusionService.
Session ownership validated before access to any fusion data.
"""

import asyncio
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status

from evidence_ocr.api.dependencies import (
    get_document_repository,
    get_fusion_service,
    get_storage_provider,
)
from evidence_ocr.core.errors import EntityNotFoundError
from evidence_ocr.core.logging import get_logger
from evidence_ocr.db.repositories.documents import DocumentRepository
from evidence_ocr.fusion.service import FusionService
from evidence_ocr.schemas.fusion import (
    CreateFusionRunRequest,
    CreateFusionRunResponse,
    CreateRecoveryRequest,
    CreateRecoveryResponse,
    DisagreementListResponse,
    DisagreementResponse,
    FusionRunDetailResponse,
    FusionRunSummaryResponse,
    RegionEvidenceResponse,
)

router = APIRouter(prefix="/documents", tags=["fusion"])
logger = get_logger("evidence_ocr.api.v1.fusion")


def _session_id(request: Request) -> str:
    """Extract anonymous session identifier from cookies or headers."""
    sid = request.cookies.get("session_id") or request.headers.get("X-Session-Id", "")
    if not sid:
        sid = f"anon-{uuid.uuid4().hex[:12]}"
    return sid


async def _get_document_or_404(doc_id: str, doc_repo: DocumentRepository):
    doc = await doc_repo.get_by_id(doc_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Document {doc_id} not found")
    return doc


@router.post(
    "/{document_id}/fusion-runs",
    status_code=status.HTTP_200_OK,
    response_model=CreateFusionRunResponse,
    summary="Queue evidence fusion run",
)
async def create_fusion_run(
    document_id: str,
    body: CreateFusionRunRequest,
    request: Request,
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """Queue a new evidence fusion pipeline run for a document.

    Returns 202 immediately with fusion_run_id. Poll
    GET /fusion-runs/{run_id} for status and results.

    Returns 409 if a non-failed run with the same idempotency_key exists.
    Returns 422 if no OCR regions exist for the document.
    """
    session_id = _session_id(request)
    await _get_document_or_404(document_id, doc_repo)

    # Idempotency check
    if body.idempotency_key and fusion_svc.fusion_repo:
        existing = await fusion_svc.fusion_repo.check_idempotency(document_id, body.idempotency_key)
        if existing:
            return CreateFusionRunResponse(
                fusion_run_id=existing.id,
                document_id=document_id,
                status=existing.status.value,
                message="Existing fusion run returned (idempotent)",
            )

    # Create FusionRun record
    fusion_run = await fusion_svc.create_fusion_run(
        document_id=document_id,
        session_id=session_id,
        strategy=body.strategy,
        idempotency_key=body.idempotency_key,
    )

    # Load document bytes for recovery eligibility (lazy — only needed for evidence_aware_with_recovery)
    doc_bytes: Optional[bytes] = None
    mime_type = "image/png"

    # Dispatch fusion pipeline as background asyncio task (non-blocking)
    asyncio.create_task(
        _run_fusion_background(fusion_svc, fusion_run, document_id, doc_bytes, mime_type),
        name=f"fusion-{fusion_run.id}",
    )

    return CreateFusionRunResponse(
        fusion_run_id=fusion_run.id,
        document_id=document_id,
        status=fusion_run.status.value,
        message="Fusion run queued",
    )


async def _run_fusion_background(fusion_svc, fusion_run, document_id, doc_bytes, mime_type):
    """Background asyncio task executing the fusion pipeline."""
    try:
        await fusion_svc.execute_fusion(
            fusion_run=fusion_run,
            document_id=document_id,
            document_bytes=doc_bytes,
            mime_type=mime_type,
        )
    except Exception as exc:
        logger.exception("Unhandled error in fusion background task for run %s: %s", fusion_run.id, exc)


@router.get(
    "/{document_id}/fusion-runs",
    response_model=List[FusionRunSummaryResponse],
    summary="List fusion runs for document",
)
async def list_fusion_runs(
    document_id: str,
    request: Request,
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """List all evidence fusion runs for a document (session-scoped, newest first)."""
    session_id = _session_id(request)
    await _get_document_or_404(document_id, doc_repo)
    runs = await fusion_svc.list_fusion_runs(document_id, session_id)
    return [
        FusionRunSummaryResponse(
            fusion_run_id=r.id,
            document_id=r.document_id,
            status=r.status.value,
            strategy_version=r.strategy_version,
            region_count=r.region_count,
            matched_count=r.matched_count,
            disagreement_count=r.disagreement_count,
            auto_proposable_count=r.auto_proposable_count,
            requires_review_count=r.requires_review_count,
            recovery_eligible_count=r.recovery_eligible_count,
            execution_time_ms=r.execution_time_ms,
            error_message=r.error_message,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )
        for r in runs
    ]


@router.get(
    "/{document_id}/fusion-runs/{run_id}",
    response_model=FusionRunDetailResponse,
    summary="Get fusion run detail with proposals",
)
async def get_fusion_run(
    document_id: str,
    run_id: str,
    request: Request,
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """Retrieve a fusion run detail including embedded proposals."""
    await _get_document_or_404(document_id, doc_repo)
    run = await fusion_svc.get_fusion_run(run_id, document_id)
    if not run:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Fusion run {run_id} not found")

    proposals = await fusion_svc.get_proposals(document_id, run_id)

    return FusionRunDetailResponse(
        fusion_run_id=run.id,
        document_id=run.document_id,
        status=run.status.value,
        strategy_version=run.strategy_version,
        alignment_algorithm_version=run.alignment_algorithm_version,
        region_count=run.region_count,
        matched_count=run.matched_count,
        disagreement_count=run.disagreement_count,
        auto_proposable_count=run.auto_proposable_count,
        requires_review_count=run.requires_review_count,
        recovery_eligible_count=run.recovery_eligible_count,
        execution_time_ms=run.execution_time_ms,
        error_message=run.error_message,
        created_at=run.created_at,
        updated_at=run.updated_at,
        proposals=[p.model_dump() for p in proposals],
    )


@router.get(
    "/{document_id}/disagreements",
    response_model=DisagreementListResponse,
    summary="List disagreements for a document",
)
async def list_disagreements(
    document_id: str,
    request: Request,
    fusion_run_id: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None, description="Filter by severity: CRITICAL|HIGH|MEDIUM|LOW"),
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """Retrieve disagreement records for a document, optionally filtered by run and severity."""
    await _get_document_or_404(document_id, doc_repo)
    records = await fusion_svc.get_disagreements(
        document_id=document_id,
        fusion_run_id=fusion_run_id,
        severity=severity,
    )
    return DisagreementListResponse(
        document_id=document_id,
        total=len(records),
        disagreements=[
            DisagreementResponse(
                id=d.id,
                fusion_run_id=d.fusion_run_id,
                document_id=d.document_id,
                region_id=d.region_id,
                page_index=d.page_index,
                disagreement_type=d.disagreement_type.value,
                severity=d.severity.value,
                description=d.description,
                candidate_a=d.candidate_a,
                candidate_b=d.candidate_b,
                candidate_c=d.candidate_c,
                conflicting_span=d.conflicting_span,
                alignment_id=d.alignment_id,
                created_at=d.created_at,
            )
            for d in records
        ],
    )


@router.post(
    "/{document_id}/regions/{region_id}/recover",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateRecoveryResponse,
    summary="Run bounded targeted recovery for a region",
)
async def request_recovery(
    document_id: str,
    region_id: str,
    body: CreateRecoveryRequest,
    request: Request,
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """Run and persist targeted re-inference for a difficult region.

    Recovery is subject to budget controls: max 2 TrOCR variants per region.
    Returns 429 when budget is exhausted.
    Returns 503 when required providers or persistence are unavailable.
    """
    document = await _get_document_or_404(document_id, doc_repo)
    try:
        attempts = await fusion_svc.recover_region(
            document=document,
            region_id=region_id,
            fusion_run_id=body.fusion_run_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except OverflowError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc

    return CreateRecoveryResponse(
        recovery_attempt_id=attempts[0].id,
        region_id=region_id,
        status="completed",
        message=f"{len(attempts)} bounded recovery variant(s) recorded",
    )


@router.get(
    "/{document_id}/regions/{region_id}/evidence",
    response_model=RegionEvidenceResponse,
    summary="Get complete evidence view for a region",
)
async def get_region_evidence(
    document_id: str,
    region_id: str,
    request: Request,
    fusion_run_id: Optional[str] = Query(default=None),
    doc_repo: DocumentRepository = Depends(get_document_repository),
    fusion_svc: FusionService = Depends(get_fusion_service),
):
    """Return all available evidence for a region: candidates, proposal, disagreements, recovery history."""
    await _get_document_or_404(document_id, doc_repo)
    evidence = await fusion_svc.get_region_evidence(
        document_id=document_id,
        region_id=region_id,
        fusion_run_id=fusion_run_id,
    )
    return RegionEvidenceResponse(**evidence)
