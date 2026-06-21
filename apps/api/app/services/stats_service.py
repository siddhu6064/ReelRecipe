"""
app/services/stats_service.py

Computes aggregate cooking statistics for a user's "Wrapped" card:
  - Total recipes imported
  - Unique cuisines
  - Most-used dietary tags
  - Favourite ingredient (appears most across all recipes)
  - Cook sessions completed (entries in cook_log)
  - Recipes imported this month / this year
  - Public recipes count
  - Avg recipe time
"""

from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime


async def get_user_stats(user_id: str) -> dict:
    from app.models.documents import RecipeDocument

    recipes = await RecipeDocument.find({"user_id": user_id}).to_list()

    if not recipes:
        return _empty_stats()

    now = datetime.now(UTC)

    # Basic counts
    total = len(recipes)
    public_count = sum(1 for r in recipes if r.is_public)

    # Cuisines
    cuisines = [r.cuisine for r in recipes if r.cuisine]
    unique_cuisines = list(dict.fromkeys(cuisines))   # preserve insertion order

    # Tags
    all_tags: list[str] = []
    for r in recipes:
        all_tags.extend(r.tags or [])
    top_tags = [tag for tag, _ in Counter(all_tags).most_common(5)]

    # Favourite ingredient (most frequent across all recipes)
    all_ings: list[str] = []
    for r in recipes:
        all_ings.extend(ing.name.lower() for ing in (r.ingredients or []))
    fav_ingredient = Counter(all_ings).most_common(1)[0][0].title() if all_ings else None

    # Cook sessions
    cook_sessions = sum(len(r.cook_log or []) for r in recipes)

    # Recipes this month
    this_month = sum(
        1 for r in recipes
        if r.created_at and r.created_at.year == now.year and r.created_at.month == now.month
    )

    # Recipes this year
    this_year = sum(1 for r in recipes if r.created_at and r.created_at.year == now.year)

    # Average cook time
    cook_times = [r.total_time_minutes for r in recipes if r.total_time_minutes]
    avg_time_minutes = round(sum(cook_times) / len(cook_times)) if cook_times else None

    # Most cooked cuisine (by cook_log)
    cuisine_cooks: Counter = Counter()
    for r in recipes:
        if r.cuisine and r.cook_log:
            cuisine_cooks[r.cuisine] += len(r.cook_log)
    most_cooked_cuisine = cuisine_cooks.most_common(1)[0][0] if cuisine_cooks else None

    # Streak: consecutive days with a cook session (simplified — calendar days with any cook)
    all_cook_dates = set()
    for r in recipes:
        for dt in (r.cook_log or []):
            all_cook_dates.add(dt.date())
    streak = _calc_streak(all_cook_dates)

    return {
        "total_recipes":       total,
        "public_recipes":      public_count,
        "unique_cuisines":     len(unique_cuisines),
        "top_cuisines":        unique_cuisines[:5],
        "top_tags":            top_tags,
        "favourite_ingredient": fav_ingredient,
        "cook_sessions":       cook_sessions,
        "most_cooked_cuisine": most_cooked_cuisine,
        "recipes_this_month":  this_month,
        "recipes_this_year":   this_year,
        "avg_cook_time_minutes": avg_time_minutes,
        "current_streak_days": streak,
        "generated_at":        now.isoformat(),
    }


def _empty_stats() -> dict:
    return {
        "total_recipes": 0, "public_recipes": 0, "unique_cuisines": 0,
        "top_cuisines": [], "top_tags": [], "favourite_ingredient": None,
        "cook_sessions": 0, "most_cooked_cuisine": None,
        "recipes_this_month": 0, "recipes_this_year": 0,
        "avg_cook_time_minutes": None, "current_streak_days": 0,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def _calc_streak(cook_dates: set) -> int:
    """Return the current consecutive-day streak ending today or yesterday."""
    if not cook_dates:
        return 0
    from datetime import date, timedelta
    today = date.today()
    streak = 0
    day = today
    while day in cook_dates:
        streak += 1
        day -= timedelta(days=1)
    # If not cooking today, check if streak ended yesterday
    if streak == 0:
        day = today - timedelta(days=1)
        while day in cook_dates:
            streak += 1
            day -= timedelta(days=1)
    return streak
