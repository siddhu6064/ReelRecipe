"""
tests/test_expiry.py

Tests for pantry item expiry date management:
  - Model field presence
  - POST /api/pantry/items with expiry_date
  - PUT /api/pantry/items/:id/expiry
  - GET /api/pantry/expiring?days=N
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import AsyncGenerator
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from beanie import init_beanie
from httpx import ASGITransport, AsyncClient
from mongomock_motor import AsyncMongoMockClient

from app.main import create_app
from app.models.documents import ALL_DOCUMENTS, PantryDocument, PantryItem

TEST_USER = "user_expiry_test_001"


@pytest_asyncio.fixture
async def db():
    client = AsyncMongoMockClient()
    await init_beanie(database=client["test"], document_models=ALL_DOCUMENTS)
    yield
    client.close()


@pytest_asyncio.fixture(autouse=True)
async def _beanie(db): pass


@pytest_asyncio.fixture
async def client(db) -> AsyncGenerator[AsyncClient, None]:
    from app.auth.clerk import optional_auth, require_auth
    app = create_app()
    async def _auth(): return TEST_USER
    app.dependency_overrides[require_auth] = _auth
    app.dependency_overrides[optional_auth] = _auth
    with (
        patch("app.config.database.connect_db", new_callable=AsyncMock),
        patch("app.config.database.disconnect_db", new_callable=AsyncMock),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as ac:
            yield ac
    app.dependency_overrides.clear()


# ── Model ─────────────────────────────────────────────────────────────────────

class TestPantryItemModel:

    def test_expiry_date_field_exists(self):
        item = PantryItem(name="milk")
        assert hasattr(item, "expiry_date")
        assert item.expiry_date is None

    def test_expiry_date_stored(self):
        expiry = datetime(2025, 12, 31, tzinfo=UTC)
        item = PantryItem(name="eggs", expiry_date=expiry)
        assert item.expiry_date == expiry


# ── Add with expiry ────────────────────────────────────────────────────────────

class TestAddItemWithExpiry:

    @pytest.mark.asyncio
    async def test_add_item_with_expiry_date(self, client, db):
        resp = await client.post("/api/pantry/items", json={
            "name": "milk",
            "quantity": 2,
            "unit": "L",
            "expiry_date": "2025-12-31",
        })
        assert resp.status_code == 201
        data = resp.json()["data"]
        assert data["expiry_date"] is not None
        assert "2025-12-31" in data["expiry_date"]

    @pytest.mark.asyncio
    async def test_add_item_without_expiry_date(self, client, db):
        resp = await client.post("/api/pantry/items", json={"name": "salt"})
        assert resp.status_code == 201
        assert resp.json()["data"]["expiry_date"] is None

    @pytest.mark.asyncio
    async def test_add_item_invalid_expiry_format(self, client, db):
        """Invalid date strings are silently ignored (graceful degradation)."""
        resp = await client.post("/api/pantry/items", json={
            "name": "cheese",
            "expiry_date": "not-a-date",
        })
        assert resp.status_code == 201   # still created, expiry just skipped


# ── PUT /expiry ────────────────────────────────────────────────────────────────

class TestExpiryEndpoint:

    @pytest.mark.asyncio
    async def test_set_expiry_date(self, client, db):
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[PantryItem(name="yoghurt", quantity=1)],
        )
        await pantry.insert()
        item_id = pantry.items[0].id

        resp = await client.put(
            f"/api/pantry/items/{item_id}/expiry",
            json={"expiry_date": "2025-06-30"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["expiry_date"] is not None
        assert "2025-06-30" in resp.json()["data"]["expiry_date"]

        updated = await PantryDocument.find_one({"user_id": TEST_USER})
        assert updated.items[0].expiry_date is not None

    @pytest.mark.asyncio
    async def test_clear_expiry_date(self, client, db):
        expiry = datetime(2025, 6, 30, tzinfo=UTC)
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[PantryItem(name="butter", expiry_date=expiry)],
        )
        await pantry.insert()
        item_id = pantry.items[0].id

        resp = await client.put(
            f"/api/pantry/items/{item_id}/expiry",
            json={"expiry_date": None},
        )
        assert resp.status_code == 200
        assert resp.json()["data"]["expiry_date"] is None

    @pytest.mark.asyncio
    async def test_invalid_date_returns_400(self, client, db):
        pantry = PantryDocument(user_id=TEST_USER, items=[PantryItem(name="bread")])
        await pantry.insert()
        item_id = pantry.items[0].id

        resp = await client.put(
            f"/api/pantry/items/{item_id}/expiry",
            json={"expiry_date": "32/13/2025"},
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_expiry_on_unknown_item_returns_404(self, client, db):
        resp = await client.put(
            "/api/pantry/items/nonexistent-id/expiry",
            json={"expiry_date": "2025-12-31"},
        )
        assert resp.status_code == 404


# ── GET /expiring ──────────────────────────────────────────────────────────────

class TestExpiringItems:

    @pytest.mark.asyncio
    async def test_returns_items_expiring_within_window(self, client, db):
        soon = datetime.now(UTC) + timedelta(days=3)
        later = datetime.now(UTC) + timedelta(days=30)
        past = datetime.now(UTC) - timedelta(days=1)

        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[
                PantryItem(name="milk",    expiry_date=soon),
                PantryItem(name="chicken", expiry_date=later),
                PantryItem(name="yoghurt", expiry_date=past),
                PantryItem(name="salt"),   # no expiry
            ],
        )
        await pantry.insert()

        resp = await client.get("/api/pantry/expiring?days=7")
        assert resp.status_code == 200
        data = resp.json()["data"]
        names = [i["name"] for i in data["items"]]

        assert "milk" in names           # expires in 3 days ✓
        assert "chicken" not in names    # expires in 30 days, outside window
        assert "salt" not in names       # no expiry
        assert "yoghurt" in names        # already expired — still surfaced

    @pytest.mark.asyncio
    async def test_sorted_by_soonest_expiry(self, client, db):
        d1 = datetime.now(UTC) + timedelta(days=1)
        d5 = datetime.now(UTC) + timedelta(days=5)
        d3 = datetime.now(UTC) + timedelta(days=3)

        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[
                PantryItem(name="C", expiry_date=d5),
                PantryItem(name="A", expiry_date=d1),
                PantryItem(name="B", expiry_date=d3),
            ],
        )
        await pantry.insert()

        resp = await client.get("/api/pantry/expiring?days=10")
        names = [i["name"] for i in resp.json()["data"]["items"]]
        assert names == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_empty_when_nothing_expiring(self, client, db):
        pantry = PantryDocument(
            user_id=TEST_USER,
            items=[
                PantryItem(name="rice"),
                PantryItem(name="pasta", expiry_date=datetime.now(UTC) + timedelta(days=60)),
            ],
        )
        await pantry.insert()

        resp = await client.get("/api/pantry/expiring?days=7")
        assert resp.json()["data"]["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_window_days_in_response(self, client, db):
        await PantryDocument(user_id=TEST_USER, items=[]).insert()
        resp = await client.get("/api/pantry/expiring?days=14")
        assert resp.json()["data"]["window_days"] == 14
