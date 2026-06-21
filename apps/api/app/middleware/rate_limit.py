"""
app/middleware/rate_limit.py

Fix 4 — Redis-backed rate limiter for the /api/process endpoint.

Previous implementation: in-memory dict — resets on every restart
and doesn't work across multiple API instances.

New implementation: Redis INCR + EXPIRE — atomic, persistent across
restarts, works correctly with horizontal scaling on Railway.

Fallback: if Redis is unavailable, falls back to the in-memory
implementation so the app keeps running (just without persistence).

Free tier: 10 video imports per user per day.
Key format: rl:user:<clerk_id> or rl:ip:<ip_address>
TTL: 86400 seconds (24 hours from first request in the window)
"""

from __future__ import annotations

import time
from collections import defaultdict

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)

FREE_TIER_DAILY_LIMIT = 10
WINDOW_SECONDS = 86_400  # 24 hours

# In-memory fallback (used when Redis is unavailable)
_fallback_store: dict[str, tuple[int, float]] = defaultdict(lambda: (0, time.time()))


def _rate_limit_key(request: Request) -> str:
    """Key = clerk_id when authenticated, else IP address."""
    clerk_id = getattr(request.state, "clerk_id", None)
    if clerk_id:
        return f"rl:user:{clerk_id}"
    client_ip = request.headers.get("X-Forwarded-For", "")
    if client_ip:
        return f"rl:ip:{client_ip.split(',')[0].strip()}"
    return f"rl:ip:{request.client.host if request.client else 'unknown'}"


async def check_rate_limit(request: Request) -> JSONResponse | None:
    """
    Returns a 429 JSONResponse if rate limit exceeded, else None.
    Tries Redis first; falls back to in-memory on any Redis error.
    """
    settings = get_settings()
    if settings.is_test or settings.env == "development":
        return None

    key = _rate_limit_key(request)

    # Try Redis-backed check first
    try:
        result = await _redis_check(key, settings.redis_url)
        if result is not None:
            return _build_429(request, result["retry_after"]) if result["exceeded"] else None
    except Exception as exc:
        logger.warning("rate_limit_redis_unavailable_using_fallback", error=str(exc))

    # Fallback: in-memory (survives Redis outage, but not restarts)
    return _memory_check(key, request)


async def _redis_check(key: str, redis_url: str) -> dict | None:
    """
    Use Redis INCR + EXPIRE for atomic, persistent rate limiting.

    INCR is atomic — safe for concurrent requests across multiple
    API instances. EXPIRE only sets TTL on first request in window.

    Returns {"exceeded": bool, "retry_after": int} or raises on error.
    """
    import redis.asyncio as aioredis

    client = aioredis.from_url(redis_url, decode_responses=True, socket_timeout=1.0)
    try:
        pipe = client.pipeline()
        pipe.incr(key)
        pipe.ttl(key)
        count, ttl = await pipe.execute()

        # Set 24h expiry only on first increment (ttl == -1 means no expiry set yet)
        if ttl == -1:
            await client.expire(key, WINDOW_SECONDS)
            ttl = WINDOW_SECONDS

        exceeded = int(count) > FREE_TIER_DAILY_LIMIT
        retry_after = max(0, int(ttl))

        if exceeded:
            logger.warning("rate_limit_exceeded_redis", key=key, count=count)
            # Roll back the increment so it doesn't count against them
            await client.decr(key)

        return {"exceeded": exceeded, "retry_after": retry_after}
    finally:
        await client.aclose()


def _memory_check(key: str, request: Request) -> JSONResponse | None:
    """In-memory fallback rate check."""
    count, window_start = _fallback_store[key]
    now = time.time()

    if now - window_start > WINDOW_SECONDS:
        _fallback_store[key] = (1, now)
        return None

    if count >= FREE_TIER_DAILY_LIMIT:
        logger.warning("rate_limit_exceeded_memory", key=key, count=count)
        retry_after = int(WINDOW_SECONDS - (now - window_start))
        return _build_429(request, retry_after)

    _fallback_store[key] = (count + 1, window_start)
    return None


def _build_429(request: Request, retry_after: int) -> JSONResponse:
    request_id = getattr(request.state, "request_id", "unknown")
    hours = round(retry_after / 3600, 1)
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content={
            "ok": False,
            "error": {
                "code": "RATE_LIMITED",
                "message": (
                    f"Free tier allows {FREE_TIER_DAILY_LIMIT} video imports per day. "
                    f"Try again in {hours} hours."
                ),
                "request_id": request_id,
            },
        },
        headers={"Retry-After": str(retry_after)},
    )
