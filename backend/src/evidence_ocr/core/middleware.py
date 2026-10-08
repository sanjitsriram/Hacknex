"""Application middlewares for request tracing, correlation IDs, and timing."""

import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from evidence_ocr.core.logging import get_logger, request_id_ctx

logger = get_logger("evidence_ocr.middleware")


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """Middleware to inject, track, and propagate X-Request-ID and timing across requests."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Extract or generate correlation ID
        req_id = request.headers.get("X-Request-ID")
        if not req_id or not req_id.strip():
            req_id = f"req-{uuid.uuid4().hex[:12]}"

        # Bind to context variable for the duration of this request
        token = request_id_ctx.set(req_id)
        start_time = time.perf_counter()

        try:
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000.0

            # Attach tracing headers to the response
            response.headers["X-Request-ID"] = req_id
            response.headers["X-Response-Time-Ms"] = f"{duration_ms:.2f}"

            # Log request lifecycle (skip verbose health check logging unless debug/failed)
            is_health = request.url.path.startswith("/api/v1/health")
            if not is_health or response.status_code >= 400:
                logger.info(
                    "%s %s -> %d in %.2fms",
                    request.method,
                    request.url.path,
                    response.status_code,
                    duration_ms,
                )
            return response
        finally:
            request_id_ctx.reset(token)
