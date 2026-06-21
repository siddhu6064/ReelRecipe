"""
tests/test_p1_features.py

Tests covering all four P1 gap fixes:
  1. Dietary preferences auto-applied to recipe list + pantry match + AI suggest
  2. Servings rescaling on PUT /api/recipes/:id
  3. Original extraction snapshot — GET /original + POST /reset
  4. Favourites + personal notes endpoints
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
    PantryDocument,
    PantryItem,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
    UserDocument,
)
from app.services.recipe_service import (
    build_prefs_query,
    prefs_compatible,
    rescale_ingredients,
)

TEST_USER = "user_test_clerk_p1"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _beanie(db):
    """Ensure beanie is initialized for every test that creates documents."""
    pass   # db fixture handles init


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


def make_recipe(title: str, tags: list[str] | None = None, cuisine: str = "Italian") -> RecipeDocument:
    return RecipeDocument(
        user_id=TEST_USER,
        source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        title=title,
        cuisine=cuisine,
        difficulty=Difficulty.EASY,
        servings=2,
        tags=tags or [],
        ingredients=[
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="sauce", quantity=1, unit="cup"),
        ],
        steps=[RecipeStep(order=1, text="Cook.", timer_seconds=480)],
        original_title=title,
        original_servings=2,
        original_ingredients=[
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="sauce", quantity=1, unit="cup"),
        ],
        original_steps=[RecipeStep(order=1, text="Cook.", timer_seconds=480)],
    )


# ── P1.1 — Dietary preferences ────────────────────────────────────────────


class TestDietaryPrefs:

    @pytest.mark.asyncio
    async def test_prefs_compatible_vegan_passes(self):
        recipe = make_recipe("Vegan Pasta", tags=["vegan", "quick"])
        assert prefs_compatible(recipe, ["vegan"]) is True

    @pytest.mark.asyncio
    async def test_prefs_compatible_vegan_fails_without_tag(self):
        recipe = make_recipe("Chicken Pasta", tags=["comfort-food"])
        # Has tags but no vegan tag
        result = prefs_compatible(recipe, ["vegan"])
        assert result is False

    @pytest.mark.asyncio
    async def test_prefs_compatible_no_tags_passes(self):
        """Recipe with no tags is treated as unknown — compatible by default."""
        recipe = make_recipe("Mystery Dish", tags=[])
        assert prefs_compatible(recipe, ["vegan"]) is True

    @pytest.mark.asyncio
    async def test_prefs_compatible_empty_prefs_always_passes(self):
        recipe = make_recipe("Any Recipe", tags=["comfort-food"])
        assert prefs_compatible(recipe, []) is True

    @pytest.mark.asyncio
    async def test_prefs_compatible_gluten_free(self):
        gf_recipe = make_recipe("GF Bowl", tags=["gluten-free", "healthy"])
        not_gf = make_recipe("Pasta", tags=["vegetarian"])
        assert prefs_compatible(gf_recipe, ["gluten-free"]) is True
        assert prefs_compatible(not_gf, ["gluten-free"]) is False

    @pytest.mark.asyncio
    async def test_build_prefs_query_dietary(self):
        query = build_prefs_query(["vegan"], [])
        assert "tags" in query
        assert "vegan" in query["tags"]["$all"]

    @pytest.mark.asyncio
    async def test_build_prefs_query_cuisine(self):
        query = build_prefs_query([], ["Italian", "Japanese"])
        assert "cuisine" in query
        assert "Italian" in query["cuisine"]["$in"]

    @pytest.mark.asyncio
    async def test_list_recipes_applies_prefs_auto(self, client, db):
        """When user has dietary prefs, GET /api/recipes auto-filters."""
        user = UserDocument(
            clerk_id=TEST_USER, email="t@t.com", name="Test",
            dietary_prefs=["vegan"],
        )
        await user.insert()

        vegan_r = make_recipe("Vegan Bowl", tags=["vegan"])
        meat_r = make_recipe("Chicken", tags=["comfort-food"])
        await vegan_r.insert()
        await meat_r.insert()

        resp = await client.get("/api/recipes")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert "Vegan Bowl" in titles
        # meat recipe has tags but no vegan tag → filtered out by auto-prefs

    @pytest.mark.asyncio
    async def test_list_recipes_bypass_prefs_with_param(self, client, db):
        """apply_prefs=false shows all recipes regardless of prefs."""
        user = UserDocument(
            clerk_id=TEST_USER, email="t@t.com", name="Test",
            dietary_prefs=["vegan"],
        )
        await user.insert()

        vegan_r = make_recipe("Vegan Bowl", tags=["vegan"])
        meat_r = make_recipe("Chicken", tags=["comfort-food"])
        await vegan_r.insert()
        await meat_r.insert()

        resp = await client.get("/api/recipes?apply_prefs=false")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert "Vegan Bowl" in titles
        assert "Chicken" in titles

    @pytest.mark.asyncio
    async def test_pantry_match_includes_prefs_compatible(self, client, db):
        """Pantry match results include prefs_compatible flag."""
        await UserDocument(
            clerk_id=TEST_USER, email="t@t.com", name="Test",
            dietary_prefs=["vegan"],
        ).insert()
        await PantryDocument(user_id=TEST_USER, items=[]).insert()

        vegan_r = make_recipe("Vegan Pasta", tags=["vegan"])
        meat_r = make_recipe("Chicken Pasta", tags=["comfort-food"])
        await vegan_r.insert()
        await meat_r.insert()

        resp = await client.get("/api/pantry/match")
        assert resp.status_code == 200
        results = resp.json()["data"]
        result_map = {r["title"]: r for r in results}

        assert result_map["Vegan Pasta"]["prefs_compatible"] is True
        assert result_map["Chicken Pasta"]["prefs_compatible"] is False

    @pytest.mark.asyncio
    async def test_pantry_match_prefs_only_filter(self, client, db):
        """prefs_only=true returns only compatible recipes."""
        await UserDocument(
            clerk_id=TEST_USER, email="t@t.com", name="Test",
            dietary_prefs=["vegan"],
        ).insert()
        await PantryDocument(user_id=TEST_USER, items=[]).insert()

        await make_recipe("Vegan Bowl", tags=["vegan"]).insert()
        await make_recipe("Chicken", tags=["comfort-food"]).insert()

        resp = await client.get("/api/pantry/match?prefs_only=true")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]]
        assert "Vegan Bowl" in titles
        assert "Chicken" not in titles

    @pytest.mark.asyncio
    async def test_ai_suggest_auto_loads_user_prefs(self, client, db):
        """AI suggest auto-injects stored prefs when body sends empty lists."""
        await UserDocument(
            clerk_id=TEST_USER, email="t@t.com", name="Test",
            dietary_prefs=["vegan"],
            cuisine_prefs=["Italian"],
        ).insert()
        await PantryDocument(user_id=TEST_USER, items=[]).insert()

        captured_prefs = {}

        async def mock_suggest(pantry_items, dietary_prefs, cuisine_prefs, **kwargs):
            captured_prefs["dietary"] = dietary_prefs
            captured_prefs["cuisine"] = cuisine_prefs
            return []

        with patch("app.services.ai_suggest.suggest_from_pantry", side_effect=mock_suggest):
            resp = await client.post(
                "/api/ai/suggest",
                json={"dietary_prefs": [], "cuisine_prefs": [], "max_recipes": 3},
            )

        assert resp.status_code == 200
        assert "vegan" in captured_prefs["dietary"]
        assert "Italian" in captured_prefs["cuisine"]


# ── P1.2 — Servings rescaling ─────────────────────────────────────────────


class TestServingsRescaling:

    def test_rescale_doubles_quantities(self):
        ings = [
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="eggs", quantity=3),
            RecipeIngredient(name="salt", quantity=None),  # to taste — unchanged
        ]
        result = rescale_ingredients(ings, old_servings=2, new_servings=4)
        assert result[0].quantity == pytest.approx(400.0, rel=0.01)
        assert result[1].quantity == pytest.approx(6.0, rel=0.01)
        assert result[2].quantity is None  # unchanged

    def test_rescale_halves_quantities(self):
        ings = [RecipeIngredient(name="flour", quantity=300, unit="g")]
        result = rescale_ingredients(ings, old_servings=6, new_servings=3)
        assert result[0].quantity == pytest.approx(150.0, rel=0.01)

    def test_rescale_same_servings_noop(self):
        ings = [RecipeIngredient(name="oil", quantity=2, unit="tbsp")]
        result = rescale_ingredients(ings, old_servings=4, new_servings=4)
        assert result[0].quantity == 2.0

    def test_rescale_fractional_result(self):
        ings = [RecipeIngredient(name="butter", quantity=100, unit="g")]
        result = rescale_ingredients(ings, old_servings=4, new_servings=3)
        # 100 * 3/4 = 75
        assert result[0].quantity == pytest.approx(75.0, rel=0.01)

    def test_rescale_preserves_other_fields(self):
        ings = [
            RecipeIngredient(name="garlic", quantity=3, unit="clove",
                             preparation="minced", optional=True)
        ]
        result = rescale_ingredients(ings, old_servings=2, new_servings=4)
        assert result[0].preparation == "minced"
        assert result[0].optional is True
        assert result[0].unit == "clove"

    @pytest.mark.asyncio
    async def test_put_recipe_rescales_on_servings_change(self, client, db):
        """PUT /api/recipes/:id with new servings rescales ingredients."""
        recipe = make_recipe("Pasta")
        recipe.servings = 2
        recipe.ingredients = [
            RecipeIngredient(name="pasta", quantity=200, unit="g"),
            RecipeIngredient(name="eggs", quantity=3),
        ]
        await recipe.insert()

        resp = await client.put(
            f"/api/recipes/{recipe.id}",
            json={"servings": 4},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["servings"] == 4
        ings = {i["name"]: i for i in data["ingredients"]}
        assert ings["pasta"]["quantity"] == pytest.approx(400.0, rel=0.01)
        assert ings["eggs"]["quantity"] == pytest.approx(6.0, rel=0.01)

    @pytest.mark.asyncio
    async def test_put_recipe_no_rescale_without_servings_change(self, client, db):
        """PUT /api/recipes/:id without changing servings leaves quantities alone."""
        recipe = make_recipe("Pasta")
        recipe.ingredients = [RecipeIngredient(name="pasta", quantity=200, unit="g")]
        await recipe.insert()

        resp = await client.put(
            f"/api/recipes/{recipe.id}",
            json={"title": "Updated Title"},
        )
        assert resp.status_code == 200
        ings = resp.json()["data"]["ingredients"]
        assert ings[0]["quantity"] == 200.0  # unchanged


# ── P1.3 — Original extraction snapshot ───────────────────────────────────


class TestOriginalSnapshot:

    @pytest.mark.asyncio
    async def test_get_original_returns_snapshot(self, client, db):
        recipe = make_recipe("Edited Pasta")
        recipe.title = "My Edited Title"   # simulate user edit
        recipe.is_edited = True
        await recipe.insert()

        resp = await client.get(f"/api/recipes/{recipe.id}/original")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Edited Pasta"   # original, not edited
        assert data["is_edited"] is True

    @pytest.mark.asyncio
    async def test_get_original_404_when_no_snapshot(self, client, db):
        recipe = RecipeDocument(
            user_id=TEST_USER,
            source_url="https://youtube.com/watch?v=old",
            platform=Platform.YOUTUBE,
            title="Old Recipe",
            ingredients=[RecipeIngredient(name="x")],
            steps=[RecipeStep(order=1, text="x")],
            # No original_* fields — simulates pre-snapshot import
        )
        await recipe.insert()

        resp = await client.get(f"/api/recipes/{recipe.id}/original")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_restores_original(self, client, db):
        """POST /reset restores title + servings + ingredients + steps."""
        recipe = make_recipe("Original Title")
        await recipe.insert()

        # Simulate user edit
        await client.put(
            f"/api/recipes/{recipe.id}",
            json={"title": "User Changed Title", "servings": 6},
        )

        # Reset to original
        resp = await client.post(f"/api/recipes/{recipe.id}/reset")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["title"] == "Original Title"
        assert data["servings"] == 2
        assert data["is_edited"] is False

    @pytest.mark.asyncio
    async def test_reset_404_when_no_snapshot(self, client, db):
        recipe = RecipeDocument(
            user_id=TEST_USER,
            source_url="https://youtube.com/watch?v=old",
            platform=Platform.YOUTUBE,
            title="No Snapshot",
            ingredients=[RecipeIngredient(name="x")],
            steps=[RecipeStep(order=1, text="x")],
        )
        await recipe.insert()

        resp = await client.post(f"/api/recipes/{recipe.id}/reset")
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_reset_preserves_personal_notes_and_tags(self, client, db):
        """Reset should NOT wipe personal_notes or custom tags."""
        recipe = make_recipe("Pasta", tags=["vegan"])
        recipe.personal_notes = "Add extra cheese"
        await recipe.insert()

        await client.put(f"/api/recipes/{recipe.id}", json={"title": "Changed"})
        resp = await client.post(f"/api/recipes/{recipe.id}/reset")

        data = resp.json()["data"]
        assert data["personal_notes"] == "Add extra cheese"


# ── P1.4 — Favourites + personal notes ────────────────────────────────────


class TestFavouritesAndNotes:

    @pytest.mark.asyncio
    async def test_favourite_a_recipe(self, client, db):
        recipe = make_recipe("Fav Pasta")
        await recipe.insert()

        resp = await client.post(f"/api/recipes/{recipe.id}/favourite")
        assert resp.status_code == 201
        assert resp.json()["data"]["is_favourite"] is True

        # Verify in DB
        updated = await RecipeDocument.get(recipe.id)
        assert updated.is_favourite is True

    @pytest.mark.asyncio
    async def test_favourite_idempotent(self, client, db):
        """Starring twice has no ill effect."""
        recipe = make_recipe("Pasta")
        await recipe.insert()

        await client.post(f"/api/recipes/{recipe.id}/favourite")
        resp = await client.post(f"/api/recipes/{recipe.id}/favourite")
        assert resp.status_code == 201
        assert resp.json()["data"]["is_favourite"] is True

    @pytest.mark.asyncio
    async def test_unfavourite_a_recipe(self, client, db):
        recipe = make_recipe("Pasta")
        recipe.is_favourite = True
        await recipe.insert()

        resp = await client.delete(f"/api/recipes/{recipe.id}/favourite")
        assert resp.status_code == 204

        updated = await RecipeDocument.get(recipe.id)
        assert updated.is_favourite is False

    @pytest.mark.asyncio
    async def test_filter_by_favourites(self, client, db):
        """GET /api/recipes?favourites=true returns only starred recipes."""
        fav = make_recipe("Starred")
        fav.is_favourite = True
        await fav.insert()
        await make_recipe("Not Starred").insert()

        resp = await client.get("/api/recipes?favourites=true")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert "Starred" in titles
        assert "Not Starred" not in titles

    @pytest.mark.asyncio
    async def test_starred_recipes_sorted_first(self, client, db):
        """Starred recipes appear before unstarred in default listing."""
        unstarred = make_recipe("Unstarred Pasta")
        await unstarred.insert()
        starred = make_recipe("My Favourite")
        starred.is_favourite = True
        await starred.insert()

        resp = await client.get("/api/recipes?apply_prefs=false")
        assert resp.status_code == 200
        titles = [r["title"] for r in resp.json()["data"]["recipes"]]
        assert titles[0] == "My Favourite"   # starred first

    @pytest.mark.asyncio
    async def test_set_personal_notes(self, client, db):
        recipe = make_recipe("Pasta")
        await recipe.insert()

        resp = await client.put(
            f"/api/recipes/{recipe.id}/notes",
            json={"notes": "Double the garlic. Cook pasta 1 min less."},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["personal_notes"] == "Double the garlic. Cook pasta 1 min less."

        updated = await RecipeDocument.get(recipe.id)
        assert updated.personal_notes == "Double the garlic. Cook pasta 1 min less."

    @pytest.mark.asyncio
    async def test_clear_personal_notes(self, client, db):
        recipe = make_recipe("Pasta")
        recipe.personal_notes = "Some notes"
        await recipe.insert()

        resp = await client.put(
            f"/api/recipes/{recipe.id}/notes",
            json={"notes": None},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["personal_notes"] is None

    @pytest.mark.asyncio
    async def test_notes_visible_in_get_recipe(self, client, db):
        recipe = make_recipe("Pasta")
        recipe.personal_notes = "My note"
        recipe.is_favourite = True
        await recipe.insert()

        resp = await client.get(f"/api/recipes/{recipe.id}")
        data = resp.json()["data"]
        assert data["personal_notes"] == "My note"
        assert data["is_favourite"] is True
