"""
app/routers/recipes.py

GET    /api/recipes               — list cookbook (search, filter, auto-apply prefs)
GET    /api/recipes/:id           — single recipe
PUT    /api/recipes/:id           — edit fields (triggers rescale when servings changes)
DELETE /api/recipes/:id           — remove from cookbook
GET    /api/recipes/:id/original  — return the original AI-extracted version
POST   /api/recipes/:id/reset     — restore original AI extraction
POST   /api/recipes/:id/favourite — star a recipe
DELETE /api/recipes/:id/favourite — un-star a recipe
PUT    /api/recipes/:id/notes     — set personal cooking notes
"""

from __future__ import annotations

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import RecipeDocument, UserDocument
from app.routers.schemas import RecipeFilterParams, RecipeUpdateRequest
from app.services.recipe_service import prefs_compatible, rescale_ingredients
from app.services.snapshot_service import pop_snapshot, push_snapshot

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


# ── Schema ─────────────────────────────────────────────────────────────────


class NotesRequest(BaseModel):
    notes: str | None = None


# ── List + filter ──────────────────────────────────────────────────────────


@router.get("", summary="List user cookbook")
async def list_recipes(
    filters: RecipeFilterParams = Depends(),
    favourites: bool = Query(default=False, description="Only return starred recipes"),
    apply_prefs: bool = Query(default=True, description="Auto-apply user dietary/cuisine prefs"),
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns the user's cookbook with optional filtering.

    When apply_prefs=true (default) and no explicit cuisine/tags filter is
    passed, the user's stored dietary and cuisine preferences are applied
    automatically so the default view shows relevant recipes first.
    """
    query: dict = {"user_id": user_id}

    # Explicit filters take priority over auto-prefs
    if filters.cuisine:
        query["cuisine"] = filters.cuisine
    if filters.difficulty:
        query["difficulty"] = filters.difficulty
    if filters.tags:
        query["tags"] = {"$all": filters.tags}
    if filters.search:
        query["title"] = {"$regex": filters.search, "$options": "i"}
    if favourites:
        query["is_favourite"] = True

    # Auto-apply stored user preferences when no explicit cuisine/tag filter
    if apply_prefs and not filters.cuisine and not filters.tags:
        user = await UserDocument.find_one({"clerk_id": user_id})
        if user:
            if user.cuisine_prefs and not filters.cuisine:
                # Soft filter: show preferred cuisines first (not exclusive)
                # For now, apply as an OR filter so user still sees all
                pass   # Cuisine preference is a sort hint, not a hard filter
            # Dietary: hard filter — only show compatible recipes by default
            if user.dietary_prefs:
                from app.services.recipe_service import build_prefs_query
                prefs_query = build_prefs_query(user.dietary_prefs, [])
                # Merge tag filters
                if "tags" in prefs_query:
                    query.setdefault("tags", {})
                    if "$all" in prefs_query["tags"]:
                        existing = query["tags"].get("$all", []) if isinstance(query["tags"], dict) else []
                        query["tags"] = {"$all": list(set(existing + prefs_query["tags"]["$all"]))}

    recipes = (
        await RecipeDocument.find(query)
        .skip(filters.offset)
        .limit(filters.limit)
        .sort([("is_favourite", -1), ("created_at", -1)])   # starred first
        .to_list()
    )
    total = await RecipeDocument.find(query).count()

    return {
        "ok": True,
        "data": {
            "recipes": [r.model_dump(mode="json") for r in recipes],
            "total": total,
            "limit": filters.limit,
            "offset": filters.offset,
        },
    }


# ── Single recipe ──────────────────────────────────────────────────────────


@router.get("/{recipe_id}", summary="Get single recipe")
async def get_recipe(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    recipe = await _get_owned_recipe(recipe_id, user_id)
    return {"ok": True, "data": recipe.model_dump(mode="json")}


# ── Edit ───────────────────────────────────────────────────────────────────


@router.put("/{recipe_id}", summary="Edit recipe fields")
async def update_recipe(
    recipe_id: str,
    body: RecipeUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Update any recipe field.
    When `servings` changes, all ingredient quantities are proportionally
    rescaled to the new serving count automatically.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    update_data = body.model_dump(exclude_none=True)
    if not update_data:
        return {"ok": True, "data": recipe.model_dump(mode="json")}

    # Build undo label before applying changes
    changed = list(update_data.keys())
    label = f"Edited: {', '.join(changed)}"
    if "servings" in changed:
        label = f"Scaled to {update_data['servings']} servings"
    elif "title" in changed:
        label = "Edited title"
    elif "ingredients" in changed:
        label = "Edited ingredients"
    elif "steps" in changed:
        label = "Edited steps"

    # Snapshot current state BEFORE mutation (enables undo)
    await push_snapshot(recipe, label)

    # Rescale ingredients when servings changes
    new_servings = update_data.get("servings")
    if new_servings and new_servings != recipe.servings and recipe.ingredients:
        update_data["ingredients"] = rescale_ingredients(
            ingredients=recipe.ingredients,
            old_servings=recipe.servings,
            new_servings=new_servings,
        )

    for field, value in update_data.items():
        setattr(recipe, field, value)

    recipe.is_edited = True
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    return {"ok": True, "data": recipe.model_dump(mode="json")}


# ── Delete ─────────────────────────────────────────────────────────────────


@router.delete("/{recipe_id}", summary="Delete recipe", status_code=204)
async def delete_recipe(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    recipe = await _get_owned_recipe(recipe_id, user_id)
    await recipe.delete()


# ── Original extraction ─────────────────────────────────────────────────────


@router.get("/{recipe_id}/original", summary="Get original AI extraction")
async def get_original(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns the original GPT-4o extraction — the recipe as it was
    imported, before any manual edits.
    Returns 404 if the recipe was imported before the snapshot feature existed.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    if recipe.original_ingredients is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "No original snapshot available for this recipe. "
                "Snapshots are created for all recipes imported after the P1 update."
            ),
        )

    return {
        "ok": True,
        "data": {
            "title": recipe.original_title or recipe.title,
            "servings": recipe.original_servings or recipe.servings,
            "ingredients": [i.model_dump(mode="json") for i in recipe.original_ingredients],
            "steps": [s.model_dump(mode="json") for s in (recipe.original_steps or [])],
            "is_edited": recipe.is_edited,
        },
    }


@router.post("/{recipe_id}/reset", summary="Reset to original AI extraction")
async def reset_to_original(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Restores title, servings, ingredients, and steps to the original
    GPT-4o extraction. personal_notes and tags are preserved.
    Raises 404 if no snapshot exists.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    if recipe.original_ingredients is None:
        raise HTTPException(
            status_code=404,
            detail="No original snapshot available for this recipe.",
        )

    recipe.title = recipe.original_title or recipe.title
    recipe.servings = recipe.original_servings or recipe.servings
    recipe.ingredients = recipe.original_ingredients
    recipe.steps = recipe.original_steps or recipe.steps
    recipe.is_edited = False
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    return {"ok": True, "data": recipe.model_dump(mode="json")}


# ── Favourite ──────────────────────────────────────────────────────────────


@router.post("/{recipe_id}/favourite", summary="Star a recipe", status_code=201)
async def add_favourite(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    recipe = await _get_owned_recipe(recipe_id, user_id)
    if not recipe.is_favourite:
        recipe.is_favourite = True
        recipe.updated_at = datetime.now(UTC)
        await recipe.save()
    return {"ok": True, "data": {"is_favourite": True}}


@router.delete("/{recipe_id}/favourite", summary="Un-star a recipe", status_code=204)
async def remove_favourite(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    recipe = await _get_owned_recipe(recipe_id, user_id)
    if recipe.is_favourite:
        recipe.is_favourite = False
        recipe.updated_at = datetime.now(UTC)
        await recipe.save()


# ── Personal notes ─────────────────────────────────────────────────────────


@router.put("/{recipe_id}/notes", summary="Set personal cooking notes")
async def update_notes(
    recipe_id: str,
    body: NotesRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Save free-text personal notes for a recipe (shopping reminders,
    tweaks, timing notes, etc.). Pass notes=null to clear.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)
    recipe.personal_notes = body.notes
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()
    return {"ok": True, "data": {"personal_notes": recipe.personal_notes}}


# ── Undo / history ───────────────────────────────────────────────────────────


@router.post("/{recipe_id}/undo", summary="Undo last edit")
async def undo_last_edit(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Restores the recipe to the state before the most recent edit.
    Returns 404 if there is nothing to undo.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    snapshot = pop_snapshot(recipe)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Nothing to undo.")

    recipe.title = snapshot.title
    recipe.servings = snapshot.servings
    recipe.ingredients = snapshot.ingredients
    recipe.steps = snapshot.steps
    recipe.personal_notes = snapshot.personal_notes
    recipe.tags = snapshot.tags
    recipe.is_edited = bool(recipe.edit_snapshots)   # still edited if history remains
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    return {"ok": True, "data": recipe.model_dump(mode="json"), "undid": snapshot.label}


@router.get("/{recipe_id}/history", summary="Get edit history")
async def get_history(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns the list of edit snapshots for this recipe, most recent first.
    Each entry has snapshot_id, label, created_at — not the full recipe data.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)
    snapshots = list(reversed(recipe.edit_snapshots or []))
    return {
        "ok": True,
        "data": [
            {
                "snapshot_id": s.snapshot_id,
                "label": s.label,
                "created_at": s.created_at.isoformat(),
            }
            for s in snapshots
        ],
    }


# ── Reorder ───────────────────────────────────────────────────────────────────


class ReorderRequest(BaseModel):
    ids: list[str]   # ordered list of ingredient/step IDs in the desired new sequence


@router.put("/{recipe_id}/ingredients/reorder", summary="Reorder ingredients")
async def reorder_ingredients(
    recipe_id: str,
    body: ReorderRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Reorders recipe ingredients to match the provided ID sequence.
    IDs not present in the recipe are ignored.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    await push_snapshot(recipe, "Reordered ingredients")

    id_to_ing = {i.id: i for i in recipe.ingredients}
    ordered = [id_to_ing[id_] for id_ in body.ids if id_ in id_to_ing]
    # Append any ingredients not in the provided list (safety net)
    provided_ids = set(body.ids)
    ordered += [i for i in recipe.ingredients if i.id not in provided_ids]

    recipe.ingredients = ordered
    recipe.is_edited = True
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    return {"ok": True, "data": recipe.model_dump(mode="json")}


@router.put("/{recipe_id}/steps/reorder", summary="Reorder steps")
async def reorder_steps(
    recipe_id: str,
    body: ReorderRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Reorders recipe steps to match the provided ID sequence,
    then renumbers order 1..N.
    """
    recipe = await _get_owned_recipe(recipe_id, user_id)

    await push_snapshot(recipe, "Reordered steps")

    id_to_step = {s.id: s for s in recipe.steps}
    ordered = [id_to_step[id_] for id_ in body.ids if id_ in id_to_step]
    # Append any steps not in the provided list
    provided_ids = set(body.ids)
    ordered += [s for s in recipe.steps if s.id not in provided_ids]

    # Renumber steps 1..N
    from app.models.documents import RecipeStep
    renumbered = [
        RecipeStep(id=s.id, order=i + 1, text=s.text, timer_seconds=s.timer_seconds)
        for i, s in enumerate(ordered)
    ]

    recipe.steps = renumbered
    recipe.is_edited = True
    recipe.updated_at = datetime.now(UTC)
    await recipe.save()

    return {"ok": True, "data": recipe.model_dump(mode="json")}


# ── Helper ─────────────────────────────────────────────────────────────────


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
