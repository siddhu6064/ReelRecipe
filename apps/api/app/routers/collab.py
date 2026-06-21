"""
app/routers/collab.py

Recipe collaboration — share a recipe with other users for viewing or editing.

POST  /api/recipes/:id/invite             — generate invite link (owner only)
GET   /api/recipes/:id/collaborators      — list collaborators (owner only)
PATCH /api/recipes/:id/collaborators/:uid — change collaborator role
DELETE /api/recipes/:id/collaborators/:uid — remove collaborator
GET   /api/recipes/:id/can-edit           — permission check (any authed user)
POST  /api/invites/accept/:token          — accept an invite via token
"""

from __future__ import annotations

from datetime import UTC, datetime

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import CollaboratorEntry, CollaboratorRole, RecipeDocument

router = APIRouter(tags=["collaboration"])


# ── Schemas ────────────────────────────────────────────────────────────────


class InviteRequest(BaseModel):
    role: str = "viewer"   # "viewer" | "editor"


class RoleUpdateRequest(BaseModel):
    role: str              # "viewer" | "editor"


# ── Invite ─────────────────────────────────────────────────────────────────


@router.post("/api/recipes/{recipe_id}/invite", summary="Generate invite link", status_code=201)
async def create_invite(
    recipe_id: str,
    body: InviteRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Generates a one-time invite token for the recipe.
    The returned token is appended to the app URL so recipients
    can accept by visiting /invites/accept/:token.
    """
    recipe = await _get_owned(recipe_id, user_id)

    role = CollaboratorRole.EDITOR if body.role == "editor" else CollaboratorRole.VIEWER
    entry = CollaboratorEntry(user_id="pending", role=role)   # user_id set on accept

    collabs = list(recipe.collaborators or [])
    collabs.append(entry)
    recipe.collaborators = collabs
    await recipe.save()

    invite_url = f"https://reelrecipes.app/invites/accept/{entry.invite_token}"
    return {
        "ok": True,
        "data": {
            "invite_token": entry.invite_token,
            "invite_url": invite_url,
            "role": role.value,
            "expires": "never",   # tokens don't expire — revoke by removing collaborator
        },
    }


# ── List collaborators ─────────────────────────────────────────────────────


@router.get("/api/recipes/{recipe_id}/collaborators", summary="List collaborators")
async def list_collaborators(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    recipe = await _get_owned(recipe_id, user_id)
    accepted = [c for c in (recipe.collaborators or []) if c.accepted]
    pending  = [c for c in (recipe.collaborators or []) if not c.accepted]

    def _serialize(c: CollaboratorEntry) -> dict:
        return {
            "user_id": c.user_id,
            "email": c.email,
            "role": c.role.value,
            "accepted": c.accepted,
            "invited_at": c.invited_at.isoformat(),
        }

    return {
        "ok": True,
        "data": {
            "accepted": [_serialize(c) for c in accepted],
            "pending":  [_serialize(c) for c in pending],
        },
    }


# ── Change role ────────────────────────────────────────────────────────────


@router.patch(
    "/api/recipes/{recipe_id}/collaborators/{collab_user_id}",
    summary="Change collaborator role",
)
async def update_role(
    recipe_id: str,
    collab_user_id: str,
    body: RoleUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    recipe = await _get_owned(recipe_id, user_id)

    new_role = CollaboratorRole.EDITOR if body.role == "editor" else CollaboratorRole.VIEWER
    updated = False
    for c in recipe.collaborators or []:
        if c.user_id == collab_user_id:
            c.role = new_role
            updated = True
            break

    if not updated:
        raise HTTPException(status_code=404, detail="Collaborator not found")

    await recipe.save()
    return {"ok": True, "data": {"user_id": collab_user_id, "role": new_role.value}}


# ── Remove collaborator ────────────────────────────────────────────────────


@router.delete(
    "/api/recipes/{recipe_id}/collaborators/{collab_user_id}",
    summary="Remove collaborator",
    status_code=204,
)
async def remove_collaborator(
    recipe_id: str,
    collab_user_id: str,
    user_id: str = Depends(get_current_user),
) -> None:
    recipe = await _get_owned(recipe_id, user_id)
    recipe.collaborators = [c for c in (recipe.collaborators or []) if c.user_id != collab_user_id]
    await recipe.save()


# ── Permission check ───────────────────────────────────────────────────────


@router.get("/api/recipes/{recipe_id}/can-edit", summary="Check edit permission")
async def can_edit(
    recipe_id: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Returns whether the current user can edit this recipe.
    True for: the owner, or an accepted collaborator with 'editor' role.
    """
    try:
        oid = PydanticObjectId(recipe_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid recipe ID")

    recipe = await RecipeDocument.get(oid)
    if not recipe:
        raise HTTPException(status_code=404, detail="Recipe not found")

    if recipe.user_id == user_id:
        return {"ok": True, "data": {"can_edit": True, "role": "owner"}}

    for c in (recipe.collaborators or []):
        if c.user_id == user_id and c.accepted:
            return {
                "ok": True,
                "data": {
                    "can_edit": c.role == CollaboratorRole.EDITOR,
                    "role": c.role.value,
                },
            }

    return {"ok": True, "data": {"can_edit": False, "role": None}}


# ── Accept invite ──────────────────────────────────────────────────────────


@router.post("/api/invites/accept/{token}", summary="Accept invite token", status_code=200)
async def accept_invite(
    token: str,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Finds the pending CollaboratorEntry matching the token, sets
    user_id to the current user, and marks it as accepted.
    """
    # Scan all recipes for a matching pending token
    recipe = await RecipeDocument.find_one(
        {"collaborators": {"$elemMatch": {"invite_token": token, "accepted": False}}}
    )
    if not recipe:
        raise HTTPException(status_code=404, detail="Invite not found or already accepted")

    for c in recipe.collaborators:
        if c.invite_token == token and not c.accepted:
            c.user_id = user_id
            c.accepted = True
            break

    await recipe.save()
    return {
        "ok": True,
        "data": {
            "recipe_id": str(recipe.id),
            "recipe_title": recipe.title,
        },
    }


# ── Helper ─────────────────────────────────────────────────────────────────


async def _get_owned(recipe_id: str, user_id: str) -> RecipeDocument:
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
