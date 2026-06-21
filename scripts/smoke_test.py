"""
scripts/smoke_test.py

Post-deployment smoke tests for ReelRecipes production API.
Run with: pytest scripts/smoke_test.py -v

Required env vars:
  API_URL            — e.g. https://reelrecipes-api.railway.app
  SMOKE_TEST_TOKEN   — valid Clerk JWT for a test account (optional)

Tests check:
  1. Health endpoint responds 200
  2. /version returns current version
  3. Auth-protected routes return 401 without token
  4. Auth-protected routes return 200 with valid token
  5. Job import endpoint accepts a real YouTube URL
  6. Job polling returns expected shape
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

API_URL = os.getenv("API_URL", "http://localhost:8000").rstrip("/")
TOKEN = os.getenv("SMOKE_TEST_TOKEN", "")
YOUTUBE_TEST_URL = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"

headers_authed = {"Authorization": f"Bearer {TOKEN}"} if TOKEN else {}


# ── Connectivity ─────────────────────────────────────────────────────────────


def test_health_endpoint():
    """API is alive and returns ok."""
    r = httpx.get(f"{API_URL}/health", timeout=15)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("ok") is True, f"Unexpected health body: {body}"


def test_version_endpoint():
    """Version endpoint returns a version string."""
    r = httpx.get(f"{API_URL}/version", timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert "version" in body, f"No version in response: {body}"
    print(f"  → Running version: {body['version']}")


# ── Authentication ────────────────────────────────────────────────────────────


def test_protected_route_without_token_returns_401():
    """Recipes endpoint rejects unauthenticated request."""
    r = httpx.get(f"{API_URL}/api/recipes", timeout=10)
    assert r.status_code == 401, (
        f"Expected 401 without token, got {r.status_code}"
    )


def test_protected_route_with_invalid_token_returns_401():
    """Recipes endpoint rejects a forged JWT."""
    r = httpx.get(
        f"{API_URL}/api/recipes",
        headers={"Authorization": "Bearer this.is.fake"},
        timeout=10,
    )
    assert r.status_code == 401, (
        f"Expected 401 with invalid token, got {r.status_code}"
    )


@pytest.mark.skipif(not TOKEN, reason="SMOKE_TEST_TOKEN not set")
def test_authenticated_recipe_list():
    """Authenticated user can list their recipes."""
    r = httpx.get(f"{API_URL}/api/recipes", headers=headers_authed, timeout=10)
    assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert "recipes" in body["data"]
    assert "total" in body["data"]
    print(f"  → Recipe count: {body['data']['total']}")


@pytest.mark.skipif(not TOKEN, reason="SMOKE_TEST_TOKEN not set")
def test_authenticated_pantry():
    """Authenticated user can access their pantry."""
    r = httpx.get(f"{API_URL}/api/pantry", headers=headers_authed, timeout=10)
    assert r.status_code == 200
    body = r.json()
    assert body.get("ok") is True
    assert "items" in body["data"]


# ── Video import ───────────────────────────────────────────────────────────────


@pytest.mark.skipif(not TOKEN, reason="SMOKE_TEST_TOKEN not set")
def test_import_video_creates_job():
    """Submitting a valid YouTube URL creates a job and returns job_id."""
    r = httpx.post(
        f"{API_URL}/api/jobs/import",
        json={"url": YOUTUBE_TEST_URL},
        headers=headers_authed,
        timeout=15,
    )
    assert r.status_code in (200, 202), (
        f"Import returned {r.status_code}: {r.text}"
    )
    body = r.json()
    assert body.get("ok") is True
    assert "jobId" in body["data"], f"No jobId in response: {body}"
    job_id = body["data"]["jobId"]
    print(f"  → Created job: {job_id}")
    return job_id


@pytest.mark.skipif(not TOKEN, reason="SMOKE_TEST_TOKEN not set")
def test_job_polling_returns_correct_shape():
    """Job status endpoint returns all required fields."""
    # First create a job
    create_resp = httpx.post(
        f"{API_URL}/api/jobs/import",
        json={"url": YOUTUBE_TEST_URL},
        headers=headers_authed,
        timeout=15,
    )
    if create_resp.status_code not in (200, 202):
        pytest.skip("Could not create test job")

    job_id = create_resp.json()["data"]["jobId"]

    # Poll it
    r = httpx.get(f"{API_URL}/api/jobs/{job_id}", headers=headers_authed, timeout=10)
    assert r.status_code == 200
    data = r.json()["data"]

    required = {"jobId", "status", "progress", "currentStep", "progressMessage",
                "error", "errorCode", "resultId", "completedAt"}
    missing = required - set(data.keys())
    assert not missing, f"Job payload missing fields: {missing}"
    assert data["status"] in ("queued", "processing", "completed", "failed")
    assert 0 <= data["progress"] <= 100


# ── AI endpoints ───────────────────────────────────────────────────────────────


@pytest.mark.skipif(not TOKEN, reason="SMOKE_TEST_TOKEN not set")
def test_ai_suggest_endpoint_accepts_request():
    """AI suggest endpoint accepts a well-formed request and returns 200."""
    r = httpx.post(
        f"{API_URL}/api/ai/suggest",
        json={"dietary_prefs": [], "cuisine_prefs": [], "max_recipes": 3},
        headers=headers_authed,
        timeout=60,   # AI can take a moment
    )
    assert r.status_code == 200, f"AI suggest returned {r.status_code}: {r.text}"
    body = r.json()
    assert body.get("ok") is True
    assert isinstance(body["data"], list)


# ── Response time ─────────────────────────────────────────────────────────────


def test_health_response_time():
    """Health check responds in under 2 seconds."""
    start = time.time()
    r = httpx.get(f"{API_URL}/health", timeout=5)
    elapsed = time.time() - start
    assert r.status_code == 200
    assert elapsed < 2.0, f"Health check took {elapsed:.2f}s (> 2s)"
    print(f"  → Health check: {elapsed * 1000:.0f}ms")
