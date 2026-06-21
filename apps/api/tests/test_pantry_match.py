"""
tests/test_pantry_match.py

Unit tests for pantry_match.py — fuzzy matching and % scoring.
Uses mongomock-motor so RecipeDocument can be instantiated.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from beanie import init_beanie
from mongomock_motor import AsyncMongoMockClient

from app.models.documents import (
    ALL_DOCUMENTS,
    Difficulty,
    PantryItem,
    Platform,
    RecipeDocument,
    RecipeIngredient,
    RecipeStep,
)
from app.services.pantry_match import MATCH_THRESHOLD, _best_match, score_recipe, score_recipes


@pytest_asyncio.fixture(autouse=True)
async def beanie_init():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


def make_pantry(names: list[str]) -> list[PantryItem]:
    return [PantryItem(name=n) for n in names]


def make_recipe(ingredients: list[str], optional: list[str] | None = None) -> RecipeDocument:
    optional = optional or []
    return RecipeDocument(
        user_id="clerk_001",
        source_url="https://youtube.com/watch?v=abc",
        title="Test Recipe",
        difficulty=Difficulty.EASY,
        ingredients=[
            RecipeIngredient(name=ing, optional=(ing in optional))
            for ing in ingredients
        ],
        steps=[RecipeStep(order=1, text="Cook it.")],
    )


# ── _best_match ────────────────────────────────────────────────────────────


def test_exact_match():
    pantry = make_pantry(["garlic", "onion", "tomato"])
    name, score = _best_match("garlic", pantry)
    assert name == "garlic"
    assert score == 100.0


def test_partial_match_cloves():
    pantry = make_pantry(["garlic"])
    name, score = _best_match("garlic cloves", pantry)
    assert name == "garlic"
    assert score >= MATCH_THRESHOLD


def test_no_match_below_threshold():
    pantry = make_pantry(["flour", "sugar"])
    name, score = _best_match("salmon", pantry)
    assert name is None
    assert score == 0.0


def test_empty_pantry():
    name, score = _best_match("olive oil", [])
    assert name is None
    assert score == 0.0


def test_case_insensitive():
    pantry = make_pantry(["Olive Oil"])
    name, score = _best_match("olive oil", pantry)
    assert name is not None
    assert score >= MATCH_THRESHOLD


# ── score_recipe ───────────────────────────────────────────────────────────


def test_perfect_match():
    pantry = make_pantry(["spaghetti", "eggs", "pancetta", "pecorino", "black pepper"])
    recipe = make_recipe(["spaghetti", "eggs", "pancetta", "pecorino", "black pepper"])
    result = score_recipe(pantry, recipe)
    assert result["match_pct"] == 1.0
    assert result["missing_ingredients"] == []


def test_zero_match():
    pantry = make_pantry(["flour", "sugar", "butter"])
    recipe = make_recipe(["salmon", "miso", "ginger", "soy sauce"])
    result = score_recipe(pantry, recipe)
    assert result["match_pct"] == 0.0
    assert len(result["missing_ingredients"]) == 4


def test_partial_match():
    pantry = make_pantry(["pasta", "tomato sauce"])
    recipe = make_recipe(["pasta", "tomato sauce", "mozzarella", "basil"])
    result = score_recipe(pantry, recipe)
    assert result["match_pct"] == pytest.approx(0.5, abs=0.01)
    assert "pasta" in result["matched_ingredients"]
    assert "mozzarella" in result["missing_ingredients"]


def test_optional_ingredients_excluded():
    pantry = make_pantry(["pasta", "tomato sauce"])
    recipe = make_recipe(
        ["pasta", "tomato sauce", "truffle"],
        optional=["truffle"],
    )
    result = score_recipe(pantry, recipe)
    assert result["match_pct"] == 1.0
    assert result["total_required"] == 2


def test_result_contains_recipe_metadata():
    pantry = make_pantry(["chicken"])
    recipe = make_recipe(["chicken", "garlic"])
    result = score_recipe(pantry, recipe)
    assert "recipe_id" in result
    assert "title" in result
    assert "match_pct" in result
    assert "matched_ingredients" in result
    assert "missing_ingredients" in result


# ── score_recipes ──────────────────────────────────────────────────────────


def test_score_recipes_sorted_descending():
    pantry = make_pantry(["pasta", "eggs", "flour"])
    r1 = make_recipe(["pasta", "eggs", "salmon", "cream"])   # 2/4 = 0.5
    r2 = make_recipe(["pasta", "eggs", "flour"])              # 3/3 = 1.0
    r3 = make_recipe(["miso", "tofu", "dashi"])               # 0/3 = 0.0

    results = score_recipes(pantry, [r1, r2, r3])
    assert results[0]["match_pct"] == 1.0
    assert results[1]["match_pct"] == pytest.approx(0.5, abs=0.01)
    assert results[2]["match_pct"] == 0.0


def test_score_recipes_empty_pantry():
    pantry: list[PantryItem] = []
    recipe = make_recipe(["chicken", "garlic", "lemon"])
    results = score_recipes(pantry, [recipe])
    assert results[0]["match_pct"] == 0.0
    assert len(results[0]["missing_ingredients"]) == 3


def test_score_recipes_empty_list():
    pantry = make_pantry(["flour"])
    results = score_recipes(pantry, [])
    assert results == []
