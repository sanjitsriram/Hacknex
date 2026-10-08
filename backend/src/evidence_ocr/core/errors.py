"""Standardized error hierarchy and FastAPI exception handlers."""

from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from evidence_ocr.core.logging import get_logger, request_id_ctx

logger = get_logger("evidence_ocr.errors")


class EvidenceOCRError(Exception):
    """Base domain exception for all EvidenceOCR backend errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class EntityNotFoundError(EvidenceOCRError):
    """Raised when a requested resource does not exist."""

    def __init__(self, entity_name: str, entity_id: str) -> None:
        super().__init__(
            message=f"{entity_name} with id '{entity_id}' was not found.",
            code="NOT_FOUND",
            status_code=status.HTTP_404_NOT_FOUND,
            details={"entity_name": entity_name, "entity_id": entity_id},
        )


class EntityConflictError(EvidenceOCRError):
    """Raised when an entity conflict occurs (e.g. duplicate key or state collision)."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="CONFLICT",
            status_code=status.HTTP_409_CONFLICT,
            details=details,
        )


class PreconditionFailedError(EvidenceOCRError):
    """Raised when optimistic concurrency checks fail (e.g. revision mismatch)."""

    def __init__(self, message: str, expected_revision: int, actual_revision: int) -> None:
        super().__init__(
            message=message,
            code="PRECONDITION_FAILED",
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            details={"expected_revision": expected_revision, "actual_revision": actual_revision},
        )


class InvalidInputError(EvidenceOCRError):
    """Raised when business validation on input fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="VALIDATION_FAILED",
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            details=details,
        )


class InvalidStateTransitionError(EvidenceOCRError):
    """Raised when an invalid state transition is requested."""

    def __init__(self, message: str, current_state: str, requested_state: str) -> None:
        super().__init__(
            message=message,
            code="INVALID_STATE_TRANSITION",
            status_code=status.HTTP_400_BAD_REQUEST,
            details={"current_state": current_state, "requested_state": requested_state},
        )


class DatabaseUnavailableError(EvidenceOCRError):
    """Raised when the database connection or cluster is unreachable."""

    def __init__(self, message: str = "Database service is currently unreachable.") -> None:
        super().__init__(
            message=message,
            code="DATABASE_UNAVAILABLE",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )


class ProviderUnavailableError(EvidenceOCRError):
    """Raised when an external cloud provider (OCR/VLM/Storage) is unreachable."""

    def __init__(self, provider_name: str, message: str) -> None:
        super().__init__(
            message=f"External provider '{provider_name}' error: {message}",
            code="PROVIDER_UNAVAILABLE",
            status_code=status.HTTP_502_BAD_GATEWAY,
            details={"provider_name": provider_name},
        )


class StorageOperationError(EvidenceOCRError):
    """Raised when an object storage or GridFS operation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="STORAGE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class DatabaseOperationError(EvidenceOCRError):
    """Raised when an unexpected database persistence operation fails."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(
            message=message,
            code="DATABASE_ERROR",
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


def format_error_response(
    code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
) -> JSONResponse:
    """Format standard API error payload."""
    payload = {
        "error": {
            "code": code,
            "message": message,
            "status_code": status_code,
            "request_id": request_id or request_id_ctx.get(),
            "details": details or {},
        }
    }
    return JSONResponse(status_code=status_code, content=payload)


async def evidence_ocr_exception_handler(request: Request, exc: EvidenceOCRError) -> JSONResponse:
    """Handler for all domain exceptions."""
    logger.warning(
        "Domain error [%s]: %s (status=%d)",
        exc.code,
        exc.message,
        exc.status_code,
        extra={"details": exc.details},
    )
    return format_error_response(
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        details=exc.details,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handler for FastAPI request validation errors."""
    errors = exc.errors()
    details = {"validation_errors": errors}
    logger.info("Request validation failed on %s %s: %s", request.method, request.url.path, errors)
    return format_error_response(
        code="UNPROCESSABLE_ENTITY",
        message="Request validation failed. Verify payload fields and formats.",
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        details=details,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all handler for unhandled exceptions."""
    logger.exception("Unhandled server exception processing %s %s: %s", request.method, request.url.path, str(exc))
    return format_error_response(
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected server error occurred. Please contact system administrators.",
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
