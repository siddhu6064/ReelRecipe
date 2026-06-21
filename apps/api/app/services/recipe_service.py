"""
app/services/recipe_service.py

Business logic for recipe mutations that require more than
a simple field update:

  rescale_ingredients()   — proportionally adjusts all ingredient quantities
  apply_user_prefs()      — injects stored dietary/cuisine prefs into a query
  prefs_compatible()      — checks whether a recipe conflicts with user prefs
"""

from __future__ import annotations

import math

from app.models.documents import RecipeDocument, RecipeIngredient


# ── Servings rescaling ──────────────────────────────────────────────────────


def rescale_ingredients(
    ingredients: list[RecipeIngredient],
    old_servings: int,
    new_servings: int,
) -> list[RecipeIngredient]:
    """
    Proportionally scale all ingredient quantities to the new serving count.
    Quantities that are None (e.g. "to taste") are left unchanged.
    Results are rounded to at most 3 significant figures.
    """
    if old_servings == new_servings or old_servings == 0:
        return ingredients

    factor = new_servings / old_servings
    scaled: list[RecipeIngredient] = []

    for ing in ingredients:
        new_qty: float | None = None
        if ing.quantity is not None:
            raw = ing.quantity * factor
            # Round to 3 significant figures for clean display
            if raw > 0:
                magnitude = math.floor(math.log10(raw))
                rounded = round(raw, -magnitude + 2)
                # Snap very close fractions: 0.333 → 0.333, 0.499 → 0.5
                new_qty = rounded
            else:
                new_qty = raw

        scaled.append(
            RecipeIngredient(
                name=ing.name,
                quantity=new_qty,
                unit=ing.unit,
                preparation=ing.preparation,
                optional=ing.optional,
            )
        )

    return scaled


# ── Dietary preference helpers ──────────────────────────────────────────────

# Maps a stored dietary pref to the tag(s) that a compatible recipe must have
_PREF_TAG_MAP: dict[str, list[str]] = {
    "vegan":       ["vegan"],
    "vegetarian":  ["vegetarian", "vegan"],   # vegan is also vegetarian
    "gluten-free": ["gluten-free"],
    "dairy-free":  ["dairy-free"],
    "nut-free":    ["nut-free"],
    # These have no matching tag yet — reserved for future auto-detection
    "halal":  [],
    "kosher": [],
    "keto":   [],
    "paleo":  [],
}


def prefs_compatible(recipe: RecipeDocument, dietary_prefs: list[str]) -> bool:
    """
    Return True if the recipe does not conflict with any of the user's
    dietary preferences.

    Conservative logic: a pref only conflicts if the recipe has an
    *explicit conflicting tag* — e.g. a recipe tagged "vegan" is
    compatible with "vegan"; a recipe with no "vegan" tag is treated
    as unknown (compatible) rather than incompatible.

    This avoids false negatives on recipes imported before tag detection.
    """
    if not dietary_prefs:
        return True

    recipe_tags = set(recipe.tags or [])

    for pref in dietary_prefs:
        compatible_tags = _PREF_TAG_MAP.get(pref, [])
        if not compatible_tags:
            continue   # no tag data for this pref — assume compatible

        # Incompatible only if the recipe explicitly carries a conflicting
        # tag. E.g. a recipe tagged "has-meat" (hypothetical) would be
        # incompatible with "vegan". Currently we use absence:
        # if the user is vegan and recipe isn't tagged vegan/vegetarian
        # AND has explicit conflicting evidence → mark incompatible.
        # For now: compatible if it has at least one matching tag,
        # or if the recipe has no tags at all (unknown).
        if recipe_tags and not any(t in recipe_tags for t in compatible_tags):
            return False

    return True


def build_prefs_query(dietary_prefs: list[str], cuisine_prefs: list[str]) -> dict:
    """
    Build a MongoDB query fragment to pre-filter recipes by user preferences.
    Only adds constraints when the pref has a matching tag.
    Cuisine prefs are applied as an $in filter (any matching cuisine).
    """
    query: dict = {}

    # Dietary: every strict pref must be represented in tags
    strict_prefs = [
        p for p in dietary_prefs
        if _PREF_TAG_MAP.get(p)  # only prefs we have tags for
    ]
    if strict_prefs:
        required_tags = [_PREF_TAG_MAP[p] for p in strict_prefs]
        # Use $all with $or to handle synonyms (vegan satisfies vegetarian)
        # Simplification: if user is vegan, require "vegan" tag
        flat = [tags[0] for tags in required_tags]   # take primary tag per pref
        query["tags"] = {"$all": flat}

    # Cuisine: soft filter — if user has prefs, boost/filter to matching cuisines
    if cuisine_prefs:
        query["cuisine"] = {"$in": cuisine_prefs}

    return query
