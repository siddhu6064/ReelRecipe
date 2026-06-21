"""
app/services/ai_suggest.py

Generates recipe suggestions from pantry contents using GPT-4o.
Results cached in Redis for 24h keyed by user_id + pantry fingerprint.
"""

from __future__ import annotations

import hashlib
import json
import logging

from openai import AsyncOpenAI

from app.config.settings import get_settings
from app.models.documents import PantryItem

logger = logging.getLogger(__name__)

_CACHE_TTL = 86_400  # 24 hours


def _pantry_fingerprint(items: list[PantryItem]) -> str:
    names = sorted(i.name for i in items)
    return hashlib.md5("|".join(names).encode()).hexdigest()[:12]


async def suggest_from_pantry(
    pantry_items: list[PantryItem],
    dietary_prefs: list[str],
    cuisine_prefs: list[str],
    max_recipes: int,
    user_id: str,
) -> list[dict]:
    """
    Returns a list of recipe suggestion dicts. Each dict contains
    title, description, cuisine, ingredients[], steps[], tags[].
    """
    settings = get_settings()
    cache_key = f"ai_suggest:{user_id}:{_pantry_fingerprint(pantry_items)}"

    # Try Redis cache
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True)
        cached = await r.get(cache_key)
        if cached:
            logger.debug("ai_suggest_cache_hit for user: %s", user_id)
            return json.loads(cached)
    except Exception:
        pass  # Cache unavailable — proceed without

    pantry_str = ", ".join(i.name for i in pantry_items) if pantry_items else "empty pantry"
    diet_str = ", ".join(dietary_prefs) if dietary_prefs else "none"
    cuisine_str = ", ".join(cuisine_prefs) if cuisine_prefs else "any"

    system_prompt = """\
You are a creative chef AI. Given a pantry contents list, generate recipe suggestions.
Return ONLY valid JSON — an array of recipe objects, no markdown, no preamble.

Each recipe object must match this schema:
{
  "title": "string",
  "description": "string — one sentence",
  "cuisine": "string",
  "difficulty": "easy | medium | hard",
  "servings": integer,
  "prep_time_minutes": integer,
  "cook_time_minutes": integer,
  "total_time_minutes": integer,
  "ingredients": [{"name":"string","quantity":number|null,"unit":"string|null","preparation":"string|null","optional":false}],
  "steps": [{"order":integer,"text":"string","timer_seconds":integer|null}],
  "tags": ["string"]
}"""

    user_prompt = (
        f"Pantry: {pantry_str}\n"
        f"Dietary preferences: {diet_str}\n"
        f"Cuisine preferences: {cuisine_str}\n"
        f"Generate {max_recipes} recipes I can make with primarily these ingredients."
    )

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.chat.completions.create(
        model=settings.openai_extraction_model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0.7,
        response_format={"type": "json_object"},
    )

    raw = response.choices[0].message.content or "[]"
    try:
        parsed = json.loads(raw)
        # GPT may return {"recipes": [...]} or directly [...]
        if isinstance(parsed, dict):
            recipes = parsed.get("recipes") or list(parsed.values())[0]
        else:
            recipes = parsed
    except (json.JSONDecodeError, IndexError, KeyError):
        recipes = []

    # Cache result
    try:
        await r.setex(cache_key, _CACHE_TTL, json.dumps(recipes))
    except Exception:
        pass

    return recipes
