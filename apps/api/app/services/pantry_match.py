"""
app/services/pantry_match.py

Fuzzy ingredient matching between a user's pantry and recipe ingredient lists.

Algorithm:
  - For each recipe ingredient, find the best matching pantry item using
    rapidfuzz.token_set_ratio (handles "garlic cloves" vs "garlic" etc.)
  - A match is accepted if similarity >= MATCH_THRESHOLD (75)
  - match_pct = matched_count / total_ingredients
"""

from __future__ import annotations

from rapidfuzz import fuzz

from app.models.documents import PantryItem, RecipeDocument

MATCH_THRESHOLD = 75  # minimum fuzzy similarity score (0–100)


def _best_match(ingredient_name: str, pantry_items: list[PantryItem]) -> tuple[str | None, float]:
    """
    Returns (pantry_item_name, score) for the best pantry match,
    or (None, 0.0) if no item exceeds the threshold.
    """
    best_name: str | None = None
    best_score = 0.0

    needle = ingredient_name.lower().strip()
    for item in pantry_items:
        score = fuzz.token_set_ratio(needle, item.name.lower().strip())
        if score > best_score:
            best_score = score
            best_name = item.name

    if best_score >= MATCH_THRESHOLD:
        return best_name, best_score
    return None, 0.0


def score_recipe(
    pantry_items: list[PantryItem],
    recipe: RecipeDocument,
) -> dict:
    """
    Score a single recipe against the pantry.
    Returns a dict with match_pct, matched_ingredients, missing_ingredients.
    """
    matched: list[str] = []
    missing: list[str] = []

    for ingredient in recipe.ingredients:
        if ingredient.optional:
            continue
        match_name, _ = _best_match(ingredient.name, pantry_items)
        if match_name:
            matched.append(ingredient.name)
        else:
            missing.append(ingredient.name)

    total = len(matched) + len(missing)
    match_pct = round(len(matched) / total, 3) if total > 0 else 0.0

    return {
        "recipe_id": str(recipe.id),
        "title": recipe.title,
        "thumbnail_url": recipe.thumbnail_url,
        "cuisine": recipe.cuisine,
        "difficulty": recipe.difficulty,
        "total_time_minutes": recipe.total_time_minutes,
        "tags": recipe.tags,
        "match_pct": match_pct,
        "matched_count": len(matched),
        "total_required": total,
        "matched_ingredients": matched,
        "missing_ingredients": missing,
    }


def score_recipes(
    pantry_items: list[PantryItem],
    recipes: list[RecipeDocument],
) -> list[dict]:
    """
    Score all user recipes and return sorted by match_pct descending.
    """
    results = [score_recipe(pantry_items, r) for r in recipes]
    results.sort(key=lambda x: x["match_pct"], reverse=True)
    return results
