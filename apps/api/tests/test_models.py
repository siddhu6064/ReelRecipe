"""
tests/test_models.py

Schema validation tests for RecipeDocument, PantryDocument, JobDocument.
Uses mongomock-motor so Beanie is initialised but no real MongoDB needed.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.documents import (
    ALL_DOCUMENTS,
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


@pytest_asyncio.fixture(autouse=True)
async def beanie_init():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


# ── RecipeDocument ─────────────────────────────────────────────────────────


def test_recipe_minimal_valid():
    r = RecipeDocument(
        user_id="clerk_001",
        source_url="https://youtube.com/watch?v=abc",
        title="Test Recipe",
        ingredients=[RecipeIngredient(name="salt")],
        steps=[RecipeStep(order=1, text="Add salt.")],
    )
    assert r.title == "Test Recipe"
    assert r.difficulty == Difficulty.MEDIUM
    assert r.servings == 2
    assert r.is_edited is False


def test_recipe_full_fields(sample_recipe):
    assert sample_recipe.cuisine == "Italian"
    assert sample_recipe.total_time_minutes == 30
    assert len(sample_recipe.ingredients) == 5
    assert len(sample_recipe.steps) == 5
    assert "quick" in sample_recipe.tags
    assert sample_recipe.nutrition.calories == 650.0


def test_recipe_ingredient_optional_default():
    ing = RecipeIngredient(name="chilli flakes")
    assert ing.optional is False
    assert ing.quantity is None
    assert ing.unit is None


def test_recipe_step_timer_nullable():
    s = RecipeStep(order=1, text="Chop onions.")
    assert s.timer_seconds is None


def test_recipe_requires_user_id():
    with pytest.raises(Exception):
        RecipeDocument(
            source_url="https://youtube.com/watch?v=abc",
            title="No User",
        )


def test_recipe_difficulty_enum():
    r = RecipeDocument(
        user_id="clerk_001",
        source_url="https://youtube.com/watch?v=abc",
        title="Easy Recipe",
        difficulty=Difficulty.EASY,
        ingredients=[],
        steps=[],
    )
    assert r.difficulty == "easy"


# ── PantryDocument ─────────────────────────────────────────────────────────


def test_pantry_empty_by_default():
    p = PantryDocument(user_id="clerk_001")
    assert p.items == []


def test_pantry_with_items(sample_pantry):
    assert len(sample_pantry.items) == 5
    names = [i.name for i in sample_pantry.items]
    assert "spaghetti" in names
    assert "eggs" in names


def test_pantry_item_category_default():
    item = PantryItem(name="mystery ingredient")
    assert item.category == IngredientCategory.OTHER


def test_pantry_item_has_uuid_id():
    item = PantryItem(name="flour")
    assert len(item.id) == 36


def test_pantry_item_name_required():
    with pytest.raises(Exception):
        PantryItem()


# ── JobDocument ────────────────────────────────────────────────────────────


def test_job_default_status():
    job = JobDocument(url="https://youtube.com/watch?v=abc", platform=Platform.YOUTUBE)
    assert job.status == JobStatus.QUEUED
    assert job.progress == 0
    assert job.result_id is None


def test_job_result_id_set_on_completion(sample_job):
    sample_job.result_id = "507f1f77bcf86cd799439012"
    sample_job.status = JobStatus.COMPLETED
    assert sample_job.result_id == "507f1f77bcf86cd799439012"


def test_job_progress_bounds():
    with pytest.raises(Exception):
        JobDocument(url="https://youtube.com/watch?v=abc", platform=Platform.YOUTUBE, progress=101)
    with pytest.raises(Exception):
        JobDocument(url="https://youtube.com/watch?v=abc", platform=Platform.YOUTUBE, progress=-1)


def test_job_platform_enum():
    job = JobDocument(url="https://tiktok.com/@user/video/123", platform=Platform.TIKTOK)
    assert job.platform == "tiktok"


# ── NutritionInfo ──────────────────────────────────────────────────────────


def test_nutrition_all_nullable():
    n = NutritionInfo()
    assert n.calories is None
    assert n.protein_g is None


def test_nutrition_full_values():
    n = NutritionInfo(calories=500.0, protein_g=30.0, carbs_g=60.0, fat_g=15.0)
    assert n.calories == 500.0
    assert n.fat_g == 15.0
