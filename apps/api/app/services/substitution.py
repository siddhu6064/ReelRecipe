"""
app/services/substitution.py

GPT-4o-mini ingredient substitution suggestions.
Returns 2–3 alternatives with notes on how each affects the dish.
"""

from __future__ import annotations

import json
import logging
import re

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.models.documents import RecipeDocument

logger = logging.getLogger(__name__)


async def get_substitutions(recipe: RecipeDocument, ingredient_name: str) -> dict:
    """
    Returns {"ingredient": str, "substitutions": [{"name": str, "notes": str}]}.
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    # Find the ingredient in the recipe for context
    matched = next(
        (i for i in recipe.ingredients if ingredient_name.lower() in i.name.lower()),
        None,
    )
    context_qty = ""
    if matched and matched.quantity:
        context_qty = f" ({matched.quantity} {matched.unit or ''})".strip()

    system_prompt = """\
You are a culinary expert. Suggest ingredient substitutions.
Return ONLY valid JSON — no markdown, no preamble:
{
  "ingredient": "string — the ingredient being substituted",
  "substitutions": [
    {
      "name": "string — substitute ingredient name",
      "notes": "string — how this affects texture, flavour, or the cooking process"
    }
  ]
}
Provide 2–3 substitutions ordered from most to least recommended."""

    user_prompt = (
        f"Recipe: {recipe.title}\n"
        f"Ingredient to substitute: {ingredient_name}{context_qty}\n"
        f"Suggest substitutions."
    )

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.4,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "{}"
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"ingredient": ingredient_name, "substitutions": []}

    return result
