"""
app/config/analytics.py

PostHog server-side analytics.
Tracks key events to understand usage, conversion, and the growth loop.

Events tracked:
  import_started      — user pastes URL and hits Import
  import_completed    — job finished successfully with N pins
  trip_saved          — authenticated user saves a trip
  trip_shared         — user generates a share link
  chat_message_sent   — user sends a message to the AI assistant
  pin_edited          — user edits/adds/removes a pin manually

All events are anonymised — we send distinct_id (clerk_id or guest UUID),
never PII like email or name.
"""

from __future__ import annotations

from app.config.logging import get_logger

logger = get_logger(__name__)

_posthog = None


def _get_client():
    global _posthog
    if _posthog is not None:
        return _posthog

    from app.config.settings import get_settings

    settings = get_settings()

    if not settings.posthog_api_key or settings.is_test:
        return None

    import posthog

    posthog.api_key = settings.posthog_api_key
    posthog.host = settings.posthog_host
    posthog.debug = settings.is_development
    _posthog = posthog
    return posthog


def track(
    distinct_id: str,
    event: str,
    properties: dict | None = None,
) -> None:
    """
    Fire a PostHog event. Safe to call from async context — PostHog
    batches and sends in a background thread.
    No-ops silently in test env or if POSTHOG_API_KEY is unset.
    """
    ph = _get_client()
    if ph is None:
        return
    try:
        ph.capture(
            distinct_id=distinct_id,
            event=event,
            properties=properties or {},
        )
    except Exception as exc:
        logger.warning("analytics_track_failed", event=event, error=str(exc))


# ── Typed event helpers ────────────────────────────────────────


def track_import_started(user_id: str | None, url: str, platform: str) -> None:
    track(
        distinct_id=user_id or "guest",
        event="import_started",
        properties={"url": url, "platform": platform},
    )


def track_import_completed(
    user_id: str | None,
    job_id: str,
    platform: str,
    pin_count: int,
    geocoded_count: int,
    signal_type: str,
) -> None:
    track(
        distinct_id=user_id or "guest",
        event="import_completed",
        properties={
            "job_id": job_id,
            "platform": platform,
            "pin_count": pin_count,
            "geocoded_count": geocoded_count,
            "signal_type": signal_type,
        },
    )


def track_trip_saved(user_id: str, trip_id: str, pin_count: int) -> None:
    track(
        distinct_id=user_id,
        event="trip_saved",
        properties={"trip_id": trip_id, "pin_count": pin_count},
    )


def track_trip_shared(user_id: str, trip_id: str) -> None:
    track(
        distinct_id=user_id,
        event="trip_shared",
        properties={"trip_id": trip_id},
    )


def track_chat_message_sent(user_id: str | None, trip_id: str) -> None:
    track(
        distinct_id=user_id or "guest",
        event="chat_message_sent",
        properties={"trip_id": trip_id},
    )


def track_pin_edited(
    user_id: str | None,
    trip_id: str,
    action: str,  # "add" | "edit" | "delete" | "reorder"
) -> None:
    track(
        distinct_id=user_id or "guest",
        event="pin_edited",
        properties={"trip_id": trip_id, "action": action},
    )
