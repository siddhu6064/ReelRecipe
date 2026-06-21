"""
app/routers/ai.py

POST /api/ai/suggest         — generate recipes from pantry contents
POST /api/ai/chat/:recipe_id — conversational Q&A about a recipe
POST /api/ai/substitute      — suggest ingredient substitutions
"""

from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import PantryDocument, RecipeDocument
from app.routers.schemas import AIChatMessage, AISuggestRequest, SubstituteRequest

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.post("/suggest", summary="Generate recipes from pantry")
async def suggest_recipes(
    body: AISuggestRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Reads the user's pantry + preferences, asks GPT-4o for 3–5
    full recipe suggestions. Results are cached in Redis for 24h.
    """
    from app.services.ai_suggest import suggest_from_pantry

    pantry = await PantryDocument.find_one({"user_id": user_id})
    items = pantry.items if pantry else []

    # Auto-merge stored user prefs with any explicit prefs from the request body.
    # Request body prefs take precedence — stored prefs fill in what's not specified.
    effective_dietary = body.dietary_prefs
    effective_cuisine = body.cuisine_prefs

    if not effective_dietary or not effective_cuisine:
        from app.models.documents import UserDocument
        user = await UserDocument.find_one({"clerk_id": user_id})
        if user:
            if not effective_dietary:
                effective_dietary = user.dietary_prefs
            if not effective_cuisine:
                effective_cuisine = user.cuisine_prefs

    recipes = await suggest_from_pantry(
        pantry_items=items,
        dietary_prefs=effective_dietary,
        cuisine_prefs=effective_cuisine,
        max_recipes=body.max_recipes,
        user_id=user_id,
    )
    return {"ok": True, "data": recipes}


@router.post("/chat/{recipe_id}", summary="Chat about a recipe")
async def chat_about_recipe(
    recipe_id: str,
    body: AIChatMessage,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Conversational Q&A about a specific recipe. Accepts a history array
    so the client maintains conversation state.
    """
    from app.services.ai_chat import chat_about

    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await RecipeDocument.get(oid)
    if not recipe or recipe.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recipe not found")

    reply = await chat_about(recipe=recipe, message=body.message, history=body.history)
    return {"ok": True, "data": {"reply": reply}}


@router.post("/substitute", summary="Suggest ingredient substitutions")
async def substitute_ingredient(
    body: SubstituteRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Given a recipe + ingredient name, returns 2–3 alternative ingredients
    with notes on how each substitution affects the dish.
    """
    from app.services.substitution import get_substitutions

    try:
        oid = PydanticObjectId(body.recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await RecipeDocument.get(oid)
    if not recipe or recipe.user_id != user_id:
        raise HTTPException(status_code=404, detail="Recipe not found")

    subs = await get_substitutions(recipe=recipe, ingredient_name=body.ingredient_name)
    return {"ok": True, "data": subs}
