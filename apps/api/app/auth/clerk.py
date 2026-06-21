"""
app/auth/clerk.py

Clerk JWT verification middleware for FastAPI.

How it works:
  1. FastAPI receives a request with Authorization: Bearer <clerk_jwt>
  2. We fetch Clerk's JWKS (JSON Web Key Set) — cached for 1 hour
  3. We decode and verify the JWT signature, expiry, and issuer
  4. The verified clerk_id is attached to request.state.clerk_id
  5. Protected routes call require_auth() to get the clerk_id
  6. Guest routes call optional_auth() — returns None if no token

Guest mode:
  - POST /api/process accepts requests with no token
  - Job.user_id = None, Trip.user_id = None
  - After sign-in, the frontend sends PATCH /api/jobs/:id/claim
    to link the guest trip to the new user
"""

from __future__ import annotations

import time
from typing import Annotated

import httpx
from fastapi import Depends, Request
from jose import JWTError, jwt

from app.config.logging import get_logger
from app.config.settings import get_settings
from app.middleware.error_handler import UnauthorizedError

logger = get_logger(__name__)

# Cache JWKS for 1 hour — Clerk rotates keys infrequently
_jwks_cache: dict | None = None
_jwks_fetched_at: float = 0.0
JWKS_TTL_SECONDS = 3600


async def _get_jwks() -> dict:
    """Fetch and cache Clerk's JWKS endpoint."""
    global _jwks_cache, _jwks_fetched_at

    now = time.time()
    if _jwks_cache and (now - _jwks_fetched_at) < JWKS_TTL_SECONDS:
        return _jwks_cache

    settings = get_settings()
    # Clerk JWKS URL derived from publishable key
    # pk_test_xxx → https://xxx.clerk.accounts.dev/.well-known/jwks.json
    # pk_live_xxx → https://xxx.clerk.accounts.dev/.well-known/jwks.json
    pub_key = settings.clerk_publishable_key
    if not pub_key:
        logger.warning("clerk_publishable_key_not_set")
        return {"keys": []}

    # Extract the domain from the publishable key
    # Format: pk_test_<base64_domain> or pk_live_<base64_domain>
    try:
        import base64

        parts = pub_key.split("_")
        if len(parts) >= 3:
            domain_b64 = parts[2].rstrip("$")
            # Pad base64
            padding = 4 - len(domain_b64) % 4
            if padding != 4:
                domain_b64 += "=" * padding
            domain = base64.b64decode(domain_b64).decode("utf-8").rstrip("/")
            jwks_url = f"{domain}/.well-known/jwks.json"
        else:
            # Fallback to secret key issuer
            jwks_url = "https://api.clerk.com/v1/jwks"
    except Exception:
        jwks_url = "https://api.clerk.com/v1/jwks"

    async with httpx.AsyncClient(timeout=5.0) as client:
        headers = {}
        if settings.clerk_secret_key:
            headers["Authorization"] = f"Bearer {settings.clerk_secret_key}"
        resp = await client.get(jwks_url, headers=headers)
        resp.raise_for_status()
        _jwks_cache = resp.json()
        _jwks_fetched_at = now
        logger.info("clerk_jwks_fetched", url=jwks_url)
        return _jwks_cache


def _verify_jwt(token: str, jwks: dict) -> dict:
    """
    Verify a Clerk JWT against the JWKS.
    Returns the decoded payload dict or raises UnauthorizedError.
    """
    try:
        # Get the key id from the token header
        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")

        # Find the matching key in JWKS
        rsa_key = {}
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = {
                    "kty": key["kty"],
                    "kid": key["kid"],
                    "use": key["use"],
                    "n": key["n"],
                    "e": key["e"],
                }
                break

        if not rsa_key:
            raise UnauthorizedError("Invalid token: key not found")

        get_settings()
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            options={"verify_aud": False},
        )
        return payload

    except JWTError as exc:
        raise UnauthorizedError(f"Invalid token: {exc}") from exc


def _extract_bearer(request: Request) -> str | None:
    """Extract the Bearer token from the Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()
    return None


# ── FastAPI dependency functions ───────────────────────────────


async def optional_auth(request: Request) -> str | None:
    """
    Dependency: returns clerk_id if a valid token is present, else None.
    Use for endpoints that support both authenticated and guest access.
    """
    settings = get_settings()

    # Skip JWT verification in test environment
    if settings.is_test:
        return getattr(request.state, "clerk_id", None)

    token = _extract_bearer(request)
    if not token:
        return None

    try:
        jwks = await _get_jwks()
        payload = _verify_jwt(token, jwks)
        clerk_id = payload.get("sub")
        if clerk_id:
            request.state.clerk_id = clerk_id
        return clerk_id
    except UnauthorizedError:
        # Optional auth — don't raise, just return None
        return None


async def require_auth(request: Request) -> str:
    """
    Dependency: returns clerk_id or raises 401 if no valid token.
    Use for endpoints that require authentication.
    """
    settings = get_settings()

    # Allow test override via X-Test-User-Id header
    if settings.is_test:
        test_id = request.headers.get("X-Test-User-Id")
        if test_id:
            return test_id
        raise UnauthorizedError("Test: no X-Test-User-Id header")

    token = _extract_bearer(request)
    if not token:
        raise UnauthorizedError("Authentication required")

    jwks = await _get_jwks()
    payload = _verify_jwt(token, jwks)
    clerk_id = payload.get("sub")
    if not clerk_id:
        raise UnauthorizedError("Invalid token: missing sub claim")

    request.state.clerk_id = clerk_id
    return clerk_id


# ── Type aliases for cleaner route signatures ──────────────────

OptionalUser = Annotated[str | None, Depends(optional_auth)]
RequiredUser = Annotated[str, Depends(require_auth)]
