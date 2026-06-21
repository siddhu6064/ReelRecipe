"""
tests/test_p3_features.py

Tests for P3 features:
  1. Community explore feed — list, trending, public by share token
  2. Visibility toggle       — make recipe public/private, share token generated
  3. Duplicate recipe         — copy to own cookbook, share_count incremented
  4. Recipe collections       — CRUD + add/remove recipes
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
from app.models.collection import RecipeCollection
from app.models.documents import (
    ALL_DOCUMENTS,
    Difficulty,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)

TEST_USER   = "user_test_p3_001"
OTHER_USER  = "user_other_p3_999"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _beanie(db):
    pass


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


def make_recipe(title: str, user_id: str = TEST_USER, is_public: bool = False) -> RecipeDocument:
    r = RecipeDocument(
        user_id=user_id,
        source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        title=title,
        cuisine="Italian",
        difficulty=Difficulty.EASY,
        servings=2,
        tags=["quick"],
        ingredients=[RecipeIngredient(name="pasta", quantity=200, unit="g")],
        steps=[RecipeStep(order=1, text="Cook pasta.")],
        is_public=is_public,
        original_title=title,
        original_servings=2,
        original_ingredients=[RecipeIngredient(name="pasta", quantity=200, unit="g")],
        original_steps=[RecipeStep(order=1, text="Cook pasta.")],
    )
    if is_public:
        r.share_token = f"tok_{title.lower().replace(' ', '_')}"
        r.view_count = 0
    return r


# ── P3.2 — Explore feed ───────────────────────────────────────────────────


class TestExploreFeed:

    @pytest.mark.asyncio
    async def test_explore_returns_only_public_recipes(self, client, db):
        await make_recipe("Public Pasta", is_public=True).insert()
        await make_recipe("Private Risotto", is_public=False).insert()

        resp = await client.get("/api/explore")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert "Public Pasta" in titles
        assert "Private Risotto" not in titles

    @pytest.mark.asyncio
    async def test_explore_empty_returns_zero(self, client, db):
        resp = await client.get("/api/explore")
        assert resp.status_code == 200
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_explore_includes_total_count(self, client, db):
        for i in range(5):
            await make_recipe(f"Recipe {i}", is_public=True).insert()

        resp = await client.get("/api/explore?limit=2")
        data = resp.json()["data"]
        assert data["total"] == 5
        assert len(data["recipes"]) == 2

    @pytest.mark.asyncio
    async def test_explore_filters_by_cuisine(self, client, db):
        italian = make_recipe("Pasta", is_public=True)
        italian.cuisine = "Italian"
        await italian.insert()

        japanese = make_recipe("Ramen", is_public=True)
        japanese.cuisine = "Japanese"
        await japanese.insert()

        resp = await client.get("/api/explore?cuisine=Italian")
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert "Pasta" in titles
        assert "Ramen" not in titles

    @pytest.mark.asyncio
    async def test_explore_trending_sorted_by_views(self, client, db):
        low = make_recipe("Low Views", is_public=True)
        low.view_count = 5
        await low.insert()

        high = make_recipe("High Views", is_public=True)
        high.view_count = 500
        await high.insert()

        resp = await client.get("/api/explore/trending")
        titles = [r["title"] for r in resp.json()["data"]]
        assert titles[0] == "High Views"

    @pytest.mark.asyncio
    async def test_public_recipe_by_token(self, client, db):
        recipe = make_recipe("Token Recipe", is_public=True)
        recipe.share_token = "abc123safe"
        await recipe.insert()

        resp = await client.get("/api/explore/recipe/abc123safe")
        assert resp.status_code == 200
        assert resp.json()["data"]["title"] == "Token Recipe"

    @pytest.mark.asyncio
    async def test_public_recipe_increments_view_count(self, client, db):
        recipe = make_recipe("View Test", is_public=True)
        recipe.share_token = "viewtoken1"
        recipe.view_count = 10
        await recipe.insert()

        await client.get("/api/explore/recipe/viewtoken1")
        updated = await RecipeDocument.get(recipe.id)
        assert updated.view_count == 11

    @pytest.mark.asyncio
    async def test_unknown_share_token_returns_404(self, client, db):
        resp = await client.get("/api/explore/recipe/nonexistent")
        assert resp.status_code == 404


# ── P3.2 — Visibility toggle ─────────────────────────────────────────────


class TestVisibility:

    @pytest.mark.asyncio
    async def test_make_recipe_public_generates_share_token(self, client, db):
        recipe = await make_recipe("My Pasta").insert()

        resp = await client.patch(
            f"/api/recipes/{recipe.id}/visibility",
            json={"is_public": True},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["is_public"] is True
        assert data["share_token"] is not None
        assert data["share_url"].startswith("https://reelrecipes.app/r/")

    @pytest.mark.asyncio
    async def test_make_recipe_private(self, client, db):
        recipe = make_recipe("Public Recipe", is_public=True)
        recipe.share_token = "existing_tok"
        await recipe.insert()

        resp = await client.patch(
            f"/api/recipes/{recipe.id}/visibility",
            json={"is_public": False},
        )
        data = resp.json()["data"]
        assert data["is_public"] is False
        assert data["share_url"] is None

    @pytest.mark.asyncio
    async def test_share_token_stable_on_re_publish(self, client, db):
        """Share token generated once — doesn't change on re-publish."""
        recipe = await make_recipe("Stable Token").insert()

        resp1 = await client.patch(f"/api/recipes/{recipe.id}/visibility", json={"is_public": True})
        token1 = resp1.json()["data"]["share_token"]

        await client.patch(f"/api/recipes/{recipe.id}/visibility", json={"is_public": False})
        resp2 = await client.patch(f"/api/recipes/{recipe.id}/visibility", json={"is_public": True})
        token2 = resp2.json()["data"]["share_token"]

        assert token1 == token2

    @pytest.mark.asyncio
    async def test_cannot_change_visibility_of_others_recipe(self, client, db):
        recipe = make_recipe("Theirs", user_id=OTHER_USER)
        await recipe.insert()

        resp = await client.patch(
            f"/api/recipes/{recipe.id}/visibility",
            json={"is_public": True},
        )
        assert resp.status_code == 403


