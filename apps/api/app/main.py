"""
app/main.py

FastAPI application factory for ReelRecipes.
All middleware, routers, and exception handlers are registered here.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.database import connect_db, disconnect_db
from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.middleware import (
    AppError,
    RequestLoggingMiddleware,
    app_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.routers import health_router

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    settings = get_settings()
    configure_logging()

    from app.config.sentry import init_sentry
    init_sentry()

    logger.info("app_starting", version=settings.version, env=settings.env)
    await connect_db()
    logger.info("app_ready", host=settings.api_host, port=settings.api_port)

    yield

    logger.info("app_shutting_down")
    await disconnect_db()
    logger.info("app_stopped")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="ReelRecipes API",
        description="AI-powered cooking video to structured recipe extractor",
        version=settings.version,
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        openapi_url="/openapi.json" if settings.debug else None,
        lifespan=lifespan,
    )

    # ── Middleware ────────────────────────────────────────────
    app.add_middleware(RequestLoggingMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-Id"],
    )

    # ── Exception handlers ────────────────────────────────────
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)

    # ── Routers ───────────────────────────────────────────────
    app.include_router(health_router)

    # Jobs (video import + WebSocket progress)
    from app.routers.jobs import router as jobs_router
    from app.routers.jobs import ws_router
    from app.routers.import_video import router as import_router

    app.include_router(import_router)
    app.include_router(jobs_router)
    app.include_router(ws_router)

    # Recipes CRUD
    from app.routers.recipes import router as recipes_router
    app.include_router(recipes_router)

    # Pantry CRUD + match
    from app.routers.pantry import router as pantry_router
    app.include_router(pantry_router)

    # AI endpoints (suggest, chat, substitute)
    from app.routers.ai import router as ai_router
    app.include_router(ai_router)

    # Users / profile
    from app.routers.users import clerk_router, router as users_router
    app.include_router(users_router)
    app.include_router(clerk_router)

    # Meal planner
    from app.routers.meal_plan import router as meal_plan_router
    app.include_router(meal_plan_router)

    # Community explore feed
    from app.routers.explore import router as explore_router
    app.include_router(explore_router)

    # Recipe collections
    from app.routers.collections import router as collections_router
    app.include_router(collections_router)

    # P4: export, stats, cost, collaboration
    from app.routers.export import router as export_router
    from app.routers.collab import router as collab_router
    app.include_router(export_router)
    app.include_router(collab_router)

    return app


app = create_app()
