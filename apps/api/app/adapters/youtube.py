"""
app/adapters/youtube.py

YouTube adapter — the richest signal source.

Fetch strategy:
  1. Extract video_id from URL (youtube.com/watch?v= or youtu.be/ shortlinks)
  2. Call YouTube Data API v3 for title, description, channel, duration,
     thumbnail, published_at (requires YOUTUBE_API_KEY)
  3. Fetch closed captions via youtube-transcript-api (free, no API key needed)
     Priority: manual en > auto-generated en > any available language
  4. If no CC available, set has_captions=False — Whisper fallback happens
     in the extraction pipeline (Phase 3 Week 6)

Rate limits: YouTube Data API = 10,000 units/day on free tier.
A videos.list call costs 1 unit. Safe for hundreds of imports/day.
"""

from __future__ import annotations

import asyncio
import re
from functools import partial
from typing import Any

import httpx
from youtube_transcript_api import (
    NoTranscriptFound,
    TranscriptsDisabled,
    YouTubeTranscriptApi,
)

from app.adapters.base import (
    AdapterOutput,
    BaseAdapter,
    CaptionsSource,
    TranscriptSegment,
)
from app.config.logging import get_logger
from app.config.settings import get_settings
from app.middleware.error_handler import AppError
from app.models.documents import Platform

logger = get_logger(__name__)

# Regex patterns for all known YouTube URL shapes
_YT_PATTERNS = [
    re.compile(r"(?:youtube\.com/watch\?.*v=)([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:youtu\.be/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/shorts/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/embed/)([a-zA-Z0-9_-]{11})"),
    re.compile(r"(?:youtube\.com/v/)([a-zA-Z0-9_-]{11})"),
]

_DATA_API_BASE = "https://www.googleapis.com/youtube/v3"
# ISO 8601 duration → seconds (e.g. PT1H2M3S)
_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def extract_video_id(url: str) -> str | None:
    for pattern in _YT_PATTERNS:
        match = pattern.search(url)
        if match:
            return match.group(1)
    return None


def parse_duration(iso: str) -> float:
    """Convert ISO 8601 duration string to total seconds."""
    m = _DURATION_RE.match(iso)
    if not m:
        return 0.0
    h = int(m.group(1) or 0)
    mins = int(m.group(2) or 0)
    s = int(m.group(3) or 0)
    return float(h * 3600 + mins * 60 + s)


class YouTubeAdapter(BaseAdapter):
    platform = Platform.YOUTUBE

    async def fetch(self, url: str) -> AdapterOutput:
        video_id = extract_video_id(url)
        if not video_id:
            raise AppError(
                f"Could not extract YouTube video ID from URL: {url}",
                code="INVALID_URL",
                status_code=400,
            )

        canonical_url = f"https://www.youtube.com/watch?v={video_id}"
        logger.info("youtube_adapter_fetch", video_id=video_id)

        # ── Step 1: Fetch metadata via YouTube Data API ────────
        metadata = await self._fetch_metadata(video_id)

        output = AdapterOutput(
            platform=Platform.YOUTUBE,
            url=url,
            video_id=video_id,
            canonical_url=canonical_url,
            title=metadata.get("title", f"YouTube video {video_id}"),
            description=self._clean_description(metadata.get("description")),
            thumbnail_url=self._best_thumbnail(metadata.get("thumbnails", {})),
            duration_seconds=parse_duration(metadata.get("duration", "")),
            channel_name=metadata.get("channelTitle"),
            published_at=metadata.get("publishedAt"),
            hashtags=self._extract_hashtags(metadata.get("description", "") or ""),
        )

        # ── Step 2: Fetch transcript via youtube-transcript-api ─
        await self._fetch_transcript(video_id, output)

        logger.info(
            "youtube_adapter_done",
            video_id=video_id,
            captions_source=output.captions_source,
            transcript_length=len(output.transcript or ""),
            hashtag_count=len(output.hashtags),
        )
        return output

    # ── Private helpers ────────────────────────────────────────

    async def _fetch_metadata(self, video_id: str) -> dict[str, Any]:
        settings = get_settings()

        if not settings.youtube_api_key:
            logger.warning("youtube_api_key_missing_using_stub_metadata", video_id=video_id)
            return {
                "title": f"YouTube Video ({video_id})",
                "description": "",
                "channelTitle": "Unknown Channel",
                "duration": "PT10M",
                "thumbnails": {},
                "publishedAt": None,
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                f"{_DATA_API_BASE}/videos",
                params={
                    "id": video_id,
                    "part": "snippet,contentDetails",
                    "key": settings.youtube_api_key,
                },
            )
            resp.raise_for_status()
            data = resp.json()

        items = data.get("items", [])
        if not items:
            raise AppError(
                f"YouTube video {video_id} not found or is private",
                code="VIDEO_UNAVAILABLE",
                status_code=404,
            )

        snippet = items[0].get("snippet", {})
        content_details = items[0].get("contentDetails", {})
        return {
            "title": snippet.get("title", ""),
            "description": snippet.get("description", ""),
            "channelTitle": snippet.get("channelTitle", ""),
            "publishedAt": snippet.get("publishedAt"),
            "thumbnails": snippet.get("thumbnails", {}),
            "duration": content_details.get("duration", ""),
        }

    async def _fetch_transcript(self, video_id: str, output: AdapterOutput) -> None:
        """
        Try to fetch CC transcript. Falls back through:
          manual en → manual (any lang) → auto-generated en → auto (any lang)

        Sets output.transcript, output.caption_segments, output.captions_source.
        """
        try:
            transcript_list = await _run_in_thread(YouTubeTranscriptApi.list_transcripts, video_id)

            # Preference order for transcript selection
            transcript = None
            for lang in ["en", "en-US", "en-GB"]:
                try:
                    transcript = transcript_list.find_manually_created_transcript([lang])
                    break
                except Exception:
                    continue

            if transcript is None:
                try:
                    transcript = transcript_list.find_generated_transcript(["en"])
                except Exception:
                    # Take whatever is available
                    try:
                        transcript = next(iter(transcript_list))
                    except StopIteration:
                        raise NoTranscriptFound(video_id, [], {})

            raw = await _run_in_thread(transcript.fetch)

            segments = [
                TranscriptSegment(
                    start=entry.start,
                    end=entry.start + entry.duration,
                    text=entry.text,
                )
                for entry in raw
            ]

            output.caption_segments = segments
            output.transcript = self._segments_to_text(segments)
            output.has_captions = True
            output.captions_source = CaptionsSource.YOUTUBE_CC

        except TranscriptsDisabled:
            output.add_warning("Transcripts disabled for this video")
        except NoTranscriptFound:
            output.add_warning("No transcript found — Whisper fallback will be used")
        except Exception as exc:
            output.add_warning(f"Transcript fetch failed: {exc}")

    @staticmethod
    def _best_thumbnail(thumbnails: dict) -> str | None:
        """Pick the highest-resolution thumbnail available."""
        for key in ("maxres", "standard", "high", "medium", "default"):
            if key in thumbnails:
                return thumbnails[key].get("url")
        return None


# ── Thread helper for sync youtube-transcript-api calls ────────


async def _run_in_thread(fn, *args, **kwargs):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, partial(fn, *args, **kwargs))
