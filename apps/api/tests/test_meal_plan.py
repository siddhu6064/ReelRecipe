"""
tests/test_meal_plan.py

Tests for the meal plan router — CRUD + shopping list generation.
"""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import create_app
from app.models.documents import (
    ALL_DOCUMENTS,
    Difficulty,
    PantryDocument,
    PantryItem,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)
from app.models.meal_plan import MealPlanDocument, MealSlot

TEST_USER = "user_test_clerk_001"


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

    async def _fake_auth() -> str:
        return TEST_USER

    app.dependency_overrides[require_auth] = _fake_auth
    app.dependency_overrides[optional_auth] = _fake_auth

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
        title="Pasta Carbonara",
        difficulty=Difficulty.MEDIUM,
        servings=2,
        ingredients=[
            RecipeIngredient(name="spaghetti", quantity=200, unit="g"),
            RecipeIngredient(name="pancetta", quantity=100, unit="g"),
            RecipeIngredient(name="eggs", quantity=3),
        ],
        steps=[RecipeStep(order=1, text="Cook pasta.", timer_seconds=480)],
        tags=["comfort-food"],
    )
    await r.insert()
    return r


@pytest_asyncio.fixture
async def plan(db) -> MealPlanDocument:
    p = MealPlanDocument(user_id=TEST_USER, title="My Week")
    await p.insert()
    return p


# ── Create / list plans ────────────────────────────────────────────────────


class TestMealPlanCRUD:

    @pytest.mark.asyncio
    async def test_create_plan(self, client, db):
        resp = await client.post(
            "/api/meal-plans",
            json={"title": "Healthy Week", "week_start_date": "2025-03-10"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["title"] == "Healthy Week"
        assert data["week_start_date"] == "2025-03-10"
        assert data["is_active"] is True
        assert len(data["days"]) == 7

    @pytest.mark.asyncio
    async def test_list_plans_empty(self, client, db):
        resp = await client.get("/api/meal-plans")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_list_plans_returns_all_for_user(self, client, db):
        await client.post("/api/meal-plans", json={"title": "Plan A"})
        await client.post("/api/meal-plans", json={"title": "Plan B"})
        resp = await client.get("/api/meal-plans")
        assert resp.status_code == 200
        assert len(resp.json()["data"]) == 2

    @pytest.mark.asyncio
    async def test_get_plan_by_id(self, client, plan):
        resp = await client.get(f"/api/meal-plans/{plan.id}")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "My Week"

    @pytest.mark.asyncio
    async def test_get_plan_not_found(self, client, db):
        resp = await client.get("/api/meal-plans/507f1f77bcf86cd799439000")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_active_plan(self, client, plan):
        resp = await client.get("/api/meal-plans/active")
        assert resp.status_code == 200
        assert resp.json()["data"]["is_active"] is True

    @pytest.mark.asyncio
    async def test_get_active_plan_404_when_none(self, client, db):
        resp = await client.get("/api/meal-plans/active")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_create_plan_deactivates_previous(self, client, db):
        resp1 = await client.post("/api/meal-plans", json={"title": "Old Plan"})
        plan1_id = resp1.json()["data"]["id"]

        await client.post("/api/meal-plans", json={"title": "New Plan"})

        resp_old = await client.get(f"/api/meal-plans/{plan1_id}")
        assert resp_old.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_delete_plan(self, client, plan):
        resp = await client.delete(f"/api/meal-plans/{plan.id}")
        assert resp.status_code == 204

        resp2 = await client.get(f"/api/meal-plans/{plan.id}")
        assert resp2.status_code == 404

    @pytest.mark.asyncio
    async def test_get_plan_wrong_user(self, client, db):
        other_plan = MealPlanDocument(user_id="other_user_999", title="Theirs")
        await other_plan.insert()
        resp = await client.get(f"/api/meal-plans/{other_plan.id}")
        assert resp.status_code == 403


# ── Add / remove meals ─────────────────────────────────────────────────────


class TestMealOperations:

    @pytest.mark.asyncio
    async def test_add_meal_to_day(self, client, plan, recipe):
        resp = await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={
                "day_index": 0,
                "recipe_id": str(recipe.id),
                "slot": "dinner",
            },
        )
        assert resp.status_code == 200
        days = resp.json()["data"]["days"]
        monday = next(d for d in days if d["day_index"] == 0)
        assert len(monday["meals"]) == 1
        assert monday["meals"][0]["recipe_title"] == "Pasta Carbonara"
        assert monday["meals"][0]["slot"] == "dinner"

    @pytest.mark.asyncio
    async def test_add_multiple_meals_same_day(self, client, plan, recipe):
        for slot in ("breakfast", "lunch", "dinner"):
            await client.post(
                f"/api/meal-plans/{plan.id}/meals",
                json={"day_index": 2, "recipe_id": str(recipe.id), "slot": slot},
            )
        resp = await client.get(f"/api/meal-plans/{plan.id}")
        wednesday = next(d for d in resp.json()["data"]["days"] if d["day_index"] == 2)
        assert len(wednesday["meals"]) == 3

    @pytest.mark.asyncio
    async def test_add_meal_with_servings_override(self, client, plan, recipe):
        resp = await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 4, "recipe_id": str(recipe.id), "servings_override": 4},
        )
        friday = next(d for d in resp.json()["data"]["days"] if d["day_index"] == 4)
        assert friday["meals"][0]["servings_override"] == 4

    @pytest.mark.asyncio
    async def test_add_meal_invalid_day_index(self, client, plan, recipe):
        resp = await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 8, "recipe_id": str(recipe.id)},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_add_meal_recipe_not_found(self, client, plan):
        resp = await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 0, "recipe_id": "507f1f77bcf86cd799439099"},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_meal(self, client, plan, recipe):
        # Add a meal first
        add_resp = await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 1, "recipe_id": str(recipe.id), "slot": "lunch"},
        )
        meal_id = add_resp.json()["data"]["days"][1]["meals"][0]["id"]

        # Remove it
        resp = await client.request(
            "DELETE",
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 1, "meal_id": meal_id},
        )
        assert resp.status_code == 204

        # Verify removed
        resp2 = await client.get(f"/api/meal-plans/{plan.id}")
        tuesday = next(d for d in resp2.json()["data"]["days"] if d["day_index"] == 1)
        assert tuesday["meals"] == []


