"""
tests/conftest.py

Shared pytest fixtures for ReelRecipes.

Key fixtures:
  settings_override  — patches env to "test" before every test
  mock_db / client   — mongomock-motor in-memory MongoDB + AsyncClient
  sample_recipe      — a fully-populated RecipeDocument
  sample_pantry      — a PantryDocument with 5 items
  sample_job         — a queued JobDocument
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

# Set test env BEFORE importing any app modules
os.environ.setdefault("ENV", "test")
os.environ.setdefault("MONGODB_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGODB_DB", "reelrecipes_test")
os.environ.setdefault("CLERK_SECRET_KEY", "sk_test_dummy")
os.environ.setdefault("OPENAI_API_KEY", "sk-test-fake-key-for-tests")
os.environ.setdefault("NUTRITIONIX_APP_ID", "test-nix-app-id")
os.environ.setdefault("NUTRITIONIX_API_KEY", "test-nix-api-key")

from app.config.settings import get_settings
from app.main import create_app
from app.models.documents import (
    Difficulty,
    IngredientCategory,
    JobDocument,
    JobStatus,
    NutritionInfo,
    PantryDocument,
    PantryItem,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator


# ── Settings ───────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def settings_override() -> None:
    """Clear settings cache between tests to allow env overrides."""
    get_settings.cache_clear()
    yield  # type: ignore[misc]
    get_settings.cache_clear()


# ── Database mock ──────────────────────────────────────────────────────────


@pytest.fixture
def mock_db_ping() -> AsyncMock:
    return AsyncMock(return_value={"ok": 1.0})


@pytest.fixture
def mock_healthy_db(mock_db_ping: AsyncMock) -> MagicMock:
    db = MagicMock()
    db.command = mock_db_ping
    return db


@pytest.fixture
def mock_unhealthy_db() -> MagicMock:
    db = MagicMock()
    db.command = AsyncMock(side_effect=ConnectionError("Connection refused"))
    return db


# ── HTTP client ────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def client(mock_healthy_db: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient for the FastAPI app with mocked MongoDB."""
    app = create_app()
    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
        patch("app.config.database.get_db", return_value=mock_healthy_db),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac


@pytest_asyncio.fixture
async def client_unhealthy_db(mock_unhealthy_db: MagicMock) -> AsyncGenerator[AsyncClient, None]:
    app = create_app()
    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
        patch("app.config.database.get_db", return_value=mock_unhealthy_db),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac


# ── Domain fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def sample_recipe() -> RecipeDocument:
    return RecipeDocument(
        user_id="user_test_clerk_001",
        job_id="507f1f77bcf86cd799439011",
        source_url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform=Platform.YOUTUBE,
        thumbnail_url="https://img.youtube.com/vi/dQw4w9WgXcQ/hqdefault.jpg",
        video_title="Classic Spaghetti Carbonara",
        title="Spaghetti Carbonara",
        description="A classic Roman pasta dish with eggs, cheese, and pancetta.",
        cuisine="Italian",
        difficulty=Difficulty.MEDIUM,
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=20,
        total_time_minutes=30,
        ingredients=[
            RecipeIngredient(name="spaghetti", quantity=200, unit="g"),
            RecipeIngredient(name="pancetta", quantity=100, unit="g"),
            RecipeIngredient(name="egg yolks", quantity=3, unit=None),
            RecipeIngredient(name="pecorino romano", quantity=50, unit="g", preparation="grated"),
            RecipeIngredient(name="black pepper", preparation="to taste"),
        ],
        steps=[
            RecipeStep(order=1, text="Bring a large pot of salted water to a boil.", timer_seconds=None),
            RecipeStep(order=2, text="Cook spaghetti until al dente.", timer_seconds=480),
            RecipeStep(order=3, text="Fry pancetta in a pan until crispy.", timer_seconds=300),
            RecipeStep(order=4, text="Whisk egg yolks with cheese and pepper."),
            RecipeStep(order=5, text="Combine hot pasta with pancetta, then add egg mixture off heat."),
        ],
        tags=["quick", "comfort-food"],
        nutrition=NutritionInfo(
            calories=650.0, protein_g=28.0, carbs_g=72.0, fat_g=24.0
        ),
        extraction_model="gpt-4o",
        extraction_tokens=842,
    )


@pytest.fixture
def sample_pantry() -> PantryDocument:
    return PantryDocument(
        user_id="user_test_clerk_001",
        items=[
            PantryItem(name="spaghetti", quantity=500, unit="g", category=IngredientCategory.GRAINS),
            PantryItem(name="eggs", quantity=6, unit=None, category=IngredientCategory.DAIRY),
            PantryItem(name="pecorino romano", quantity=100, unit="g", category=IngredientCategory.DAIRY),
            PantryItem(name="olive oil", quantity=500, unit="ml", category=IngredientCategory.PANTRY),
            PantryItem(name="black pepper", category=IngredientCategory.SPICES),
        ],
    )


@pytest.fixture
def sample_job() -> JobDocument:
    return JobDocument(
        user_id="user_test_clerk_001",
        url="https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        platform=Platform.YOUTUBE,
        status=JobStatus.QUEUED,
    )
