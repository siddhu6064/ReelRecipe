"""
app/services/extractor.py

GPT-4o recipe extraction from video transcript.
Returns a dict ready to spread into RecipeDocument (worker adds
source_url, platform, user_id, job_id, video_title, thumbnail_url).

Post-processing pipeline:
  raw GPT JSON
    → normalise_ingredients()   (unit_normaliser + parser)
    → _auto_tag()               (dietary + time tag detection)
    → validate                  (raises ValueError on empty output)
"""

from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.services.extraction.parser import normalise_ingredients

logger = logging.getLogger(__name__)

# ── System prompt ──────────────────────────────────────────────────────────

_SYSTEM_PROMPT = """\
You are a recipe extraction specialist. Given a cooking video transcript,
extract the complete recipe and return it as valid JSON.

Return ONLY the JSON object — no markdown, no preamble, no trailing text.

Schema:
{
  "title": "string",
  "description": "string | null",
  "cuisine": "string | null  (e.g. Italian, Japanese, Mexican, American)",
  "difficulty": "easy | medium | hard",
  "servings": integer,
  "prep_time_minutes": integer | null,
  "cook_time_minutes": integer | null,
  "total_time_minutes": integer | null,
  "ingredients": [
    {
      "name": "string — ingredient name only, no quantity in the name",
      "quantity": number | null,
      "unit": "string | null — tbsp, tsp, g, kg, oz, lb, cup, ml, l, etc.",
      "preparation": "string | null — diced, minced, to taste, etc.",
      "optional": boolean
    }
  ],
  "steps": [
    {
      "order": integer,
      "text": "string — complete, self-contained step description",
      "timer_seconds": integer | null
    }
  ],
  "tags": ["string"]
}

Rules:
- Quantities must be numbers (0.5 not "1/2")
- timer_seconds: set only when the step explicitly states a duration
  (e.g. "bake for 25 minutes" → 1500; "cook until golden" → null)
- tags: include any applicable: vegan, vegetarian, gluten-free, dairy-free,
  nut-free, quick, one-pot, meal-prep, comfort-food, healthy, spicy
- If the video is NOT a cooking recipe, return valid JSON with
  empty ingredients [] and steps []
- null means undetermined — do NOT guess"""


def _clean_json(text: str) -> str:
    """Strip markdown code fences GPT sometimes wraps around JSON."""
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _auto_tag(data: dict) -> list[str]:
    """
    Supplement GPT tags with conservatively auto-detected dietary tags
    from ingredient names. Only adds tags — never removes.
    """
    existing = set(data.get("tags") or [])
    ingredient_names = " ".join(
        str(i.get("name", "")).lower() for i in (data.get("ingredients") or [])
    )

    _MEAT = {
        "chicken", "beef", "pork", "lamb", "turkey", "bacon", "ham",
        "sausage", "anchovy", "fish", "shrimp", "salmon", "tuna",
        "crab", "lobster", "squid", "prawn", "veal", "duck", "venison",
        "lard", "gelatin", "gelatine", "pancetta", "prosciutto",
        "chorizo", "salami", "pepperoni", "guanciale", "mortadella",
        "bresaola", "coppa", "nduja", "lardo",
    }
    _DAIRY = {
        "milk", "cream", "butter", "cheese", "yogurt", "yoghurt",
        "ghee", "parmesan", "mozzarella", "cheddar", "ricotta",
        "brie", "feta", "mascarpone", "whey", "lactose",
        "pecorino", "romano", "gruyere", "gouda", "brie",
        "camembert", "emmental", "halloumi", "burrata",
    }
    _GLUTEN = {
        "flour", "wheat", "bread", "pasta", "noodle", "soy sauce",
        "barley", "rye", "semolina", "couscous", "farro", "spelt",
        "breadcrumb", "crouton", "matzo", "spaghetti", "penne",
        "linguine", "fettuccine", "rigatoni", "orzo", "tortilla",
        "pita", "baguette", "croissant",
    }
    _NUTS = {
        "almond", "walnut", "cashew", "peanut", "pecan", "hazelnut",
        "pistachio", "macadamia", "pine nut", "chestnut", "praline",
    }

    has_meat  = any(k in ingredient_names for k in _MEAT)
    has_dairy = any(k in ingredient_names for k in _DAIRY)
    has_gluten = any(k in ingredient_names for k in _GLUTEN)
    has_nuts  = any(k in ingredient_names for k in _NUTS)
    has_egg   = re.search(r"\begg", ingredient_names) is not None

    if not has_meat:
        existing.add("vegetarian")
        if not has_dairy and not has_egg:
            existing.add("vegan")
    if not has_gluten:
        existing.add("gluten-free")
    if not has_dairy:
        existing.add("dairy-free")
    if not has_nuts:
        existing.add("nut-free")

    # Quick meal (≤ 30 min total)
    total = data.get("total_time_minutes") or (
        (data.get("prep_time_minutes") or 0) + (data.get("cook_time_minutes") or 0)
    )
    if total and int(total) <= 30:
        existing.add("quick")

    return sorted(existing)


async def extract_recipe(
    transcript: str,
    source_url: str,
    video_title: str | None = None,
    thumbnail_url: str | None = None,
) -> dict:
    """
    Call GPT-4o, parse the response, run post-processing, and return
    a clean dict of recipe fields.

    Raises ValueError if:
      - GPT returns invalid JSON
      - No ingredients were extracted
      - No steps were extracted
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    title_hint = f"Video title: {video_title}\n\n" if video_title else ""
    user_prompt = (
        f"{title_hint}"
        f"Extract the recipe from this cooking video transcript:\n\n"
        f"{transcript[:14_000]}"
    )

    response = await client.chat.completions.create(
        model=settings.openai_extraction_model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.1,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or ""
    usage = response.usage

    logger.info(
        "gpt4o_extraction_complete",
        tokens=usage.total_tokens if usage else 0,
        source_url=source_url,
    )

    try:
        data = json.loads(_clean_json(raw))
    except json.JSONDecodeError as exc:
        raise ValueError(f"GPT-4o returned invalid JSON: {exc}") from exc

    if not data.get("ingredients"):
        raise ValueError("No ingredients extracted — likely not a cooking video")
    if not data.get("steps"):
        raise ValueError("No cooking steps extracted")

    # Post-process
    data["ingredients"] = normalise_ingredients(data["ingredients"])
    data["tags"] = _auto_tag(data)

    # Provenance (stripped by worker before RecipeDocument creation)
    data["extraction_model"] = settings.openai_extraction_model
    data["extraction_tokens"] = usage.total_tokens if usage else 0

    return data
