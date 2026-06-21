"""
app/middleware/error_handler.py

Catches all unhandled exceptions and returns consistent JSON error shapes.
Every error response matches the ApiError contract from @reelroutes/shared:

  {
    "ok": false,
    "error": {
      "code": "NOT_FOUND",
      "message": "Trip not found",
      "request_id": "01J...",
      "fields": {}          # only on validation errors
    }
  }
"""

from __future__ import annotations

import traceback

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.logging import get_logger

logger = get_logger(__name__)

# ── Custom application exceptions ─────────────────────────────


class AppError(Exception):
    """Base class for all application-level errors."""

    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_ERROR",
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        fields: dict[str, list[str]] | None = None,
    ) -> None:
        self.message = message
        self.code = code
        self.status_code = status_code
        self.fields = fields
        super().__init__(message)


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: str | None = None) -> None:
        msg = f"{resource} not found"
        if identifier:
            msg = f"{resource} '{identifier}' not found"
        super().__init__(msg, code="NOT_FOUND", status_code=status.HTTP_404_NOT_FOUND)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(message, code="UNAUTHORIZED", status_code=status.HTTP_401_UNAUTHORIZED)


class ForbiddenError(AppError):
    def __init__(self, message: str = "You do not have permission to access this resource") -> None:
        super().__init__(message, code="FORBIDDEN", status_code=status.HTTP_403_FORBIDDEN)


class ConflictError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, code="CONFLICT", status_code=status.HTTP_409_CONFLICT)


class ValidationError(AppError):
    def __init__(self, message: str, fields: dict[str, list[str]] | None = None) -> None:
        super().__init__(
            message,
            code="VALIDATION_ERROR",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            fields=fields,
        )


# ── Response builder ──────────────────────────────────────────


def _error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    fields: dict[str, list[str]] | None = None,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    body: dict = {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
            "request_id": request_id,
        },
    }
    if fields:
        body["error"]["fields"] = fields
    return JSONResponse(status_code=status_code, content=body)


# ── Exception handlers (registered in main.py) ────────────────


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.warning(
        "app_error",
        code=exc.code,
        message=exc.message,
        status_code=exc.status_code,
        path=str(request.url),
    )
    return _error_response(request, exc.status_code, exc.code, exc.message, exc.fields)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    code_map = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        409: "CONFLICT",
        429: "RATE_LIMITED",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }
    code = code_map.get(exc.status_code, "HTTP_ERROR")
    message = str(exc.detail) if exc.detail else "An error occurred"

    logger.warning(
        "http_exception",
        code=code,
        status_code=exc.status_code,
        path=str(request.url),
    )
    return _error_response(request, exc.status_code, code, message)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Converts Pydantic v2 validation errors to field-level error map."""
    fields: dict[str, list[str]] = {}
    for error in exc.errors():
        loc = error.get("loc", ())
        # Skip the first element if it's "body"
        field_parts = [str(p) for p in loc if p != "body"]
        field = ".".join(field_parts) or "request"
        fields.setdefault(field, []).append(error.get("msg", "Invalid value"))

    logger.warning(
        "validation_error",
        fields=fields,
        path=str(request.url),
    )
    return _error_response(
        request,
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        "Request validation failed",
        fields,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler — logs full traceback, returns generic 500."""
    logger.error(
        "unhandled_exception",
        exc_type=type(exc).__name__,
        exc_message=str(exc),
        traceback=traceback.format_exc(),
        path=str(request.url),
    )
    return _error_response(
        request,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "INTERNAL_ERROR",
        "An unexpected error occurred. Our team has been notified.",
    )
