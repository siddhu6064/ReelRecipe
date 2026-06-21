"""
app/services/ai_chat.py

Conversational Q&A about a specific recipe using GPT-4o-mini.
The caller maintains conversation history and passes it on each request.
"""

from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.models.documents import RecipeDocument

logger = logging.getLogger(__name__)


def _recipe_context(recipe: RecipeDocument) -> str:
    """Build a compact text representation of the recipe for the system prompt."""
    ingredients = "\n".join(
        f"  - {i.quantity or ''} {i.unit or ''} {i.name}".strip()
        for i in recipe.ingredients
    )
    steps = "\n".join(f"  {s.order}. {s.text}" for s in recipe.steps)
    return (
        f"Recipe: {recipe.title}\n"
        f"Cuisine: {recipe.cuisine or 'unknown'}\n"
        f"Difficulty: {recipe.difficulty}\n"
        f"Servings: {recipe.servings}\n"
        f"Prep: {recipe.prep_time_minutes}min  Cook: {recipe.cook_time_minutes}min\n\n"
        f"Ingredients:\n{ingredients}\n\n"
        f"Steps:\n{steps}"
    )


async def chat_about(
    recipe: RecipeDocument,
    message: str,
    history: list[dict],
) -> str:
    """
    Send a message about the recipe and return the assistant's reply.
    `history` is a list of {"role": "user"|"assistant", "content": "..."} dicts.
    """
    settings = get_settings()
    client = AsyncOpenAI(api_key=settings.openai_api_key)

    system = (
        "You are a helpful cooking assistant. Answer questions about the recipe below. "
        "Be concise, practical, and friendly. If asked about substitutions, suggest 2–3 options.\n\n"
        + _recipe_context(recipe)
    )

    messages = [{"role": "system", "content": system}]
    messages.extend(history[-10:])  # cap history at last 10 turns
    messages.append({"role": "user", "content": message})

    response = await client.chat.completions.create(
        model=settings.openai_chat_model,
        messages=messages,
        temperature=0.6,
        max_tokens=500,
    )

    reply = response.choices[0].message.content or ""
    logger.debug("ai_chat_reply", recipe_id=str(recipe.id), tokens=response.usage.total_tokens if response.usage else 0)
    return reply
