"""
app/config/database.py

MongoDB connection lifecycle managed here.
Motor provides the async driver; Beanie wraps it with ODM.

Usage:
  - Called once at FastAPI startup via lifespan context manager
  - get_db() provides the raw Motor database for edge cases
  - All normal data access goes through Beanie document methods
"""

from __future__ import annotations

import motor.motor_asyncio
from beanie import init_beanie

from app.config.logging import get_logger
from app.config.settings import get_settings
from app.models.documents import ALL_DOCUMENTS

logger = get_logger(__name__)

_client: motor.motor_asyncio.AsyncIOMotorClient | None = None  # type: ignore[type-arg]


async def connect_db() -> None:
    """
    Open the Motor connection and initialise Beanie ODM.
    Creates all collection indexes declared on document Settings classes.
    Called from the FastAPI lifespan on startup.
    """
    global _client
    settings = get_settings()

    logger.info(
        "connecting_to_mongodb", url=_redact_url(settings.mongodb_url), db=settings.mongodb_db
    )

    _client = motor.motor_asyncio.AsyncIOMotorClient(
        settings.mongodb_url,
        serverSelectionTimeoutMS=5_000,
        connectTimeoutMS=5_000,
        socketTimeoutMS=10_000,
    )

    await init_beanie(
        database=_client[settings.mongodb_db],
        document_models=ALL_DOCUMENTS,
    )

    logger.info("mongodb_connected", db=settings.mongodb_db)


async def disconnect_db() -> None:
    """Close the Motor connection. Called from FastAPI lifespan on shutdown."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("mongodb_disconnected")


def get_db() -> motor.motor_asyncio.AsyncIOMotorDatabase:  # type: ignore[type-arg]
    """
    Returns the raw Motor database object.
    Prefer Beanie document methods for all normal operations.
    This exists for aggregation pipelines and raw queries.
    """
    if _client is None:
        raise RuntimeError("Database not connected. Was connect_db() called?")
    return _client[get_settings().mongodb_db]


def _redact_url(url: str) -> str:
    """Redact passwords from MongoDB URLs before logging."""
    if "@" in url:
        scheme, rest = url.split("://", 1)
        credentials, host = rest.split("@", 1)
        user = credentials.split(":")[0]
        return f"{scheme}://{user}:***@{host}"
    return url
