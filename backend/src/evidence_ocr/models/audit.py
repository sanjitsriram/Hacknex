"""Domain models for audit logs, provenance layers, and correction events."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class AuditEvent(BaseModel):
    """Auditable review and correction action matching the frontend contract."""

    id: str = Field(description="Audit event identifier, e.g. evt-xxxxxxxx")
    document_id: str = Field(description="Target document ID")
    time: str = Field(description="UTC ISO-8601 timestamp")
    action: str = Field(description="Action name, e.g. 'Accepted alternative' or 'Manual edit'")
    detail: str = Field(description="Human readable change summary")
    reviewer: Optional[str] = Field(default="Sanjit", description="Reviewer identity")
    region_id: Optional[str] = Field(default=None, description="Affected region ID if applicable")
    previous_value: Optional[str] = Field(default=None, description="Previous value before modification")
    new_value: Optional[str] = Field(default=None, description="New value after modification")
    revision: int = Field(default=1, description="Document revision resulting from this event")


class ProvenanceRecord(BaseModel):
    """Immutable provenance record establishing the lineage of an OCR output."""

    source_type: str = Field(description="'RAW_OCR' | 'VLM_RECOVERY' | 'HUMAN_VERIFICATION'")
    provider_id: str = Field(description="Cloud model identifier or reviewer ID")
    model_version: Optional[str] = Field(default=None, description="Model version tag")
    request_hash: Optional[str] = Field(default=None, description="SHA-256 hash of input request/image")
    timestamp: str = Field(description="UTC ISO-8601 creation timestamp")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Execution parameters (temperature, etc.)")
