"""
app/routers/schemas.py

Pydantic request and response schemas for all ReelRecipes API endpoints.
Kept separate from documents.py so routers can evolve independently
of the DB layer.
"""

from __future__ import annotations

from pydantic import AnyHttpUrl, BaseModel, Field

from app.models.documents import Difficulty, IngredientCategory


# ── Import ─────────────────────────────────────────────────────────────────


class ImportRequest(BaseModel):
    url: AnyHttpUrl


# ── Recipe ─────────────────────────────────────────────────────────────────


class IngredientIn(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    preparation: str | None = None
    optional: bool = False


class StepIn(BaseModel):
    order: int
    text: str
    timer_seconds: int | None = None


class RecipeUpdateRequest(BaseModel):
    """All fields optional — PATCH-style update via PUT."""
    title: str | None = None
    description: str | None = None
    cuisine: str | None = None
    difficulty: Difficulty | None = None
    servings: int | None = None
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    ingredients: list[IngredientIn] | None = None
    steps: list[StepIn] | None = None
    tags: list[str] | None = None
    notes: str | None = None


class RecipeFilterParams(BaseModel):
    cuisine: str | None = None
    difficulty: Difficulty | None = None
    tags: list[str] | None = None
    search: str | None = None           # full-text search on title
    limit: int = Field(default=20, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


# ── Pantry ─────────────────────────────────────────────────────────────────


class PantryItemIn(BaseModel):
    name: str
    quantity: float | None = None
    unit: str | None = None
    category: IngredientCategory = IngredientCategory.OTHER
    expiry_date: str | None = None   # ISO-8601 date string, e.g. "2025-12-31"


class PantryItemUpdateRequest(BaseModel):
    quantity: float | None = None
    unit: str | None = None
    category: IngredientCategory | None = None
    expiry_date: str | None = None   # ISO-8601 date string; pass null to clear


# ── AI ─────────────────────────────────────────────────────────────────────


class AISuggestRequest(BaseModel):
    dietary_prefs: list[str] = Field(default_factory=list)
    cuisine_prefs: list[str] = Field(default_factory=list)
    max_recipes: int = Field(default=5, ge=1, le=10)


class AIChatMessage(BaseModel):
    message: str
    history: list[dict] = Field(default_factory=list)


class SubstituteRequest(BaseModel):
    recipe_id: str
    ingredient_name: str


# ── Users ──────────────────────────────────────────────────────────────────


class UserPrefsUpdateRequest(BaseModel):
    dietary_prefs: list[str] | None = None
    cuisine_prefs: list[str] | None = None
    unit_system: str | None = None      # "metric" | "imperial"
