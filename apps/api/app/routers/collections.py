"""
app/routers/collections.py

Recipe collections — named folders that group saved recipes.

GET    /api/collections               — list user's collections
POST   /api/collections               — create collection
PUT    /api/collections/:id           — rename / re-emoji
DELETE /api/collections/:id           — delete collection
GET    /api/collections/:id/recipes   — recipes in a collection (full objects)
POST   /api/collections/:id/recipes   — add recipe to collection
DELETE /api/collections/:id/recipes/:recipe_id  — remove recipe
"""

from __future__ import annotations

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.clerk import require_auth as get_current_user
from app.models.collection import RecipeCollection
from app.models.documents import RecipeDocument

router = APIRouter(prefix="/api/collections", tags=["collections"])


# ── Schemas ──────────────────────────────────────────────────────────────────


class CreateCollectionRequest(BaseModel):
    name: str
    emoji: str = "📁"


class UpdateCollectionRequest(BaseModel):
    name: str | None = None
    emoji: str | None = None


class AddRecipeRequest(BaseModel):
    recipe_id: str


# ── List / create ────────────────────────────────────────────────────────────


@router.get("", summary="List collections")
async def list_collections(user_id: str = Depends(get_current_user)) -> dict:
    cols = await RecipeCollection.find({"user_id": user_id}).sort("name").to_list()
    return {
        "ok": True,
        "data": [
            {
                **c.model_dump(mode="json"),
                "recipe_count": len(c.recipe_ids),
            }
            for c in cols
        ],
    }


@router.post("", summary="Create collection", status_code=201)
async def create_collection(
    body: CreateCollectionRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Collection name cannot be empty")

    # Enforce unique name per user
    existing = await RecipeCollection.find_one({"user_id": user_id, "name": name})
    if existing:
        raise HTTPException(status_code=409, detail=f'A collection named "{name}" already exists')

    col = RecipeCollection(user_id=user_id, name=name, emoji=body.emoji)
    await col.insert()
    return {"ok": True, "data": col.model_dump(mode="json")}


# ── Update / delete ───────────────────────────────────────────────────────────


@router.put("/{col_id}", summary="Update collection")
async def update_collection(
    col_id: str,
    body: UpdateCollectionRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    col = await _get_owned_col(col_id, user_id)

    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=400, detail="Name cannot be empty")
        # Check uniqueness
        existing = await RecipeCollection.find_one(
            {"user_id": user_id, "name": name}
        )
        if existing and str(existing.id) != col_id:
            raise HTTPException(status_code=409, detail=f'Name "{name}" already in use')
        col.name = name

    if body.emoji is not None:
        col.emoji = body.emoji

    col.updated_at = datetime.now(UTC)
    await col.save()
    return {"ok": True, "data": col.model_dump(mode="json")}


@router.delete("/{col_id}", summary="Delete collection", status_code=204)
async def delete_collection(
    col_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    col = await _get_owned_col(col_id, user_id)
    await col.delete()


# ── Recipes in collection ─────────────────────────────────────────────────────


@router.get("/{col_id}/recipes", summary="List recipes in collection")
async def list_collection_recipes(
    col_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    col = await _get_owned_col(col_id, user_id)

    # Fetch full recipe objects
    recipes: list[RecipeDocument] = []
    for rid in col.recipe_ids:
        try:
            r = await RecipeDocument.get(PydanticObjectId(rid))
            if r and r.user_id == user_id:
                recipes.append(r)
        except Exception:
            continue   # skip invalid / deleted recipes

    return {
        "ok": True,
        "data": {
            "collection": col.model_dump(mode="json"),
            "recipes": [r.model_dump(mode="json") for r in recipes],
        },
    }


@router.post("/{col_id}/recipes", summary="Add recipe to collection", status_code=201)
async def add_recipe_to_collection(
    col_id: str,
    body: AddRecipeRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    col = await _get_owned_col(col_id, user_id)

    # Verify recipe exists and belongs to user
    try:
        recipe = await RecipeDocument.get(PydanticObjectId(body.recipe_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    if not recipe or recipe.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if body.recipe_id in col.recipe_ids:
        return {"ok": True, "data": col.model_dump(mode="json"), "added": False}

    col.recipe_ids.append(body.recipe_id)
    col.updated_at = datetime.now(UTC)
    await col.save()
    return {"ok": True, "data": col.model_dump(mode="json"), "added": True}


@router.delete("/{col_id}/recipes/{recipe_id}", summary="Remove recipe from collection", status_code=204)
async def remove_recipe_from_collection(
    col_id: str,
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    col = await _get_owned_col(col_id, user_id)
    col.recipe_ids = [rid for rid in col.recipe_ids if rid != recipe_id]
    col.updated_at = datetime.now(UTC)
    await col.save()


# ── Helper ────────────────────────────────────────────────────────────────────


async def _get_owned_col(col_id: str, user_id: str) -> RecipeCollection:
    try:
        oid = PydanticObjectId(col_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid collection ID")
    col = await RecipeCollection.get(oid)
    if not col:
        raise HTTPException(status_code=404, detail="Collection not found")
    if col.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your collection")
    return col
