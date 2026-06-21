"""
app/config/logging.py

Configures structlog for structured JSON logging in production
and pretty console logging in local/test environments.
All log lines include request_id, env, and version automatically.
"""

from __future__ import annotations

import logging
import sys

import structlog

from app.config.settings import get_settings


def configure_logging() -> None:
    settings = get_settings()

    shared_processors: list[structlog.types.Processor] = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        # Add app metadata to every log line
        _add_app_context,
    ]

    if settings.debug:
        # Pretty coloured output for local dev
        renderer: structlog.types.Processor = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # Machine-readable JSON for staging / production
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=[
            *shared_processors,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            logging.DEBUG if settings.debug else logging.INFO
        ),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            *shared_processors,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.DEBUG if settings.debug else logging.INFO)

    # Silence noisy third-party loggers
    for noisy in ("uvicorn.access", "motor", "pymongo"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def _add_app_context(
    logger: logging.Logger,  # noqa: ARG001 — required by structlog processor signature
    method_name: str,  # noqa: ARG001 — required by structlog processor signature
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    settings = get_settings()
    event_dict["env"] = settings.env
    event_dict["version"] = settings.version
    return event_dict


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
