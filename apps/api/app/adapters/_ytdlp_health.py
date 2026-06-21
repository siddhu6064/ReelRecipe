"""
app/adapters/_ytdlp_health.py

yt-dlp health monitoring and resilience layer.

Problems it solves:
  - Instagram/TikTok actively block old yt-dlp versions
  - A stale yt-dlp version silently fails with cryptic errors
  - Transient failures (429, network) are retried; permanent failures
    (private content, geo-block) are classified and surfaced clearly

Strategy:
  - Cache yt-dlp version check result for 24 hours
  - Classify errors into retryable vs. permanent before retrying
  - Provide clear user-facing messages per failure type
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from enum import StrEnum

from app.config.logging import get_logger

logger = get_logger(__name__)

# Version check cache — avoid checking on every request
_version_checked_at: float = 0.0
_version_ok: bool = True
VERSION_CHECK_INTERVAL = 86_400  # 24 hours


class AdapterErrorType(StrEnum):
    RATE_LIMITED = "rate_limited"
    PRIVATE_CONTENT = "private_content"
    GEO_BLOCKED = "geo_blocked"
    STALE_YTDLP = "stale_ytdlp"
    NETWORK_ERROR = "network_error"
    UNKNOWN = "unknown"


# User-facing messages per error type
ERROR_MESSAGES: dict[AdapterErrorType, str] = {
    AdapterErrorType.RATE_LIMITED: (
        "This platform is temporarily rate-limited. "
        "We extracted what we could from the description and hashtags."
    ),
    AdapterErrorType.PRIVATE_CONTENT: (
        "This video is private or requires login. " "Only public videos can be imported."
    ),
    AdapterErrorType.GEO_BLOCKED: (
        "This video isn't available in our server's region. "
        "Try sharing from the platform app directly."
    ),
    AdapterErrorType.STALE_YTDLP: (
        "Platform format changed — we're updating our extractor. "
        "Processing continued with available signals."
    ),
    AdapterErrorType.NETWORK_ERROR: (
        "Network error fetching video. " "Processing continued with available signals."
    ),
    AdapterErrorType.UNKNOWN: (
        "Could not fetch full video metadata. " "Extracted what was available."
    ),
}


@dataclass
class ClassifiedError:
    error_type: AdapterErrorType
    retryable: bool
    user_message: str
    raw_message: str


def classify_error(exc: Exception) -> ClassifiedError:
    """
    Map a yt-dlp exception to a structured ClassifiedError.
    Determines whether to retry and what to tell the user.
    """
    msg = str(exc).lower()

    if any(x in msg for x in ("private", "login required", "sign in", "members only")):
        return ClassifiedError(
            AdapterErrorType.PRIVATE_CONTENT,
            retryable=False,
            user_message=ERROR_MESSAGES[AdapterErrorType.PRIVATE_CONTENT],
            raw_message=str(exc),
        )

    if any(x in msg for x in ("429", "too many requests", "rate limit", "ratelimit")):
        return ClassifiedError(
            AdapterErrorType.RATE_LIMITED,
            retryable=True,
            user_message=ERROR_MESSAGES[AdapterErrorType.RATE_LIMITED],
            raw_message=str(exc),
        )

    if any(x in msg for x in ("not available in your country", "geo", "region", "unavailable")):
        return ClassifiedError(
            AdapterErrorType.GEO_BLOCKED,
            retryable=False,
            user_message=ERROR_MESSAGES[AdapterErrorType.GEO_BLOCKED],
            raw_message=str(exc),
        )

    if any(
        x in msg
        for x in (
            "unable to extract",
            "unsupported url",
            "no video formats",
            "format changed",
            "sign_in_required",
        )
    ):
        return ClassifiedError(
            AdapterErrorType.STALE_YTDLP,
            retryable=False,
            user_message=ERROR_MESSAGES[AdapterErrorType.STALE_YTDLP],
            raw_message=str(exc),
        )

    if any(x in msg for x in ("connection", "timeout", "network", "ssl", "errno")):
        return ClassifiedError(
            AdapterErrorType.NETWORK_ERROR,
            retryable=True,
            user_message=ERROR_MESSAGES[AdapterErrorType.NETWORK_ERROR],
            raw_message=str(exc),
        )

    return ClassifiedError(
        AdapterErrorType.UNKNOWN,
        retryable=False,
        user_message=ERROR_MESSAGES[AdapterErrorType.UNKNOWN],
        raw_message=str(exc),
    )


async def ytdlp_extract_with_retry(
    url: str,
    max_retries: int = 2,
    base_delay: float = 2.0,
) -> tuple[dict, list[str]]:
    """
    Run yt-dlp extraction with automatic retry on transient errors.
    Returns (info_dict, warnings_list).

    On permanent errors (private, geo-block), returns ({}, [user_message])
    immediately without retrying.

    On transient errors (rate limit, network), retries up to max_retries
    times with exponential backoff.
    """
    from app.adapters._ytdlp_mixin import ytdlp_extract

    warnings: list[str] = []

    for attempt in range(max_retries + 1):
        try:
            info = await ytdlp_extract(url)
            if attempt > 0:
                logger.info("ytdlp_retry_succeeded", url=url, attempt=attempt)
            return info, warnings

        except Exception as exc:
            classified = classify_error(exc)

            logger.warning(
                "ytdlp_error",
                url=url,
                attempt=attempt,
                error_type=classified.error_type,
                retryable=classified.retryable,
                raw=classified.raw_message[:200],
            )

            if not classified.retryable:
                # Permanent failure — don't waste retries
                warnings.append(classified.user_message)
                return {}, warnings

            if attempt < max_retries:
                delay = base_delay * (2**attempt)
                logger.info("ytdlp_retrying", attempt=attempt + 1, delay=delay)
                await asyncio.sleep(delay)
            else:
                warnings.append(classified.user_message)

    return {}, warnings


async def check_ytdlp_version() -> bool:
    """
    Check if yt-dlp is up to date. Cached for 24 hours.
    Returns True if version looks acceptable.
    Logs a warning (but doesn't fail) if version is old.
    """
    global _version_checked_at, _version_ok

    now = time.time()
    if now - _version_checked_at < VERSION_CHECK_INTERVAL:
        return _version_ok

    try:
        import yt_dlp

        version_str = yt_dlp.version.__version__
        # yt-dlp dates versions like 2024.08.07
        # Warn if the build is more than 90 days old
        parts = version_str.split(".")
        if len(parts) == 3:
            import datetime

            try:
                build_date = datetime.date(int(parts[0]), int(parts[1]), int(parts[2]))
                age_days = (datetime.date.today() - build_date).days
                if age_days > 90:
                    logger.warning(
                        "ytdlp_version_old",
                        version=version_str,
                        age_days=age_days,
                        action="consider running: pip install -U yt-dlp",
                    )
                    _version_ok = False
                else:
                    _version_ok = True
            except ValueError:
                _version_ok = True
        _version_checked_at = now
    except Exception:
        _version_ok = True  # don't block on version check failures

    return _version_ok
