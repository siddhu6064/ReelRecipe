"""
app/adapters/instagram.py

Instagram adapter — uses yt-dlp to fetch Reel / video metadata.

Available signals:
  - Title (usually empty for Reels — falls back to description snippet)
  - Description / caption (rich text with hashtags, mentions, locations)
  - Hashtags extracted from the caption
  - Tagged location (if the creator set one)
  - Creator handle

Not available without auth:
  - Audio transcript (Whisper fallback handles this in Week 6)
  - Private account content (fails gracefully with a warning)

Instagram rate-limits unauthenticated yt-dlp requests. We handle
this gracefully: if extraction fails, we return whatever partial
metadata was recoverable and flag the job for retry.
"""

from __future__ import annotations

import re

from app.adapters._ytdlp_mixin import extract_hashtags_from_ytdlp
from app.adapters.base import AdapterOutput, BaseAdapter, CaptionsSource
from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

_IG_URL_RE = re.compile(r"instagram\.com/(?:reel|p|tv)/([A-Za-z0-9_-]+)")


def extract_shortcode(url: str) -> str | None:
    m = _IG_URL_RE.search(url)
    return m.group(1) if m else None


class InstagramAdapter(BaseAdapter):
    platform = Platform.INSTAGRAM

    async def fetch(self, url: str) -> AdapterOutput:
        shortcode = extract_shortcode(url)
        video_id = shortcode or url.split("/")[-2] or "unknown"
        canonical_url = f"https://www.instagram.com/p/{shortcode}/" if shortcode else url

        logger.info("instagram_adapter_fetch", shortcode=shortcode)

        output = AdapterOutput(
            platform=Platform.INSTAGRAM,
            url=url,
            video_id=video_id,
            canonical_url=canonical_url,
            title="Instagram Reel",
        )

        try:
            from app.adapters._ytdlp_health import ytdlp_extract_with_retry

            info, extra_warnings = await ytdlp_extract_with_retry(
                url, max_retries=2, base_delay=3.0
            )
            for w in extra_warnings:
                output.add_warning(w)
            if info:
                output = self._parse_info(info, url, video_id, canonical_url, output)
        except Exception as exc:
            err_str = str(exc).lower()
            if "private" in err_str or "login" in err_str:
                output.add_warning("Instagram post is private or requires login")
            elif "rate" in err_str or "429" in err_str:
                output.add_warning("Instagram rate limited — retry after cooldown")
            else:
                output.add_warning(f"yt-dlp extraction failed: {exc}")

        logger.info(
            "instagram_adapter_done",
            video_id=video_id,
            captions_source=output.captions_source,
            hashtag_count=len(output.hashtags),
            has_location=bool(output.location_tag),
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

        # Instagram often puts the location in the title field
        location_tag = (
            info.get("location")
            or info.get("location_name")
            or _extract_inline_location(description)
        )

        hashtags = extract_hashtags_from_ytdlp(info)

        creator = info.get("uploader_id") or info.get("uploader") or info.get("channel")
        creator_handle = f"@{creator.lstrip('@')}" if creator else None

        output.title = cleaned_desc[:80] if cleaned_desc else "Instagram Reel"
        output.description = cleaned_desc
        output.thumbnail_url = info.get("thumbnail")
        output.duration_seconds = info.get("duration")
        output.channel_name = info.get("uploader")
        output.creator_handle = creator_handle
        output.published_at = _parse_timestamp(info.get("timestamp"))
        output.hashtags = hashtags
        output.location_tag = location_tag
        output.mentions = _extract_mentions(description)

        # Build text transcript from description (captions not available without auth)
        if cleaned_desc:
            output.transcript = cleaned_desc
            output.has_captions = False
            output.captions_source = CaptionsSource.DESCRIPTION
        elif hashtags:
            output.captions_source = CaptionsSource.HASHTAGS

        return output


# ── Helpers ────────────────────────────────────────────────────


def _extract_inline_location(text: str) -> str | None:
    """
    Some creators write location inline: '📍 Tokyo, Japan' or '@ Shibuya'.
    Try to extract these as a weak location signal.
    """
    patterns = [
        re.compile(r"📍\s*([^\n#@]{3,60})"),
        re.compile(r"@\s+([A-Z][a-zA-Z\s]{2,40})(?:\n|$)"),
    ]
    for pattern in patterns:
        m = pattern.search(text)
        if m:
            loc = m.group(1).strip().rstrip(".,;")
            if loc:
                return loc
    return None


def _extract_mentions(text: str) -> list[str]:
    return re.findall(r"@(\w+)", text)


def _parse_timestamp(ts: int | float | None) -> str | None:
    if ts is None:
        return None
    from datetime import UTC, datetime

    return datetime.fromtimestamp(float(ts), tz=UTC).isoformat()
