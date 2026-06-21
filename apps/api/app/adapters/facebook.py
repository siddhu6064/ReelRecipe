"""
app/adapters/facebook.py

Facebook adapter — yt-dlp for Watch videos and Reels.

Available signals:
  - Post title / description text
  - Hashtags from description
  - Tagged location (Facebook embeds this in the info_dict)
  - Channel / Page name

Not available without auth:
  - Private group videos
  - Stories

Facebook Reels use the same extraction path as Watch videos.
fb.watch shortlinks are resolved by yt-dlp automatically.
"""

from __future__ import annotations

import re

from app.adapters._ytdlp_mixin import extract_hashtags_from_ytdlp, ytdlp_extract
from app.adapters.base import AdapterOutput, BaseAdapter, CaptionsSource
from app.adapters.instagram import _parse_timestamp
from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

_FB_VIDEO_ID_RE = re.compile(r"(?:videos?/|watch/?\?v=|v=)(\d+)")
_FB_REEL_RE = re.compile(r"reel[s]?/(\d+)")


def extract_facebook_id(url: str) -> str | None:
    for pattern in (_FB_REEL_RE, _FB_VIDEO_ID_RE):
        m = pattern.search(url)
        if m:
            return m.group(1)
    return None


class FacebookAdapter(BaseAdapter):
    platform = Platform.FACEBOOK

    async def fetch(self, url: str) -> AdapterOutput:
        video_id = extract_facebook_id(url) or "unknown"
        logger.info("facebook_adapter_fetch", video_id=video_id)

        output = AdapterOutput(
            platform=Platform.FACEBOOK,
            url=url,
            video_id=video_id,
            canonical_url=url,
            title="Facebook Video",
        )

        try:
            info = await ytdlp_extract(url)
            output = self._parse_info(info, url, video_id, output)
        except Exception as exc:
            err_str = str(exc).lower()
            if "login" in err_str or "private" in err_str or "age" in err_str:
                output.add_warning("Facebook video requires login or is private")
            else:
                output.add_warning(f"yt-dlp extraction failed: {exc}")

        logger.info(
            "facebook_adapter_done",
            video_id=video_id,
            captions_source=output.captions_source,
            has_location=bool(output.location_tag),
        )
        return output

    def _parse_info(
        self, info: dict, url: str, video_id: str, output: AdapterOutput
    ) -> AdapterOutput:
        description = info.get("description") or info.get("title") or ""
        cleaned_desc = self._clean_description(description)

        # Facebook sometimes exposes location directly in info_dict
        location_tag = info.get("location") or info.get("location_name") or info.get("address")

        hashtags = extract_hashtags_from_ytdlp(info)

        output.title = info.get("title") or cleaned_desc[:80] or "Facebook Video"
        output.description = cleaned_desc
        output.thumbnail_url = info.get("thumbnail")
        output.duration_seconds = info.get("duration")
        output.channel_name = info.get("uploader") or info.get("channel")
        output.published_at = _parse_timestamp(info.get("timestamp"))
        output.hashtags = hashtags
        output.location_tag = str(location_tag) if location_tag else None

        if cleaned_desc:
            output.transcript = cleaned_desc
            output.captions_source = CaptionsSource.DESCRIPTION
        elif hashtags:
            output.captions_source = CaptionsSource.HASHTAGS

        output.has_captions = False
        return output
