"""
app/adapters/base.py

Abstract base class for all platform adapters.

Every adapter:
  1. Accepts a URL
  2. Fetches metadata and content from the platform
  3. Returns a normalised AdapterOutput with consistent field names

The extraction service then operates on AdapterOutput regardless of which
platform the video came from — no platform-specific code leaks downstream.

Signal priority (richest → sparsest):
  youtube_cc > auto_captions > whisper > description_only > hashtags_only
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal

from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

# ── Caption / transcript source enum ──────────────────────────


class CaptionsSource(StrEnum):
    YOUTUBE_CC = "youtube_cc"  # YouTube closed captions / auto-generated
    WHISPER = "whisper"  # OpenAI Whisper audio transcription
    DESCRIPTION = "description"  # Platform description text only
    HASHTAGS = "hashtags"  # Hashtags only — sparsest signal
    NONE = "none"  # No usable signal found


# ── Timed transcript segment ───────────────────────────────────


@dataclass
class TranscriptSegment:
    """One timed line from a caption file or Whisper output."""

    start: float  # seconds from video start
    end: float  # seconds from video start
    text: str

    @property
    def duration(self) -> float:
        return self.end - self.start


# ── Normalised adapter output ──────────────────────────────────


@dataclass
class AdapterOutput:
    """
    Consistent signal bundle produced by every platform adapter.
    The AI extraction service reads only this shape — never platform internals.
    """

    # ── Identity ───────────────────────────────────────────────
    platform: Platform
    url: str  # original URL as submitted
    video_id: str  # platform-specific ID (e.g. YouTube watch?v=)
    canonical_url: str  # cleaned, canonical URL

    # ── Metadata ───────────────────────────────────────────────
    title: str
    description: str | None = None
    thumbnail_url: str | None = None
    duration_seconds: float | None = None
    channel_name: str | None = None
    creator_handle: str | None = None  # @username on Instagram/TikTok
    published_at: str | None = None  # ISO 8601 or None

    # ── Transcript / caption signals ───────────────────────────
    transcript: str | None = None  # full plain-text transcript
    caption_segments: list[TranscriptSegment] = field(default_factory=list)
    captions_source: CaptionsSource = CaptionsSource.NONE
    has_captions: bool = False

    # ── Social signals ─────────────────────────────────────────
    hashtags: list[str] = field(default_factory=list)
    location_tag: str | None = None  # tagged location if the creator set one
    mentions: list[str] = field(default_factory=list)

    # ── Diagnostics ────────────────────────────────────────────
    fetch_warnings: list[str] = field(default_factory=list)

    # ── Computed properties ────────────────────────────────────

    @property
    def signal_quality(self) -> Literal["rich", "medium", "sparse"]:
        """
        Rough quality grade used to set extraction expectations.
        Rich  → full timed transcript available
        Medium → description + hashtags or short transcript
        Sparse → hashtags only or no usable text
        """
        if self.captions_source in (CaptionsSource.YOUTUBE_CC, CaptionsSource.WHISPER):
            return "rich"
        if self.description or len(self.hashtags) >= 3:
            return "medium"
        return "sparse"

    @property
    def best_signal_text(self) -> str:
        """
        Returns the richest available text for extraction,
        in order of preference: transcript > description > hashtags joined.
        """
        if self.transcript:
            return self.transcript
        parts: list[str] = []
        if self.description:
            parts.append(self.description)
        if self.location_tag:
            parts.append(f"Location: {self.location_tag}")
        if self.hashtags:
            parts.append("Hashtags: " + " ".join(f"#{h}" for h in self.hashtags))
        return "\n\n".join(parts) if parts else ""

    def add_warning(self, msg: str) -> None:
        logger.warning("adapter_warning", platform=self.platform, message=msg)
        self.fetch_warnings.append(msg)


# ── Abstract adapter ───────────────────────────────────────────


class BaseAdapter(ABC):
    """
    All platform adapters inherit from this class and implement fetch().

    Design rules:
      - fetch() must NEVER raise for expected platform errors (private video,
        geo-block, rate limit). Instead it degrades gracefully by returning
        whatever signals are available and logging a warning.
      - fetch() MAY raise for truly unexpected errors (network timeout after
        retries, malformed response that cannot be recovered from).
      - Adapters must not import each other — they are independent.
    """

    platform: Platform  # set as a class attribute by each subclass

    @abstractmethod
    async def fetch(self, url: str) -> AdapterOutput:
        """
        Fetch all available signals from the given URL.
        Returns an AdapterOutput regardless of partial failure.
        """
        ...

    @staticmethod
    def _clean_description(text: str | None) -> str | None:
        """Strip excessive whitespace and null-ish strings."""
        if not text:
            return None
        cleaned = " ".join(text.split())
        return cleaned if cleaned else None

    @staticmethod
    def _extract_hashtags(text: str) -> list[str]:
        """Pull #tags from any text string, deduplicated, lowercased."""
        import re

        tags = re.findall(r"#(\w+)", text)
        seen: set[str] = set()
        result: list[str] = []
        for tag in tags:
            lower = tag.lower()
            if lower not in seen:
                seen.add(lower)
                result.append(lower)
        return result

    @staticmethod
    def _segments_to_text(segments: list[TranscriptSegment]) -> str:
        """Join timed segments into a single readable transcript string."""
        return " ".join(s.text.strip() for s in segments if s.text.strip())
