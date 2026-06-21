"""
app/routers/explore.py

Community recipe feed — public recipes shared by all users.

GET  /api/explore                  — paginated public feed (newest first)
GET  /api/explore/trending         — sorted by view_count + recency
GET  /api/explore/recipe/:token    — public recipe by share token (no auth)
PATCH /api/recipes/:id/visibility  — toggle public/private
POST  /api/recipes/:id/duplicate   — copy a public recipe into own cookbook
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.clerk import optional_auth, require_auth
from app.models.documents import RecipeDocument

router = APIRouter(tags=["explore"])


# ── Public feed ─────────────────────────────────────────────────────────────


@router.get("/api/explore", summary="Community recipe feed")
async def explore_feed(
    limit: int = Query(default=20, ge=1, le=50),
    offset: int = Query(default=0, ge=0),
    cuisine: str | None = Query(default=None),
    tags: list[str] = Query(default=[]),
) -> dict:
    """
    Returns recently-published public recipes from all users.
    No authentication required — accessible without login.
    """
    query: dict = {"is_public": True}
    if cuisine:
        query["cuisine"] = cuisine
    if tags:
        query["tags"] = {"$all": tags}

    recipes = (
        await RecipeDocument.find(query)
        .skip(offset)
        .limit(limit)
        .sort("-created_at")
        .to_list()
    )
    total = await RecipeDocument.find(query).count()

    return {
        "ok": True,
        "data": {
            "recipes": [_public_recipe(r) for r in recipes],
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/api/explore/trending", summary="Trending public recipes")
async def explore_trending(
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    """
    Returns the most-viewed public recipes, weighted toward recency.
    Sorted by view_count descending.
    """
    recipes = (
        await RecipeDocument.find({"is_public": True})
        .sort([("view_count", -1), ("created_at", -1)])
        .limit(limit)
        .to_list()
    )
    return {
        "ok": True,
        "data": [_public_recipe(r) for r in recipes],
    }


@router.get("/api/explore/recipe/{share_token}", summary="View public recipe by share token")
async def public_recipe_by_token(share_token: str) -> dict:
    """
    Fetch a public recipe via its stable share token.
    No authentication required — safe to embed in shareable links.
    Increments view_count each time it's called.
    """
    recipe = await RecipeDocument.find_one({"share_token": share_token, "is_public": True})
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found or no longer public.")

    # Increment view count (fire and forget — failure doesn't block response)
    try:
        recipe.view_count += 1
        await recipe.save()
    except Exception:
        pass

    return {"ok": True, "data": _public_recipe(recipe)}


# ── Visibility toggle ────────────────────────────────────────────────────────


class VisibilityRequest(BaseModel):
    is_public: bool


@router.patch("/api/recipes/{recipe_id}/visibility", summary="Toggle recipe public/private")
async def set_visibility(
    recipe_id: str,
    body: VisibilityRequest,
    user_id: str = Depends(require_auth),
) -> dict:
    """
    Make a recipe public (appears in the explore feed) or private.
    Generates a stable share_token when making public for the first time.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    recipe.is_public = body.is_public

    if body.is_public and not recipe.share_token:
        # Generate a stable, URL-safe share token on first publication
        recipe.share_token = secrets.token_urlsafe(12)

    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    share_url = (
        f"https://reelrecipes.app/r/{recipe.share_token}"
        if recipe.share_token and recipe.is_public
        else None
    )

    return {
        "ok": True,
        "data": {
            "is_public": recipe.is_public,
            "share_token": recipe.share_token,
            "share_url": share_url,
        },
    }


# ── Duplicate ────────────────────────────────────────────────────────────────


@router.post("/api/recipes/{recipe_id}/duplicate", summary="Copy recipe to my cookbook", status_code=201)
async def duplicate_recipe(
    recipe_id: str,
    user_id: str = Depends(require_auth),
) -> dict:
    """
    Copies a public recipe into the authenticated user's cookbook.
    Increments the original recipe's share_count.
    The copy is always private (is_public=False) and fully editable.
    """
    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    original = await RecipeDocument.get(oid)
    if not original:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if not original.is_public and original.user_id != user_id:
        raise HTTPException(status_code=403, detail="Recipe is not public")

    # Create a full copy owned by the requesting user
    copy = RecipeDocument(
        user_id=user_id,
        source_url=original.source_url,
        platform=original.platform,
        title=f"{original.title} (copy)",
        description=original.description,
        cuisine=original.cuisine,
        difficulty=original.difficulty,
        servings=original.servings,
        prep_time_minutes=original.prep_time_minutes,
        cook_time_minutes=original.cook_time_minutes,
        total_time_minutes=original.total_time_minutes,
        thumbnail_url=original.thumbnail_url,
        ingredients=list(original.ingredients),
        steps=list(original.steps),
        tags=list(original.tags),
        nutrition=original.nutrition,
        # Copy snapshot so the user can also reset to the AI original
        original_title=original.original_title,
        original_servings=original.original_servings,
        original_ingredients=original.original_ingredients,
        original_steps=original.original_steps,
        # Always private on duplicate
        is_public=False,
    )
    await copy.insert()

    # Increment original's share count
    try:
        original.share_count += 1
        await original.save()
    except Exception:
        pass

    return {"ok": True, "data": copy.model_dump(mode="json")}


# ── Helpers ──────────────────────────────────────────────────────────────────


def _public_recipe(recipe: RecipeDocument) -> dict:
    """Return a safe public-facing subset of recipe fields."""
    return {
        "id": str(recipe.id),
        "title": recipe.title,
        "description": recipe.description,
        "cuisine": recipe.cuisine,
        "difficulty": recipe.difficulty,
        "total_time_minutes": recipe.total_time_minutes,
        "thumbnail_url": recipe.thumbnail_url,
        "tags": recipe.tags,
        "servings": recipe.servings,
        "view_count": recipe.view_count,
        "share_count": recipe.share_count,
        "share_token": recipe.share_token,
        "ingredients": [i.model_dump(mode="json") for i in recipe.ingredients],
        "steps": [s.model_dump(mode="json") for s in recipe.steps],
        "nutrition": recipe.nutrition.model_dump(mode="json") if recipe.nutrition else None,
        "created_at": recipe.created_at.isoformat() if recipe.created_at else None,
    }


async def _get_owned_recipe(recipe_id: str, user_id: str) -> RecipeDocument:
    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")
    recipe = await RecipeDocument.get(oid)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if recipe.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your recipe")
    return recipe
