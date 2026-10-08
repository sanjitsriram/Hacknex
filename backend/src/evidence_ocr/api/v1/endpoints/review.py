"""Human review, region confirmation, and transcript editing endpoints."""

from typing import Annotated
from fastapi import APIRouter, Depends, status
from evidence_ocr.api.dependencies import get_review_service
from evidence_ocr.review.service import ReviewService
from evidence_ocr.schemas.review import (
    CompleteReviewRequest,
    CompleteReviewResponse,
    RegionUpdateRequest,
    RegionUpdateResponse,
    ReviewSessionResponse,
    TranscriptUpdateRequest,
    TranscriptUpdateResponse,
)

router = APIRouter(prefix="/documents", tags=["Review"])


@router.get(
    "/{id}/review",
    response_model=ReviewSessionResponse,
    summary="Get document review session",
    description="Loads the document transcript, source review regions, candidate options, and audit history.",
)
async def get_review_session(
    id: str,
    review_service: Annotated[ReviewService, Depends(get_review_service)],
) -> ReviewSessionResponse:
    """Retrieve active review session for document."""
    return await review_service.get_review_session(id)


@router.patch(
    "/{id}/regions/{regionId}",
    response_model=RegionUpdateResponse,
    summary="Update region decision",
    description="Applies reviewer decision or illegibility mark to a region, checking optimistic revision.",
)
async def update_region(
    id: str,
    regionId: str,
    payload: RegionUpdateRequest,
    review_service: Annotated[ReviewService, Depends(get_review_service)],
) -> RegionUpdateResponse:
    """Update decision on a single region."""
    return await review_service.update_region_decision(
        document_id=id,
        region_id=regionId,
        decision=payload.decision,
        is_illegible=payload.is_illegible,
        expected_revision=payload.expected_revision,
        reviewer=payload.reviewer or "Sanjit",
    )


@router.patch(
    "/{id}/transcript",
    response_model=TranscriptUpdateResponse,
    summary="Update full transcript",
    description="Updates the full document transcript, validating optimistic concurrency revision.",
)
async def update_transcript(
    id: str,
    payload: TranscriptUpdateRequest,
    review_service: Annotated[ReviewService, Depends(get_review_service)],
) -> TranscriptUpdateResponse:
    """Update full transcript text."""
    return await review_service.update_transcript(
        document_id=id,
        text=payload.text,
        expected_revision=payload.expected_revision,
        reviewer=payload.reviewer or "Sanjit",
    )


@router.post(
    "/{id}/complete",
    response_model=CompleteReviewResponse,
    summary="Complete human review",
    description="Finalizes human review. Rejects if unresolved mandatory review regions remain.",
)
async def complete_review(
    id: str,
    payload: CompleteReviewRequest,
    review_service: Annotated[ReviewService, Depends(get_review_service)],
) -> CompleteReviewResponse:
    """Finalize document review."""
    return await review_service.complete_review(
        document_id=id,
        expected_revision=payload.expected_revision,
        reviewer=payload.reviewer or "Sanjit",
    )
