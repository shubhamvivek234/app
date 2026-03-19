"""
Phase 0.7 — HTTP Security Headers + Request trace_id middleware.
Every response gets security headers. Every request gets a trace_id injected.
"""
import uuid
import logging
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

_SECURITY_HEADERS = {
    "Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains; preload",
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects HSTS, CSP, and other security headers on every response."""

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        for header, value in _SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


class TraceIDMiddleware(BaseHTTPMiddleware):
    """
    Generates a UUID trace_id per request. Binds it to structlog context
    so all log lines within that request include trace_id automatically.
    Returns X-Trace-ID in response for client-side correlation.
    """

    def __init__(self, app: ASGIApp, header_name: str = "X-Trace-ID") -> None:
        super().__init__(app)
        self._header_name = header_name

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        trace_id = request.headers.get(self._header_name) or str(uuid.uuid4())
        request.state.trace_id = trace_id

        # Bind to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)

        response = await call_next(request)
        response.headers[self._header_name] = trace_id
        return response
