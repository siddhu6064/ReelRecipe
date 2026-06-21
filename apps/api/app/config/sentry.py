"""
app/config/sentry.py

Sentry error monitoring setup for FastAPI and the ARQ worker.

Initialise once at startup — Sentry automatically captures:
  - Unhandled exceptions in FastAPI routes
  - Slow DB queries (if performance monitoring is enabled)
  - ARQ task failures when init_sentry() is called in the worker

Usage:
  from app.config.sentry import init_sentry
  init_sentry()   # called in main.py lifespan and job_worker.py startup

Environment variables:
  SENTRY_DSN          — required to enable Sentry (skip if empty)
  SENTRY_ENVIRONMENT  — "development" | "staging" | "production"
  SENTRY_TRACES_RATE  — float 0.0–1.0, sample rate for performance traces
"""

from __future__ import annotations

from app.config.logging import get_logger

logger = get_logger(__name__)


def init_sentry() -> None:
    """
    Initialise the Sentry SDK.
    Safe to call multiple times — Sentry's own guard prevents re-init.
    No-ops silently if SENTRY_DSN is not set.
    """
    from app.config.settings import get_settings

    settings = get_settings()

    if not settings.sentry_dsn:
        logger.info("sentry_disabled_no_dsn")
        return

    import sentry_sdk
    from sentry_sdk.integrations.asyncio import AsyncioIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration
    from sentry_sdk.integrations.starlette import StarletteIntegration

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.sentry_environment,
        traces_sample_rate=settings.sentry_traces_rate,
        integrations=[
            StarletteIntegration(transaction_style="endpoint"),
            FastApiIntegration(transaction_style="endpoint"),
            AsyncioIntegration(),
        ],
        # Scrub sensitive fields from payloads
        send_default_pii=False,
        # Ignore routine 4xx errors — only capture real bugs
        ignore_errors=[
            # These are user errors, not bugs
        ],
        before_send=_before_send,
    )

    logger.info(
        "sentry_initialised",
        environment=settings.sentry_environment,
        traces_rate=settings.sentry_traces_rate,
    )


def _before_send(event: dict, hint: dict) -> dict | None:
    """
    Filter out expected errors before sending to Sentry.
    Returns None to drop the event, or the event to send it.
    """
    # Don't send 404 / 403 / 422 errors — these are user errors not bugs
    if "exc_info" in hint:
        exc_type, exc_value, _ = hint["exc_info"]
        from app.middleware.error_handler import AppError

        if isinstance(exc_value, AppError):  # noqa: SIM102
            if exc_value.status_code in (400, 401, 403, 404, 422, 429):
                return None

    return event


def capture_exception(exc: Exception, context: dict | None = None) -> None:
    """Manually capture an exception with optional extra context."""
    try:
        import sentry_sdk

        with sentry_sdk.push_scope() as scope:
            if context:
                for k, v in context.items():
                    scope.set_extra(k, v)
            sentry_sdk.capture_exception(exc)
    except Exception:
        pass  # Never let Sentry crash the application


def set_user_context(clerk_id: str | None) -> None:
    """Attach the current user's Clerk ID to Sentry events."""
    try:
        import sentry_sdk

        if clerk_id:
            sentry_sdk.set_user({"id": clerk_id})
    except Exception:
        pass
