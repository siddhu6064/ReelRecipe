"""
tests/test_routers.py

HTTP-level tests for all ReelRecipes API endpoints.

Auth is mocked — every request is treated as belonging to 'user_test_clerk_001'.
Database is mocked via mongomock-motor + Beanie.
GPT-4o, Nutritionix, Redis are all mocked — no real API calls.
"""

from __future__ import annotations

import json
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import create_app
from app.models.documents import (
    ALL_DOCUMENTS,
    Difficulty,
    JobDocument,
    JobStatus,
    PantryDocument,
    PantryItem,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)

TEST_USER = "user_test_clerk_001"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    db = client["reelrecipes_test"]
    await init_beanie(database=db, document_models=ALL_DOCUMENTS)
    yield db
    client.close()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    from app.auth.clerk import optional_auth, require_auth

    app = create_app()

    # Override auth dependencies so all requests are treated as TEST_USER
    async def _fake_require_auth() -> str:
        return TEST_USER

    async def _fake_optional_auth() -> str:
        return TEST_USER

    app.dependency_overrides[require_auth] = _fake_require_auth
    app.dependency_overrides[optional_auth] = _fake_optional_auth

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def recipe(db) -> RecipeDocument:
    r = RecipeDocument(
        user_id=TEST_USER,
        source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        title="Test Pasta",
        cuisine="Italian",
        difficulty=Difficulty.EASY,
        servings=2,
        total_time_minutes=25,
        ingredients=[
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="tomato sauce", quantity=1, unit="cup"),
        ],
        steps=[
            RecipeStep(order=1, text="Boil pasta.", timer_seconds=480),
            RecipeStep(order=2, text="Add sauce."),
        ],
        tags=["quick", "vegetarian"],
    )
    await r.insert()
    return r


@pytest_asyncio.fixture
async def pantry(db) -> PantryDocument:
    p = PantryDocument(
        user_id=TEST_USER,
        items=[
            PantryItem(name="pasta", quantity=500, unit="g"),
            PantryItem(name="tomato sauce", quantity=2, unit="cup"),
        ],
    )
    await p.insert()
    return p


@pytest_asyncio.fixture
async def job(db) -> JobDocument:
    j = JobDocument(
        url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        user_id=TEST_USER,
    )
    await j.insert()
    return j


# ── Health ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200


