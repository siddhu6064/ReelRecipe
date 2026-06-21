"""
app/routers/export.py

GET  /api/recipes/:id/export/pdf  — stream recipe as PDF
POST /api/recipes/:id/cook-session — log a Cook Mode completion
GET  /api/recipes/:id/cost         — estimate ingredient cost
GET  /api/users/me/stats            — user cooking stats (Wrapped)
"""

from __future__ import annotations

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.auth.clerk import require_auth as get_current_user

router = APIRouter(tags=["export"])


# ── PDF export ─────────────────────────────────────────────────────────────


@router.get(
    "/api/recipes/{recipe_id}/export/pdf",
    summary="Download recipe as PDF",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}}}},
)
async def export_recipe_pdf(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> Response:
    """
    Generates a printable A4 recipe card and streams it as a PDF.
    Available for own recipes and public recipes.
    """
    from app.models.documents import RecipeDocument
    from app.services.pdf_service import generate_recipe_pdf

    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await RecipeDocument.get(oid)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if recipe.user_id != user_id and not recipe.is_public:
        raise HTTPException(status_code=403, detail="Not your recipe")

    pdf_bytes = generate_recipe_pdf(recipe)
    safe_title = "".join(c for c in recipe.title if c.isalnum() or c in " _-")[:50]
    filename = f"{safe_title.replace(' ', '_')}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Cook session logging ────────────────────────────────────────────────────


@router.post(
    "/api/recipes/{recipe_id}/cook-session",
    summary="Log a Cook Mode completion",
    status_code=201,
)
async def log_cook_session(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Called by the mobile Cook Mode when the user taps 'Done 🎉'.
    Appends a UTC timestamp to recipe.cook_log for stats tracking.
    """
    from datetime import UTC, datetime
    from app.models.documents import RecipeDocument

    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await RecipeDocument.get(oid)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")
    if recipe.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not your recipe")

    cook_log = list(recipe.cook_log or [])
    cook_log.append(datetime.now(UTC))
    recipe.cook_log = cook_log
    await recipe.save()

    return {"ok": True, "data": {"total_sessions": len(cook_log)}}


# ── Recipe cost ─────────────────────────────────────────────────────────────


@router.get(
    "/api/recipes/{recipe_id}/cost",
    summary="Estimate recipe ingredient cost",
)
async def recipe_cost(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Estimates the cost of a recipe using pantry item prices.
    Prices must be set via PUT /api/pantry/items/:id with estimated_cost_per_unit.
    Returns None for ingredients with no price set.
    """
    from app.services.cost_service import estimate_recipe_cost

    result = await estimate_recipe_cost(recipe_id, user_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Recipe not found")

    return {"ok": True, "data": result}


# ── User stats ──────────────────────────────────────────────────────────────


@router.get(
    "/api/users/me/stats",
    summary="Get user cooking stats (Wrapped)",
)
async def user_stats(user_id: str = Depends(get_current_user)) -> dict:
    """
    Returns aggregate cooking statistics for the current user:
    total recipes, cuisines tried, top tags, favourite ingredient,
    cook sessions, streak, and more — the 'Wrapped' card data.
    """
    from app.services.stats_service import get_user_stats
    stats = await get_user_stats(user_id)
    return {"ok": True, "data": stats}
