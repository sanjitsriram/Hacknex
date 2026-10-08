"""Domain models for regions, normalized bounding boxes, and candidate provenance."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field, model_validator


class BoundingBox(BaseModel):
    """Normalized bounding box coordinates relative to the original unrotated document page.
    
    Coordinates are normalized percentage values [0.0, 100.0] matching frontend conventions.
    """

    x: float = Field(ge=0.0, le=100.0, description="Left coordinate percentage")
    y: float = Field(ge=0.0, le=100.0, description="Top coordinate percentage")
    w: float = Field(gt=0.0, le=100.0, description="Width percentage")
    h: float = Field(gt=0.0, le=100.0, description="Height percentage")

    @model_validator(mode="after")
    def validate_bounds(self) -> "BoundingBox":
        if self.x + self.w > 100.001:
            raise ValueError(f"Bounding box exceeds page width: x ({self.x}) + w ({self.w}) > 100")
        if self.y + self.h > 100.001:
            raise ValueError(f"Bounding box exceeds page height: y ({self.y}) + h ({self.h}) > 100")
        return self


class CandidateSuggestion(BaseModel):
    """An OCR or VLM candidate proposal with explicit model provenance."""

    text: str = Field(description="Proposed text string")
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Raw provider confidence")
    calibrated_score: Optional[float] = Field(default=None, ge=0.0, le=1.0, description="Calibrated confidence")
    provider_id: str = Field(description="Cloud model identifier, e.g. 'google-vision-v1' or 'mock-ocr'")
    model_version: str = Field(description="Pinned model version tag")


class RegionReviewStatus(str, Enum):
    """Status of human verification on this region."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    ILLEGIBLE = "illegible"


class RegionEntity(BaseModel):
    """Region entity representing an identified line or word segment with candidates."""

    id: str = Field(description="Region identifier, e.g. 'r1'")
    document_id: str = Field(description="Associated document ID")
    page_index: int = Field(default=0, ge=0, description="Page index (0-indexed)")
    line: str = Field(description="Full line context string")
    original: str = Field(description="Primary OCR baseline reading")
    alternatives: List[str] = Field(default_factory=list, description="Alternative candidate readings")
    candidates_detail: List[CandidateSuggestion] = Field(
        default_factory=list, description="Detailed candidate provenance with model versions"
    )
    reason: str = Field(description="Human-readable reason for review flag")
    reason_codes: List[str] = Field(
        default_factory=list,
        description="Structured reason codes, e.g. ['MODEL_DISAGREEMENT', 'LOW_CONFIDENCE']",
    )
    bounding_box: BoundingBox = Field(description="Normalized bounding box coordinates")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="Raw detected polygon vertices [[x1, y1], [x2, y2], ...] in pixel space"
    )
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Raw model recognition score"
    )
    provider_id: Optional[str] = Field(
        default=None, description="Provider identifier (e.g. 'paddleocr-cloud')"
    )
    model_version: Optional[str] = Field(
        default=None, description="Model identifier / version (e.g. 'PP-OCRv6')"
    )
    provider_job_id: Optional[str] = Field(
        default=None, description="External provider asynchronous job identifier"
    )
    source_sha256: Optional[str] = Field(
        default=None, description="SHA-256 hash of the input document"
    )
    status: RegionReviewStatus = Field(default=RegionReviewStatus.PENDING)
    reviewer_decision: Optional[str] = Field(default=None, description="Human confirmed or edited text")
    is_illegible: bool = Field(default=False, description="Flag indicating region marked illegible")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
    updated_at: str = Field(description="UTC ISO-8601 last update timestamp")
