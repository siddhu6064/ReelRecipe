"""
tests/test_job_pipeline.py

Integration tests for the full extract_recipe_job pipeline.

All external services are mocked:
  - MongoDB via mongomock-motor
  - OpenAI GPT-4o (extractor)
  - Nutritionix API (nutrition)
  - Platform adapters (YouTube / yt-dlp)
  - Whisper transcription

Tests verify the state transitions: QUEUED → PROCESSING → COMPLETED / FAILED
and that the resulting RecipeDocument is created correctly.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.documents import (
    ALL_DOCUMENTS,
    JobDocument,
    JobErrorCode,
    JobStatus,
    Platform,
    RecipeDocument,
)
from app.services.job_service import JobService
from app.workers.job_worker import extract_recipe_job


# ── Database setup ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def beanie_db():
    """Spin up a fresh mongomock-motor database for each test."""
    client = AsyncMongoMockClient()
    db = client["reelrecipes_test"]
    await init_beanie(database=db, document_models=ALL_DOCUMENTS)
    yield db
    client.close()


# ── Mock helpers ───────────────────────────────────────────────────────────

RECIPE_GPT_RESPONSE = {
    "title": "Test Pasta",
    "description": "A simple pasta dish.",
    "cuisine": "Italian",
    "difficulty": "easy",
    "servings": 2,
    "prep_time_minutes": 5,
    "cook_time_minutes": 15,
    "total_time_minutes": 20,
    "ingredients": [
        {"name": "pasta", "quantity": 200, "unit": "g", "preparation": None, "optional": False},
        {"name": "tomato sauce", "quantity": 1, "unit": "cup", "preparation": None, "optional": False},
    ],
    "steps": [
        {"order": 1, "text": "Boil pasta.", "timer_seconds": 480},
        {"order": 2, "text": "Add sauce.", "timer_seconds": None},
    ],
    "tags": ["quick", "comfort-food"],
}


def _mock_gpt_response(data: dict = None) -> MagicMock:
    data = data or RECIPE_GPT_RESPONSE
    msg = MagicMock()
    msg.content = json.dumps(data)
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.total_tokens = 300
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


def _mock_adapter_output(transcript: str = "Today we make pasta with tomato sauce.") -> MagicMock:
    """Mock AdapterOutput with a valid transcript."""
    from app.adapters.base import CaptionsSource
    output = MagicMock()
    output.transcript = transcript
    output.best_signal_text = transcript
    output.captions_source = CaptionsSource.YOUTUBE_CC
    output.title = "Test Pasta Video"
    output.thumbnail_url = "https://img.youtube.com/vi/test/hqdefault.jpg"
    return output


def _mock_nutrition_response() -> dict:
    return {
        "calories": 400.0,
        "protein_g": 12.0,
        "carbs_g": 70.0,
        "fat_g": 5.0,
        "fiber_g": 3.0,
        "sugar_g": 8.0,
        "sodium_mg": 300.0,
        "fetched_at": "2025-01-01T00:00:00",
    }


# ── Happy path ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_completes_successfully(beanie_db):
    """Full pipeline: adapter → GPT → nutrition → RecipeDocument created."""
    # Create a queued job
    job = JobDocument(
        url="https://youtube.com/watch?v=test123",
        platform=Platform.YOUTUBE,
        user_id="user_clerk_001",
    )
    await job.insert()
    job_id = str(job.id)

    mock_adapter = MagicMock()
    mock_adapter.fetch = AsyncMock(return_value=_mock_adapter_output())

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.adapters.registry.get_adapter", return_value=mock_adapter),
        patch("app.services.extractor.AsyncOpenAI") as MockGPT,
        patch("app.services.nutrition.httpx.AsyncClient") as MockHttp,
    ):
        # Wire GPT mock
        MockGPT.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_gpt_response()
        )

        # Wire Nutritionix mock
        nix_resp = MagicMock()
        nix_resp.raise_for_status = MagicMock()
        nix_resp.json = MagicMock(return_value={
            "foods": [{
                "nf_calories": 800.0, "nf_protein": 24.0,
                "nf_total_carbohydrate": 140.0, "nf_total_fat": 10.0,
                "nf_dietary_fiber": 6.0, "nf_sugars": 16.0, "nf_sodium": 600.0,
            }]
        })
        mock_http_instance = AsyncMock()
        mock_http_instance.__aenter__ = AsyncMock(return_value=mock_http_instance)
        mock_http_instance.__aexit__ = AsyncMock(return_value=False)
        mock_http_instance.post = AsyncMock(return_value=nix_resp)
        MockHttp.return_value = mock_http_instance

        await extract_recipe_job({}, job_id)

    # Verify job is COMPLETED
    updated_job = await JobService.get(job_id)
    assert updated_job.status == JobStatus.COMPLETED
    assert updated_job.progress == 100
    assert updated_job.result_id is not None
    assert updated_job.completed_at is not None

    # Verify RecipeDocument was created
    recipe = await RecipeDocument.get(updated_job.result_id)
    assert recipe is not None
    assert recipe.title == "Test Pasta"
    assert recipe.user_id == "user_clerk_001"
    assert recipe.job_id == job_id
    assert len(recipe.ingredients) == 2
    assert len(recipe.steps) == 2
    assert recipe.platform == Platform.YOUTUBE


@pytest.mark.asyncio
async def test_pipeline_sets_nutrition(beanie_db):
    """Nutrition data should be attached to the recipe when Nutritionix succeeds."""
    job = JobDocument(url="https://youtube.com/watch?v=nutri", platform=Platform.YOUTUBE, user_id="u1")
    await job.insert()

    mock_adapter = MagicMock()
    mock_adapter.fetch = AsyncMock(return_value=_mock_adapter_output())

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.adapters.registry.get_adapter", return_value=mock_adapter),
        patch("app.services.extractor.AsyncOpenAI") as MockGPT,
        patch("app.services.nutrition.fetch_nutrition", new_callable=AsyncMock) as mock_nix,
    ):
        MockGPT.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_gpt_response()
        )
        mock_nix.return_value = _mock_nutrition_response()

        await extract_recipe_job({}, str(job.id))

    updated = await JobService.get(str(job.id))
    recipe = await RecipeDocument.get(updated.result_id)
    assert recipe.nutrition is not None
    assert recipe.nutrition.calories == pytest.approx(400.0, abs=1.0)


# ── Failure paths ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_fails_no_transcript(beanie_db):
    """If adapter returns no transcript and Whisper returns empty, job fails."""
    job = JobDocument(url="https://youtube.com/watch?v=noaudio", platform=Platform.YOUTUBE)
    await job.insert()

    from app.adapters.base import CaptionsSource
    empty_output = MagicMock()
    empty_output.transcript = None
    empty_output.best_signal_text = ""
    empty_output.captions_source = CaptionsSource.NONE
    empty_output.title = "Silent Video"
    empty_output.thumbnail_url = None

    mock_adapter = MagicMock()
    mock_adapter.fetch = AsyncMock(return_value=empty_output)

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.adapters.registry.get_adapter", return_value=mock_adapter),
        patch("app.services.extraction.whisper.transcribe_url",
              new_callable=AsyncMock, return_value=("", [], None)),
    ):
        await extract_recipe_job({}, str(job.id))

    updated = await JobService.get(str(job.id))
    assert updated.status == JobStatus.FAILED
    assert updated.error_code == JobErrorCode.TRANSCRIPT_FAILED


@pytest.mark.asyncio
async def test_pipeline_fails_no_recipe_found(beanie_db):
    """If GPT finds no ingredients, job should fail with NO_RECIPE_FOUND."""
    job = JobDocument(url="https://youtube.com/watch?v=notcooking", platform=Platform.YOUTUBE)
    await job.insert()

    mock_adapter = MagicMock()
    mock_adapter.fetch = AsyncMock(
        return_value=_mock_adapter_output("This is a travel vlog with no cooking.")
    )

    bad_response = {**RECIPE_GPT_RESPONSE, "ingredients": [], "steps": []}

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.adapters.registry.get_adapter", return_value=mock_adapter),
        patch("app.services.extractor.AsyncOpenAI") as MockGPT,
    ):
        MockGPT.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_gpt_response(bad_response)
        )
        await extract_recipe_job({}, str(job.id))

    updated = await JobService.get(str(job.id))
    assert updated.status == JobStatus.FAILED
    assert updated.error_code == JobErrorCode.NO_RECIPE_FOUND


@pytest.mark.asyncio
async def test_pipeline_whisper_fallback_used(beanie_db):
    """When adapter returns no captions, Whisper fallback should be invoked."""
    job = JobDocument(url="https://tiktok.com/@chef/video/123", platform=Platform.TIKTOK)
    await job.insert()

    from app.adapters.base import CaptionsSource
    no_captions = MagicMock()
    no_captions.transcript = None
    no_captions.best_signal_text = ""
    no_captions.captions_source = CaptionsSource.NONE
    no_captions.title = "TikTok Recipe"
    no_captions.thumbnail_url = None

    mock_adapter = MagicMock()
    mock_adapter.fetch = AsyncMock(return_value=no_captions)

    whisper_transcript = "Here is how to make pasta carbonara..."

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.adapters.registry.get_adapter", return_value=mock_adapter),
        patch("app.services.extraction.whisper.transcribe_url",
              new_callable=AsyncMock, return_value=(whisper_transcript, [], None)) as mock_whisper,
        patch("app.services.extractor.AsyncOpenAI") as MockGPT,
        patch("app.services.nutrition.fetch_nutrition", new_callable=AsyncMock, return_value=None),
    ):
        MockGPT.return_value.chat.completions.create = AsyncMock(
            return_value=_mock_gpt_response()
        )
        await extract_recipe_job({}, str(job.id))

    mock_whisper.assert_awaited_once()
    updated = await JobService.get(str(job.id))
    assert updated.status == JobStatus.COMPLETED


# ── JobService unit tests ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_job_service_find_existing_queued(beanie_db):
    url = "https://youtube.com/watch?v=dedup"
    job = JobDocument(url=url, platform=Platform.YOUTUBE)
    await job.insert()

    found = await JobService.find_existing_queued(url)
    assert found is not None
    assert str(found.id) == str(job.id)


@pytest.mark.asyncio
async def test_job_service_find_existing_not_found_completed(beanie_db):
    """Completed jobs should NOT be returned as existing queued jobs."""
    from datetime import UTC, datetime

    url = "https://youtube.com/watch?v=done"
    job = JobDocument(
        url=url, platform=Platform.YOUTUBE,
        status=JobStatus.COMPLETED, completed_at=datetime.now(UTC),
    )
    await job.insert()

    found = await JobService.find_existing_queued(url)
    assert found is None


@pytest.mark.asyncio
async def test_job_service_set_processing(beanie_db):
    from app.models.documents import JobStep

    job = JobDocument(url="https://youtube.com/watch?v=proc", platform=Platform.YOUTUBE)
    await job.insert()

    await JobService.set_processing(job, JobStep.EXTRACTING_RECIPE, "Extracting…", progress=55)
    refreshed = await JobService.get(str(job.id))
    assert refreshed.status == JobStatus.PROCESSING
    assert refreshed.progress == 55
    assert refreshed.current_step == JobStep.EXTRACTING_RECIPE
    assert refreshed.started_at is not None


@pytest.mark.asyncio
async def test_job_service_set_completed(beanie_db):
    job = JobDocument(url="https://youtube.com/watch?v=done", platform=Platform.YOUTUBE)
    await job.insert()

    await JobService.set_completed(job, result_id="507f1f77bcf86cd799439099")
    refreshed = await JobService.get(str(job.id))
    assert refreshed.status == JobStatus.COMPLETED
    assert refreshed.progress == 100
    assert refreshed.result_id == "507f1f77bcf86cd799439099"
    assert refreshed.completed_at is not None


@pytest.mark.asyncio
async def test_job_service_set_failed(beanie_db):
    job = JobDocument(url="https://youtube.com/watch?v=fail", platform=Platform.YOUTUBE)
    await job.insert()

    await JobService.set_failed(job, "Something went wrong", JobErrorCode.UNKNOWN_ERROR)
    refreshed = await JobService.get(str(job.id))
    assert refreshed.status == JobStatus.FAILED
    assert "Something went wrong" in refreshed.error
    assert refreshed.error_code == JobErrorCode.UNKNOWN_ERROR
