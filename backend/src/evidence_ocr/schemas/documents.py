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
    source_url: Optional[str] = Field(default=None, description="Direct or presigned URL to stored original")
    status: DocumentStatus = Field(description="Initial document lifecycle status")
    revision: int = Field(default=1, description="Initial revision counter")


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


class DocumentListResponse(BaseModel):
    """Paginated list of documents."""

    items: List[DocumentItemResponse] = Field(description="List of document summaries")
    next_cursor: Optional[str] = Field(default=None, description="Cursor for the next page")
    total: int = Field(ge=0, description="Total documents matching query")
