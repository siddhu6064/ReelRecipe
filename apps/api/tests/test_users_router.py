"""
tests/test_users_router.py

Tests for users.py and the Clerk webhook endpoint.
Covers: webhook upsert, profile GET, prefs PUT, error paths.
"""

from __future__ import annotations

from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import create_app
from app.models.documents import ALL_DOCUMENTS, UserDocument

TEST_USER = "user_test_clerk_001"


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    db = client["reelrecipes_test"]
    await init_beanie(database=db, document_models=ALL_DOCUMENTS)
    yield db
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
        dietary_prefs=["vegetarian"],
        cuisine_prefs=["italian"],
        unit_system="metric",
    )
    await user.insert()
    return user


# ── Clerk webhook ──────────────────────────────────────────────────────────


class TestClerkWebhook:

    @pytest.mark.asyncio
    async def test_user_created_inserts_document(self, client, db):
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_new_001",
                "first_name": "Alice",
                "last_name": "Smith",
                "email_addresses": [{"email_address": "alice@example.com"}],
                "image_url": "https://example.com/avatar.jpg",
            },
        }
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

        user = await UserDocument.find_one({"clerk_id": "clerk_new_001"})
        assert user is not None
        assert user.email == "alice@example.com"
        assert user.name == "Alice Smith"
        assert user.avatar_url == "https://example.com/avatar.jpg"

    @pytest.mark.asyncio
    async def test_user_updated_updates_existing(self, client, existing_user):
        payload = {
            "type": "user.updated",
            "data": {
                "id": TEST_USER,
                "first_name": "Updated",
                "last_name": "Name",
                "email_addresses": [{"email_address": "updated@example.com"}],
                "image_url": None,
            },
        }
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 200

        user = await UserDocument.find_one({"clerk_id": TEST_USER})
        assert user.name == "Updated Name"
        assert user.email == "updated@example.com"

    @pytest.mark.asyncio
    async def test_unknown_event_type_ignored(self, client, db):
        payload = {"type": "session.created", "data": {"id": "sess_001"}}
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 200
        assert resp.json() == {"ok": True, "ignored": True}

    @pytest.mark.asyncio
    async def test_missing_clerk_id_returns_400(self, client, db):
        payload = {
            "type": "user.created",
            "data": {
                "first_name": "No",
                "last_name": "ID",
                "email_addresses": [],
            },
        }
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_json_returns_400(self, client, db):
        resp = await client.post(
            "/api/clerk/webhooks",
            content=b"not json at all",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_user_created_no_email_falls_back_to_empty(self, client, db):
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_no_email",
                "first_name": "Ghost",
                "last_name": "User",
                "email_addresses": [],
                "image_url": None,
            },
        }
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 200
        user = await UserDocument.find_one({"clerk_id": "clerk_no_email"})
        assert user is not None
        assert user.email == ""

    @pytest.mark.asyncio
    async def test_user_name_falls_back_to_email_when_no_name(self, client, db):
        payload = {
            "type": "user.created",
            "data": {
                "id": "clerk_no_name",
                "first_name": None,
                "last_name": None,
                "email_addresses": [{"email_address": "noname@example.com"}],
                "image_url": None,
            },
        }
        resp = await client.post("/api/clerk/webhooks", json=payload)
        assert resp.status_code == 200
        user = await UserDocument.find_one({"clerk_id": "clerk_no_name"})
        assert user.name == "noname@example.com"


# ── GET /api/users/me ──────────────────────────────────────────────────────


class TestGetMe:

    @pytest.mark.asyncio
    async def test_get_me_returns_profile(self, client, existing_user):
        resp = await client.get("/api/users/me")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        data = body["data"]
        assert data["clerk_id"] == TEST_USER
        assert data["email"] == "test@example.com"
        assert data["name"] == "Test User"
        assert data["dietary_prefs"] == ["vegetarian"]
        assert data["unit_system"] == "metric"

    @pytest.mark.asyncio
    async def test_get_me_404_when_not_synced(self, client, db):
        # No UserDocument exists for TEST_USER
        resp = await client.get("/api/users/me")
        assert resp.status_code == 404


# ── PUT /api/users/me/prefs ────────────────────────────────────────────────


class TestUpdatePrefs:

    @pytest.mark.asyncio
    async def test_update_dietary_prefs(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/prefs",
            json={"dietary_prefs": ["vegan", "gluten-free"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["data"]["dietary_prefs"] == ["vegan", "gluten-free"]

    @pytest.mark.asyncio
    async def test_update_cuisine_prefs(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/prefs",
            json={"cuisine_prefs": ["japanese", "mexican"]},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["cuisine_prefs"] == ["japanese", "mexican"]

    @pytest.mark.asyncio
    async def test_update_unit_system_imperial(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/prefs",
            json={"unit_system": "imperial"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["unit_system"] == "imperial"

    @pytest.mark.asyncio
    async def test_update_unit_system_invalid(self, client, existing_user):
        resp = await client.put(
            "/api/users/me/prefs",
            json={"unit_system": "furlongs"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_partial_update_preserves_other_fields(self, client, existing_user):
        """Only dietary_prefs is updated — cuisine_prefs and unit_system unchanged."""
        resp = await client.put(
            "/api/users/me/prefs",
            json={"dietary_prefs": ["dairy-free"]},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dietary_prefs"] == ["dairy-free"]
        assert data["cuisine_prefs"] == ["italian"]    # unchanged
        assert data["unit_system"] == "metric"          # unchanged

    @pytest.mark.asyncio
    async def test_update_prefs_404_when_user_missing(self, client, db):
        resp = await client.put(
            "/api/users/me/prefs",
            json={"dietary_prefs": ["vegan"]},
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_empty_body_is_noop(self, client, existing_user):
        """Empty update body makes no changes."""
        resp = await client.put("/api/users/me/prefs", json={})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["dietary_prefs"] == ["vegetarian"]  # unchanged
