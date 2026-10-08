"""Shared API schemas for health, error responses, and pagination."""

from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """Health check payload for liveness and readiness probes."""

    status: str = Field(description="'alive', 'ready', or 'not_ready'")
    database: Optional[str] = Field(default=None, description="'connected' or 'disconnected'")
    timestamp: str = Field(description="UTC ISO-8601 evaluation timestamp")
    version: str = Field(default="0.1.0", description="Application service version")
    error: Optional[str] = Field(default=None, description="Diagnostic detail if not ready")


class APIError(BaseModel):
    """Standardized error structure."""

    code: str = Field(description="Machine-readable error classification code")
    message: str = Field(description="Human-readable explanation of the error")
    status_code: int = Field(description="Corresponding HTTP status code")
    request_id: Optional[str] = Field(default=None, description="Tracing correlation identifier")
    details: Dict[str, Any] = Field(default_factory=dict, description="Structured contextual diagnostics")


class ErrorResponse(BaseModel):
    """Envelope for all API error responses."""

    error: APIError


class PaginationParams(BaseModel):
    """Query parameters for cursor-based or offset pagination."""

    limit: int = Field(default=20, ge=1, le=100, description="Items per page")
    cursor: Optional[str] = Field(default=None, description="Opaque pagination cursor")
