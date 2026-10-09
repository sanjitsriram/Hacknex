"""Pydantic schemas for Document Intelligence API requests and responses."""

from typing import List, Optional
from pydantic import BaseModel, Field
from evidence_ocr.models.region import BoundingBox


class DocumentIntelligenceRequest(BaseModel):
    """Request payload for dispatching PaddleOCR-VL document intelligence."""

    pipeline_version: str = Field(default="v1.0.0", description="Reproducible pipeline version tag")
    idempotency_key: Optional[str] = Field(default=None, description="Client idempotency key")
    force: bool = Field(default=False, description="Force cancel active or stuck job and restart")


class LayoutBlockResponse(BaseModel):
    """Layout block with bounding box, category, reading order, and extracted content."""

    block_id: str = Field(description="Block identifier, e.g. 'blk-p0-001'")
    page_index: int = Field(description="0-indexed document page number")
    block_type: str = Field(description="Layout classification (paragraph_title, text, table, etc.)")
    bounding_box: BoundingBox = Field(description="Normalized percentage coordinates [0.0, 100.0]")
    polygon: Optional[List[List[float]]] = Field(default=None, description="Polygon vertices if available")
    raw_bbox: Optional[List[float]] = Field(default=None, description="Original pixel bounding box")
    content: str = Field(description="Extracted text or Markdown content")
    reading_order: int = Field(description="Reading order index on page")
    confidence: Optional[float] = Field(default=None, description="Model detection confidence")


class ParsedPageResponse(BaseModel):
    """Parsed page summary with ordered layout blocks and Markdown."""

    page_index: int = Field(description="0-indexed page index")
    width: int = Field(description="Page width in pixels")
    height: int = Field(description="Page height in pixels")
    markdown_text: str = Field(description="Page Markdown content")
    blocks: List[LayoutBlockResponse] = Field(default_factory=list, description="Ordered layout blocks")
    reading_order_sequence: List[str] = Field(default_factory=list, description="Sequence of block IDs in reading order")
    tables_count: int = Field(default=0, description="Number of detected tables on this page")


class DocumentParsingRunResponse(BaseModel):
    """Full response for a PaddleOCR-VL document intelligence execution run."""

    id: str = Field(description="Parsing run ID")
    document_id: str = Field(description="Target document ID")
    job_id: str = Field(description="Associated job ID")
    provider_id: str = Field(description="Provider name ('paddleocr-cloud')")
    model_version: str = Field(description="Model version ('PaddleOCR-VL-1.6')")
    provider_job_id: Optional[str] = Field(default=None, description="Cloud provider job ID")
    input_sha256: Optional[str] = Field(default=None, description="SHA-256 of document")
    page_count: int = Field(description="Total pages processed")
    markdown_text: str = Field(description="Consolidated document Markdown")
    pages: List[ParsedPageResponse] = Field(default_factory=list, description="Parsed pages")
    total_blocks: int = Field(description="Total layout blocks extracted")
    execution_time_ms: float = Field(description="Provider latency in milliseconds")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
