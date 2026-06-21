"""
app/routers/pantry.py

GET    /api/pantry              — get user pantry
POST   /api/pantry/items        — add ingredient
PUT    /api/pantry/items/:id    — edit ingredient
DELETE /api/pantry/items/:id    — remove ingredient
GET    /api/pantry/match        — recipes ranked by pantry match %
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import PantryDocument, PantryItem, RecipeDocument
from app.routers.schemas import PantryItemIn, PantryItemUpdateRequest
from app.services.pantry_match import score_recipes

router = APIRouter(prefix="/api/pantry", tags=["pantry"])


async def _get_or_create_pantry(user_id: str) -> PantryDocument:
    pantry = await PantryDocument.find_one({"user_id": user_id})
    if not pantry:
        pantry = PantryDocument(user_id=user_id)
        await pantry.insert()
    return pantry


@router.get("", summary="Get user pantry")
async def get_pantry(user_id: str = Depends(get_current_user)) -> dict:
    pantry = await _get_or_create_pantry(user_id)
    return {"ok": True, "data": pantry.model_dump(mode="json")}


@router.post("/items", summary="Add pantry item", status_code=201)
async def add_item(
    body: PantryItemIn,
    user_id: str = Depends(get_current_user),
) -> dict:
    pantry = await _get_or_create_pantry(user_id)
    from datetime import datetime as _dt
    expiry = None
    if getattr(body, 'expiry_date', None):
        try:
            parsed = _dt.fromisoformat(body.expiry_date)
            expiry = parsed.replace(tzinfo=UTC) if parsed.tzinfo else parsed.replace(hour=23, minute=59, second=59, tzinfo=UTC)
        except ValueError:
            pass

    item = PantryItem(
        id=str(uuid.uuid4()),
        name=body.name.strip().lower(),
        quantity=body.quantity,
        expiry_date=expiry,
        unit=body.unit,
        category=body.category,
    )
    pantry.items.append(item)
    pantry.updated_at = datetime.now(UTC)
    await pantry.save()
    return {"ok": True, "data": item.model_dump(mode="json")}


@router.put("/items/{item_id}", summary="Update pantry item")
async def update_item(
    item_id: str,
    body: PantryItemUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    pantry = await _get_or_create_pantry(user_id)
    item = next((i for i in pantry.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")

    if body.quantity is not None:
        item.quantity = body.quantity
    if body.unit is not None:
        item.unit = body.unit
    if body.category is not None:
        item.category = body.category
    # Handle expiry_date — None means "clear it", missing means "leave it"
    if hasattr(body, 'expiry_date'):
        if body.expiry_date:
            from datetime import datetime as _dt
            try:
                item.expiry_date = _dt.fromisoformat(body.expiry_date).replace(tzinfo=UTC)
            except ValueError:
                pass
        else:
            item.expiry_date = None
    item.updated_at = datetime.now(UTC)
    pantry.updated_at = datetime.now(UTC)
    await pantry.save()
    return {"ok": True, "data": item.model_dump(mode="json")}


@router.delete("/items/{item_id}", summary="Remove pantry item", status_code=204)
async def delete_item(
    item_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    pantry = await _get_or_create_pantry(user_id)
    pantry.items = [i for i in pantry.items if i.id != item_id]
    pantry.updated_at = datetime.now(UTC)
    await pantry.save()


@router.get("/match", summary="Recipes ranked by pantry match %")
async def match_recipes(
    user_id: str = Depends(get_current_user),
    prefs_only: bool = Query(default=False, description="Only return recipes compatible with user dietary prefs"),
) -> dict:
    """
    Returns all user recipes scored by how many ingredients they can
    cover from the pantry, descending. Each entry includes:
      - recipe id, title, thumbnail
      - match_pct (0.0–1.0)
      - matched_ingredients []
      - missing_ingredients []
      - prefs_compatible: bool — whether the recipe fits user dietary prefs
    """
    from app.models.documents import UserDocument
    from app.services.recipe_service import prefs_compatible as _prefs_compatible

    pantry = await _get_or_create_pantry(user_id)
    recipes = await RecipeDocument.find({"user_id": user_id}).to_list()

    # Load user prefs for compatibility tagging
    user = await UserDocument.find_one({"clerk_id": user_id})
    dietary_prefs = user.dietary_prefs if user else []

    results = score_recipes(pantry.items, recipes)

    # Annotate each result with prefs_compatible
    recipe_map = {str(r.id): r for r in recipes}
    for result in results:
        recipe = recipe_map.get(result["recipe_id"])
        result["prefs_compatible"] = (
            _prefs_compatible(recipe, dietary_prefs) if recipe else True
        )

    # Optionally filter to only pref-compatible recipes
    if prefs_only:
        results = [r for r in results if r["prefs_compatible"]]

    return {"ok": True, "data": results}


# ── Barcode lookup ──────────────────────────────────────────────────────────


@router.get("/barcode/{barcode}", summary="Look up a product barcode")
async def barcode_lookup(
    barcode: str,
    _: str = Depends(get_current_user),
) -> dict:
    """
    Resolves a product barcode (EAN-13 / UPC-A) to a pantry ingredient name
    via the Open Food Facts API (free, no key required).

    Returns the product name, category, and brand — auto-fills the
    add-ingredient form in the mobile barcode scanner.
    """
    from app.services.barcode_service import lookup_barcode

    if not barcode.isdigit():
        raise HTTPException(status_code=400, detail="Barcode must contain digits only")

    result = await lookup_barcode(barcode)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"Barcode {barcode} not found in Open Food Facts database.",
        )
    return {"ok": True, "data": result}


# ── Price update ────────────────────────────────────────────────────────────


class PriceUpdateRequest(BaseModel):
    estimated_cost_per_unit: float | None


@router.put("/items/{item_id}/price", summary="Set ingredient price for cost estimation")
async def update_item_price(
    item_id: str,
    body: PriceUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Sets or clears the price per unit for a pantry ingredient.
    Used by GET /api/recipes/:id/cost to estimate total recipe cost.
    """
    pantry = await _get_or_create_pantry(user_id)
    item = next((i for i in pantry.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found")

    item.estimated_cost_per_unit = body.estimated_cost_per_unit
    item.updated_at = datetime.now(UTC)
    await pantry.save()

    return {"ok": True, "data": {"id": item_id, "estimated_cost_per_unit": item.estimated_cost_per_unit}}


# ── Expiry management ────────────────────────────────────────────────────────


class ExpiryUpdateRequest(BaseModel):
    expiry_date: str | None   # ISO-8601 or null to clear


@router.put("/items/{item_id}/expiry", summary="Set or clear expiry date on a pantry item")
async def update_item_expiry(
    item_id: str,
    body: ExpiryUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Sets or clears the expiry date for a pantry item.
    Pass expiry_date as an ISO-8601 string (e.g. "2025-12-31") or null to clear.
    """
    pantry = await _get_or_create_pantry(user_id)
    item = next((i for i in pantry.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=404, detail="Pantry item not found")

    if body.expiry_date:
        from datetime import datetime as _dt
        try:
            item.expiry_date = _dt.fromisoformat(body.expiry_date).replace(tzinfo=UTC)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid date format. Use ISO-8601 (e.g. 2025-12-31)")
    else:
        item.expiry_date = None

    item.updated_at = datetime.now(UTC)
    await pantry.save()
    return {
        "ok": True,
        "data": {
            "id": item_id,
            "expiry_date": item.expiry_date.isoformat() if item.expiry_date else None,
        },
    }


@router.get("/expiring", summary="List pantry items expiring within N days")
async def expiring_items(
    days: int = Query(default=7, ge=1, le=90, description="Look-ahead window in days"),
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns pantry items that expire within the next `days` days.
    Useful for surfacing 'use it up' recipe suggestions.
    """
    from datetime import timedelta
    pantry = await _get_or_create_pantry(user_id)
    cutoff = datetime.now(UTC) + timedelta(days=days)

    expiring = [
        item for item in pantry.items
        if item.expiry_date is not None and item.expiry_date.replace(tzinfo=UTC) <= cutoff
    ]

    # Sort by soonest expiry first
    expiring.sort(key=lambda i: i.expiry_date)

    return {
        "ok": True,
        "data": {
            "items": [i.model_dump(mode="json") for i in expiring],
            "total": len(expiring),
            "window_days": days,
        },
    }
