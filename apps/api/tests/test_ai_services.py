"""
tests/test_ai_services.py

Unit tests for all AI-backed services.
OpenAI API and Nutritionix are fully mocked — no real calls in CI.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

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

TEST_USER = "user_test_clerk_001"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture(autouse=True)
async def beanie_init():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


@pytest.fixture
def sample_recipe() -> RecipeDocument:
    return RecipeDocument(
        user_id=TEST_USER,
        source_url="https://youtube.com/watch?v=test",
        platform=Platform.YOUTUBE,
        title="Spaghetti Carbonara",
        cuisine="Italian",
        difficulty=Difficulty.MEDIUM,
        servings=2,
        prep_time_minutes=10,
        cook_time_minutes=20,
        ingredients=[
            RecipeIngredient(name="spaghetti", quantity=200, unit="g"),
            RecipeIngredient(name="pancetta", quantity=100, unit="g"),
            RecipeIngredient(name="egg yolks", quantity=3),
            RecipeIngredient(name="pecorino romano", quantity=50, unit="g"),
        ],
        steps=[
            RecipeStep(order=1, text="Boil pasta.", timer_seconds=480),
            RecipeStep(order=2, text="Fry pancetta.", timer_seconds=300),
            RecipeStep(order=3, text="Combine with egg mixture."),
        ],
        tags=["comfort-food"],
    )


@pytest.fixture
def pantry_items() -> list[PantryItem]:
    return [
        PantryItem(name="spaghetti", quantity=500, unit="g"),
        PantryItem(name="eggs", quantity=6),
        PantryItem(name="olive oil", quantity=500, unit="ml"),
        PantryItem(name="garlic", quantity=1, unit="bulb"),
    ]


# ── Helper to build mock OpenAI response ──────────────────────────────────


def _mock_openai_response(content: str, tokens: int = 200) -> MagicMock:
    msg = MagicMock()
    msg.content = content
    choice = MagicMock()
    choice.message = msg
    usage = MagicMock()
    usage.total_tokens = tokens
    resp = MagicMock()
    resp.choices = [choice]
    resp.usage = usage
    return resp


# ── ai_suggest.py ──────────────────────────────────────────────────────────


class TestAISuggest:

    @pytest.mark.asyncio
    async def test_suggest_returns_list_of_recipes(self, pantry_items):
        from app.services.ai_suggest import suggest_from_pantry

        mock_recipes = [
            {
                "title": "Aglio e Olio",
                "description": "Simple garlic pasta.",
                "cuisine": "Italian",
                "difficulty": "easy",
                "servings": 2,
                "prep_time_minutes": 5,
                "cook_time_minutes": 15,
                "total_time_minutes": 20,
                "ingredients": [
                    {"name": "spaghetti", "quantity": 200, "unit": "g"},
                    {"name": "garlic", "quantity": 4, "unit": "clove"},
                    {"name": "olive oil", "quantity": 4, "unit": "tbsp"},
                ],
                "steps": [
                    {"order": 1, "text": "Boil pasta.", "timer_seconds": 480},
                    {"order": 2, "text": "Sauté garlic in oil.", "timer_seconds": 120},
                ],
                "tags": ["quick", "vegan"],
            }
        ]

        gpt_resp = _mock_openai_response(
            json.dumps({"recipes": mock_recipes})
        )

        with (
            patch("app.services.ai_suggest.AsyncOpenAI") as MockGPT,
            patch("redis.asyncio") as mock_redis_mod,
        ):
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            # Mock Redis — cache miss then successful set
            mock_r = AsyncMock()
            mock_r.get = AsyncMock(return_value=None)
            mock_r.setex = AsyncMock()
            mock_redis_mod.from_url = MagicMock(return_value=mock_r)

            result = await suggest_from_pantry(
                pantry_items=pantry_items,
                dietary_prefs=[],
                cuisine_prefs=["italian"],
                max_recipes=3,
                user_id=TEST_USER,
            )

        assert isinstance(result, list)
        assert len(result) == 1
        assert result[0]["title"] == "Aglio e Olio"

    @pytest.mark.asyncio
    async def test_suggest_uses_cache_on_hit(self, pantry_items):
        from app.services.ai_suggest import suggest_from_pantry

        cached = [{"title": "Cached Recipe", "ingredients": [], "steps": []}]

        with patch("redis.asyncio") as mock_redis_mod:
            mock_r = AsyncMock()
            mock_r.get = AsyncMock(return_value=json.dumps(cached))
            mock_redis_mod.from_url = MagicMock(return_value=mock_r)

            result = await suggest_from_pantry(
                pantry_items=pantry_items,
                dietary_prefs=[],
                cuisine_prefs=[],
                max_recipes=3,
                user_id=TEST_USER,
            )

        assert result == cached

    @pytest.mark.asyncio
    async def test_suggest_handles_dict_response(self, pantry_items):
        """GPT sometimes returns {\"recipes\": [...]} — should unwrap correctly."""
        from app.services.ai_suggest import suggest_from_pantry

        payload = {"recipes": [{"title": "R1"}, {"title": "R2"}]}
        gpt_resp = _mock_openai_response(json.dumps(payload))

        with (
            patch("app.services.ai_suggest.AsyncOpenAI") as MockGPT,
            patch("redis.asyncio") as mock_redis_mod,
        ):
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            mock_r = AsyncMock()
            mock_r.get = AsyncMock(return_value=None)
            mock_r.setex = AsyncMock()
            mock_redis_mod.from_url = MagicMock(return_value=mock_r)

            result = await suggest_from_pantry(
                pantry_items=pantry_items,
                dietary_prefs=[],
                cuisine_prefs=[],
                max_recipes=5,
                user_id=TEST_USER,
            )

        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_suggest_empty_pantry(self):
        from app.services.ai_suggest import suggest_from_pantry

        gpt_resp = _mock_openai_response(json.dumps([]))

        with (
            patch("app.services.ai_suggest.AsyncOpenAI") as MockGPT,
            patch("redis.asyncio") as mock_redis_mod,
        ):
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            mock_r = AsyncMock()
            mock_r.get = AsyncMock(return_value=None)
            mock_r.setex = AsyncMock()
            mock_redis_mod.from_url = MagicMock(return_value=mock_r)

            result = await suggest_from_pantry(
                pantry_items=[],
                dietary_prefs=["vegan"],
                cuisine_prefs=[],
                max_recipes=3,
                user_id=TEST_USER,
            )
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_suggest_redis_unavailable_still_works(self, pantry_items):
        """If Redis is down, suggestion still works (no cache)."""
        from app.services.ai_suggest import suggest_from_pantry

        mock_recipes = [{"title": "Pasta", "ingredients": [], "steps": []}]
        gpt_resp = _mock_openai_response(json.dumps(mock_recipes))

        with (
            patch("app.services.ai_suggest.AsyncOpenAI") as MockGPT,
            patch("redis.asyncio") as mock_redis_mod,
        ):
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            # Redis raises on connect
            mock_redis_mod.from_url = MagicMock(
                side_effect=ConnectionError("Redis unavailable")
            )

            result = await suggest_from_pantry(
                pantry_items=pantry_items,
                dietary_prefs=[],
                cuisine_prefs=[],
                max_recipes=3,
                user_id=TEST_USER,
            )
        assert isinstance(result, list)


# ── ai_chat.py ─────────────────────────────────────────────────────────────


class TestAIChat:

    @pytest.mark.asyncio
    async def test_chat_returns_reply(self, sample_recipe):
        from app.services.ai_chat import chat_about

        gpt_resp = _mock_openai_response(
            "You can substitute guanciale for pancetta — same curing method."
        )

        with patch("app.services.ai_chat.AsyncOpenAI") as MockGPT:
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            reply = await chat_about(
                recipe=sample_recipe,
                message="Can I substitute pancetta?",
                history=[],
            )

        assert "guanciale" in reply

    @pytest.mark.asyncio
    async def test_chat_includes_history(self, sample_recipe):
        from app.services.ai_chat import chat_about

        gpt_resp = _mock_openai_response("Yes, it works well.")

        history = [
            {"role": "user", "content": "Is this recipe authentic?"},
            {"role": "assistant", "content": "Yes, it's classic Roman."},
        ]

        with patch("app.services.ai_chat.AsyncOpenAI") as MockGPT:
            mock_create = AsyncMock(return_value=gpt_resp)
            MockGPT.return_value.chat.completions.create = mock_create

            await chat_about(
                recipe=sample_recipe,
                message="Can I add cream?",
                history=history,
            )

            # Verify history was passed to the API call
            call_kwargs = mock_create.call_args
            messages_sent = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
            # Should include system + history + new message
            assert len(messages_sent) >= 4

    @pytest.mark.asyncio
    async def test_chat_caps_history_at_10_turns(self, sample_recipe):
        from app.services.ai_chat import chat_about

        gpt_resp = _mock_openai_response("Short answer.")

        # 20 history entries — should be capped to last 10
        long_history = [
            {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
            for i in range(20)
        ]

        with patch("app.services.ai_chat.AsyncOpenAI") as MockGPT:
            mock_create = AsyncMock(return_value=gpt_resp)
            MockGPT.return_value.chat.completions.create = mock_create

            await chat_about(
                recipe=sample_recipe,
                message="One more question",
                history=long_history,
            )

            call_kwargs = mock_create.call_args
            messages_sent = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
            # system(1) + capped_history(10) + new_message(1) = 12
            assert len(messages_sent) <= 12

    @pytest.mark.asyncio
    async def test_chat_recipe_context_included(self, sample_recipe):
        from app.services.ai_chat import _recipe_context

        context = _recipe_context(sample_recipe)
        assert "Spaghetti Carbonara" in context
        assert "spaghetti" in context
        assert "pancetta" in context

    @pytest.mark.asyncio
    async def test_chat_empty_history(self, sample_recipe):
        from app.services.ai_chat import chat_about

        gpt_resp = _mock_openai_response("Great question!")

        with patch("app.services.ai_chat.AsyncOpenAI") as MockGPT:
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            reply = await chat_about(
                recipe=sample_recipe,
                message="How long does this take?",
                history=[],
            )
        assert isinstance(reply, str)
        assert len(reply) > 0


# ── substitution.py ────────────────────────────────────────────────────────


class TestSubstitution:

    @pytest.mark.asyncio
    async def test_get_substitutions_returns_list(self, sample_recipe):
        from app.services.substitution import get_substitutions

        mock_result = {
            "ingredient": "pancetta",
            "substitutions": [
                {"name": "guanciale", "notes": "Traditional Roman alternative."},
                {"name": "bacon", "notes": "Smokier flavour, widely available."},
                {"name": "turkey bacon", "notes": "Leaner option."},
            ],
        }
        gpt_resp = _mock_openai_response(json.dumps(mock_result))

        with patch("app.services.substitution.AsyncOpenAI") as MockGPT:
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            result = await get_substitutions(
                recipe=sample_recipe,
                ingredient_name="pancetta",
            )

        assert result["ingredient"] == "pancetta"
        assert len(result["substitutions"]) == 3
        assert result["substitutions"][0]["name"] == "guanciale"

    @pytest.mark.asyncio
    async def test_get_substitutions_with_quantity_context(self, sample_recipe):
        """Ingredient with known quantity should include it in the prompt."""
        from app.services.substitution import get_substitutions

        mock_result = {
            "ingredient": "pecorino romano",
            "substitutions": [
                {"name": "parmesan", "notes": "Milder flavour."},
            ],
        }
        gpt_resp = _mock_openai_response(json.dumps(mock_result))

        with patch("app.services.substitution.AsyncOpenAI") as MockGPT:
            mock_create = AsyncMock(return_value=gpt_resp)
            MockGPT.return_value.chat.completions.create = mock_create

            result = await get_substitutions(
                recipe=sample_recipe,
                ingredient_name="pecorino romano",
            )

            # Verify the prompt included the ingredient
            call_kwargs = mock_create.call_args
            messages = call_kwargs.kwargs.get("messages") or call_kwargs.args[0]
            user_msg = messages[-1]["content"]
            assert "pecorino romano" in user_msg

        assert result["substitutions"][0]["name"] == "parmesan"

    @pytest.mark.asyncio
    async def test_get_substitutions_handles_invalid_json(self, sample_recipe):
        """If GPT returns garbled JSON, returns a safe fallback."""
        from app.services.substitution import get_substitutions

        gpt_resp = _mock_openai_response("Sorry, I cannot help with that.")

        with patch("app.services.substitution.AsyncOpenAI") as MockGPT:
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            result = await get_substitutions(
                recipe=sample_recipe,
                ingredient_name="spaghetti",
            )

        # Should return a valid structure even on bad JSON
        assert "ingredient" in result
        assert "substitutions" in result

    @pytest.mark.asyncio
    async def test_get_substitutions_unknown_ingredient(self, sample_recipe):
        """Ingredient not in recipe still works — context from recipe title used."""
        from app.services.substitution import get_substitutions

        mock_result = {
            "ingredient": "truffle oil",
            "substitutions": [
                {"name": "regular olive oil", "notes": "No truffle aroma."},
            ],
        }
        gpt_resp = _mock_openai_response(json.dumps(mock_result))

        with patch("app.services.substitution.AsyncOpenAI") as MockGPT:
            MockGPT.return_value.chat.completions.create = AsyncMock(
                return_value=gpt_resp
            )
            result = await get_substitutions(
                recipe=sample_recipe,
                ingredient_name="truffle oil",
            )

        assert result["ingredient"] == "truffle oil"


# ── nutrition.py ───────────────────────────────────────────────────────────


class TestNutrition:

    @pytest.mark.asyncio
    async def test_fetch_nutrition_success(self):
        from app.services.nutrition import fetch_nutrition

        mock_foods = [
            {
                "nf_calories": 400.0, "nf_protein": 14.0,
                "nf_total_carbohydrate": 72.0, "nf_total_fat": 6.0,
                "nf_dietary_fiber": 3.0, "nf_sugars": 5.0, "nf_sodium": 250.0,
            }
        ]

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"foods": mock_foods})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        ingredients = [
            {"name": "spaghetti", "quantity": 200, "unit": "g"},
            {"name": "eggs", "quantity": 3, "unit": None},
        ]

        with patch("app.services.nutrition.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_nutrition(ingredients=ingredients, servings=2)

        assert result is not None
        assert result["calories"] == pytest.approx(200.0, abs=1.0)  # 400 / 2 servings
        assert result["protein_g"] == pytest.approx(7.0, abs=0.5)
        assert "fetched_at" in result

    @pytest.mark.asyncio
    async def test_fetch_nutrition_no_api_keys_returns_none(self):
        from app.services.nutrition import fetch_nutrition

        with patch("app.services.nutrition.get_settings") as mock_settings:
            mock_settings.return_value.nutritionix_app_id = ""
            mock_settings.return_value.nutritionix_api_key = ""

            result = await fetch_nutrition(
                ingredients=[{"name": "pasta", "quantity": 200}],
                servings=2,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_nutrition_api_error_returns_none(self):
        from app.services.nutrition import fetch_nutrition

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Network error"))

        with patch("app.services.nutrition.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_nutrition(
                ingredients=[{"name": "chicken", "quantity": 200}],
                servings=2,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_nutrition_empty_foods_returns_none(self):
        from app.services.nutrition import fetch_nutrition

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"foods": []})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.nutrition.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_nutrition(
                ingredients=[{"name": "air", "quantity": 1}],
                servings=1,
            )

        assert result is None

    @pytest.mark.asyncio
    async def test_fetch_nutrition_divides_by_servings(self):
        from app.services.nutrition import fetch_nutrition

        mock_foods = [{"nf_calories": 900.0, "nf_protein": 45.0,
                       "nf_total_carbohydrate": 90.0, "nf_total_fat": 30.0,
                       "nf_dietary_fiber": 0.0, "nf_sugars": 0.0, "nf_sodium": 0.0}]
        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={"foods": mock_foods})

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.nutrition.httpx.AsyncClient", return_value=mock_client):
            result = await fetch_nutrition(
                ingredients=[{"name": "pasta", "quantity": 300}],
                servings=3,
            )

        assert result["calories"] == pytest.approx(300.0, abs=1.0)  # 900 / 3
        assert result["protein_g"] == pytest.approx(15.0, abs=0.5)  # 45 / 3

    def test_build_query_with_quantities(self):
        from app.services.nutrition import _build_query

        ingredients = [
            {"name": "flour", "quantity": 2, "unit": "cup"},
            {"name": "salt", "quantity": None, "unit": None},
        ]
        query = _build_query(ingredients)
        assert "2 cup flour" in query
        assert "salt" in query

    def test_build_query_empty_list(self):
        from app.services.nutrition import _build_query

        assert _build_query([]) == ""
