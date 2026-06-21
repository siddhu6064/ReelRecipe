"""
app/services/cost_service.py

Estimates the ingredient cost for a recipe using prices stored on
PantryItem.estimated_cost_per_unit.

Matching uses the same fuzzy matcher as pantry_match.py so "garlic cloves"
correctly picks up "garlic" in the pantry price list.

Returns a breakdown dict:
  {
    "total_cost":   float | None,     # sum of priced ingredients
    "currency":     "USD",
    "coverage_pct": float,            # fraction of ingredients with a price
    "breakdown": [
      { "ingredient": str, "cost": float | None, "has_price": bool }
    ]
  }
"""

from __future__ import annotations


async def estimate_recipe_cost(recipe_id: str, user_id: str) -> dict | None:
    from beanie import PydanticObjectId
    from app.models.documents import PantryDocument, RecipeDocument
    from app.services.pantry_match import _best_match

    try:
        recipe = await RecipeDocument.get(PydanticObjectId(recipe_id))
    except Exception:
        return None
    if not recipe:
        return None

    pantry = await PantryDocument.find_one({"user_id": user_id})
    pantry_items = pantry.items if pantry else []

    # Build price lookup: ingredient name → cost_per_unit
    price_map: dict[str, float] = {}
    for item in pantry_items:
        if item.estimated_cost_per_unit is not None:
            price_map[item.name.lower()] = item.estimated_cost_per_unit

    breakdown = []
    total = 0.0
    priced_count = 0

    for ing in recipe.ingredients:
        if ing.optional:
            breakdown.append({"ingredient": ing.name, "cost": None, "has_price": False})
            continue

        # Fuzzy-match ingredient to pantry items that have prices
        priced_items = [p for p in pantry_items if p.estimated_cost_per_unit is not None]
        match_name, score = _best_match(ing.name, priced_items)

        if match_name and score >= 70:
            unit_price = price_map.get(match_name.lower())
            if unit_price is not None:
                qty = ing.quantity or 1.0
                cost = round(unit_price * qty, 2)
                total += cost
                priced_count += 1
                breakdown.append({"ingredient": ing.name, "cost": cost, "has_price": True})
                continue

        breakdown.append({"ingredient": ing.name, "cost": None, "has_price": False})

    total_ings = len([i for i in recipe.ingredients if not i.optional])
    coverage = round(priced_count / total_ings, 3) if total_ings else 0.0

    return {
        "total_cost":    round(total, 2) if priced_count > 0 else None,
        "currency":      "USD",
        "coverage_pct":  coverage,
        "priced_count":  priced_count,
        "total_ingredients": total_ings,
        "breakdown":     breakdown,
    }
