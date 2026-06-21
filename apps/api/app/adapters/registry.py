"""
app/adapters/registry.py

Maps Platform enum values to their concrete adapter instances.
The job worker calls get_adapter(platform).fetch(url) — it never
instantiates adapters directly.

Adding a new platform:
  1. Create app/adapters/myplatform.py with class MyPlatformAdapter(BaseAdapter)
  2. Add an entry to _REGISTRY below
  3. Add a test in tests/adapters/test_myplatform.py
"""

from __future__ import annotations

from app.adapters.base import AdapterOutput, BaseAdapter
from app.adapters.facebook import FacebookAdapter
from app.adapters.instagram import InstagramAdapter
from app.adapters.tiktok import TikTokAdapter
from app.adapters.twitter import TwitterAdapter
from app.adapters.youtube import YouTubeAdapter
from app.config.logging import get_logger
from app.models.documents import Platform

logger = get_logger(__name__)

_REGISTRY: dict[Platform, BaseAdapter] = {
    Platform.YOUTUBE: YouTubeAdapter(),
    Platform.INSTAGRAM: InstagramAdapter(),
    Platform.TIKTOK: TikTokAdapter(),
    Platform.FACEBOOK: FacebookAdapter(),
    Platform.TWITTER: TwitterAdapter(),
}


def get_adapter(platform: Platform) -> BaseAdapter:
    """
    Returns the adapter for the given platform.
    Falls back to InstagramAdapter (yt-dlp) for unknown platforms
    since yt-dlp supports a broad range of video sites.
    """
    if platform not in _REGISTRY:
        logger.warning("no_adapter_for_platform_using_ytdlp_fallback", platform=platform)
        return InstagramAdapter()
    return _REGISTRY[platform]


async def fetch_from_url(url: str, platform: Platform) -> AdapterOutput:
    """
    Convenience function: get the right adapter and fetch.
    This is what the job worker calls.
    """
    adapter = get_adapter(platform)
    logger.info("adapter_fetch_start", platform=platform, url=url)
    output = await adapter.fetch(url)
    logger.info(
        "adapter_fetch_complete",
        platform=platform,
        signal_quality=output.signal_quality,
        captions_source=output.captions_source,
        transcript_chars=len(output.transcript or ""),
        warnings=len(output.fetch_warnings),
    )
    return output
