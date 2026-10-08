"""API schemas for human review, region decisions, and transcript edits."""

from typing import List, Optional
from pydantic import BaseModel, Field


class RegionItemResponse(BaseModel):
    """Region item formatted matching frontend expectations."""

    id: str = Field(description="Region identifier, e.g. 'r1'")
    line: str = Field(description="Original line context")
    original: str = Field(description="Baseline recognized reading")
    alternatives: List[str] = Field(default_factory=list, description="Alternative suggestions")
    reason: str = Field(description="Human explanation for flagging")
    x: float = Field(description="Normalized left coordinate percentage [0-100]")
    y: float = Field(description="Normalized top coordinate percentage [0-100]")
    w: float = Field(description="Normalized width percentage [0-100]")
    h: float = Field(description="Normalized height percentage [0-100]")
    status: str = Field(default="pending", description="Region review status")
    decision: Optional[str] = Field(default=None, description="Human decision value")


class AuditEventResponse(BaseModel):
    """Audit log entry for review changes."""

    id: str = Field(description="Event identifier")
    time: str = Field(description="ISO-8601 timestamp")
    action: str = Field(description="Action name")
    detail: str = Field(description="Change summary")


class ReviewSessionResponse(BaseModel):
    """Complete review workspace payload for a document."""

    document_id: str = Field(description="Document ID")
    transcript: str = Field(description="Current full transcript text")
    regions: List[RegionItemResponse] = Field(description="Target review regions")
    revision: int = Field(description="Current document revision counter")
    reviewed: bool = Field(description="Whether all mandatory regions are resolved")
    events: List[AuditEventResponse] = Field(default_factory=list, description="Activity history")


class RegionUpdateRequest(BaseModel):
    """Update payload for confirming or editing a region decision."""

    decision: str = Field(max_length=500, description="Confirmed text for the region")
    is_illegible: bool = Field(default=False, description="Whether marked as illegible")
    expected_revision: int = Field(ge=1, description="Expected document revision for concurrency check")
    reviewer: Optional[str] = Field(default="Sanjit", description="Reviewer name")


class RegionUpdateResponse(BaseModel):
    """Response after updating a region."""

    region: RegionItemResponse = Field(description="Updated region item")
    revision: int = Field(description="New document revision counter")
    audit_event: AuditEventResponse = Field(description="Recorded audit event")


class TranscriptUpdateRequest(BaseModel):
    """Update payload for editing the full document transcript."""

    text: str = Field(description="Updated full transcript text")
    expected_revision: int = Field(ge=1, description="Expected document revision for concurrency check")
    reviewer: Optional[str] = Field(default="Sanjit", description="Reviewer name")


class TranscriptUpdateResponse(BaseModel):
    """Response after updating transcript text."""

    text: str = Field(description="Updated transcript text")
    revision: int = Field(description="New document revision counter")
    audit_event: AuditEventResponse = Field(description="Recorded audit event")


class CompleteReviewRequest(BaseModel):
    """Payload to finalize and mark review complete."""

    expected_revision: int = Field(ge=1, description="Expected document revision")
    reviewer: Optional[str] = Field(default="Sanjit", description="Reviewer name")


class CompleteReviewResponse(BaseModel):
    """Response after marking review complete."""

    document_id: str = Field(description="Document ID")
    status: str = Field(description="Updated document status, e.g. 'Reviewed'")
    revision: int = Field(description="New document revision")
