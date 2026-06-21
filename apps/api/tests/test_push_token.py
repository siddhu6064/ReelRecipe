"""
tests/test_push_token.py

Tests for the push token registration/deregistration endpoints
and the push_service notification sender.

All HTTP calls and Expo API calls are mocked — no real network traffic.
"""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import create_app
from app.models.documents import ALL_DOCUMENTS, UserDocument

TEST_USER = "user_test_clerk_001"
VALID_TOKEN = "ExponentPushToken[xxxxxxxxxxxxxxxxxxxxxx]"
VALID_TOKEN_EA = "ea:APA91bHPRgkFLJu13p4kaEg"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    from app.auth.clerk import optional_auth, require_auth

    app = create_app()

    async def _fake_auth() -> str:
        return TEST_USER

    app.dependency_overrides[require_auth] = _fake_auth
    app.dependency_overrides[optional_auth] = _fake_auth

    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://testserver",
        ) as ac:
            yield ac

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def existing_user(db) -> UserDocument:
    user = UserDocument(
        clerk_id=TEST_USER,
        email="test@example.com",
        name="Test User",
    )
    await user.insert()
    return user


# ── PUT /api/users/me/push-token ───────────────────────────────────────────


class TestRegisterPushToken:

    @pytest.mark.asyncio
    async def test_register_expo_token(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": VALID_TOKEN},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["updated"] is True

        # Verify stored in DB
        user = await UserDocument.find_one({"clerk_id": TEST_USER})
        assert user.push_token == VALID_TOKEN

    @pytest.mark.asyncio
    async def test_register_ea_format_token(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": VALID_TOKEN_EA},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is True

    @pytest.mark.asyncio
    async def test_idempotent_same_token(self, client, existing_user):
        """Registering same token twice → updated=False on second call."""
        # First registration
        await client.put("/api/users/me/push-token", json={"push_token": VALID_TOKEN})

        # Second registration with same token
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": VALID_TOKEN},
        )
        assert resp.status_code == 200
        assert resp.json()["updated"] is False

    @pytest.mark.asyncio
    async def test_invalid_token_format_rejected(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": "not-a-valid-token"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_empty_token_rejected(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": ""},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_user_not_found_returns_404(self, client, db):
        # No UserDocument exists for TEST_USER
        resp = await client.put(
            "/api/users/me/push-token",
            json={"push_token": VALID_TOKEN},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_to_new_token(self, client, existing_user):
        """Changing devices — token updates to new value."""
        old_token = "ExponentPushToken[oldoldoldoldoldoldold]"
        new_token = "ExponentPushToken[newnewnewnewnewnewnew]"

        await client.put("/api/users/me/push-token", json={"push_token": old_token})
        await client.put("/api/users/me/push-token", json={"push_token": new_token})

        user = await UserDocument.find_one({"clerk_id": TEST_USER})
        assert user.push_token == new_token


# ── DELETE /api/users/me/push-token ───────────────────────────────────────


class TestDeregisterPushToken:

    @pytest.mark.asyncio
    async def test_deregister_clears_token(self, client, existing_user):
        # Register first
        await client.put("/api/users/me/push-token", json={"push_token": VALID_TOKEN})

        # Deregister
        resp = await client.delete("/api/users/me/push-token")
        assert resp.status_code == 204

        # Verify cleared
        user = await UserDocument.find_one({"clerk_id": TEST_USER})
        assert user.push_token is None

    @pytest.mark.asyncio
    async def test_deregister_when_no_token_is_noop(self, client, existing_user):
        """Deregistering when no token is stored should succeed silently."""
        resp = await client.delete("/api/users/me/push-token")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deregister_user_not_found_returns_404(self, client, db):
        resp = await client.delete("/api/users/me/push-token")
        assert resp.status_code == 404


# ── push_service.py ────────────────────────────────────────────────────────


class TestPushService:

    @pytest.mark.asyncio
    async def test_send_recipe_ready_success(self):
        from app.services.push_service import send_recipe_ready

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "data": [{"status": "ok", "id": "abc123"}]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client):
            result = await send_recipe_ready(
                push_token=VALID_TOKEN,
                recipe_title="Spaghetti Carbonara",
                recipe_id="507f1f77bcf86cd799439001",
            )

        assert result is True
        mock_client.post.assert_awaited_once()

        # Verify payload shape
        call_kwargs = mock_client.post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
        assert payload["to"] == VALID_TOKEN
        assert "Spaghetti Carbonara" in payload["body"]
        assert payload["data"]["recipeId"] == "507f1f77bcf86cd799439001"
        assert payload["data"]["type"] == "recipe_ready"

    @pytest.mark.asyncio
    async def test_send_recipe_ready_expo_ticket_error(self):
        """Expo returns error ticket — should return False, not raise."""
        from app.services.push_service import send_recipe_ready

        mock_resp = MagicMock()
        mock_resp.raise_for_status = MagicMock()
        mock_resp.json = MagicMock(return_value={
            "data": [{"status": "error", "details": {"error": "DeviceNotRegistered"}}]
        })

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_resp)

        with patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client):
            result = await send_recipe_ready(
                push_token=VALID_TOKEN,
                recipe_title="Pasta",
                recipe_id="507f1f77bcf86cd799439002",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_recipe_ready_network_error_returns_false(self):
        """Network failure must never raise — returns False silently."""
        from app.services.push_service import send_recipe_ready

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(side_effect=Exception("Connection refused"))

        with patch("app.services.push_service.httpx.AsyncClient", return_value=mock_client):
            result = await send_recipe_ready(
                push_token=VALID_TOKEN,
                recipe_title="Pasta",
                recipe_id="507f1f77bcf86cd799439003",
            )

        assert result is False

    @pytest.mark.asyncio
    async def test_send_recipe_ready_empty_token_returns_false(self):
        """Empty push token short-circuits without hitting the API."""
        from app.services.push_service import send_recipe_ready

        result = await send_recipe_ready(
            push_token="",
            recipe_title="Pasta",
            recipe_id="507f1f77bcf86cd799439004",
        )
        assert result is False

    @pytest.mark.asyncio
    async def test_clear_invalid_token(self, db):
        """clear_invalid_token() removes the token from UserDocument."""
        from app.services.push_service import clear_invalid_token

        user = UserDocument(
            clerk_id=TEST_USER,
            email="test@example.com",
            name="Test",
            push_token=VALID_TOKEN,
        )
        await user.insert()

        await clear_invalid_token(TEST_USER)

        refreshed = await UserDocument.find_one({"clerk_id": TEST_USER})
        assert refreshed.push_token is None
