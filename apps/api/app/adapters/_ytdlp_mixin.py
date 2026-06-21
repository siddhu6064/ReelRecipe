"""
app/adapters/_ytdlp_mixin.py

Shared yt-dlp logic used by the Instagram, TikTok, Facebook, and Twitter adapters.

yt-dlp is invoked with extract_flat=False and no actual download — we only
want metadata and, where available, subtitle/caption files. For platforms
without captions, the Whisper fallback runs in Phase 3 Week 6.

Thread note: yt-dlp's YoutubeDL is synchronous. We run it in an executor
to avoid blocking the async event loop.
"""

from __future__ import annotations

import asyncio
import io
from contextlib import redirect_stderr
from typing import Any

from app.adapters.base import CaptionsSource, TranscriptSegment
from app.config.logging import get_logger

logger = get_logger(__name__)

# Suppress yt-dlp's verbose stderr output in tests/CI
_QUIET_OPTS = {
    "quiet": True,
    "no_warnings": True,
    "extract_flat": False,
    "skip_download": True,  # metadata only — no video download
    "writesubtitles": False,
    "writeautomaticsub": False,
    "noplaylist": True,
}


async def ytdlp_extract(url: str, extra_opts: dict | None = None) -> dict[str, Any]:
    """
    Run yt-dlp info extraction in a thread pool executor.
    Returns the info_dict or raises on failure.
    """
    import yt_dlp

    opts = {**_QUIET_OPTS, **(extra_opts or {})}

    def _extract() -> dict:
        buf = io.StringIO()
        with redirect_stderr(buf), yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False) or {}

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _extract)


def parse_ytdlp_subtitles(info: dict) -> tuple[list[TranscriptSegment], CaptionsSource]:
    """
    Extract subtitle segments from a yt-dlp info_dict.
    Returns (segments, source) where source is YOUTUBE_CC if found, else NONE.

    yt-dlp returns subtitles under info["subtitles"] and
    auto-generated under info["automatic_captions"].
    Each entry is a list of format dicts; we prefer vtt/json3 formats.
    """
    segments: list[TranscriptSegment] = []

    for key in ("subtitles", "automatic_captions"):
        subs: dict = info.get(key) or {}
        if not subs:
            continue

        # Prefer English; fall back to first available language
        for lang in ("en", "en-US", next(iter(subs.keys())) if subs else None):
            if lang not in subs:
                continue
            formats = subs[lang]
            for fmt in formats:
                if fmt.get("ext") in ("vtt", "json3", "srv3", "srv2", "srv1"):
                    # yt-dlp doesn't download subs in skip_download mode,
                    # but the URL is available. We return empty segments here
                    # and rely on the description signal instead.
                    # Full sub download is a Phase 3 Week 6 enhancement.
                    return [], CaptionsSource.YOUTUBE_CC

    return segments, CaptionsSource.NONE


def extract_hashtags_from_ytdlp(info: dict) -> list[str]:
    """Pull hashtags from yt-dlp info_dict tags and description."""
    from app.adapters.base import BaseAdapter

    tags: list[str] = []
    # yt-dlp 'tags' field
    for tag in info.get("tags") or []:
        tags.append(str(tag).lower().lstrip("#"))
    # Also scan description
    desc = info.get("description") or ""
    tags.extend(BaseAdapter._extract_hashtags(desc))

    # Deduplicate preserving order
    seen: set[str] = set()
    result: list[str] = []
    for t in tags:
        if t not in seen and t:
            seen.add(t)
            result.append(t)
    return result
