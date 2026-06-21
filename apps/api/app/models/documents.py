"""
app/models/documents.py

Beanie ODM document models for all ReelRecipes MongoDB collections.

Collections:
  - users     (clerk_id unique index)
  - recipes   (compound: user_id + created_at desc; tags, cuisine indexes)
  - pantry    (one per user, upsert pattern)
  - jobs      (url + status indexes; TTL on completed_at)
"""

from __future__ import annotations

import uuid
import secrets
from datetime import UTC, datetime
from enum import StrEnum as Enum
from typing import Annotated, ClassVar

from beanie import Document, Indexed
from pydantic import BaseModel, Field
from pymongo import ASCENDING, DESCENDING, IndexModel


# ── Enums ──────────────────────────────────────────────────────────────────


class Platform(Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TIKTOK = "tiktok"
    FACEBOOK = "facebook"
    TWITTER = "twitter"
    UNKNOWN = "unknown"


class JobStatus(Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class JobStep(Enum):
    FETCHING_VIDEO = "fetching_video"
    TRANSCRIBING = "transcribing"
    EXTRACTING_RECIPE = "extracting_recipe"
    FETCHING_NUTRITION = "fetching_nutrition"
    FINALIZING = "finalizing"


class JobErrorCode(Enum):
    UNSUPPORTED_PLATFORM = "UNSUPPORTED_PLATFORM"
    VIDEO_UNAVAILABLE = "VIDEO_UNAVAILABLE"
    PRIVATE_VIDEO = "PRIVATE_VIDEO"
    TRANSCRIPT_FAILED = "TRANSCRIPT_FAILED"
    NO_RECIPE_FOUND = "NO_RECIPE_FOUND"
    EXTRACTION_FAILED = "EXTRACTION_FAILED"
    RATE_LIMITED = "RATE_LIMITED"
    UNKNOWN_ERROR = "UNKNOWN_ERROR"


class Difficulty(Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class IngredientCategory(Enum):
    PRODUCE = "produce"
    MEAT = "meat"
    SEAFOOD = "seafood"
    DAIRY = "dairy"
    GRAINS = "grains"
    PANTRY = "pantry"
    SPICES = "spices"
    FROZEN = "frozen"
    BEVERAGES = "beverages"
    OTHER = "other"


# ── Embedded: Recipe sub-models ────────────────────────────────────────────


class RecipeIngredient(BaseModel):
    """A single ingredient in a recipe with parsed quantity and unit."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str
    quantity: float | None = None
    unit: str | None = None          # "tbsp", "g", "cup", "whole", etc.
    preparation: str | None = None   # "diced", "minced", "to taste"
    optional: bool = False


class RecipeStep(BaseModel):
    """One step in the cooking process."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order: int
    text: str
    timer_seconds: int | None = None  # non-None when step has a timed action


class NutritionInfo(BaseModel):
    """Per-serving macro breakdown from Nutritionix."""

    calories: float | None = None
    protein_g: float | None = None
    carbs_g: float | None = None
    fat_g: float | None = None
    fiber_g: float | None = None
    sugar_g: float | None = None
    sodium_mg: float | None = None
    fetched_at: datetime | None = None


# ── Embedded: Pantry sub-model ─────────────────────────────────────────────



class EditSnapshot(BaseModel):
    """
    A full snapshot of a RecipeDocument's mutable fields taken before every edit.
    Enables undo and a full edit history. Capped at 10 per recipe.
    """
    snapshot_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    label: str                         # human-readable description of the edit
    title: str
    servings: int
    ingredients: list["RecipeIngredient"]
    steps: list["RecipeStep"]
    personal_notes: str | None = None
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class PantryItem(BaseModel):
    """A single ingredient in the user's pantry."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str                                      # canonical name used for fuzzy match
    quantity: float | None = None
    unit: str | None = None
    category: IngredientCategory = IngredientCategory.OTHER
    estimated_cost_per_unit: float | None = None  # user-set price per unit for cost estimation
    expiry_date: datetime | None = None           # optional best-before / expiry date
    added_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


# ── Document: User ─────────────────────────────────────────────────────────


class UserDocument(Document):
    """
    Mirrors a Clerk user into MongoDB for recipe ownership queries.
    Synced via Clerk webhooks (user.created, user.updated).
    """

    clerk_id: Annotated[str, Indexed(unique=True)]
    email: str
    name: str
    avatar_url: str | None = None
    push_token: str | None = None  # Expo push token for "recipe ready" notifications

    # User preferences
    dietary_prefs: list[str] = Field(default_factory=list)   # ["vegan", "gluten-free"]
    cuisine_prefs: list[str] = Field(default_factory=list)   # ["italian", "japanese"]
    unit_system: str = "metric"                               # "metric" | "imperial"

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "users"
        indexes: ClassVar[list] = [
            IndexModel([("clerk_id", ASCENDING)], unique=True, name="uq_users_clerk_id"),
            IndexModel([("email", ASCENDING)], name="idx_users_email"),
        ]


# ── Document: Recipe ───────────────────────────────────────────────────────


class CollaboratorRole(Enum):
    """Access level for a shared recipe collaborator."""
    VIEWER = "viewer"
    EDITOR = "editor"


class CollaboratorEntry(BaseModel):
    """A single collaborator on a shared recipe."""
    user_id: str                      # Clerk ID
    email: str | None = None          # denormalised for display
    role: CollaboratorRole = CollaboratorRole.VIEWER
    invited_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    accepted: bool = False
    invite_token: str = Field(default_factory=lambda: __import__('secrets').token_urlsafe(24))



class RecipeDocument(Document):
    """
    A structured recipe extracted from a cooking video.
    Owned by the importing user; extracted fields are fully editable.
    """

    user_id: str                          # clerk_id of the importing user
    job_id: str | None = None            # provenance — which import job created this

    # ── Video source ──────────────────────────────────────────
    source_url: str
    platform: Platform = Platform.UNKNOWN
    thumbnail_url: str | None = None
    video_title: str | None = None        # raw title from platform API

    # ── Recipe metadata ───────────────────────────────────────
    title: str
    description: str | None = None
    cuisine: str | None = None            # "Italian", "Japanese", etc.
    difficulty: Difficulty = Difficulty.MEDIUM
    servings: int = 2
    prep_time_minutes: int | None = None
    cook_time_minutes: int | None = None
    total_time_minutes: int | None = None

    # ── Core content ─────────────────────────────────────────
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[RecipeStep] = Field(default_factory=list)

    # ── Auto-detected tags ────────────────────────────────────
    # e.g. ["vegan", "gluten-free", "dairy-free", "quick"]
    tags: list[str] = Field(default_factory=list)

    # ── Nutrition (from Nutritionix) ──────────────────────────
    nutrition: NutritionInfo | None = None

    # ── AI provenance ─────────────────────────────────────────
    extraction_model: str | None = None
    extraction_tokens: int = 0
    extracted_at: datetime | None = None

    # ── User edits ────────────────────────────────────────────
    is_edited: bool = False                 # True once user has manually edited any field
    is_favourite: bool = False              # Starred by the user
    personal_notes: str | None = None      # Free-text cooking diary / personal notes

    # ── Community / sharing ───────────────────────────────────
    is_public: bool = False                 # Visible in the community explore feed
    collaborators: list[CollaboratorEntry] = Field(default_factory=list)
    cook_log: list[datetime] = Field(default_factory=list)   # UTC timestamps when Cook Mode completed
    view_count: int = 0                     # Incremented on each public view
    share_count: int = 0                    # Incremented on duplicate actions
    share_token: str | None = None          # Stable token for public link sharing

    # ── Edit history (undo stack) ─────────────────────────────
    edit_snapshots: list[EditSnapshot] = Field(default_factory=list)

    # ── Original AI extraction snapshot ──────────────────────
    # Written ONCE at import — never overwritten.
    # Allows "Reset to original" after manual edits.
    original_title: str | None = None
    original_servings: int | None = None
    original_ingredients: list[RecipeIngredient] | None = None
    original_steps: list[RecipeStep] | None = None

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "recipes"
        indexes: ClassVar[list] = [
            # Primary list: all recipes for a user, newest first
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_recipes_user_created",
            ),
            # Filter by cuisine
            IndexModel(
                [("user_id", ASCENDING), ("cuisine", ASCENDING)],
                name="idx_recipes_user_cuisine",
            ),
            # Filter by tags (multikey)
            IndexModel(
                [("user_id", ASCENDING), ("tags", ASCENDING)],
                name="idx_recipes_user_tags",
            ),
            # Filter by difficulty
            IndexModel(
                [("user_id", ASCENDING), ("difficulty", ASCENDING)],
                name="idx_recipes_user_difficulty",
            ),
            # Job provenance lookup
            IndexModel(
                [("job_id", ASCENDING)],
                sparse=True,
                name="idx_recipes_job_id",
            ),
        ]


# ── Document: Pantry ───────────────────────────────────────────────────────


class PantryDocument(Document):
    """
    One pantry per user. Ingredients are embedded as PantryItem[].
    Created on first item add; never deleted — cleared via PUT with items=[].
    """

    user_id: Annotated[str, Indexed(unique=True)]   # clerk_id
    items: list[PantryItem] = Field(default_factory=list)

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    class Settings:
        name: ClassVar[str] = "pantry"
        indexes: ClassVar[list] = [
            IndexModel([("user_id", ASCENDING)], unique=True, name="uq_pantry_user_id"),
        ]


# ── Document: Job ──────────────────────────────────────────────────────────


class JobDocument(Document):
    """
    Represents a single video import/extraction task.
    Workers update status, progress, and step fields as the pipeline advances.
    Client polls GET /api/jobs/:id every 3s or connects to WS /ws/jobs/:id.
    """

    user_id: str | None = None
    url: str
    platform: Platform = Platform.UNKNOWN

    status: JobStatus = JobStatus.QUEUED
    progress: int = Field(default=0, ge=0, le=100)
    current_step: JobStep | None = None
    progress_message: str | None = None

    # Pipeline artifacts
    transcript: str | None = None

    # Error state
    error: str | None = None
    error_code: JobErrorCode | None = None

    # Result — set when status == COMPLETED
    result_id: str | None = None          # RecipeDocument.id as string

    # Extraction provenance
    extraction_model: str | None = None
    extraction_tokens: int = 0
    extracted_at: datetime | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    started_at: datetime | None = None
    completed_at: datetime | None = None

    class Settings:
        name: ClassVar[str] = "jobs"
        indexes: ClassVar[list] = [
            # Deduplication: don't re-process same URL if already in-flight
            IndexModel(
                [("url", ASCENDING), ("status", ASCENDING)],
                name="idx_jobs_url_status",
            ),
            # User's job history
            IndexModel(
                [("user_id", ASCENDING), ("created_at", DESCENDING)],
                name="idx_jobs_user_created",
            ),
            # Worker picks up queued jobs by age
            IndexModel(
                [("status", ASCENDING), ("created_at", ASCENDING)],
                name="idx_jobs_status_created",
            ),
            # TTL: auto-delete completed/failed jobs after 30 days (2_592_000s)
            IndexModel(
                [("completed_at", ASCENDING)],
                expireAfterSeconds=2_592_000,
                sparse=True,
                name="idx_jobs_ttl",
            ),
        ]


# ── Convenience list for Beanie.init_beanie() ──────────────────────────────

from app.models.meal_plan import MealPlanDocument  # noqa: E402
from app.models.collection import RecipeCollection  # noqa: E402

ALL_DOCUMENTS: list[type[Document]] = [
    UserDocument,
    RecipeDocument,
    PantryDocument,
    JobDocument,
    MealPlanDocument,
    RecipeCollection,
]
