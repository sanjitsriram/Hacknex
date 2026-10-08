"""Domain models for structured document parsing runs, layout blocks, and reading order."""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from evidence_ocr.models.region import BoundingBox


class LayoutBlock(BaseModel):
    """Normalized layout element representing a paragraph, title, table, or visual structure."""

    block_id: str = Field(description="Unique block identifier within document/page, e.g. 'blk-p0-001'")
    page_index: int = Field(default=0, ge=0, description="0-indexed document page number")
    block_type: str = Field(
        description="Layout classification: paragraph_title, text, table, formula, chart, seal, figure, etc."
    )
    bounding_box: BoundingBox = Field(description="Normalized percentage bounding box [0.0, 100.0]")
    polygon: Optional[List[List[float]]] = Field(
        default=None, description="Raw detected polygon vertices in pixel or normalized space"
    )
    raw_bbox: Optional[List[float]] = Field(
        default=None, description="Original unnormalized pixel bounding box [min_x, min_y, max_x, max_y]"
    )
    content: str = Field(description="Extracted text or Markdown content for this layout block")
    reading_order: int = Field(default=1, ge=1, description="1-indexed reading order sequence on the page")
    confidence: Optional[float] = Field(
        default=None, ge=0.0, le=1.0, description="Optional detection confidence score from provider"
    )


class ParsedPage(BaseModel):
    """Complete parsed page containing layout blocks, dimensions, and page Markdown."""

    page_index: int = Field(ge=0, description="0-indexed document page number")
    width: int = Field(gt=0, description="Page width in pixels")
    height: int = Field(gt=0, description="Page height in pixels")
    markdown_text: str = Field(default="", description="Full page Markdown representation")
    blocks: List[LayoutBlock] = Field(default_factory=list, description="Ordered layout blocks on this page")
    reading_order_sequence: List[str] = Field(
        default_factory=list, description="Sequence of block_ids representing reading order"
    )
    tables_count: int = Field(default=0, ge=0, description="Number of detected tables on this page")


class DocumentParsingRun(BaseModel):
    """Persisted record of an official PaddleOCR-VL document intelligence execution."""

    id: str = Field(description="Run identifier, e.g. 'run-xxxxxxxx'")
    document_id: str = Field(description="Associated document ID")
    job_id: str = Field(description="Associated ProcessingJob ID")
    provider_id: str = Field(default="paddleocr-cloud", description="Provider identifier")
    model_version: str = Field(default="PaddleOCR-VL-1.6", description="Pinned model version tag")
    provider_job_id: Optional[str] = Field(default=None, description="External cloud job ID")
    input_sha256: Optional[str] = Field(default=None, description="SHA-256 hash of input document")
    page_count: int = Field(default=1, ge=1, description="Total processed document pages")
    markdown_text: str = Field(default="", description="Consolidated document Markdown across all pages")
    pages: List[ParsedPage] = Field(default_factory=list, description="Detailed parsed pages")
    total_blocks: int = Field(default=0, ge=0, description="Total extracted layout blocks across all pages")
    execution_time_ms: float = Field(default=0.0, ge=0.0, description="Provider inference and roundtrip latency in ms")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
