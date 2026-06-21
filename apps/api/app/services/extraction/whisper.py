"""
app/services/extraction/whisper.py

OpenAI Whisper transcription fallback for platforms without captions.

Used when:
  - Instagram Reels (no CC via yt-dlp)
  - TikTok videos (no CC via yt-dlp)
  - Facebook videos (no CC via yt-dlp)
  - Any YouTube video where CC is disabled

Workflow:
  1. yt-dlp downloads audio-only (m4a/webm) to a temp file
  2. Whisper API transcribes the audio
  3. Timed segments are returned if verbose_json format is used
  4. Temp file is cleaned up regardless of success/failure

Rate: ~$0.006/minute of audio on OpenAI's Whisper API.
For a 10-minute TikTok: ~$0.06. Acceptable for the free tier.

File size limit: Whisper API accepts up to 25 MB.
For videos longer than ~30 min we chunk the audio (future enhancement).
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from pathlib import Path

from app.adapters.base import CaptionsSource, TranscriptSegment
from app.config.logging import get_logger
from app.config.settings import get_settings

logger = get_logger(__name__)

WHISPER_MODEL = "whisper-1"
MAX_FILE_SIZE_MB = 24  # stay under the 25 MB hard limit
SUPPORTED_FORMATS = ("mp4", "m4a", "webm", "mp3", "wav", "ogg", "flac")


async def transcribe_url(url: str) -> tuple[str, list[TranscriptSegment], CaptionsSource]:
    """
    Download audio from url and transcribe with Whisper.

    Returns:
        (transcript_text, timed_segments, CaptionsSource.WHISPER)

    Falls back to empty string + empty segments if anything fails.
    """
    settings = get_settings()

    if not settings.openai_api_key:
        logger.warning("whisper_skipped_no_api_key", url=url)
        return "", [], CaptionsSource.NONE

    with tempfile.TemporaryDirectory() as tmpdir:
        audio_path = await _download_audio(url, tmpdir)
        if audio_path is None:
            return "", [], CaptionsSource.NONE

        file_size_mb = Path(audio_path).stat().st_size / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            logger.warning(
                "whisper_file_too_large",
                size_mb=round(file_size_mb, 1),
                url=url,
            )
            # TODO: chunk audio for long videos
            return "", [], CaptionsSource.NONE

        transcript, segments = await _call_whisper(audio_path, settings.openai_api_key)

    if transcript:
        logger.info(
            "whisper_transcription_complete",
            chars=len(transcript),
            segments=len(segments),
            url=url,
        )
        return transcript, segments, CaptionsSource.WHISPER

    return "", [], CaptionsSource.NONE


async def _download_audio(url: str, tmpdir: str) -> str | None:
    """Download audio-only stream to tmpdir using yt-dlp."""
    import yt_dlp

    output_template = os.path.join(tmpdir, "audio.%(ext)s")
    opts = {
        "format": "bestaudio[filesize<25M]/bestaudio",
        "outtmpl": output_template,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "64",  # low bitrate — speech only
            }
        ],
    }

    def _download() -> str | None:
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
            # Find the downloaded file
            for fname in os.listdir(tmpdir):
                if fname.startswith("audio"):
                    return os.path.join(tmpdir, fname)
        except Exception as exc:
            logger.warning("whisper_download_failed", url=url, error=str(exc))
        return None

    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _download)


async def _call_whisper(
    audio_path: str,
    api_key: str,
) -> tuple[str, list[TranscriptSegment]]:
    """Call the Whisper API and return (transcript, segments)."""
    from openai import AsyncOpenAI

    client = AsyncOpenAI(api_key=api_key)

    try:
        with open(audio_path, "rb") as audio_file:
            response = await client.audio.transcriptions.create(
                model=WHISPER_MODEL,
                file=audio_file,
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # Build timed segments from Whisper's verbose output
        segments: list[TranscriptSegment] = []
        if hasattr(response, "segments") and response.segments:
            for seg in response.segments:
                segments.append(
                    TranscriptSegment(
                        start=float(seg.start),
                        end=float(seg.end),
                        text=str(seg.text).strip(),
                    )
                )

        transcript = str(response.text).strip() if hasattr(response, "text") else ""
        return transcript, segments

    except Exception as exc:
        logger.error("whisper_api_error", error=str(exc), audio_path=audio_path)
        return "", []
