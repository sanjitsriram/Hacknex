"""Domain models for Phase 6 evidence fusion, alignment, disagreement detection, and recovery."""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class FusionStatus(str, Enum):
    """Lifecycle status of an evidence fusion job."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PROVIDER_UNAVAILABLE = "provider_unavailable"


class FusionRun(BaseModel):
    """Persisted record of an evidence fusion pipeline execution for a document."""
    id: str = Field(description="Unique fusion run identifier, e.g. frun-xxxxxxxx")
    document_id: str = Field(description="Associated document ID")
    strategy_version: str = Field(default="evidence-aware-v1")
    alignment_algorithm_version: str = Field(default="spatial-v1")
    status: FusionStatus = Field(default=FusionStatus.QUEUED)
    region_count: int = Field(default=0, ge=0)
    matched_count: int = Field(default=0, ge=0)
    disagreement_count: int = Field(default=0, ge=0)
    recovery_eligible_count: int = Field(default=0, ge=0)
    auto_proposable_count: int = Field(default=0, ge=0)
    requires_review_count: int = Field(default=0, ge=0)
    execution_time_ms: Optional[float] = Field(default=None, ge=0.0)
    error_message: Optional[str] = Field(default=None)
    created_by_session: str = Field(description="Anonymous session identifier for ownership scoping")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
    updated_at: str = Field(description="UTC ISO-8601 last update timestamp")


class MatchStatus(str, Enum):
    """Result of spatial alignment between an OCR region and a VL layout block."""
    MATCHED_ONE_TO_ONE = "matched_one_to_one"
    MATCHED_CONTAINMENT = "matched_containment"
    UNMATCHED_REGION = "unmatched_region"
    UNMATCHED_BLOCK = "unmatched_block"


class EvidenceAlignment(BaseModel):
    """Spatial alignment record linking an OCR region to a VL layout block."""
    id: str = Field(description="Unique alignment record ID")
    fusion_run_id: str
    document_id: str
    page_index: int = Field(default=0, ge=0)
    region_id: Optional[str] = Field(default=None)
    vl_block_id: Optional[str] = Field(default=None)
    match_status: MatchStatus
    iou_score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    cost_value: Optional[float] = Field(default=None, ge=0.0)
    match_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    weights_used: Dict[str, float] = Field(default_factory=lambda: {"w1": 0.5, "w2": 0.3, "w3": 0.1, "w4": 0.1})
    reading_order_region: Optional[int] = Field(default=None)
    reading_order_block: Optional[int] = Field(default=None)
    created_at: str


class AlignOpType(str, Enum):
    """Word-level alignment operation type."""
    MATCH = "MATCH"
    SUBSTITUTION = "SUBSTITUTION"
    INSERTION = "INSERTION"
    DELETION = "DELETION"


class AgreementLevel(str, Enum):
    """Multi-model agreement level at an alignment position."""
    FULL_AGREEMENT = "FULL_AGREEMENT"
    MINORITY_DISAGREEMENT = "MINORITY_DISAGREEMENT"
    FULL_DISAGREEMENT = "FULL_DISAGREEMENT"
    MISSING_TEXT = "MISSING_TEXT"
    EXTRA_TEXT = "EXTRA_TEXT"
    SINGLE_MODEL_ONLY = "SINGLE_MODEL_ONLY"


class HypothesisCandidate(BaseModel):
    """A single model text candidate for a region."""
    source_model: str
    model_version: str
    raw_text: str = Field(description="Exact raw model output - never modified")
    normalized_text: str = Field(description="Lowercase/whitespace-normalized text used only for alignment")
    raw_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    word_tokens: List[str] = Field(default_factory=list)


class AlignedPosition(BaseModel):
    """One word-position in the multi-model alignment lattice."""
    position: int
    agreement: AgreementLevel
    candidates_at_position: Dict[str, Optional[str]]
    conflict_chars: Optional[str] = Field(default=None)
    is_critical: bool = Field(default=False)


class AlignedHypotheses(BaseModel):
    """ROVER-inspired multi-model text alignment result for a single region."""
    region_id: str
    candidates: List[HypothesisCandidate] = Field(default_factory=list)
    positions: List[AlignedPosition] = Field(default_factory=list)
    pairwise_ops: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)
    overall_agreement: AgreementLevel = Field(default=AgreementLevel.SINGLE_MODEL_ONLY)


class DisagreementSeverity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class DisagreementType(str, Enum):
    MODEL_DISAGREEMENT = "MODEL_DISAGREEMENT"
    LOW_RAW_CONFIDENCE = "LOW_RAW_CONFIDENCE"
    MISSING_TEXT = "MISSING_TEXT"
    EXTRA_TEXT = "EXTRA_TEXT"
    GEOMETRY_MISMATCH = "GEOMETRY_MISMATCH"
    READING_ORDER_CONFLICT = "READING_ORDER_CONFLICT"
    NUMERIC_CONFLICT = "NUMERIC_CONFLICT"
    DATE_CONFLICT = "DATE_CONFLICT"
    UNIT_CONFLICT = "UNIT_CONFLICT"
    UNSUPPORTED_COMPLETION_SUSPECTED = "UNSUPPORTED_COMPLETION_SUSPECTED"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class DisagreementRecord(BaseModel):
    """Explainable disagreement record linked to an image region and contributing hypotheses."""
    id: str
    fusion_run_id: str
    document_id: str
    region_id: str
    page_index: int = Field(default=0, ge=0)
    disagreement_type: DisagreementType
    severity: DisagreementSeverity
    description: str
    candidate_a: Optional[Dict[str, Any]] = Field(default=None)
    candidate_b: Optional[Dict[str, Any]] = Field(default=None)
    candidate_c: Optional[Dict[str, Any]] = Field(default=None)
    conflicting_span: Optional[str] = Field(default=None)
    char_span_start: Optional[int] = Field(default=None)
    char_span_end: Optional[int] = Field(default=None)
    alignment_id: Optional[str] = Field(default=None)
    created_at: str


class RecoveryVariantType(str, Enum):
    ORIGINAL = "original"
    PADDED = "padded"
    CLAHE_GRAY = "clahe_gray"
    DESKEWED = "deskewed"


class RecoveryOutcome(str, Enum):
    IMPROVED = "improved"
    NEUTRAL = "neutral"
    REGRESSED = "regressed"
    TIMEOUT = "timeout"
    PROVIDER_UNAVAILABLE = "provider_unavailable"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DUPLICATE_VARIANT = "duplicate_variant"


class RecoveryAttempt(BaseModel):
    """Persisted record of one bounded re-inference attempt on an image variant."""
    id: str
    fusion_run_id: Optional[str] = Field(default=None)
    document_id: str
    region_id: str
    page_index: int = Field(default=0, ge=0)
    variant_type: RecoveryVariantType
    variant_hash: str = Field(description="SHA-256 hex of the variant image bytes for dedup")
    transform_params: Dict[str, Any] = Field(default_factory=dict)
    model_provider: str
    model_version: str
    recovered_text: Optional[str] = Field(default=None)
    recovered_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    execution_time_ms: float = Field(default=0.0, ge=0.0)
    outcome: RecoveryOutcome
    created_at: str


class FusionProposal(BaseModel):
    """Conservative evidence-linked transcription proposal for a region."""
    id: str
    fusion_run_id: str
    document_id: str
    region_id: str
    page_index: int = Field(default=0, ge=0)
    proposed_text: Optional[str] = Field(default=None)
    strategy_version: str = Field(default="evidence-aware-v1")
    auto_proposable: bool = Field(default=False)
    requires_review: bool = Field(default=True)
    disagreement_reasons: List[str] = Field(default_factory=list)
    candidates: List[Dict[str, Any]] = Field(default_factory=list)
    uncertainty_indicators: List[str] = Field(default_factory=list)
    recovery_attempt_ids: List[str] = Field(default_factory=list)
    is_human_verified: bool = Field(default=False)
    calibration_status: str = Field(default="UNCALIBRATED")
    source_evidence_reference: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str