# ── P3.2 — Duplicate ─────────────────────────────────────────────────────


class TestDuplicate:

    @pytest.mark.asyncio
    async def test_duplicate_public_recipe(self, client, db):
        original = make_recipe("Community Pasta", user_id=OTHER_USER, is_public=True)
        await original.insert()

        resp = await client.post(f"/api/recipes/{original.id}/duplicate")
        assert resp.status_code == 201
        copy = resp.json()["data"]
        assert copy["user_id"] == TEST_USER
        assert "copy" in copy["title"].lower()
        assert copy["is_public"] is False  # copies always start private

    @pytest.mark.asyncio
    async def test_duplicate_increments_share_count(self, client, db):
        original = make_recipe("Shared Recipe", user_id=OTHER_USER, is_public=True)
        original.share_count = 3
        await original.insert()

        await client.post(f"/api/recipes/{original.id}/duplicate")

        updated = await RecipeDocument.get(original.id)
        assert updated.share_count == 4

    @pytest.mark.asyncio
    async def test_duplicate_copies_ingredients_and_steps(self, client, db):
        original = make_recipe("Full Recipe", user_id=OTHER_USER, is_public=True)
        await original.insert()

        resp = await client.post(f"/api/recipes/{original.id}/duplicate")
        copy = resp.json()["data"]
        assert len(copy["ingredients"]) == 1
        assert copy["ingredients"][0]["name"] == "pasta"

    @pytest.mark.asyncio
    async def test_cannot_duplicate_private_recipe(self, client, db):
        private = make_recipe("Private", user_id=OTHER_USER, is_public=False)
        await private.insert()

        resp = await client.post(f"/api/recipes/{private.id}/duplicate")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_can_duplicate_own_recipe(self, client, db):
        """Users can duplicate their own recipes (public or private)."""
        own = await make_recipe("My Recipe", user_id=TEST_USER, is_public=False).insert()
        resp = await client.post(f"/api/recipes/{own.id}/duplicate")
        assert resp.status_code == 201


# ── P3.3 — Collections ────────────────────────────────────────────────────


