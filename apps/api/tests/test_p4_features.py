"""
tests/test_p4_features.py

Tests for P4 features:
  1. PDF export       — GET /api/recipes/:id/export/pdf
  2. Cook session log — POST /api/recipes/:id/cook-session
  3. User stats       — GET /api/users/me/stats
  4. Recipe cost      — GET /api/recipes/:id/cost + pantry prices
  5. Collaboration    — invite, accept, can-edit, role change
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
    ALL_DOCUMENTS, CollaboratorEntry, CollaboratorRole,
    Difficulty, PantryDocument, PantryItem, Platform,
    RecipeDocument, RecipeIngredient, RecipeStep,
)

TEST_USER  = "user_test_p4_001"
OTHER_USER = "user_test_p4_002"


# ── Fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()

@pytest_asyncio.fixture(autouse=True)
async def _beanie(db): pass

@pytest_asyncio.fixture
async def client(db):
    from app.auth.clerk import optional_auth, require_auth
    app = create_app()
    async def _auth(): return TEST_USER
    app.dependency_overrides[require_auth] = _auth
    app.dependency_overrides[optional_auth] = _auth
    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            yield ac
    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def other_client(db):
    from app.auth.clerk import optional_auth, require_auth
    app = create_app()
    async def _auth(): return OTHER_USER
    app.dependency_overrides[require_auth] = _auth
    app.dependency_overrides[optional_auth] = _auth
    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            yield ac
    app.dependency_overrides.clear()


def make_recipe(user_id: str = TEST_USER, public: bool = False) -> RecipeDocument:
    return RecipeDocument(
        user_id=user_id, source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE, title="Test Carbonara",
        difficulty=Difficulty.MEDIUM, servings=2, tags=["comfort-food"],
        cuisine="Italian",
        ingredients=[
            RecipeIngredient(name="spaghetti", quantity=200, unit="g"),
            RecipeIngredient(name="eggs", quantity=3),
            RecipeIngredient(name="pancetta", quantity=100, unit="g"),
        ],
        steps=[
            RecipeStep(order=1, text="Boil pasta in salted water.", timer_seconds=480),
            RecipeStep(order=2, text="Fry pancetta until crispy."),
            RecipeStep(order=3, text="Combine with egg mixture off the heat."),
        ],
        original_title="Test Carbonara", original_servings=2,
        original_ingredients=[RecipeIngredient(name="spaghetti", quantity=200, unit="g")],
        original_steps=[RecipeStep(order=1, text="Cook.")],
        is_public=public,
    )


# ── P4.1 — PDF export ─────────────────────────────────────────────────────

class TestPDFExport:

    @pytest.mark.asyncio
    async def test_export_returns_pdf_bytes(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.get(f"/api/recipes/{recipe.id}/export/pdf")
        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 1000          # real PDF, not empty
        assert resp.content[:4] == b"%PDF"        # PDF magic bytes

    @pytest.mark.asyncio
    async def test_export_pdf_has_download_header(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.get(f"/api/recipes/{recipe.id}/export/pdf")
        assert "attachment" in resp.headers.get("content-disposition", "")

    @pytest.mark.asyncio
    async def test_export_public_recipe_accessible_by_others(self, other_client, db):
        recipe = make_recipe(user_id=TEST_USER, public=True); await recipe.insert()
        resp = await other_client.get(f"/api/recipes/{recipe.id}/export/pdf")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_export_private_recipe_blocked_for_others(self, other_client, db):
        recipe = make_recipe(user_id=TEST_USER, public=False); await recipe.insert()
        resp = await other_client.get(f"/api/recipes/{recipe.id}/export/pdf")
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pdf_service_generates_valid_pdf(self):
        from app.services.pdf_service import generate_recipe_pdf
        recipe = make_recipe()
        # Add nutrition for full coverage
        from app.models.documents import NutritionInfo
        recipe.nutrition = NutritionInfo(calories=450, protein_g=22, carbs_g=60, fat_g=15)
        pdf_bytes = generate_recipe_pdf(recipe)
        assert isinstance(pdf_bytes, bytes)
        assert pdf_bytes[:4] == b"%PDF"
        assert len(pdf_bytes) > 500


# ── P4.1 — Cook session log ────────────────────────────────────────────────

class TestCookSession:

    @pytest.mark.asyncio
    async def test_log_cook_session(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.post(f"/api/recipes/{recipe.id}/cook-session")
        assert resp.status_code == 201
        assert resp.json()["data"]["total_sessions"] == 1

    @pytest.mark.asyncio
    async def test_multiple_cook_sessions_accumulate(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        await client.post(f"/api/recipes/{recipe.id}/cook-session")
        await client.post(f"/api/recipes/{recipe.id}/cook-session")
        resp = await client.post(f"/api/recipes/{recipe.id}/cook-session")
        assert resp.json()["data"]["total_sessions"] == 3

    @pytest.mark.asyncio
    async def test_cook_session_stored_in_cook_log(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        await client.post(f"/api/recipes/{recipe.id}/cook-session")
        updated = await RecipeDocument.get(recipe.id)
        assert len(updated.cook_log) == 1


# ── P4.2 — User stats ─────────────────────────────────────────────────────

class TestUserStats:

    @pytest.mark.asyncio
    async def test_stats_empty_for_new_user(self, client, db):
        resp = await client.get("/api/users/me/stats")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_recipes"] == 0
        assert data["cook_sessions"] == 0

    @pytest.mark.asyncio
    async def test_stats_counts_recipes(self, client, db):
        for t in ["Pasta", "Pizza", "Risotto"]:
            r = make_recipe(); r.title = t; await r.insert()
        resp = await client.get("/api/users/me/stats")
        assert resp.json()["data"]["total_recipes"] == 3

    @pytest.mark.asyncio
    async def test_stats_counts_unique_cuisines(self, client, db):
        for cuisine in ["Italian", "Japanese", "Italian", "Mexican"]:
            r = make_recipe(); r.cuisine = cuisine; await r.insert()
        resp = await client.get("/api/users/me/stats")
        data = resp.json()["data"]
        assert data["unique_cuisines"] == 3   # Italian, Japanese, Mexican

    @pytest.mark.asyncio
    async def test_stats_counts_cook_sessions(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        await client.post(f"/api/recipes/{recipe.id}/cook-session")
        await client.post(f"/api/recipes/{recipe.id}/cook-session")
        resp = await client.get("/api/users/me/stats")
        assert resp.json()["data"]["cook_sessions"] == 2

    @pytest.mark.asyncio
    async def test_stats_finds_favourite_ingredient(self, client, db):
        for _ in range(3):
            r = make_recipe(); await r.insert()   # all have "spaghetti"
        resp = await client.get("/api/users/me/stats")
        assert resp.json()["data"]["favourite_ingredient"] is not None

    @pytest.mark.asyncio
    async def test_stats_has_all_required_fields(self, client, db):
        resp = await client.get("/api/users/me/stats")
        data = resp.json()["data"]
        required = {
            "total_recipes", "public_recipes", "unique_cuisines", "top_cuisines",
            "top_tags", "favourite_ingredient", "cook_sessions",
            "recipes_this_month", "recipes_this_year",
            "avg_cook_time_minutes", "current_streak_days", "generated_at",
        }
        assert required <= set(data.keys())


# ── P4.3 — Recipe cost ────────────────────────────────────────────────────

class TestRecipeCost:

    @pytest.mark.asyncio
    async def test_cost_with_no_prices_returns_none_total(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        await PantryDocument(user_id=TEST_USER, items=[]).insert()
        resp = await client.get(f"/api/recipes/{recipe.id}/cost")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_cost"] is None
        assert data["coverage_pct"] == 0.0

    @pytest.mark.asyncio
    async def test_cost_calculates_from_pantry_prices(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[
                PantryItem(name="spaghetti", quantity=500, unit="g", estimated_cost_per_unit=0.01),
                PantryItem(name="eggs", quantity=12, estimated_cost_per_unit=0.30),
            ],
        )
        await pantry.insert()
        resp = await client.get(f"/api/recipes/{recipe.id}/cost")
        data = resp.json()["data"]
        assert data["total_cost"] is not None
        assert data["total_cost"] > 0
        assert data["coverage_pct"] > 0

    @pytest.mark.asyncio
    async def test_price_update_endpoint(self, client, db):
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[PantryItem(name="pasta", quantity=500, unit="g")],
        )
        await pantry.insert()
        item_id = pantry.items[0].id

        resp = await client.put(
            f"/api/pantry/items/{item_id}/price",
            json={"estimated_cost_per_unit": 0.015},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["estimated_cost_per_unit"] == 0.015

    @pytest.mark.asyncio
    async def test_price_clear(self, client, db):
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[PantryItem(name="pasta", estimated_cost_per_unit=0.01)],
        )
        await pantry.insert()
        item_id = pantry.items[0].id

        resp = await client.put(
            f"/api/pantry/items/{item_id}/price",
            json={"estimated_cost_per_unit": None},
        )
        assert resp.json()["data"]["estimated_cost_per_unit"] is None


# ── P4.4 — Collaboration ─────────────────────────────────────────────────

class TestCollaboration:

    @pytest.mark.asyncio
    async def test_create_invite(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.post(
            f"/api/recipes/{recipe.id}/invite",
            json={"role": "viewer"},
        )
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert "invite_token" in data
        assert "invite_url" in data
        assert data["role"] == "viewer"

    @pytest.mark.asyncio
    async def test_create_editor_invite(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.post(
            f"/api/recipes/{recipe.id}/invite",
            json={"role": "editor"},
        )
        assert resp.json()["data"]["role"] == "editor"

    @pytest.mark.asyncio
    async def test_accept_invite(self, client, other_client, db):
        recipe = make_recipe(); await recipe.insert()

        # Owner creates invite
        invite_resp = await client.post(
            f"/api/recipes/{recipe.id}/invite",
            json={"role": "viewer"},
        )
        token = invite_resp.json()["data"]["invite_token"]

        # Other user accepts
        accept_resp = await other_client.post(f"/api/invites/accept/{token}")
        assert accept_resp.status_code == 200
        assert accept_resp.json()["data"]["recipe_id"] == str(recipe.id)

    @pytest.mark.asyncio
    async def test_can_edit_returns_true_for_owner(self, client, db):
        recipe = make_recipe(); await recipe.insert()
        resp = await client.get(f"/api/recipes/{recipe.id}/can-edit")
        assert resp.json()["data"]["can_edit"] is True
        assert resp.json()["data"]["role"] == "owner"

    @pytest.mark.asyncio
    async def test_can_edit_returns_false_for_stranger(self, other_client, db):
        recipe = make_recipe(public=True); await recipe.insert()
        resp = await other_client.get(f"/api/recipes/{recipe.id}/can-edit")
        assert resp.json()["data"]["can_edit"] is False

    @pytest.mark.asyncio
    async def test_can_edit_true_for_editor_collaborator(self, client, other_client, db):
        recipe = make_recipe(); await recipe.insert()

        invite_resp = await client.post(
            f"/api/recipes/{recipe.id}/invite", json={"role": "editor"}
        )
        token = invite_resp.json()["data"]["invite_token"]
        await other_client.post(f"/api/invites/accept/{token}")

        resp = await other_client.get(f"/api/recipes/{recipe.id}/can-edit")
        assert resp.json()["data"]["can_edit"] is True

    @pytest.mark.asyncio
    async def test_change_collaborator_role(self, client, other_client, db):
        recipe = make_recipe(); await recipe.insert()
        invite_resp = await client.post(
            f"/api/recipes/{recipe.id}/invite", json={"role": "viewer"}
        )
        token = invite_resp.json()["data"]["invite_token"]
        await other_client.post(f"/api/invites/accept/{token}")

        resp = await client.patch(
            f"/api/recipes/{recipe.id}/collaborators/{OTHER_USER}",
            json={"role": "editor"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["role"] == "editor"

    @pytest.mark.asyncio
    async def test_remove_collaborator(self, client, other_client, db):
        recipe = make_recipe(); await recipe.insert()
        invite_resp = await client.post(
            f"/api/recipes/{recipe.id}/invite", json={"role": "viewer"}
        )
        token = invite_resp.json()["data"]["invite_token"]
        await other_client.post(f"/api/invites/accept/{token}")

        resp = await client.delete(
            f"/api/recipes/{recipe.id}/collaborators/{OTHER_USER}"
        )
        assert resp.status_code == 204

        updated = await RecipeDocument.get(recipe.id)
        assert not any(c.user_id == OTHER_USER and c.accepted for c in updated.collaborators)

    @pytest.mark.asyncio
    async def test_invalid_invite_token_returns_404(self, client, db):
        resp = await client.post("/api/invites/accept/bad-token-xyz")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_list_collaborators(self, client, other_client, db):
        recipe = make_recipe(); await recipe.insert()
        invite_resp = await client.post(
            f"/api/recipes/{recipe.id}/invite", json={"role": "viewer"}
        )
        token = invite_resp.json()["data"]["invite_token"]
        await other_client.post(f"/api/invites/accept/{token}")

        resp = await client.get(f"/api/recipes/{recipe.id}/collaborators")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert len(data["accepted"]) == 1
        assert data["accepted"][0]["user_id"] == OTHER_USER
