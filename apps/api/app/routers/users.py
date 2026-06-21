"""
app/routers/users.py

POST /api/clerk/webhooks          — Clerk user.created / user.updated sync
GET  /api/users/me                — current user profile
PUT  /api/users/me/prefs          — update dietary / cuisine prefs
PUT  /api/users/me/push-token     — register Expo push token (mobile, called on sign-in)
DELETE /api/users/me/push-token   — deregister push token (mobile, called on sign-out)
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.auth.clerk import require_auth as get_current_user
from app.models.documents import UserDocument
from app.routers.schemas import UserPrefsUpdateRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/users", tags=["users"])
clerk_router = APIRouter(prefix="/api/clerk", tags=["clerk-webhooks"])


# ── Request schemas ────────────────────────────────────────────────────────


class PushTokenRequest(BaseModel):
    push_token: str


# ── Clerk webhook — sync user to MongoDB ──────────────────────────────────


@clerk_router.post("/webhooks", include_in_schema=False)
async def clerk_webhook(request: Request) -> dict:
    """
    Receives Clerk user.created and user.updated events and upserts
    the corresponding UserDocument in MongoDB.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    event_type = payload.get("type")
    data = payload.get("data", {})

    if event_type not in ("user.created", "user.updated"):
        return {"ok": True, "ignored": True}

    clerk_id = data.get("id")
    if not clerk_id:
        raise HTTPException(status_code=400, detail="Missing user id")

    email_addresses = data.get("email_addresses") or []
    email = email_addresses[0].get("email_address", "") if email_addresses else ""
    first = data.get("first_name") or ""
    last = data.get("last_name") or ""
    name = f"{first} {last}".strip() or email
    avatar_url = data.get("image_url")

    existing = await UserDocument.find_one({"clerk_id": clerk_id})
    if existing:
        existing.email = email
        existing.name = name
        existing.avatar_url = avatar_url
        existing.updated_at = datetime.now(UTC)
        await existing.save()
    else:
        user = UserDocument(clerk_id=clerk_id, email=email, name=name, avatar_url=avatar_url)
        await user.insert()

    return {"ok": True}


# ── User profile ───────────────────────────────────────────────────────────


@router.get("/me", summary="Get current user profile")
async def get_me(user_id: str = Depends(get_current_user)) -> dict:
    user = await UserDocument.find_one({"clerk_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return {"ok": True, "data": user.model_dump(mode="json")}


@router.put("/me/prefs", summary="Update user preferences")
async def update_prefs(
    body: UserPrefsUpdateRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    user = await UserDocument.find_one({"clerk_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if body.dietary_prefs is not None:
        user.dietary_prefs = body.dietary_prefs
    if body.cuisine_prefs is not None:
        user.cuisine_prefs = body.cuisine_prefs
    if body.unit_system is not None:
        if body.unit_system not in ("metric", "imperial"):
            raise HTTPException(status_code=400, detail="unit_system must be 'metric' or 'imperial'")
        user.unit_system = body.unit_system

    user.updated_at = datetime.now(UTC)
    await user.save()
    return {"ok": True, "data": user.model_dump(mode="json")}


# ── Push token ────────────────────────────────────────────────────────────


@router.put("/me/push-token", summary="Register Expo push token")
async def register_push_token(
    body: PushTokenRequest,
    user_id: str = Depends(get_current_user),
) -> dict:
    """
    Called by the mobile app after requesting push notification permission.
    Stores the Expo push token so the server can send 'recipe ready'
    notifications when a job completes.

    Idempotent — safe to call on every app launch.
    """
    token = body.push_token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="push_token must not be empty")

    # Validate Expo push token format: ExponentPushToken[xxx] or ea:xxx
    if not (token.startswith("ExponentPushToken[") or token.startswith("ea:")):
        raise HTTPException(
            status_code=400,
            detail="Invalid push token format. Expected ExponentPushToken[...] or ea:...",
        )

    user = await UserDocument.find_one({"clerk_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # No-op if token hasn't changed — avoids unnecessary writes
    if user.push_token == token:
        return {"ok": True, "updated": False}

    user.push_token = token
    user.updated_at = datetime.now(UTC)
    await user.save()

    logger.info("push_token_registered: %s", user_id)
    return {"ok": True, "updated": True}


@router.delete("/me/push-token", summary="Deregister push token", status_code=204)
async def deregister_push_token(user_id: str = Depends(get_current_user)) -> None:
    """
    Called on sign-out so the server stops sending notifications
    to this device.
    """
    user = await UserDocument.find_one({"clerk_id": user_id})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.push_token = None
    user.updated_at = datetime.now(UTC)
    await user.save()
    logger.info("push_token_deregistered: %s", user_id)
