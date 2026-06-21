"""
tests/test_p2_features.py

Tests covering P2 gap fixes:
  1. Undo / edit history  — push_snapshot, POST /undo, GET /history
  2. Drag-to-reorder       — PUT /steps/reorder, PUT /ingredients/reorder
  3. Barcode scanner       — GET /api/pantry/barcode/:code (mocked OFF API)
"""

from __future__ import annotations

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
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)
from app.services.snapshot_service import MAX_SNAPSHOTS, pop_snapshot, push_snapshot

TEST_USER = "user_test_clerk_p2"


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


def make_recipe(title: str = "Test Pasta") -> RecipeDocument:
    return RecipeDocument(
        user_id=TEST_USER,
        source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        title=title,
        difficulty=Difficulty.EASY,
        servings=2,
        tags=["comfort-food"],
        ingredients=[
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="eggs", quantity=3),
            RecipeIngredient(name="pancetta", quantity=100, unit="g"),
        ],
        steps=[
            RecipeStep(order=1, text="Boil water."),
            RecipeStep(order=2, text="Fry pancetta."),
            RecipeStep(order=3, text="Mix eggs."),
        ],
        original_title=title,
        original_servings=2,
        original_ingredients=[RecipeIngredient(name="pasta", quantity=200, unit="g")],
        original_steps=[RecipeStep(order=1, text="Cook.")],
    )


# ── P2.1 — snapshot_service unit tests ────────────────────────────────────


class TestSnapshotService:

    @pytest.mark.asyncio
    async def test_push_snapshot_stores_current_state(self, db):
        recipe = make_recipe("Original Title")
        await recipe.insert()

        await push_snapshot(recipe, "Edited title")

        assert len(recipe.edit_snapshots) == 1
        snap = recipe.edit_snapshots[0]
        assert snap.label == "Edited title"
        assert snap.title == "Original Title"
        assert len(snap.ingredients) == 3

    @pytest.mark.asyncio
    async def test_push_snapshot_caps_at_max(self, db):
        recipe = make_recipe()
        await recipe.insert()

        for i in range(MAX_SNAPSHOTS + 3):
            await push_snapshot(recipe, f"Edit {i}")

        assert len(recipe.edit_snapshots) == MAX_SNAPSHOTS

    @pytest.mark.asyncio
    async def test_pop_snapshot_returns_last(self, db):
        recipe = make_recipe()
        await recipe.insert()

        await push_snapshot(recipe, "Edit 1")
        await push_snapshot(recipe, "Edit 2")

        snap = pop_snapshot(recipe)
        assert snap.label == "Edit 2"
        assert len(recipe.edit_snapshots) == 1

    @pytest.mark.asyncio
    async def test_pop_snapshot_on_empty_returns_none(self, db):
        recipe = make_recipe()
        await recipe.insert()
        assert pop_snapshot(recipe) is None

    @pytest.mark.asyncio
    async def test_push_snapshot_preserves_notes_and_tags(self, db):
        recipe = make_recipe()
        recipe.personal_notes = "Extra garlic!"
        recipe.tags = ["quick", "vegan"]
        await recipe.insert()

        await push_snapshot(recipe, "Test")
        snap = recipe.edit_snapshots[-1]

        assert snap.personal_notes == "Extra garlic!"
        assert "vegan" in snap.tags


# ── P2.1 — Undo endpoint ──────────────────────────────────────────────────


