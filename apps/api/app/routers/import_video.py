"""
app/routers/import_video.py

POST /api/jobs/import — accepts a cooking video URL, detects platform,
creates a Job, enqueues the ARQ extract_recipe_job task, returns job_id.

Client then polls GET /api/jobs/:id or connects to WS /ws/jobs/:id.
"""

from __future__ import annotations

import re

from fastapi import APIRouter, Request

from app.auth.clerk import optional_auth as get_optional_user
from app.middleware.rate_limit import check_rate_limit
from app.models.documents import Platform
from app.routers.schemas import ImportRequest
from app.services.job_service import JobService



async def _enqueue_job(job_id: str, request) -> None:  # type: ignore[no-untyped-def]
    """Enqueue extract_recipe_job. Extracted for easy mocking in tests."""
    from arq import create_pool
    from arq.connections import RedisSettings
    from app.config.settings import get_settings

    settings = get_settings()
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    await redis.enqueue_job("extract_recipe_job", job_id)
    await redis.aclose()


router = APIRouter(prefix="/api/jobs", tags=["import"])

PLATFORM_PATTERNS: list[tuple[re.Pattern, Platform]] = [
    (re.compile(r"(youtube\.com|youtu\.be)"), Platform.YOUTUBE),
    (re.compile(r"instagram\.com"), Platform.INSTAGRAM),
    (re.compile(r"tiktok\.com"), Platform.TIKTOK),
    (re.compile(r"(facebook\.com|fb\.watch)"), Platform.FACEBOOK),
    (re.compile(r"(twitter\.com|x\.com)"), Platform.TWITTER),
]


def detect_platform(url: str) -> Platform:
    for pattern, platform in PLATFORM_PATTERNS:
        if pattern.search(url):
            return platform
    return Platform.UNKNOWN


@router.post("/import", summary="Submit cooking video URL for recipe extraction", status_code=202)
async def import_video(body: ImportRequest, request: Request) -> dict:
    """
    Accepts a cooking video URL. Detects the platform, deduplicates,
    creates a JobDocument, enqueues extract_recipe_job on the ARQ worker,
    and returns the job_id immediately for the client to track.
    """
    rate_limit_response = await check_rate_limit(request)
    if rate_limit_response:
        return rate_limit_response  # type: ignore[return-value]

    url = str(body.url).strip()
    platform = detect_platform(url)

    # Deduplication — return existing in-flight job for same URL
    existing = await JobService.find_existing_queued(url)
    if existing:
        return {
            "ok": True,
            "data": {
                "jobId": str(existing.id),
                "status": existing.status,
                "deduplicated": True,
            },
        }

    user_id = await get_optional_user(request)
    job = await JobService.create(url=url, platform=platform, user_id=user_id)

    # Enqueue ARQ task
    await _enqueue_job(str(job.id), request)

    return {
        "ok": True,
        "data": {
            "jobId": str(job.id),
            "status": job.status,
            "deduplicated": False,
        },
    }
