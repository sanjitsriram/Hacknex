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
    document_id: Optional[str] = Field(default=None, description="Document identifier alias")
    name: str = Field(description="Display title of the document")
    original_filename: Optional[str] = Field(default=None, description="Original filename of the uploaded document")
    content_type: Optional[str] = Field(default=None, description="MIME type of uploaded original")
    file_size_bytes: Optional[int] = Field(default=None, description="Exact file size in bytes")
    sha256: Optional[str] = Field(default=None, description="Cryptographic SHA-256 hex digest of file")
    gridfs_file_id: Optional[str] = Field(default=None, description="GridFS file identifier string")
    page_count: Optional[int] = Field(default=None, description="Total verified page count")
    pages: int = Field(default=1, ge=1, description="Total page count (frontend compatible)")
    kind: str = Field(default="Field notes", description="Document genre or domain classification")
    language: str = Field(default="English", description="Expected primary document language")
    status: DocumentStatus = Field(default=DocumentStatus.READY_FOR_BACKEND)
    processing_status: Optional[str] = Field(default=None, description="Lifecycle status string")
    schema_version: int = Field(default=1, description="Document entity schema version")
    added: str = Field(description="Creation human timestamp or ISO date")
    size: str = Field(description="Formatted human-readable size or description")
    sample: bool = Field(default=False, description="Flag indicating sample/demo document fixture")
    file_key: Optional[str] = Field(default=None, description="Storage object key in document bucket")
    mime: Optional[str] = Field(default=None, description="MIME type of uploaded original")
    source_url: Optional[str] = Field(default=None, description="Presigned or relative access URL")
    revision: int = Field(default=1, ge=1, description="Monotonically increasing optimistic revision")
    upload_timestamp: Optional[str] = Field(default=None, description="UTC ISO-8601 upload timestamp")
    created_at: str = Field(description="UTC ISO-8601 creation timestamp")
    updated_at: str = Field(description="UTC ISO-8601 last update timestamp")

    def model_post_init(self, __context: object) -> None:
        if not self.document_id:
            self.document_id = self.id
        if self.page_count is None:
            self.page_count = self.pages
        elif self.pages != self.page_count:
            self.pages = self.page_count
        if not self.content_type:
            self.content_type = self.mime
        elif not self.mime:
            self.mime = self.content_type
        if not self.processing_status:
            self.processing_status = self.status.value
        if not self.upload_timestamp:
            self.upload_timestamp = self.created_at