class TestCollections:

    @pytest.mark.asyncio
    async def test_create_collection(self, client, db):
        resp = await client.post(
            "/api/collections",
            json={"name": "Weeknight Dinners", "emoji": "🍝"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["name"] == "Weeknight Dinners"
        assert data["emoji"] == "🍝"
        assert data["recipe_ids"] == []

    @pytest.mark.asyncio
    async def test_list_collections_empty(self, client, db):
        resp = await client.get("/api/collections")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_list_collections_sorted_by_name(self, client, db):
        await client.post("/api/collections", json={"name": "Zebra"})
        await client.post("/api/collections", json={"name": "Apple"})
        await client.post("/api/collections", json={"name": "Mango"})

        resp = await client.get("/api/collections")
        names = [c["name"] for c in resp.json()["data"]]
        assert names == sorted(names)

    @pytest.mark.asyncio
    async def test_duplicate_name_rejected(self, client, db):
        await client.post("/api/collections", json={"name": "Favourites"})
        resp = await client.post("/api/collections", json={"name": "Favourites"})
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_update_collection_name_and_emoji(self, client, db):
        create = await client.post("/api/collections", json={"name": "Old Name", "emoji": "📁"})
        col_id = create.json()["data"]["id"]

        resp = await client.put(f"/api/collections/{col_id}", json={"name": "New Name", "emoji": "🥗"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["name"] == "New Name"
        assert data["emoji"] == "🥗"

    @pytest.mark.asyncio
    async def test_delete_collection(self, client, db):
        create = await client.post("/api/collections", json={"name": "Temp"})
        col_id = create.json()["data"]["id"]

        resp = await client.delete(f"/api/collections/{col_id}")
        assert resp.status_code == 204

        check = await client.get("/api/collections")
        assert check.json()["data"] == []

    @pytest.mark.asyncio
    async def test_add_recipe_to_collection(self, client, db):
        recipe = await make_recipe("Pasta").insert()
        create = await client.post("/api/collections", json={"name": "Italian"})
        col_id = create.json()["data"]["id"]

        resp = await client.post(
            f"/api/collections/{col_id}/recipes",
            json={"recipe_id": str(recipe.id)},
        )
        assert resp.status_code == 201
        assert resp.json()["added"] is True
        assert str(recipe.id) in resp.json()["data"]["recipe_ids"]

    @pytest.mark.asyncio
    async def test_add_recipe_idempotent(self, client, db):
        recipe = await make_recipe("Pasta").insert()
        create = await client.post("/api/collections", json={"name": "Italian"})
        col_id = create.json()["data"]["id"]

        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(recipe.id)})
        resp = await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(recipe.id)})
        assert resp.json()["added"] is False
        assert resp.json()["data"]["recipe_ids"].count(str(recipe.id)) == 1

    @pytest.mark.asyncio
    async def test_remove_recipe_from_collection(self, client, db):
        recipe = await make_recipe("Pasta").insert()
        create = await client.post("/api/collections", json={"name": "Italian"})
        col_id = create.json()["data"]["id"]
        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(recipe.id)})

        resp = await client.delete(f"/api/collections/{col_id}/recipes/{recipe.id}")
        assert resp.status_code == 204

        check = await client.get(f"/api/collections/{col_id}/recipes")
        assert check.json()["data"]["recipes"] == []

    @pytest.mark.asyncio
    async def test_list_collection_recipes(self, client, db):
        r1 = await make_recipe("Pasta").insert()
        r2 = await make_recipe("Risotto").insert()
        create = await client.post("/api/collections", json={"name": "Italian"})
        col_id = create.json()["data"]["id"]
        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(r1.id)})
        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(r2.id)})

        resp = await client.get(f"/api/collections/{col_id}/recipes")
        assert resp.status_code == 200
        recipes = resp.json()["data"]["recipes"]
        titles = {r["title"] for r in recipes}
        assert titles == {"Pasta", "Risotto"}

    @pytest.mark.asyncio
    async def test_collection_recipe_count_in_list(self, client, db):
        r1 = await make_recipe("Pasta").insert()
        r2 = await make_recipe("Risotto").insert()
        create = await client.post("/api/collections", json={"name": "Italian"})
        col_id = create.json()["data"]["id"]
        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(r1.id)})
        await client.post(f"/api/collections/{col_id}/recipes", json={"recipe_id": str(r2.id)})

        resp = await client.get("/api/collections")
        col = resp.json()["data"][0]
        assert col["recipe_count"] == 2

    @pytest.mark.asyncio
    async def test_cannot_access_other_users_collection(self, client, db):
        other_col = RecipeCollection(user_id=OTHER_USER, name="Theirs")
        await other_col.insert()

        resp = await client.get(f"/api/collections/{other_col.id}/recipes")
        assert resp.status_code == 403
