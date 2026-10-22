"""
Phase 0.7 — HTTP Security Headers + Request trace_id middleware.
Every response gets security headers. Every request gets a trace_id injected.
"""
import time
import uuid
import logging
import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp
from utils.observability import event_log
from utils.request_context import clear_trace_id, set_trace_id

logger = logging.getLogger(__name__)
_QUIET_PATHS = {"/health", "/ready", "/metrics", "/api/v1/outreach/health"}

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
        set_trace_id(trace_id)

        # Bind to structlog context for this request
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        start_time = time.perf_counter()
        path = request.url.path
        method = request.method
        try:
            response = await call_next(request)
            response.headers[self._header_name] = trace_id
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            status_code = response.status_code
            if path not in _QUIET_PATHS or status_code >= 400:
                level = "error" if status_code >= 500 else ("warning" if status_code >= 400 else "info")
                event_log(
                    logger,
                    level,
                    "http.request.completed",
                    trace_id=trace_id,
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
            return response
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            event_log(
                logger,
                "error",
                "http.request.failed",
                trace_id=trace_id,
                method=method,
                path=path,
                duration_ms=duration_ms,
                error_type=type(exc).__name__,
            )
            raise
        finally:
            structlog.contextvars.clear_contextvars()
            clear_trace_id()
