"""API schemas for document ingestion and listing."""

from typing import List, Optional
from pydantic import BaseModel, Field
from evidence_ocr.models.document import DocumentStatus


class DocumentCreateRequest(BaseModel):
    """Metadata provided during document ingestion."""

    title: str = Field(min_length=1, max_length=200, description="User-assigned document title")
    kind: str = Field(default="Field notes", description="Document type or category")
    expected_language: str = Field(default="English", description="Expected primary language")


class DocumentUploadResponse(BaseModel):
    """Response returned upon successful document upload."""

    document_id: str = Field(description="Generated unique document identifier")
    name: str = Field(default="Untitled document", description="Document title")
    original_filename: Optional[str] = Field(default=None, description="Original filename")
    content_type: Optional[str] = Field(default=None, description="Verified MIME type")
    file_size_bytes: Optional[int] = Field(default=None, description="Exact file size in bytes")
    sha256: Optional[str] = Field(default=None, description="SHA-256 digest")
    gridfs_file_id: Optional[str] = Field(default=None, description="GridFS file identifier string")
    page_count: Optional[int] = Field(default=1, description="Verified page count")
    source_url: Optional[str] = Field(default=None, description="Relative access URL to stored original")
    status: DocumentStatus = Field(description="Initial document lifecycle status")
    revision: int = Field(default=1, description="Initial revision counter")
    created_at: Optional[str] = Field(default=None, description="ISO creation timestamp")


class DocumentItemResponse(BaseModel):
    """Document representation matching frontend DocumentItem contract."""

    id: str = Field(description="Document ID")
    name: str = Field(description="Document display name / title")
    kind: str = Field(description="Document category")
    language: str = Field(description="Language tag")
    pages: int = Field(description="Total pages")
    status: str = Field(description="Review status string")
    added: str = Field(description="Formatted added date or string")
    size: str = Field(description="Formatted file size")
    sample: bool = Field(description="Whether document is a sample fixture")
    url: Optional[str] = Field(default=None, description="Source URL")
    mime: Optional[str] = Field(default=None, description="MIME type")
    revision: int = Field(default=1, description="Document revision version")
    sha256: Optional[str] = Field(default=None, description="SHA-256 digest")
    gridfs_file_id: Optional[str] = Field(default=None, description="GridFS file identifier string")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes")


class DocumentDetailResponse(BaseModel):
    """Full detail schema for single document inspection."""

    id: str = Field(description="Document ID")
    document_id: str = Field(description="Document ID alias")
    name: str = Field(description="Document title")
    original_filename: Optional[str] = Field(default=None, description="Original filename")
    content_type: Optional[str] = Field(default=None, description="MIME type")
    file_size_bytes: Optional[int] = Field(default=None, description="File size in bytes")
    sha256: Optional[str] = Field(default=None, description="SHA-256 digest")
    gridfs_file_id: Optional[str] = Field(default=None, description="GridFS file ID")
    page_count: int = Field(default=1, description="Total verified page count")
    pages: int = Field(default=1, description="Page count")
    kind: str = Field(default="Field notes")
    language: str = Field(default="English")
    status: str = Field(description="Status string")
    processing_status: str = Field(description="Lifecycle status string")
    sample: bool = Field(default=False)
    source_url: Optional[str] = Field(default=None)
    revision: int = Field(default=1)
    schema_version: int = Field(default=1)
    created_at: str
    updated_at: str


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: List[DocumentItemResponse] = Field(description="List of document summaries")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for the next page")
    total: int = Field(ge=0, description="Total documents matching query")