# ── Shopping list ──────────────────────────────────────────────────────────


class TestShoppingList:

    @pytest.mark.asyncio
    async def test_empty_plan_returns_no_items(self, client, plan):
        resp = await client.get(f"/api/meal-plans/{plan.id}/shopping")
        assert resp.status_code == 200
        body = resp.json()["data"]
        assert body["items"] == []
        assert body["total_count"] == 0

    @pytest.mark.asyncio
    async def test_shopping_list_excludes_pantry_items(self, client, plan, recipe, db):
        # User has spaghetti in pantry but not pancetta
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[PantryItem(name="spaghetti", quantity=500, unit="g")],
        )
        await pantry.insert()

        await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 0, "recipe_id": str(recipe.id)},
        )

        resp = await client.get(f"/api/meal-plans/{plan.id}/shopping")
        items = resp.json()["data"]["items"]
        names = [i["name"].lower() for i in items]
        assert "spaghetti" not in names    # have it
        assert "pancetta" in names         # need it
        assert "eggs" in names             # need it

    @pytest.mark.asyncio
    async def test_shopping_list_all_in_pantry(self, client, plan, recipe, db):
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[
                PantryItem(name="spaghetti"),
                PantryItem(name="pancetta"),
                PantryItem(name="eggs"),
            ],
        )
        await pantry.insert()

        await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 0, "recipe_id": str(recipe.id)},
        )

        resp = await client.get(f"/api/meal-plans/{plan.id}/shopping")
        assert resp.json()["data"]["total_count"] == 0

    @pytest.mark.asyncio
    async def test_shopping_list_deduplicates_across_days(self, client, plan, recipe, db):
        """Same ingredient needed on Mon and Wed appears only once."""
        for day in (0, 2):
            await client.post(
                f"/api/meal-plans/{plan.id}/meals",
                json={"day_index": day, "recipe_id": str(recipe.id)},
            )

        resp = await client.get(f"/api/meal-plans/{plan.id}/shopping")
        items = resp.json()["data"]["items"]
        names = [i["name"].lower() for i in items]
        # No duplicates
        assert len(names) == len(set(names))

    @pytest.mark.asyncio
    async def test_shopping_list_shows_which_recipes_need_ingredient(self, client, plan, recipe, db):
        await client.post(
            f"/api/meal-plans/{plan.id}/meals",
            json={"day_index": 0, "recipe_id": str(recipe.id)},
        )
        resp = await client.get(f"/api/meal-plans/{plan.id}/shopping")
        items = resp.json()["data"]["items"]
        # Each item should list which recipes need it
        for item in items:
            assert "needed_for" in item
            assert isinstance(item["needed_for"], list)
            assert len(item["needed_for"]) >= 1