class TestUndoEndpoint:

    @pytest.mark.asyncio
    async def test_undo_restores_previous_title(self, client, db):
        recipe = make_recipe("Original Title")
        await recipe.insert()

        # Make an edit (triggers snapshot)
        await client.put(f"/api/recipes/{recipe.id}", json={"title": "New Title"})

        # Undo
        resp = await client.post(f"/api/recipes/{recipe.id}/undo")
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["title"] == "Original Title"
        assert "title" in body["undid"]

    @pytest.mark.asyncio
    async def test_undo_nothing_returns_404(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        resp = await client.post(f"/api/recipes/{recipe.id}/undo")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_multiple_undos(self, client, db):
        recipe = make_recipe("V1")
        await recipe.insert()

        await client.put(f"/api/recipes/{recipe.id}", json={"title": "V2"})
        await client.put(f"/api/recipes/{recipe.id}", json={"title": "V3"})

        await client.post(f"/api/recipes/{recipe.id}/undo")
        resp = await client.post(f"/api/recipes/{recipe.id}/undo")
        assert resp.json()["data"]["title"] == "V1"

    @pytest.mark.asyncio
    async def test_undo_restores_servings_and_ingredients(self, client, db):
        """Undoing a servings scale restores original quantities."""
        recipe = make_recipe()
        await recipe.insert()

        await client.put(f"/api/recipes/{recipe.id}", json={"servings": 4})
        resp = await client.post(f"/api/recipes/{recipe.id}/undo")

        data = resp.json()["data"]
        assert data["servings"] == 2
        ing_map = {i["name"]: i for i in data["ingredients"]}
        assert ing_map["pasta"]["quantity"] == pytest.approx(200.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_is_edited_cleared_when_all_undone(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        await client.put(f"/api/recipes/{recipe.id}", json={"title": "Changed"})
        resp = await client.post(f"/api/recipes/{recipe.id}/undo")

        assert resp.json()["data"]["is_edited"] is False


# ── P2.1 — History endpoint ───────────────────────────────────────────────


class TestHistoryEndpoint:

    @pytest.mark.asyncio
    async def test_history_empty_when_no_edits(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        resp = await client.get(f"/api/recipes/{recipe.id}/history")
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    @pytest.mark.asyncio
    async def test_history_returns_entries_newest_first(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        await client.put(f"/api/recipes/{recipe.id}", json={"title": "V2"})
        await client.put(f"/api/recipes/{recipe.id}", json={"title": "V3"})

        resp = await client.get(f"/api/recipes/{recipe.id}/history")
        entries = resp.json()["data"]
        assert len(entries) == 2
        # Newest (V3 edit) first
        assert "V3" in entries[0]["label"] or "title" in entries[0]["label"]

    @pytest.mark.asyncio
    async def test_history_has_required_fields(self, client, db):
        recipe = make_recipe()
        await recipe.insert()
        await client.put(f"/api/recipes/{recipe.id}", json={"title": "Changed"})

        resp = await client.get(f"/api/recipes/{recipe.id}/history")
        entry = resp.json()["data"][0]
        assert "snapshot_id" in entry
        assert "label" in entry
        assert "created_at" in entry


# ── P2.2 — Reorder ingredients ────────────────────────────────────────────


class TestReorderIngredients:

    @pytest.mark.asyncio
    async def test_reorder_ingredients(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        refreshed = await RecipeDocument.get(recipe.id)
        ing_ids = [i.id for i in refreshed.ingredients]
        new_order = [ing_ids[2], ing_ids[0], ing_ids[1]]   # pancetta, pasta, eggs

        resp = await client.put(
            f"/api/recipes/{recipe.id}/ingredients/reorder",
            json={"ids": new_order},
        )
        assert resp.status_code == 200
        result_names = [i["name"] for i in resp.json()["data"]["ingredients"]]
        assert result_names == ["pancetta", "pasta", "eggs"]

    @pytest.mark.asyncio
    async def test_reorder_creates_snapshot(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        refreshed = await RecipeDocument.get(recipe.id)
        ids = [i.id for i in refreshed.ingredients]
        await client.put(
            f"/api/recipes/{recipe.id}/ingredients/reorder",
            json={"ids": list(reversed(ids))},
        )

        updated = await RecipeDocument.get(recipe.id)
        assert len(updated.edit_snapshots) == 1
        assert updated.edit_snapshots[0].label == "Reordered ingredients"

    @pytest.mark.asyncio
    async def test_reorder_unknown_ids_ignored(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        resp = await client.put(
            f"/api/recipes/{recipe.id}/ingredients/reorder",
            json={"ids": ["fake-id-1", "fake-id-2"]},
        )
        # Unknown IDs ignored — original order preserved
        assert resp.status_code == 200
        result_names = [i["name"] for i in resp.json()["data"]["ingredients"]]
        assert result_names == ["pasta", "eggs", "pancetta"]


# ── P2.2 — Reorder steps ─────────────────────────────────────────────────


class TestReorderSteps:

    @pytest.mark.asyncio
    async def test_reorder_steps_and_renumber(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        refreshed = await RecipeDocument.get(recipe.id)
        step_ids = [s.id for s in refreshed.steps]
        new_order = [step_ids[2], step_ids[1], step_ids[0]]   # reverse

        resp = await client.put(
            f"/api/recipes/{recipe.id}/steps/reorder",
            json={"ids": new_order},
        )
        assert resp.status_code == 200
        steps = resp.json()["data"]["steps"]
        texts = [s["text"] for s in steps]
        assert texts == ["Mix eggs.", "Fry pancetta.", "Boil water."]
        # Check renumbering
        orders = [s["order"] for s in steps]
        assert orders == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_reorder_steps_creates_snapshot(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        refreshed = await RecipeDocument.get(recipe.id)
        ids = [s.id for s in refreshed.steps]
        await client.put(
            f"/api/recipes/{recipe.id}/steps/reorder",
            json={"ids": list(reversed(ids))},
        )

        updated = await RecipeDocument.get(recipe.id)
        assert any("Reordered steps" in s.label for s in updated.edit_snapshots)

    @pytest.mark.asyncio
    async def test_reorder_marks_recipe_as_edited(self, client, db):
        recipe = make_recipe()
        await recipe.insert()

        refreshed = await RecipeDocument.get(recipe.id)
        ids = [s.id for s in refreshed.steps]
        resp = await client.put(
            f"/api/recipes/{recipe.id}/steps/reorder",
            json={"ids": list(reversed(ids))},
        )
        assert resp.json()["data"]["is_edited"] is True


# ── P2.3 — Barcode lookup ─────────────────────────────────────────────────


class TestBarcodeLookup:

    @pytest.mark.asyncio
    async def test_valid_barcode_returns_product(self, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "status": 1,
            "product": {
                "product_name": "Organic Spaghetti 500g",
                "brands": "Barilla",
                "categories_tags": ["en:pastas"],
            },
        })

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.services.barcode_service.httpx.AsyncClient", return_value=mock_client):
            resp = await client.get("/api/pantry/barcode/8076802085738")

        assert resp.status_code == 200
        data = resp.json()["data"]
        assert "spaghetti" in data["name"].lower()
        assert data["category"] == "grains"
        assert data["brand"] == "Barilla"

    @pytest.mark.asyncio
    async def test_unknown_barcode_returns_404(self, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"status": 0, "product": {}})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.services.barcode_service.httpx.AsyncClient", return_value=mock_client):
            resp = await client.get("/api/pantry/barcode/0000000000000")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_non_digit_barcode_returns_400(self, client, db):
        resp = await client.get("/api/pantry/barcode/not-a-barcode")
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_off_api_failure_returns_404(self, client, db):
        """Open Food Facts network error → 404, not 500."""
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("app.services.barcode_service.httpx.AsyncClient", return_value=mock_client):
            resp = await client.get("/api/pantry/barcode/1234567890123")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_category_mapping_dairy(self, client, db):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "status": 1,
            "product": {
                "product_name": "Whole Milk",
                "brands": "Organic Valley",
                "categories_tags": ["en:milks", "en:dairy"],
            },
        })
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("app.services.barcode_service.httpx.AsyncClient", return_value=mock_client):
            resp = await client.get("/api/pantry/barcode/0093966000215")

        assert resp.json()["data"]["category"] == "dairy"


# ── P2.3 — barcode_service unit tests ────────────────────────────────────


class TestBarcodeService:

    @pytest.mark.asyncio
    async def test_clean_name_strips_weight(self):
        from app.services.barcode_service import _clean_name
        assert _clean_name("Spaghetti 500g Extra Fine") == "Spaghetti"

    @pytest.mark.asyncio
    async def test_clean_name_strips_whitespace(self):
        from app.services.barcode_service import _clean_name
        assert _clean_name("  Olive Oil  ") == "Olive Oil"

    def test_map_category_meat(self):
        from app.services.barcode_service import _map_category
        assert _map_category({"categories_tags": ["en:chicken-breasts"]}) == "meat"

    def test_map_category_fallback_other(self):
        from app.services.barcode_service import _map_category
        assert _map_category({"categories_tags": [], "product_name": "Mystery Item"}) == "other"
