"""
tests/test_extractor.py

Tests for the GPT-4o recipe extraction service.
OpenAI is mocked — no real API calls in CI.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.extractor import _auto_tag, _clean_json, extract_recipe

# ── Fixture: realistic GPT response ───────────────────────────────────────

CARBONARA_RESPONSE = {
    "title": "Spaghetti Carbonara",
    "description": "Classic Roman pasta with eggs, cheese and pancetta.",
    "cuisine": "Italian",
    "difficulty": "medium",
    "servings": 2,
    "prep_time_minutes": 10,
    "cook_time_minutes": 20,
    "total_time_minutes": 30,
    "ingredients": [
        {"name": "spaghetti", "quantity": 200, "unit": "g", "preparation": None, "optional": False},
        {"name": "pancetta", "quantity": 100, "unit": "g", "preparation": None, "optional": False},
        {"name": "egg yolks", "quantity": 3, "unit": None, "preparation": None, "optional": False},
        {"name": "pecorino romano", "quantity": 50, "unit": "g", "preparation": "grated", "optional": False},
        {"name": "black pepper", "quantity": None, "unit": None, "preparation": "to taste", "optional": False},
    ],
    "steps": [
        {"order": 1, "text": "Boil salted water.", "timer_seconds": None},
        {"order": 2, "text": "Cook spaghetti until al dente.", "timer_seconds": 480},
        {"order": 3, "text": "Fry pancetta until crispy.", "timer_seconds": 300},
        {"order": 4, "text": "Whisk egg yolks with cheese.", "timer_seconds": None},
        {"order": 5, "text": "Combine pasta with pancetta then add egg mixture off heat.", "timer_seconds": None},
    ],
    "tags": ["comfort-food"],
}


def _make_mock_response(data: dict, tokens: int = 500) -> MagicMock:
    """Build a mock that looks like an OpenAI ChatCompletion response."""
    msg = MagicMock()
    msg.content = json.dumps(data)

    choice = MagicMock()
    choice.message = msg

    usage = MagicMock()
    usage.total_tokens = tokens

    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ── _clean_json ────────────────────────────────────────────────────────────


class TestCleanJson:
    def test_strips_backtick_fence(self):
        raw = "```json\n{\"key\": 1}\n```"
        assert _clean_json(raw) == '{"key": 1}'

    def test_strips_plain_fence(self):
        raw = "```\n{\"key\": 1}\n```"
        assert _clean_json(raw) == '{"key": 1}'

    def test_no_fence_passthrough(self):
        raw = '{"key": 1}'
        assert _clean_json(raw) == raw

    def test_whitespace_stripped(self):
        raw = "  \n  {\"key\": 1}  \n  "
        assert _clean_json(raw) == '{"key": 1}'


# ── _auto_tag ──────────────────────────────────────────────────────────────


class TestAutoTag:
    def test_adds_vegetarian_no_meat(self):
        data = {
            "ingredients": [{"name": "tofu"}, {"name": "soy sauce"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "vegetarian" in tags

    def test_adds_vegan_no_meat_dairy_egg(self):
        data = {
            "ingredients": [{"name": "tofu"}, {"name": "broccoli"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "vegan" in tags
        assert "vegetarian" in tags

    def test_no_vegan_with_eggs(self):
        data = {
            "ingredients": [{"name": "eggs"}, {"name": "spinach"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "vegetarian" in tags
        assert "vegan" not in tags

    def test_no_vegetarian_with_chicken(self):
        data = {
            "ingredients": [{"name": "chicken breast"}, {"name": "garlic"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "vegetarian" not in tags
        assert "vegan" not in tags

    def test_gluten_free_no_wheat(self):
        data = {
            "ingredients": [{"name": "rice"}, {"name": "chicken"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "gluten-free" in tags

    def test_not_gluten_free_with_flour(self):
        data = {
            "ingredients": [{"name": "flour"}, {"name": "butter"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "gluten-free" not in tags

    def test_quick_tag_under_30_min(self):
        data = {
            "ingredients": [{"name": "eggs"}],
            "tags": [],
            "total_time_minutes": 20,
        }
        tags = _auto_tag(data)
        assert "quick" in tags

    def test_no_quick_tag_over_30_min(self):
        data = {
            "ingredients": [{"name": "beef"}],
            "tags": [],
            "total_time_minutes": 90,
        }
        tags = _auto_tag(data)
        assert "quick" not in tags

    def test_existing_tags_preserved(self):
        data = {
            "ingredients": [{"name": "spinach"}],
            "tags": ["healthy", "one-pot"],
        }
        tags = _auto_tag(data)
        assert "healthy" in tags
        assert "one-pot" in tags

    def test_dairy_free_no_dairy(self):
        data = {
            "ingredients": [{"name": "coconut oil"}, {"name": "rice"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "dairy-free" in tags

    def test_not_dairy_free_with_butter(self):
        data = {
            "ingredients": [{"name": "butter"}, {"name": "flour"}],
            "tags": [],
        }
        tags = _auto_tag(data)
        assert "dairy-free" not in tags


# ── extract_recipe ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestExtractRecipe:
    async def test_successful_extraction(self):
        mock_resp = _make_mock_response(CARBONARA_RESPONSE, tokens=842)

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat = MagicMock()
            instance.chat.completions = MagicMock()
            instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            result = await extract_recipe(
                transcript="Today we're making carbonara...",
                source_url="https://youtube.com/watch?v=abc",
                video_title="Perfect Carbonara Recipe",
            )

        assert result["title"] == "Spaghetti Carbonara"
        assert result["cuisine"] == "Italian"
        assert len(result["ingredients"]) == 5
        assert len(result["steps"]) == 5
        assert result["extraction_tokens"] == 842
        assert result["extraction_model"] is not None

    async def test_tags_enhanced_by_auto_detector(self):
        """Carbonara has pancetta (cured pork) → NOT vegetarian. Also has
        pecorino (dairy) → NOT dairy-free. Also has spaghetti (gluten) → NOT gluten-free."""
        mock_resp = _make_mock_response(CARBONARA_RESPONSE)

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            result = await extract_recipe(
                transcript="Carbonara recipe...",
                source_url="https://youtube.com/watch?v=abc",
            )

        assert "vegetarian" not in result["tags"]   # has pancetta
        assert "vegan" not in result["tags"]         # has pancetta + pecorino
        assert "dairy-free" not in result["tags"]    # has pecorino romano
        assert "gluten-free" not in result["tags"]   # has spaghetti

    async def test_raises_if_no_ingredients(self):
        bad = {**CARBONARA_RESPONSE, "ingredients": []}
        mock_resp = _make_mock_response(bad)

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            with pytest.raises(ValueError, match="No ingredients"):
                await extract_recipe(
                    transcript="Not a recipe...",
                    source_url="https://youtube.com/watch?v=abc",
                )

    async def test_raises_if_no_steps(self):
        bad = {**CARBONARA_RESPONSE, "steps": []}
        mock_resp = _make_mock_response(bad)

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            with pytest.raises(ValueError, match="No cooking steps"):
                await extract_recipe(
                    transcript="Ingredients only...",
                    source_url="https://youtube.com/watch?v=abc",
                )

    async def test_raises_on_invalid_json(self):
        msg = MagicMock()
        msg.content = "This is not JSON at all."
        choice = MagicMock()
        choice.message = msg
        usage = MagicMock()
        usage.total_tokens = 10
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=resp)

            with pytest.raises(ValueError, match="invalid JSON"):
                await extract_recipe(
                    transcript="Some text...",
                    source_url="https://youtube.com/watch?v=abc",
                )

    async def test_ingredients_normalised_after_extraction(self):
        """Units should be normalised: 'tablespoons' → 'tbsp'."""
        data = {
            **CARBONARA_RESPONSE,
            "ingredients": [
                {"name": "olive oil", "quantity": 2, "unit": "tablespoons",
                 "preparation": None, "optional": False},
            ],
        }
        mock_resp = _make_mock_response(data)

        with patch("app.services.extractor.AsyncOpenAI") as MockClient:
            instance = MockClient.return_value
            instance.chat.completions.create = AsyncMock(return_value=mock_resp)

            result = await extract_recipe(
                transcript="Use 2 tablespoons of olive oil...",
                source_url="https://youtube.com/watch?v=abc",
            )

        assert result["ingredients"][0]["unit"] == "tbsp"
