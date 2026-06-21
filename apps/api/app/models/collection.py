"""
app/models/collection.py

RecipeCollection — user-created folders for organising saved recipes.
Each collection stores recipe IDs as a simple list (no ordering for now).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, ClassVar

from beanie import Document, Indexed
from pydantic import Field
from pymongo import ASCENDING, IndexModel


class RecipeCollection(Document):
    """
    A named folder that groups recipes together.
    One user can have many collections (e.g. "Weeknight Dinners", "Date Night").
    """

    user_id: Annotated[str, Indexed()]
    name: str                                          # e.g. "Quick Weeknights"
    emoji: str = "📁"                                  # user-picked emoji icon
    recipe_ids: list[str] = Field(default_factory=list)  # RecipeDocument IDs

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "recipe_collections"
        indexes: ClassVar[list] = [
            IndexModel(
                [("user_id", ASCENDING), ("name", ASCENDING)],
                name="idx_collections_user_name",
                unique=True,
            ),
        ]
