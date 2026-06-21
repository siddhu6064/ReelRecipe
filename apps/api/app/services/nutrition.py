"""
app/services/nutrition.py

Fetches per-serving macro data from the Nutritionix Natural Language API.
Returns a NutritionInfo dict (matching the embedded model) or None on failure.

Nutritionix endpoint: POST https://trackapi.nutritionix.com/v2/natural/nutrients
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

import httpx

from app.config.settings import get_settings

logger = logging.getLogger(__name__)

_NUTRITIONIX_URL = "https://trackapi.nutritionix.com/v2/natural/nutrients"


def _build_query(ingredients: list[dict]) -> str:
    """
    Convert a list of ingredient dicts into a natural-language query string
    that Nutritionix understands, e.g. "2 tbsp olive oil\n1 cup flour".
    """
    parts: list[str] = []
    for ing in ingredients:
        qty = ing.get("quantity")
        unit = ing.get("unit") or ""
        name = ing.get("name") or ""
        if qty:
            parts.append(f"{qty} {unit} {name}".strip())
        else:
            parts.append(name.strip())
    return "\n".join(parts)


async def fetch_nutrition(ingredients: list[dict], servings: int = 2) -> dict | None:
    """
    Returns a NutritionInfo-compatible dict with per-serving macros,
    or None if the API call fails (non-blocking — recipe is still saved).
    """
    settings = get_settings()

    if not settings.nutritionix_app_id or not settings.nutritionix_api_key:
        logger.debug("nutritionix_keys_missing — skipping nutrition fetch")
        return None

    query = _build_query(ingredients)
    if not query:
        return None

    headers = {
        "x-app-id": settings.nutritionix_app_id,
        "x-app-key": settings.nutritionix_api_key,
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                _NUTRITIONIX_URL,
                headers=headers,
                json={"query": query},
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("nutritionix_fetch_failed: %s", str(exc))
        return None

    foods = data.get("foods") or []
    if not foods:
        return None

    # Aggregate all items then divide by servings
    totals = {
        "calories": 0.0,
        "protein_g": 0.0,
        "carbs_g": 0.0,
        "fat_g": 0.0,
        "fiber_g": 0.0,
        "sugar_g": 0.0,
        "sodium_mg": 0.0,
    }
    FIELD_MAP = {
        "nf_calories": "calories",
        "nf_protein": "protein_g",
        "nf_total_carbohydrate": "carbs_g",
        "nf_total_fat": "fat_g",
        "nf_dietary_fiber": "fiber_g",
        "nf_sugars": "sugar_g",
        "nf_sodium": "sodium_mg",
    }
    for food in foods:
        for api_key, local_key in FIELD_MAP.items():
            totals[local_key] += food.get(api_key) or 0.0

    safe_servings = max(servings, 1)
    per_serving = {k: round(v / safe_servings, 1) for k, v in totals.items()}
    per_serving["fetched_at"] = datetime.now(UTC).isoformat()

    return per_serving
