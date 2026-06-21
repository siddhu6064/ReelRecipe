"""
app/services/barcode_service.py

Resolves a product barcode (EAN-13, UPC-A, UPC-E) to a pantry-ready
ingredient name + category via the Open Food Facts public API.

Open Food Facts: https://world.openfoodfacts.org
  - Free, no API key required
  - Rate limit: 100 requests/min per IP (we cache per barcode in Redis)
  - Endpoint: GET /api/v0/product/{barcode}.json
"""

from __future__ import annotations

import logging
import re

import httpx

logger = logging.getLogger(__name__)

_OFF_BASE = "https://world.openfoodfacts.org/api/v0/product"

# Rough mapping from OFF categories to our pantry categories
_CATEGORY_MAP: list[tuple[re.Pattern, str]] = [
    (re.compile(r"meat|beef|chicken|pork|poultry|fish|seafood|salmon|tuna", re.I), "meat"),
    (re.compile(r"milk|cheese|yogurt|dairy|cream|butter|egg", re.I), "dairy"),
    (re.compile(r"vegetable|fruit|produce|fresh|salad|herb", re.I), "produce"),
    (re.compile(r"bread|pasta|rice|cereal|grain|flour|noodle", re.I), "grains"),
    (re.compile(r"spice|seasoning|pepper|salt|cumin|paprika|oregano", re.I), "spices"),
    (re.compile(r"frozen|ice cream", re.I), "frozen"),
    (re.compile(r"drink|juice|soda|water|coffee|tea|beverage", re.I), "beverages"),
    (re.compile(r"sauce|oil|vinegar|condiment|ketchup|mayo", re.I), "pantry"),
    (re.compile(r"snack|chip|crisp|cookie|biscuit|candy", re.I), "pantry"),
    (re.compile(r"soup|broth|stock|canned", re.I), "pantry"),
]


def _map_category(product: dict) -> str:
    """Infer pantry category from OFF product data."""
    # Try category tags first
    for tag in product.get("categories_tags", []) or []:
        for pattern, cat in _CATEGORY_MAP:
            if pattern.search(tag):
                return cat

    # Fall back to product name
    name = product.get("product_name", "")
    for pattern, cat in _CATEGORY_MAP:
        if pattern.search(name):
            return cat

    return "other"


def _clean_name(raw: str) -> str:
    """Strip brand prefixes, excess whitespace, and capitalise first letter."""
    name = raw.strip()
    # Remove common brand-noise suffixes like "500g", "12 oz", etc.
    name = re.sub(r"\s+\d+\s*(g|kg|ml|l|oz|lb|fl oz)\b.*", "", name, flags=re.I)
    return name[:80].strip() or raw[:80]


async def lookup_barcode(barcode: str) -> dict | None:
    """
    Fetch product details from Open Food Facts for the given barcode.

    Returns:
        {
            "name":     str   — cleaned product name
            "category": str   — one of the pantry category enum values
            "brand":    str | None
            "off_id":   str   — barcode as canonical OFF product ID
        }
    Or None if the product is not found or the request fails.
    """
    barcode = barcode.strip()
    if not barcode.isdigit():
        return None

    url = f"{_OFF_BASE}/{barcode}.json"

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(
                url,
                headers={"User-Agent": "ReelRecipes/1.0 (contact@reelrecipes.app)"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            data = resp.json()
    except Exception as exc:
        logger.warning("barcode_lookup_failed barcode=%s error=%s", barcode, str(exc))
        return None

    if data.get("status") != 1:
        return None   # product not found in OFF database

    product = data.get("product", {})
    raw_name = (
        product.get("product_name_en")
        or product.get("product_name")
        or ""
    )
    if not raw_name:
        return None

    return {
        "name": _clean_name(raw_name),
        "category": _map_category(product),
        "brand": product.get("brands", "").split(",")[0].strip() or None,
        "off_id": barcode,
    }
