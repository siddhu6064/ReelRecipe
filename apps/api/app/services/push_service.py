"""
app/services/push_service.py

Sends push notifications via the Expo Push API.
Called by the ARQ worker when a recipe extraction job completes.

Expo Push API docs: https://docs.expo.dev/push-notifications/sending-notifications/

Rate limits: 600 notifications/second per project.
Tokens that return DeviceNotRegistered are cleared from the user record.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"


async def send_recipe_ready(
    push_token: str,
    recipe_title: str,
    recipe_id: str,
) -> bool:
    """
    Send a 'Your recipe is ready!' push notification to a device.

    Returns True if the notification was accepted by Expo, False otherwise.
    Does NOT raise — push failures are non-critical and must never crash the worker.
    """
    if not push_token:
        return False

    payload = {
        "to": push_token,
        "title": "Recipe ready! 🍳",
        "body": f'"{recipe_title}" has been extracted and saved to your cookbook.',
        "data": {
            "type": "recipe_ready",
            "recipeId": recipe_id,
        },
        "sound": "default",
        "badge": 1,
        "channelId": "recipes",   # Android notification channel
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                _EXPO_PUSH_URL,
                json=payload,
                headers={"Accept": "application/json", "Content-Type": "application/json"},
            )
            resp.raise_for_status()
            result = resp.json()

            # Check for ticket errors
            data = result.get("data") or {}
            if isinstance(data, list):
                data = data[0] if data else {}

            if data.get("status") == "error":
                error_details = data.get("details", {})
                error_type = error_details.get("error", "")
                logger.warning(
                    "expo_push_ticket_error",
                    push_token=push_token[:20] + "...",
                    error=error_type,
                )
                return False

            logger.info(
                "push_notification_sent",
                recipe_id=recipe_id,
                token_prefix=push_token[:20],
            )
            return True

    except Exception as exc:
        # Push failures must never crash the worker
        logger.warning("push_notification_failed: recipe=%s error=%s", recipe_id, str(exc))
        return False


async def clear_invalid_token(user_id: str) -> None:
    """
    Called when Expo returns DeviceNotRegistered — clears the stale token
    so we don't keep trying to send to an uninstalled app.
    """
    from datetime import UTC, datetime
    from app.models.documents import UserDocument

    try:
        user = await UserDocument.find_one({"clerk_id": user_id})
        if user and user.push_token:
            user.push_token = None
            user.updated_at = datetime.now(UTC)
            await user.save()
            logger.info("stale_push_token_cleared", user_id=user_id)
    except Exception as exc:
        logger.warning("clear_token_failed", user_id=user_id, error=str(exc))
