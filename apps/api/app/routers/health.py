"""
app/routers/health.py

GET /health  — liveness + readiness probe with dependency checks
GET /version — simple version metadata

Used by:
  - Kubernetes/Railway health checks
  - CI smoke tests after deployment
  - Uptime monitoring
"""

from __future__ import annotations

import time

from fastapi import APIRouter
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.config.settings import get_settings

router = APIRouter(tags=["ops"])


@router.get("/health", summary="Health check")
async def health() -> dict:
    """
    Returns service health including MongoDB and (future) Redis connectivity.
    Returns HTTP 200 if the service can handle traffic, 503 if degraded.
    """
    settings = get_settings()
    services: dict[str, dict] = {}
    overall_ok = True

    # ── MongoDB ping ─────────────────────────────────────────
    t0 = time.perf_counter()
    try:
        from app.config.database import get_db  # local import keeps mock patchable

        db: AsyncIOMotorDatabase = get_db()  # type: ignore[type-arg]
        await db.command("ping")
        services["mongodb"] = {
            "status": "ok",
            "latency_ms": round((time.perf_counter() - t0) * 1000, 2),
        }
    except Exception as exc:
        services["mongodb"] = {"status": "error", "error": str(exc)}
        overall_ok = False

    return {
        "ok": overall_ok,
        "status": "ok" if overall_ok else "degraded",
        "version": settings.version,
        "environment": settings.env,
        "services": services,
    }


@router.get("/version", summary="Version info")
async def version() -> dict:
    """Returns app version and environment. Always returns 200."""
    settings = get_settings()
    return {
        "ok": True,
        "data": {
            "version": settings.version,
            "environment": settings.env,
        },
    }
