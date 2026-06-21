"""
app/routers/meal_plan.py

GET    /api/meal-plans              — list user's meal plans
POST   /api/meal-plans              — create a new plan
GET    /api/meal-plans/active       — get the currently active plan
GET    /api/meal-plans/:id          — get specific plan
PUT    /api/meal-plans/:id          — update a plan (add/remove meals)
DELETE /api/meal-plans/:id          — delete a plan
GET    /api/meal-plans/:id/shopping — generate shopping list from plan
"""

from __future__ import annotations

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import PantryDocument, RecipeDocument
from app.models.meal_plan import MealPlanDay, MealPlanDocument, MealSlot, PlannedMeal
from app.services.pantry_match import _best_match

router = APIRouter(prefix="/api/meal-plans", tags=["meal-plans"])


# ── Request schemas ────────────────────────────────────────────────────────


class CreatePlanRequest(BaseModel):
    title: str = "Weekly Plan"
    week_start_date: str | None = None


class AddMealRequest(BaseModel):
    day_index: int              # 0–6
    recipe_id: str
    slot: MealSlot = MealSlot.DINNER
    servings_override: int | None = None
    notes: str | None = None


class RemoveMealRequest(BaseModel):
    day_index: int
    meal_id: str


# ── Helpers ────────────────────────────────────────────────────────────────


async def _get_owned_plan(plan_id: str, user_id: str) -> MealPlanDocument:
    try:
        oid = PydanticObjectId(plan_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid plan ID")
    plan = await MealPlanDocument.get(oid)
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    if plan.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your meal plan")
    return plan


# ── Endpoints ──────────────────────────────────────────────────────────────


@router.get("", summary="List meal plans")
async def list_plans(user_id: str = Depends(get_current_user)) -> dict:
    plans = await MealPlanDocument.find({"user_id": user_id}).sort("-created_at").to_list()
    return {"ok": True, "data": [p.model_dump(mode="json") for p in plans]}


@router.post("", summary="Create meal plan", status_code=201)
async def create_plan(
    body: CreatePlanRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    # Deactivate previous active plan
    await MealPlanDocument.find({"user_id": user_id, "is_active": True}).update(
        {"$set": {"is_active": False}}
    )
    plan = MealPlanDocument(
        user_id=user_id,
        title=body.title,
        week_start_date=body.week_start_date,
    )
    await plan.insert()
    return {"ok": True, "data": plan.model_dump(mode="json")}


@router.get("/active", summary="Get active meal plan")
async def get_active_plan(user_id: str = Depends(get_current_user)) -> dict:
    plan = await MealPlanDocument.find_one({"user_id": user_id, "is_active": True})
    if not plan:
        raise HTTPException(status_code=404, detail="No active meal plan")
    return {"ok": True, "data": plan.model_dump(mode="json")}


@router.get("/{plan_id}", summary="Get meal plan")
async def get_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    plan = await _get_owned_plan(plan_id, user_id)
    return {"ok": True, "data": plan.model_dump(mode="json")}


@router.post("/{plan_id}/meals", summary="Add meal to plan")
async def add_meal(
    plan_id: str,
    body: AddMealRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    plan = await _get_owned_plan(plan_id, user_id)

    if not 0 <= body.day_index <= 6:
        raise HTTPException(status_code=400, detail="day_index must be 0–6")

    # Fetch recipe metadata for denormalisation
    try:
        recipe = await RecipeDocument.get(PydanticObjectId(body.recipe_id))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")
    if not recipe or recipe.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recipe not found")

    meal = PlannedMeal(
        recipe_id=body.recipe_id,
        recipe_title=recipe.title,
        recipe_thumbnail=recipe.thumbnail_url,
        slot=body.slot,
        servings_override=body.servings_override,
        notes=body.notes,
    )

    # Ensure the day exists in the plan
    day = next((d for d in plan.days if d.day_index == body.day_index), None)
    if day is None:
        day = MealPlanDay(day_index=body.day_index)
        plan.days.append(day)

    day.meals.append(meal)
    plan.updated_at = datetime.now(UTC)
    await plan.save()
    return {"ok": True, "data": plan.model_dump(mode="json")}


@router.delete("/{plan_id}/meals", summary="Remove meal from plan", status_code=204)
async def remove_meal(
    plan_id: str,
    body: RemoveMealRequest,
    user_id: str = Depends(get_current_user),
) -> None:
    plan = await _get_owned_plan(plan_id, user_id)
    for day in plan.days:
        if day.day_index == body.day_index:
            day.meals = [m for m in day.meals if m.id != body.meal_id]
    plan.updated_at = datetime.now(UTC)
    await plan.save()


@router.delete("/{plan_id}", summary="Delete meal plan", status_code=204)
async def delete_plan(
    plan_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    plan = await _get_owned_plan(plan_id, user_id)
    await plan.delete()


@router.get("/{plan_id}/shopping", summary="Generate shopping list")
async def shopping_list(
    plan_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns a deduplicated shopping list of ingredients needed for this
    meal plan that the user does NOT already have in their pantry.
    Grouped by ingredient category.
    """
    plan = await _get_owned_plan(plan_id, user_id)

    # Collect all recipe IDs in the plan
    recipe_ids: list[str] = []
    for day in plan.days:
        for meal in day.meals:
            if meal.recipe_id not in recipe_ids:
                recipe_ids.append(meal.recipe_id)

    if not recipe_ids:
        return {"ok": True, "data": {"items": [], "total_count": 0}}

    # Load pantry
    pantry = await PantryDocument.find_one({"user_id": user_id})
    pantry_items = pantry.items if pantry else []

    # Aggregate missing ingredients across all planned recipes
    missing: dict[str, dict] = {}   # name → {name, recipes_needed}

    for rid in recipe_ids:
        try:
            recipe = await RecipeDocument.get(PydanticObjectId(rid))
        except Exception:
            continue
        if not recipe:
            continue
        for ing in recipe.ingredients:
            if ing.optional:
                continue
            match_name, _ = _best_match(ing.name, pantry_items)
            if not match_name:
                key = ing.name.lower()
                if key not in missing:
                    missing[key] = {
                        "name": ing.name,
                        "unit": ing.unit,
                        "needed_for": [recipe.title],
                    }
                elif recipe.title not in missing[key]["needed_for"]:
                    missing[key]["needed_for"].append(recipe.title)

    items = sorted(missing.values(), key=lambda x: x["name"])
    return {"ok": True, "data": {"items": items, "total_count": len(items)}}