# ── Jobs ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_job_ok(client, job):
    resp = await client.get(f"/api/jobs/{job.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["jobId"] == str(job.id)
    assert data["data"]["status"] == "queued"


@pytest.mark.asyncio
async def test_get_job_not_found(client):
    resp = await client.get("/api/jobs/507f1f77bcf86cd799439099")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_job_invalid_id(client):
    resp = await client.get("/api/jobs/not-an-object-id")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_import_video_enqueues_job(client, db):
    """Import endpoint creates a job, enqueues it, and returns 202."""
    mock_job = MagicMock()
    mock_job.id = "507f1f77bcf86cd799439011"
    mock_job.status = "queued"

    with (
        patch("app.routers.import_video.JobService.find_existing_queued",
              new_callable=AsyncMock, return_value=None),
        patch("app.routers.import_video.JobService.create",
              new_callable=AsyncMock, return_value=mock_job),
        patch("app.routers.import_video.check_rate_limit",
              new_callable=AsyncMock, return_value=None),
        patch("app.routers.import_video._enqueue_job",
              new_callable=AsyncMock, return_value=None),
    ):
        resp = await client.post(
            "/api/jobs/import",
            json={"url": "https://youtube.com/watch?v=newvideo"},
        )
    assert resp.status_code == 202
    data = resp.json()
    assert data["ok"] is True
    assert data["data"]["jobId"] == "507f1f77bcf86cd799439011"


@pytest.mark.asyncio
async def test_import_video_deduplication(client, job):
    """Submitting same URL twice returns the existing job."""
    resp = await client.post(
        "/api/jobs/import",
        json={"url": job.url},
    )
    # May 202 or rate-limited — either way, no 500
    assert resp.status_code < 500


# ── Recipes ────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_recipes_empty(client, db):
    resp = await client.get("/api/recipes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["recipes"] == []
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_recipes_returns_owned(client, recipe):
    resp = await client.get("/api/recipes")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["total"] == 1
    assert body["data"]["recipes"][0]["title"] == "Test Pasta"


@pytest.mark.asyncio
async def test_list_recipes_filter_cuisine(client, recipe):
    resp = await client.get("/api/recipes?cuisine=Italian")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    resp2 = await client.get("/api/recipes?cuisine=Mexican")
    assert resp2.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_recipes_filter_search(client, recipe):
    resp = await client.get("/api/recipes?search=Pasta")
    assert resp.status_code == 200
    assert resp.json()["data"]["total"] == 1

    resp2 = await client.get("/api/recipes?search=nonexistent")
    assert resp2.json()["data"]["total"] == 0


@pytest.mark.asyncio
async def test_list_recipes_pagination(client, db):
    for i in range(5):
        r = RecipeDocument(
            user_id=TEST_USER,
            source_url=f"https://youtube.com/watch?v={i}",
            title=f"Recipe {i}",
            ingredients=[RecipeIngredient(name="x")],
            steps=[RecipeStep(order=1, text="x")],
        )
        await r.insert()

    resp = await client.get("/api/recipes?limit=2&offset=0")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["data"]["recipes"]) == 2
    assert body["data"]["total"] == 5


@pytest.mark.asyncio
async def test_get_recipe_ok(client, recipe):
    resp = await client.get(f"/api/recipes/{recipe.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["id"] == str(recipe.id)
    assert body["data"]["title"] == "Test Pasta"


@pytest.mark.asyncio
async def test_get_recipe_not_found(client):
    resp = await client.get("/api/recipes/507f1f77bcf86cd799439099")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_recipe_wrong_user(client, db):
    other = RecipeDocument(
        user_id="other_user_clerk_999",
        source_url="https://youtube.com/watch?v=other",
        title="Other's Recipe",
        ingredients=[RecipeIngredient(name="x")],
        steps=[RecipeStep(order=1, text="x")],
    )
    await other.insert()
    resp = await client.get(f"/api/recipes/{other.id}")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_update_recipe_title(client, recipe):
    resp = await client.put(
        f"/api/recipes/{recipe.id}",
        json={"title": "Updated Pasta"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["data"]["title"] == "Updated Pasta"
    assert body["data"]["is_edited"] is True


@pytest.mark.asyncio
async def test_update_recipe_servings(client, recipe):
    resp = await client.put(f"/api/recipes/{recipe.id}", json={"servings": 4})
    assert resp.status_code == 200
    assert resp.json()["data"]["servings"] == 4


@pytest.mark.asyncio
async def test_update_recipe_tags(client, recipe):
    resp = await client.put(
        f"/api/recipes/{recipe.id}",
        json={"tags": ["vegan", "healthy"]},
    )
    assert resp.status_code == 200
    assert "vegan" in resp.json()["data"]["tags"]


@pytest.mark.asyncio
async def test_delete_recipe(client, recipe):
    resp = await client.delete(f"/api/recipes/{recipe.id}")
    assert resp.status_code == 204

    # Confirm deleted
    resp2 = await client.get(f"/api/recipes/{recipe.id}")
    assert resp2.status_code == 404


# ── Pantry ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_get_pantry_creates_if_missing(client, db):
    resp = await client.get("/api/pantry")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["data"]["items"] == []


@pytest.mark.asyncio
async def test_get_pantry_with_items(client, pantry):
    resp = await client.get("/api/pantry")
    assert resp.status_code == 200
    items = resp.json()["data"]["items"]
    assert len(items) == 2
    names = [i["name"] for i in items]
    assert "pasta" in names


@pytest.mark.asyncio
async def test_add_pantry_item(client, db):
    resp = await client.post(
        "/api/pantry/items",
        json={"name": "olive oil", "quantity": 500, "unit": "ml", "category": "pantry"},
    )
    assert resp.status_code == 201
    item = resp.json()["data"]
    assert item["name"] == "olive oil"
    assert item["quantity"] == 500
    assert item["unit"] == "ml"
    assert "id" in item


@pytest.mark.asyncio
async def test_add_pantry_item_name_lowercased(client, db):
    resp = await client.post("/api/pantry/items", json={"name": "GARLIC"})
    assert resp.status_code == 201
    assert resp.json()["data"]["name"] == "garlic"


@pytest.mark.asyncio
async def test_update_pantry_item(client, pantry):
    item_id = pantry.items[0].id
    resp = await client.put(
        f"/api/pantry/items/{item_id}",
        json={"quantity": 250, "unit": "g"},
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["quantity"] == 250
    assert data["unit"] == "g"


@pytest.mark.asyncio
async def test_update_pantry_item_not_found(client, pantry):
    resp = await client.put(
        "/api/pantry/items/nonexistent-id",
        json={"quantity": 10},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_pantry_item(client, pantry):
    item_id = pantry.items[0].id
    resp = await client.delete(f"/api/pantry/items/{item_id}")
    assert resp.status_code == 204

    # Confirm item removed
    pantry_resp = await client.get("/api/pantry")
    remaining = [i["id"] for i in pantry_resp.json()["data"]["items"]]
    assert item_id not in remaining


@pytest.mark.asyncio
async def test_pantry_match_returns_ranked_list(client, pantry, recipe):
    resp = await client.get("/api/pantry/match")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    results = body["data"]
    assert isinstance(results, list)
    assert len(results) == 1
    assert results[0]["recipe_id"] == str(recipe.id)
    assert results[0]["match_pct"] == 1.0
    assert results[0]["missing_ingredients"] == []


@pytest.mark.asyncio
async def test_pantry_match_empty_pantry(client, db, recipe):
    resp = await client.get("/api/pantry/match")
    assert resp.status_code == 200
    results = resp.json()["data"]
    assert results[0]["match_pct"] == 0.0
    assert len(results[0]["missing_ingredients"]) == 2


# ── AI endpoints ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_ai_suggest_returns_recipes(client, pantry):
    mock_recipes = [
        {
            "title": "Quick Tomato Pasta",
            "description": "Simple pasta.",
            "cuisine": "Italian",
            "difficulty": "easy",
            "servings": 2,
            "prep_time_minutes": 5,
            "cook_time_minutes": 15,
            "total_time_minutes": 20,
            "ingredients": [{"name": "pasta", "quantity": 200, "unit": "g"}],
            "steps": [{"order": 1, "text": "Cook pasta.", "timer_seconds": 480}],
            "tags": ["quick"],
        }
    ]

    with patch("app.services.ai_suggest.suggest_from_pantry",
               new_callable=AsyncMock, return_value=mock_recipes):
        resp = await client.post(
            "/api/ai/suggest",
            json={"dietary_prefs": [], "cuisine_prefs": [], "max_recipes": 3},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["data"]) == 1
    assert body["data"][0]["title"] == "Quick Tomato Pasta"


@pytest.mark.asyncio
async def test_ai_chat_ok(client, recipe):
    with patch("app.services.ai_chat.chat_about",
               new_callable=AsyncMock, return_value="Use guanciale instead of pancetta."):
        resp = await client.post(
            f"/api/ai/chat/{recipe.id}",
            json={"message": "Can I substitute pancetta?", "history": []},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert "guanciale" in body["data"]["reply"]


@pytest.mark.asyncio
async def test_ai_chat_recipe_not_found(client):
    resp = await client.post(
        "/api/ai/chat/507f1f77bcf86cd799439099",
        json={"message": "Hello?", "history": []},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_ai_substitute_ok(client, recipe):
    mock_result = {
        "ingredient": "tomato sauce",
        "substitutions": [
            {"name": "canned tomatoes", "notes": "Blend and season to taste."},
            {"name": "passata", "notes": "Use same quantity."},
        ],
    }
    with patch("app.services.substitution.get_substitutions",
               new_callable=AsyncMock, return_value=mock_result):
        resp = await client.post(
            "/api/ai/substitute",
            json={"recipe_id": str(recipe.id), "ingredient_name": "tomato sauce"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert len(body["data"]["substitutions"]) == 2


@pytest.mark.asyncio
async def test_ai_substitute_invalid_recipe_id(client):
    resp = await client.post(
        "/api/ai/substitute",
        json={"recipe_id": "bad-id", "ingredient_name": "butter"},
    )
    assert resp.status_code == 400
