"""FastAPI application factory, lifespan management, middleware, and route mounting."""

from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from evidence_ocr.api.v1.router import api_v1_router
from evidence_ocr.core.config import Settings, get_settings
from evidence_ocr.core.errors import (
    EvidenceOCRError,
    evidence_ocr_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from evidence_ocr.core.logging import get_logger, setup_logging
from evidence_ocr.core.middleware import RequestCorrelationMiddleware
from evidence_ocr.core.security import SecurityHeadersMiddleware
from evidence_ocr.db.client import get_db_manager

logger = get_logger("evidence_ocr.main")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan context manager managing startup and graceful shutdown."""
    settings = getattr(app.state, "settings", get_settings())

    # Configure structured logging
    setup_logging(level=settings.log_level, log_format=settings.log_format)
    logger.info("Starting %s in %s mode...", settings.app_name, settings.environment)

    # Initialize PyMongo Async database manager
    db_manager = get_db_manager()
    await db_manager.connect(settings)

    yield

    # Clean shutdown
    logger.info("Shutting down %s...", settings.app_name)
    await db_manager.close()
    logger.info("Shutdown complete.")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    """Create and configure the FastAPI application instance."""
    cfg = settings or get_settings()

    app = FastAPI(
        title=cfg.app_name,
        description="Accuracy-first handwriting digitization platform backend foundation.",
        version="0.1.0",
        docs_url="/docs" if cfg.environment != "production" else None,
        redoc_url="/redoc" if cfg.environment != "production" else None,
        lifespan=lifespan,
    )

    # Store settings in application state
    app.state.settings = cfg

    # 1. Security Headers Middleware
    app.add_middleware(SecurityHeadersMiddleware)

    # 2. CORS Middleware configured from environment
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 3. Request Correlation and Tracing Middleware
    app.add_middleware(RequestCorrelationMiddleware)

    # 4. Standard Exception Handlers
    app.add_exception_handler(EvidenceOCRError, evidence_ocr_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # 5. Mount Versioned API Routes
    app.include_router(api_v1_router, prefix=cfg.api_v1_prefix)

    return app


# Default application instance for ASGI servers (Uvicorn)
app = create_app()
