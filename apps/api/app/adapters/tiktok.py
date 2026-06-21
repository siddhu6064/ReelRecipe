"""
app/adapters/tiktok.py

TikTok adapter — yt-dlp for metadata, description as primary signal.

TikTok specifics:
  - No captions available via yt-dlp without auth
  - Description is often rich: places, activities, hashtags
  - Hashtag culture is strong — #tokyo #japan yield good signals
  - Audio transcription (Whisper) is the primary path for place extraction
    and is triggered in Phase 3 Week 6 when transcript is absent
  - Rate limits hit quickly for unauthenticated requests — we degrade
    gracefully and never block trip creation

Creator handle extraction: TikTok URLs carry the @username in the path.
"""

from __future__ import annotations

import re

from app.adapters._ytdlp_mixin import extract_hashtags_from_ytdlp
from app.adapters.base import AdapterOutput, BaseAdapter, CaptionsSource
from app.adapters.instagram import _extract_mentions, _parse_timestamp
from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

# https://www.tiktok.com/@username/video/1234567890
_TIKTOK_URL_RE = re.compile(r"tiktok\.com/@([^/]+)/video/(\d+)")


def extract_tiktok_ids(url: str) -> tuple[str | None, str | None]:
    """Returns (creator_handle, video_id) or (None, None)."""
    m = _TIKTOK_URL_RE.search(url)
    if m:
        return m.group(1), m.group(2)
    return None, None


class TikTokAdapter(BaseAdapter):
    platform = Platform.TIKTOK

    async def fetch(self, url: str) -> AdapterOutput:
        creator, video_id = extract_tiktok_ids(url)
        canonical_url = url  # TikTok URLs don't have a simpler canonical form
        vid_id = video_id or "unknown"

        logger.info("tiktok_adapter_fetch", creator=creator, video_id=vid_id)

        output = AdapterOutput(
            platform=Platform.TIKTOK,
            url=url,
            video_id=vid_id,
            canonical_url=canonical_url,
            title="TikTok Video",
            creator_handle=f"@{creator}" if creator else None,
        )

        try:
            from app.adapters._ytdlp_health import ytdlp_extract_with_retry

            info, extra_warnings = await ytdlp_extract_with_retry(
                url, max_retries=2, base_delay=3.0
            )
            for w in extra_warnings:
                output.add_warning(w)
            if info:
                output = self._parse_info(info, url, vid_id, canonical_url, output)
        except Exception as exc:
            err_str = str(exc).lower()
            if "rate" in err_str or "429" in err_str or "too many" in err_str:
                output.add_warning(
                    "TikTok rate limited — description signals unavailable, "
                    "Whisper transcription will be used"
                )
            elif "private" in err_str or "login" in err_str:
                output.add_warning("TikTok video is private or requires login")
            else:
                output.add_warning(f"yt-dlp extraction failed: {exc}")

        logger.info(
            "tiktok_adapter_done",
            video_id=vid_id,
            captions_source=output.captions_source,
            hashtag_count=len(output.hashtags),
            needs_whisper=not output.has_captions,
        )
        return output

    def _parse_info(
        self,
        info: dict,
        url: str,
        video_id: str,
        canonical_url: str,
        output: AdapterOutput,
    ) -> AdapterOutput:
        description = info.get("description") or info.get("title") or ""
        cleaned_desc = self._clean_description(description)

        hashtags = extract_hashtags_from_ytdlp(info)

        creator = output.creator_handle or info.get("uploader_id") or info.get("uploader")

        output.title = cleaned_desc[:80] if cleaned_desc else "TikTok Video"
        output.description = cleaned_desc
        output.thumbnail_url = info.get("thumbnail")
        output.duration_seconds = info.get("duration")
        output.channel_name = info.get("uploader")
        output.creator_handle = f"@{creator.lstrip('@')}" if creator else None
        output.published_at = _parse_timestamp(info.get("timestamp"))
        output.hashtags = hashtags
        output.mentions = _extract_mentions(description)

        # TikTok has no CC in yt-dlp without auth — flag for Whisper
        if cleaned_desc:
            output.transcript = cleaned_desc
            output.captions_source = CaptionsSource.DESCRIPTION
        elif hashtags:
            output.captions_source = CaptionsSource.HASHTAGS

        # has_captions stays False — signals to the pipeline to run Whisper
        output.has_captions = False

        return output
