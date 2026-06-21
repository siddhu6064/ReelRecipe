"""
app/models/meal_plan.py

MealPlanDocument — one weekly meal plan per user.
Each day has up to 3 slots (breakfast, lunch, dinner), each pointing
at a RecipeDocument by ID.  Shopping list is derived on-the-fly from
the union of missing pantry ingredients across all planned recipes.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from enum import StrEnum as Enum
from typing import Annotated, ClassVar

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel


class MealSlot(Enum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


class PlannedMeal(BaseModel):
    """A single recipe scheduled in a meal plan slot."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    recipe_id: str                        # RecipeDocument._id as string
    recipe_title: str                     # denormalised for quick render
    recipe_thumbnail: str | None = None   # denormalised
    slot: MealSlot = MealSlot.DINNER
    servings_override: int | None = None  # override recipe default servings
    notes: str | None = None


class MealPlanDay(BaseModel):
    """One day in the meal plan."""

    day_index: int                        # 0 = Mon … 6 = Sun
    date_iso: str | None = None           # ISO date string e.g. "2025-03-10"
    meals: list[PlannedMeal] = Field(default_factory=list)


class MealPlanDocument(Document):
    """
    Weekly meal plan for one user.
    A user can have multiple plans (past + current); the active plan
    has is_active=True.  Only one plan per user should be active at once
    — enforced in the service layer.
    """

    user_id: Annotated[str, Indexed()]
    title: str = "Weekly Plan"
    week_start_date: str | None = None    # ISO date of Monday for this week
    days: list[MealPlanDay] = Field(default_factory=lambda: [MealPlanDay(day_index=i) for i in range(7)])
    is_active: bool = True

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "meal_plans"
        indexes: ClassVar[list] = [
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_meal_plans_user_created",
            ),
            IndexModel(
                [("user_id", ASCENDING), ("is_active", ASCENDING)],
                name="idx_meal_plans_user_active",
            ),
        ]
