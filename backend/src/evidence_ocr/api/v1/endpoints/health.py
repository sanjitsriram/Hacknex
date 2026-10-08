"""Health check endpoints for liveness and readiness probes."""

from datetime import datetime, timezone
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from evidence_ocr.core.errors import DatabaseUnavailableError
from evidence_ocr.db.client import get_db_manager
from evidence_ocr.schemas.common import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Liveness probe",
    description="Returns 200 if the FastAPI application process is alive and responsive.",
)
async def check_liveness() -> HealthResponse:
    """Liveness probe verifying that the application is running."""
    now = datetime.now(timezone.utc).isoformat()
    return HealthResponse(
        status="alive",
        database=None,
        timestamp=now,
        version="0.1.0",
    )


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={
        status.HTTP_200_OK: {"description": "All system dependencies are connected and ready"},
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "Dependencies are unreachable"},
    },
    summary="Readiness probe",
    description="Accurately tests MongoDB Atlas cluster availability. Returns 503 if database is disconnected.",
)
async def check_readiness():
    """Readiness probe checking MongoDB Atlas database ping."""
    now = datetime.now(timezone.utc).isoformat()
    db_mgr = get_db_manager()

    try:
        await db_mgr.ping()
        payload = HealthResponse(
            status="ready",
            database="connected",
            timestamp=now,
            version="0.1.0",
        )
        return payload
    except DatabaseUnavailableError as exc:
        payload = HealthResponse(
            status="not_ready",
            database="disconnected",
            timestamp=now,
            version="0.1.0",
            error=str(exc.message),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )
    except Exception as exc:
        payload = HealthResponse(
            status="not_ready",
            database="disconnected",
            timestamp=now,
            version="0.1.0",
            error=str(exc),
        )
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=payload.model_dump(),
        )
