"""
app/middleware/request_logging.py

Attaches a unique request_id to every request and logs
structured request/response lines with timing information.

Every log line emitted during a request will automatically
include the request_id via structlog's contextvars.
"""

from __future__ import annotations

import time
import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)

# Routes excluded from access logging (too noisy)
_SILENT_PATHS = frozenset(["/health", "/metrics"])


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = str(uuid.uuid4())
        request.state.request_id = request_id

        # Bind request_id to structlog context — all log calls during
        # this request will automatically include it
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        start = time.perf_counter()

        if request.url.path not in _SILENT_PATHS:
            logger.info(
                "request_started",
                method=request.method,
                path=request.url.path,
                query=str(request.url.query) or None,
                client_ip=_get_client_ip(request),
            )

        response: Response | None = None
        try:
            response = await call_next(request)
        except Exception:
            # Let the error handler deal with it; just log timing
            duration_ms = round((time.perf_counter() - start) * 1000, 2)
            logger.error("request_failed", duration_ms=duration_ms)
            raise
        finally:
            structlog.contextvars.clear_contextvars()

        duration_ms = round((time.perf_counter() - start) * 1000, 2)

        # Attach request_id to response headers for client-side correlation
        response.headers["X-Request-Id"] = request_id

        if request.url.path not in _SILENT_PATHS:
            log_fn = logger.warning if (response and response.status_code >= 400) else logger.info
            log_fn(
                "request_completed",
                method=request.method,
                path=request.url.path,
                status_code=response.status_code if response else 0,
                duration_ms=duration_ms,
            )

        return response


def _get_client_ip(request: Request) -> str:
    """Extract real client IP, respecting X-Forwarded-For from reverse proxies."""
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
