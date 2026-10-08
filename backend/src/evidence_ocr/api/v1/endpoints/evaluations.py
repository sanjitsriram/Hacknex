"""Benchmark evaluations endpoint."""

from typing import Annotated, Optional
from fastapi import APIRouter, Depends, Query
from evidence_ocr.api.dependencies import get_evaluation_service
from evidence_ocr.evaluation.service import EvaluationService
from evidence_ocr.schemas.evaluations import EvaluationResponse

router = APIRouter(prefix="/evaluations", tags=["Evaluations"])


@router.get(
    "",
    response_model=EvaluationResponse,
    summary="Query benchmark evaluation runs",
    description="Returns real evaluation runs with verifiable dataset hashes and sample denominators.",
)
async def list_evaluations(
    dataset: Annotated[Optional[str], Query(description="Filter by dataset name")] = None,
    subset: Annotated[Optional[str], Query(description="Filter by subset")] = None,
    metric: Annotated[Optional[str], Query(description="Filter by metric")] = None,
    evaluation_service: Annotated[EvaluationService, Depends(get_evaluation_service)] = None,
) -> EvaluationResponse:
    """Retrieve benchmark runs."""
    return await evaluation_service.list_evaluations(dataset=dataset, subset=subset, metric=metric)
