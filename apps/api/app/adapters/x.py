"""
app/adapters/twitter.py

Twitter / X adapter — yt-dlp for tweet text and video metadata.

Available signals:
  - Tweet text (often rich with place names for travel content)
  - Hashtags from tweet text
  - Alt text from embedded images/videos (rare but possible)

Limitations:
  - X's API now requires paid access for most endpoints
  - yt-dlp works for public tweets with video; text-only tweets degrade
  - No location data available via yt-dlp (Twitter removed geotagging)
  - Private/protected accounts fail gracefully

Signal quality: generally SPARSE — travel creators rarely post
detailed trip content exclusively on X. ReelRoutes supports it for
completeness but YouTube/Instagram/TikTok yield far richer signals.
"""

from __future__ import annotations

import re

from app.adapters._ytdlp_mixin import extract_hashtags_from_ytdlp, ytdlp_extract
from app.adapters.base import AdapterOutput, BaseAdapter, CaptionsSource
from app.adapters.instagram import _parse_timestamp
from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

_TWEET_ID_RE = re.compile(r"(?:twitter\.com|x\.com)/\w+/status/(\d+)")


def extract_tweet_id(url: str) -> str | None:
    m = _TWEET_ID_RE.search(url)
    return m.group(1) if m else None


class TwitterAdapter(BaseAdapter):
    platform = Platform.TWITTER

    async def fetch(self, url: str) -> AdapterOutput:
        tweet_id = extract_tweet_id(url) or "unknown"
        canonical_url = re.sub(r"twitter\.com", "x.com", url)

        logger.info("twitter_adapter_fetch", tweet_id=tweet_id)

        output = AdapterOutput(
            platform=Platform.TWITTER,
            url=url,
            video_id=tweet_id,
            canonical_url=canonical_url,
            title="X / Twitter Post",
        )

        try:
            info = await ytdlp_extract(url)
            output = self._parse_info(info, url, tweet_id, canonical_url, output)
        except Exception as exc:
            err_str = str(exc).lower()
            if "protected" in err_str or "private" in err_str or "login" in err_str:
                output.add_warning("Tweet is from a protected/private account")
            elif "not found" in err_str or "404" in err_str:
                output.add_warning("Tweet not found or has been deleted")
            else:
                output.add_warning(f"yt-dlp extraction failed: {exc}")

        logger.info(
            "twitter_adapter_done",
            tweet_id=tweet_id,
            captions_source=output.captions_source,
            hashtag_count=len(output.hashtags),
            signal_quality=output.signal_quality,
        )
        return output

    def _parse_info(
        self, info: dict, url: str, tweet_id: str, canonical_url: str, output: AdapterOutput
    ) -> AdapterOutput:
        # yt-dlp puts tweet text in 'description' or 'title'
        tweet_text = info.get("description") or info.get("title") or ""
        cleaned = self._clean_description(tweet_text)
        hashtags = extract_hashtags_from_ytdlp(info)

        creator = info.get("uploader_id") or info.get("uploader")

        output.title = cleaned[:80] if cleaned else "X / Twitter Post"
        output.description = cleaned
        output.thumbnail_url = info.get("thumbnail")
        output.duration_seconds = info.get("duration")
        output.channel_name = info.get("uploader")
        output.creator_handle = f"@{creator.lstrip('@')}" if creator else None
        output.published_at = _parse_timestamp(info.get("timestamp"))
        output.hashtags = hashtags
        output.has_captions = False

        if cleaned:
            output.transcript = cleaned
            output.captions_source = CaptionsSource.DESCRIPTION
        elif hashtags:
            output.captions_source = CaptionsSource.HASHTAGS

        return output
