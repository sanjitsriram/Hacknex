"""Domain models and database entities for ingested documents."""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class DocumentStatus(str, Enum):
    """Document lifecycle and review status, matching frontend contract."""

    NEEDS_REVIEW = "Needs review"
    REVIEWED = "Reviewed"
    READY_FOR_BACKEND = "Ready for backend"
    PROCESSING = "Processing"
    FAILED = "Failed"


class PageMetadata(BaseModel):
    """Metadata for a single document page."""

    page_index: int = Field(ge=0, description="0-indexed page number")
    width_px: int = Field(gt=0, description="Page width in pixels")
    height_px: int = Field(gt=0, description="Page height in pixels")
    dpi: Optional[int] = Field(default=300, description="DPI resolution if known")
    rotation_degrees: int = Field(default=0, description="Normalized page rotation (0, 90, 180, 270)")


class DocumentEntity(BaseModel):
    """Document persistence entity in MongoDB Atlas."""

    id: str = Field(description="Unique document identifier, e.g. doc-xxxxxxxx")
    name: str = Field(description="Display title of the document")
    kind: str = Field(default="Field notes", description="Document genre or domain classification")
    language: str = Field(default="English", description="Expected primary document language")
    pages: int = Field(default=1, ge=1, description="Total page count")
    status: DocumentStatus = Field(default=DocumentStatus.NEEDS_REVIEW)
    added: str = Field(description="Creation human timestamp or ISO date")
    size: str = Field(description="Formatted human-readable size or description")
    sample: bool = Field(default=False, description="Flag indicating sample/demo document fixture")
    file_key: Optional[str] = Field(default=None, description="Storage object key in document bucket")
    mime: Optional[str] = Field(default=None, description="MIME type of uploaded original")
    source_url: Optional[str] = Field(default=None, description="Presigned temporary access URL")
    revision: int = Field(default=1, ge=1, description="Monotonically increasing optimistic revision")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
    updated_at: str = Field(description="UTC ISO-8601 last update timestamp")
