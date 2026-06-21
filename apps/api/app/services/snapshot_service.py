"""
app/services/snapshot_service.py

Manages recipe edit history (undo stack).

push_snapshot() is called inside every PUT /api/recipes/:id BEFORE
writing the new state. This allows unlimited undo back through time,
capped at MAX_SNAPSHOTS per recipe to control document size.

Design:
  - Snapshots stored as embedded list on RecipeDocument (no separate collection)
  - LIFO order — most recent snapshot is last in the list
  - Cap: when list exceeds MAX_SNAPSHOTS, oldest are dropped
  - A snapshot stores the complete mutable state (title, servings,
    ingredients, steps, notes, tags) — enough to fully restore the recipe
"""

from __future__ import annotations

from app.models.documents import EditSnapshot, RecipeDocument

MAX_SNAPSHOTS = 10


async def push_snapshot(recipe: RecipeDocument, label: str) -> None:
    """
    Create a snapshot of the recipe's current state and append it to
    the edit history. Trims the oldest snapshot when the cap is exceeded.

    Call this BEFORE applying any mutation to the recipe.

    Args:
        recipe:  The RecipeDocument about to be mutated.
        label:   Short description of the incoming edit, e.g.
                 "Edited title", "Scaled to 4 servings", "Reordered steps".
    """
    snapshot = EditSnapshot(
        label=label,
        title=recipe.title,
        servings=recipe.servings,
        ingredients=list(recipe.ingredients),
        steps=list(recipe.steps),
        personal_notes=recipe.personal_notes,
        tags=list(recipe.tags),
    )

    snapshots = list(recipe.edit_snapshots or [])
    snapshots.append(snapshot)

    # Enforce cap — drop oldest first
    if len(snapshots) > MAX_SNAPSHOTS:
        snapshots = snapshots[-MAX_SNAPSHOTS:]

    recipe.edit_snapshots = snapshots


def pop_snapshot(recipe: RecipeDocument) -> EditSnapshot | None:
    """
    Remove and return the most recent snapshot (LIFO).
    Returns None if no snapshots exist.
    Does NOT save the recipe — caller must call recipe.save() after applying.
    """
    snapshots = list(recipe.edit_snapshots or [])
    if not snapshots:
        return None
    snapshot = snapshots.pop()
    recipe.edit_snapshots = snapshots
    return snapshot
