"""Pydantic API schemas for Phase 6 evidence fusion endpoints."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class CreateFusionRunRequest(BaseModel):
    """Request body for POST /documents/{id}/fusion-runs."""
    strategy: Optional[str] = Field(
        default="evidence_aware",
        description="Fusion strategy: best_individual | unweighted_rover | evidence_aware | evidence_aware_with_recovery",
    )
    idempotency_key: Optional[str] = Field(
        default=None,
        description="Client-provided idempotency key to prevent duplicate runs",
    )


class FusionRunSummaryResponse(BaseModel):
    """Summarised FusionRun for list responses."""
    fusion_run_id: str
    document_id: str
    status: str
    strategy_version: str
    region_count: int
    matched_count: int
    disagreement_count: int
    auto_proposable_count: int
    requires_review_count: int
    recovery_eligible_count: int
    execution_time_ms: Optional[float]
    error_message: Optional[str]
    created_at: str
    updated_at: str


class CreateFusionRunResponse(BaseModel):
    """202 response for POST /documents/{id}/fusion-runs."""
    fusion_run_id: str
    document_id: str
    status: str
    message: str = "Fusion run queued"


class FusionRunDetailResponse(FusionRunSummaryResponse):
    """Full FusionRun detail with embedded proposals."""
    proposals: List[Dict[str, Any]] = Field(default_factory=list)
    alignment_algorithm_version: str = "spatial-v1"


class DisagreementResponse(BaseModel):
    """Single disagreement record for API responses."""
    id: str
    fusion_run_id: str
    document_id: str
    region_id: str
    page_index: int
    disagreement_type: str
    severity: str
    description: str
    candidate_a: Optional[Dict[str, Any]]
    candidate_b: Optional[Dict[str, Any]]
    candidate_c: Optional[Dict[str, Any]]
    conflicting_span: Optional[str]
    alignment_id: Optional[str]
    created_at: str


class DisagreementListResponse(BaseModel):
    """List of disagreement records."""
    document_id: str
    total: int
    disagreements: List[DisagreementResponse]


class CreateRecoveryRequest(BaseModel):
    """Request body for POST /documents/{id}/regions/{rid}/recover."""
    fusion_run_id: str = Field(description="Parent fusion run ID to link recovery attempt")
    idempotency_key: Optional[str] = Field(default=None)


class CreateRecoveryResponse(BaseModel):
    """Response for a completed bounded recovery request."""
    recovery_attempt_id: str
    region_id: str
    status: str = "queued"
    message: str = "Recovery attempt queued"


class RecoveryAttemptResponse(BaseModel):
    """Single recovery attempt detail."""
    id: str
    region_id: str
    variant_type: str
    variant_hash: str
    model_provider: str
    model_version: str
    recovered_text: Optional[str]
    recovered_confidence: Optional[float]
    execution_time_ms: float
    outcome: str
    created_at: str


class RegionEvidenceResponse(BaseModel):
    """Complete evidence view for a region."""
    region_id: str
    document_id: str
    fusion_proposal: Optional[Dict[str, Any]]
    disagreements: List[Dict[str, Any]]
    recovery_attempts: List[Dict[str, Any]]
    alignments: List[Dict[str, Any]]
