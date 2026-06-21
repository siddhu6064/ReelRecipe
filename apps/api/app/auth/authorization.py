"""
app/auth/authorization.py

Authorization helpers — enforces that users can only access their own data.

Rules:
  - Authenticated users: can only read/edit trips where trip.user_id == clerk_id
  - Guest trips (user_id = None): accessible by anyone (by job_id or trip_id)
    until the user claims them after sign-up
  - Shared trips: readable by anyone with the share_token (no auth required)
  - Cross-user access always returns 403 — never 404 (avoids enumeration)
"""

from __future__ import annotations

from app.middleware.error_handler import ForbiddenError, NotFoundError
from app.models.documents import TripDocument


def assert_trip_ownership(trip: TripDocument, clerk_id: str | None) -> None:
    """
    Raise ForbiddenError if clerk_id doesn't own the trip.

    Guest trips (trip.user_id = None) are accessible without auth.
    Owned trips require the matching clerk_id.
    """
    if trip.user_id is None:
        # Guest trip — anyone can access
        return

    if clerk_id is None:
        raise ForbiddenError("Authentication required to access this trip")

    if trip.user_id != clerk_id:
        raise ForbiddenError("You do not have permission to access this trip")


def assert_can_modify(trip: TripDocument, clerk_id: str | None) -> None:
    """
    Raise ForbiddenError if the user can't modify this trip.
    Modification requires ownership (guest trips can be modified anonymously
    until claimed, then only by the owner).
    """
    assert_trip_ownership(trip, clerk_id)


async def claim_guest_trip(trip_id: str, clerk_id: str) -> TripDocument:
    """
    Link a guest trip to an authenticated user after sign-up.
    Called when a user signs in and has a pending guest trip.
    Only succeeds if the trip is unclaimed (user_id = None).
    """
    from datetime import UTC, datetime

    trip = await TripDocument.get(trip_id)
    if not trip:
        raise NotFoundError("Trip", trip_id)
    if trip.user_id is not None:
        raise ForbiddenError("This trip is already claimed by another account")

    trip.user_id = clerk_id
    trip.updated_at = datetime.now(UTC)
    await trip.save()
    return trip
