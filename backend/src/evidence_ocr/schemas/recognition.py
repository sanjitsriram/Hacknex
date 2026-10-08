"""Schemas for TrOCR and region recognition API contracts."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from evidence_ocr.models.region import BoundingBox, CandidateSuggestion


class RegionRecognitionRequest(BaseModel):
    """Request payload for on-demand region handwriting recognition."""

    bounding_box: Optional[BoundingBox] = Field(
        default=None,
        description="Optional custom bounding box coordinates in [0.0, 100.0] percentage space",
    )
    page_index: int = Field(default=0, ge=0, description="Document page index (0-indexed)")


class RegionRecognitionResponse(BaseModel):
    """Response payload returning real recognized text and model provenance."""

    document_id: str = Field(description="Document identifier")
    region_id: str = Field(description="Region identifier")
    recognized_text: str = Field(description="Real TrOCR recognized text")
    confidence: float = Field(ge=0.0, le=1.0, description="Genuine model confidence score derived from softmax")
    execution_time_ms: float = Field(ge=0.0, description="Provider inference execution latency in milliseconds")
    model_identifier: str = Field(description="Underlying model identifier, e.g. microsoft/trocr-base-handwritten")
    model_version: str = Field(description="Model snapshot or version tag")
    bounding_box: BoundingBox = Field(description="Normalized coordinates used for recognition crop")
    candidate: CandidateSuggestion = Field(description="Structured candidate suggestion entity")
    is_verified: bool = Field(default=False, description="Verification flag (always False for automated models)")


class DocumentRegionDetail(BaseModel):
    """Detailed detected region with coordinates, original polygon, and model candidates."""

    id: str = Field(description="Region identifier")
    document_id: str = Field(description="Document ID")
    page_index: int = Field(default=0, description="Page index (0-indexed)")
    line: str = Field(description="Recognized line context")
    original: str = Field(description="Primary recognized text")
    bounding_box: BoundingBox = Field(description="Normalized coordinates in [0.0, 100.0] space")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="Original unrotated detected polygon vertices in image pixels"
    )
    confidence: Optional[float] = Field(default=None, description="Model recognition score")
    provider_id: Optional[str] = Field(default=None, description="Originating provider ID")
    model_version: Optional[str] = Field(default=None, description="Model version")
    candidates_detail: List[CandidateSuggestion] = Field(
        default_factory=list, description="Independent candidate suggestions preserving provenance"
    )
    status: str = Field(default="pending", description="Human review status")
    reviewer_decision: Optional[str] = Field(default=None, description="Human decision if reviewed")
    is_illegible: bool = Field(default=False, description="Illegible marker flag")


class DocumentRegionsListResponse(BaseModel):
    """List response of all detected regions for a document."""

    document_id: str = Field(description="Target document ID")
    total: int = Field(description="Total detected region count")
    items: List[DocumentRegionDetail] = Field(description="List of detected regions")
