"""Security utilities, headers middleware, and future authorization boundaries."""

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds standard security headers to all HTTP responses."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        return response


class AuthContextStub:
    """Boundary interface placeholder for future token-based authentication context.
    
    Per Phase 1 architectural invariants, authentication infrastructure is not prematurely
    implemented, but clear boundaries and interfaces are preserved.
    """

    def __init__(self, user_id: str = "anonymous", is_authenticated: bool = False):
        self.user_id = user_id
        self.is_authenticated = is_authenticated
