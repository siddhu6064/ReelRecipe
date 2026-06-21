"""
app/services/extraction/unit_normaliser.py

Converts raw ingredient quantity/unit strings into canonical
(quantity: float | None, unit: str | None) pairs.

Handles:
  - Fractions: "1/2" → 0.5, "1 1/2" → 1.5, "¼" → 0.25
  - Unicode vulgar fractions: ½ ⅓ ¼ ¾ ⅔ ⅛ ⅜ ⅝ ⅞
  - Unit synonyms: "tablespoon" → "tbsp", "ounces" → "oz"
  - Plural normalisation: "cups" → "cup"
  - Whole items: "3 cloves" → quantity=3, unit="cloves"
  - Ranges: "2-3 cups" → quantity=2.5, unit="cup"
  - "to taste" / "pinch" → quantity=None, unit=None
"""

from __future__ import annotations

import re

# ── Unicode vulgar fractions ───────────────────────────────────────────────

_VULGAR: dict[str, float] = {
    "½": 0.5,
    "⅓": 1 / 3,
    "⅔": 2 / 3,
    "¼": 0.25,
    "¾": 0.75,
    "⅛": 0.125,
    "⅜": 0.375,
    "⅝": 0.625,
    "⅞": 0.875,
    "⅙": 1 / 6,
    "⅚": 5 / 6,
    "⅕": 0.2,
    "⅖": 0.4,
    "⅗": 0.6,
    "⅘": 0.8,
}

# ── Unit synonym table ─────────────────────────────────────────────────────
# Maps any recognised surface form → canonical abbreviation

_UNIT_SYNONYMS: dict[str, str] = {
    # volume
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "tbsp": "tbsp",
    "tbs": "tbsp",
    "T": "tbsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tsp": "tsp",
    "t": "tsp",
    "cup": "cup",
    "cups": "cup",
    "c": "cup",
    "fluid ounce": "fl oz",
    "fluid ounces": "fl oz",
    "fl oz": "fl oz",
    "fl. oz": "fl oz",
    "floz": "fl oz",
    "pint": "pint",
    "pints": "pint",
    "pt": "pint",
    "quart": "quart",
    "quarts": "quart",
    "qt": "quart",
    "gallon": "gallon",
    "gallons": "gallon",
    "gal": "gallon",
    "liter": "l",
    "liters": "l",
    "litre": "l",
    "litres": "l",
    "l": "l",
    "milliliter": "ml",
    "milliliters": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "ml": "ml",
    # weight
    "gram": "g",
    "grams": "g",
    "g": "g",
    "kilogram": "kg",
    "kilograms": "kg",
    "kg": "kg",
    "ounce": "oz",
    "ounces": "oz",
    "oz": "oz",
    "pound": "lb",
    "pounds": "lb",
    "lbs": "lb",
    "lb": "lb",
    # loose
    "pinch": "pinch",
    "pinches": "pinch",
    "dash": "dash",
    "dashes": "dash",
    "handful": "handful",
    "handfuls": "handful",
    "slice": "slice",
    "slices": "slice",
    "piece": "piece",
    "pieces": "piece",
    "clove": "clove",
    "cloves": "clove",
    "sprig": "sprig",
    "sprigs": "sprig",
    "stalk": "stalk",
    "stalks": "stalk",
    "bunch": "bunch",
    "bunches": "bunch",
    "can": "can",
    "cans": "can",
    "jar": "jar",
    "jars": "jar",
    "package": "package",
    "packages": "package",
    "pkg": "package",
    "packet": "packet",
    "packets": "packet",
    "sheet": "sheet",
    "sheets": "sheet",
    "stick": "stick",
    "sticks": "stick",
    "drop": "drop",
    "drops": "drop",
}

# ── Skip phrases (no quantity/unit) ───────────────────────────────────────

_SKIP_PHRASES = frozenset(
    [
        "to taste",
        "as needed",
        "as required",
        "a pinch",
        "a dash",
        "a handful",
        "some",
        "optional",
    ]
)

# ── Regex helpers ──────────────────────────────────────────────────────────

# "1/2", "3/4", "1 1/2" etc.
_FRACTION_RE = re.compile(r"(\d+)\s*/\s*(\d+)")
# A range like "2-3" or "2 to 3"
_RANGE_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[-–]\s*(\d+(?:\.\d+)?)")
# Leading number (int or decimal)
_NUMBER_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)")


def _parse_fraction(text: str) -> float | None:
    """Parse '1/2', '3 1/4' etc. → float.  Returns None if no fraction found."""
    # Unicode vulgar fraction at the start
    for char, val in _VULGAR.items():
        if char in text:
            # Check for a whole number before it: "1½" → 1.5
            prefix = text[: text.index(char)].strip()
            whole = float(prefix) if prefix and prefix.replace(".", "").isdigit() else 0.0
            return whole + val

    # ASCII fractions like "1/2" or "3 1/4"
    m = _FRACTION_RE.search(text)
    if m:
        num, denom = int(m.group(1)), int(m.group(2))
        if denom == 0:
            return None
        frac = num / denom
        # Check for a whole number before the fraction: "2 1/2"
        before = text[: m.start()].strip()
        whole_m = _NUMBER_RE.match(before)
        whole = float(whole_m.group(1)) if whole_m else 0.0
        return whole + frac

    return None


def parse_quantity(raw: str) -> float | None:
    """
    Convert a raw quantity string to a float.
    Examples: "2" → 2.0, "1/2" → 0.5, "1 1/2" → 1.5, "½" → 0.5,
              "2-3" → 2.5 (midpoint of range), "to taste" → None
    """
    if not raw:
        return None

    raw = raw.strip().lower()

    # Skip phrases
    if raw in _SKIP_PHRASES:
        return None
    for phrase in _SKIP_PHRASES:
        if phrase in raw:
            return None

    # Range → midpoint
    range_m = _RANGE_RE.search(raw)
    if range_m:
        lo, hi = float(range_m.group(1)), float(range_m.group(2))
        return round((lo + hi) / 2, 3)

    # Try fraction parse first (handles vulgar + ASCII)
    frac = _parse_fraction(raw)
    if frac is not None:
        return round(frac, 4)

    # Plain number
    num_m = _NUMBER_RE.match(raw)
    if num_m:
        return float(num_m.group(1))

    return None


def normalise_unit(raw: str | None) -> str | None:
    """
    Map a raw unit string to its canonical form using the synonym table.
    Returns None if the unit is unrecognised or empty.
    """
    if not raw:
        return None
    stripped = raw.strip().rstrip(".")
    # Exact match first (case-sensitive for abbreviations like 'T')
    if stripped in _UNIT_SYNONYMS:
        return _UNIT_SYNONYMS[stripped]
    # Case-insensitive fallback
    lower = stripped.lower()
    if lower in _UNIT_SYNONYMS:
        return _UNIT_SYNONYMS[lower]
    # If it's a short unrecognised token (<= 15 chars), return it as-is
    # (could be "whole", "head", "ear" etc.)
    if len(stripped) <= 15:
        return stripped.lower()
    return None
