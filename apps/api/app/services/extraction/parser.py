"""
app/services/extraction/parser.py

Parses a raw ingredient string into a structured dict matching RecipeIngredient.

Strategy:
  1. Strip optional markers
  2. Extract preparation clause (comma-separated suffix or parenthesised note)
  3. Tokenise the front to find numeric quantity + known unit
  4. Rest is the ingredient name

Uses parse_quantity() and normalise_unit() from unit_normaliser.py.
"""

from __future__ import annotations

import re

from app.services.extraction.unit_normaliser import (
    _UNIT_SYNONYMS,
    normalise_unit,
    parse_quantity,
)

# ── Canonical units set (for fast membership test) ────────────────────────

_KNOWN_UNITS: frozenset[str] = frozenset(_UNIT_SYNONYMS.keys()) | frozenset(
    _UNIT_SYNONYMS.values()
)

# ── Preparation verbs ─────────────────────────────────────────────────────

_PREP_VERBS: frozenset[str] = frozenset([
    "diced", "chopped", "minced", "sliced", "grated", "shredded", "peeled",
    "crushed", "mashed", "julienned", "cubed", "halved", "quartered",
    "roughly", "finely", "thinly", "coarsely", "freshly", "dried",
    "toasted", "roasted", "softened", "melted", "beaten", "whisked",
    "sifted", "packed", "heaped", "lightly", "well", "ground", "squeezed",
    "trimmed", "deveined", "deboned", "skinless", "boneless", "rinsed",
    "drained", "room temperature",
])

# ── Optional flag ─────────────────────────────────────────────────────────

_OPTIONAL_RE = re.compile(r"\(optional\)|\boptional\b", re.IGNORECASE)

# ── Quantity token pattern ────────────────────────────────────────────────
# Matches things like: "1", "2.5", "1/2", "1 1/2", "½", "¾", "2-3"

_QTY_TOKEN_RE = re.compile(
    r"^([\d½⅓⅔¼¾⅛⅜⅝⅞⅙⅚⅕⅖⅗⅘]+(?:[./\-–][\d]+)?(?:\s+[\d]+/[\d]+)?)"
)


def _extract_preparation(name: str) -> tuple[str, str | None]:
    """
    Split trailing preparation clause from the ingredient name.

    "garlic cloves, minced"       → ("garlic cloves", "minced")
    "butter (room temperature)"   → ("butter", "room temperature")
    "olive oil (extra virgin)"    → ("olive oil", "extra virgin")
    "fresh basil"                 → ("fresh basil", None)
    """
    prep: str | None = None

    # Parenthesised clause
    paren_m = re.search(r"\(([^)]+)\)", name)
    if paren_m:
        inner = paren_m.group(1).strip()
        if inner.lower() != "optional":
            prep = inner
        name = (name[: paren_m.start()] + name[paren_m.end():]).strip().rstrip(",").strip()

    # Comma-separated preparation suffix
    comma_idx = name.rfind(",")
    if comma_idx != -1:
        candidate = name[comma_idx + 1:].strip()
        first_word = candidate.split()[0].lower() if candidate else ""
        if first_word in _PREP_VERBS:
            prep = (f"{prep}, {candidate}" if prep else candidate)
            name = name[:comma_idx].strip()

    return name.strip(), prep


def parse_ingredient_string(raw: str) -> dict:
    """
    Parse a free-text ingredient string into a structured dict.

    Examples
    --------
    "2 cups all-purpose flour"      → {name:"all-purpose flour", quantity:2.0, unit:"cup"}
    "1/2 tsp salt"                  → {name:"salt", quantity:0.5, unit:"tsp"}
    "1 1/2 cups milk"               → {name:"milk", quantity:1.5, unit:"cup"}
    "3 garlic cloves, minced"       → {name:"garlic cloves", quantity:3.0, preparation:"minced"}
    "salt and pepper to taste"      → {name:"salt and pepper to taste", quantity:None}
    "100 g spaghetti"               → {name:"spaghetti", quantity:100.0, unit:"g"}
    """
    raw = raw.strip()
    optional = bool(_OPTIONAL_RE.search(raw))
    raw = _OPTIONAL_RE.sub("", raw).strip()

    qty: float | None = None
    unit: str | None = None
    name = raw

    # ── Step 1: try to pull a leading numeric quantity ────────────────────
    qty_m = _QTY_TOKEN_RE.match(raw)
    if qty_m:
        qty_str = qty_m.group(1).strip()
        rest = raw[qty_m.end():].strip()

        # Handle "1 1/2"-style mixed fractions that the regex split into "1" + "1/2 …"
        mixed_m = re.match(r"^(\d+/\d+)", rest)
        if mixed_m and qty_str.isdigit():
            qty_str = f"{qty_str} {mixed_m.group(1)}"
            rest = rest[mixed_m.end():].strip()

        qty = parse_quantity(qty_str)

        # ── Step 2: check if the next word is a known unit ────────────────
        tokens = rest.split()
        if tokens:
            candidate = tokens[0].lower().rstrip(".")
            # Also try two-word unit like "fluid ounce"
            two_word = f"{tokens[0]} {tokens[1]}".lower() if len(tokens) > 1 else ""
            if two_word and two_word.rstrip(".") in _UNIT_SYNONYMS:
                unit = normalise_unit(two_word)
                name = " ".join(tokens[2:])
            elif candidate in _UNIT_SYNONYMS or candidate in _KNOWN_UNITS:
                unit = normalise_unit(tokens[0])
                name = " ".join(tokens[1:])
            else:
                # No unit — everything after the number is the name
                name = rest
        else:
            name = rest

    name, prep = _extract_preparation(name)

    return {
        "name": name.strip() if name else raw.strip(),
        "quantity": qty,
        "unit": unit,
        "preparation": prep,
        "optional": optional,
    }


def normalise_ingredient(ingredient: dict) -> dict:
    """
    Normalise a GPT-structured ingredient dict:
      - quantity: coerce string fractions → float
      - unit: apply synonym table
      - name: strip whitespace
    """
    name = str(ingredient.get("name") or "").strip()
    raw_qty = ingredient.get("quantity")
    raw_unit = ingredient.get("unit")
    prep = ingredient.get("preparation")
    optional = bool(ingredient.get("optional", False))

    # Quantity coercion
    if isinstance(raw_qty, (int, float)):
        qty: float | None = float(raw_qty)
    elif isinstance(raw_qty, str):
        qty = parse_quantity(raw_qty)
    else:
        qty = None

    unit = normalise_unit(str(raw_unit)) if raw_unit else None

    return {
        "name": name,
        "quantity": qty,
        "unit": unit,
        "preparation": prep,
        "optional": optional,
    }


def normalise_ingredients(ingredients: list[dict | str]) -> list[dict]:
    """
    Normalise a mixed list of ingredient dicts or raw strings.
    Filters out items with empty names.
    """
    result: list[dict] = []
    for item in ingredients:
        if isinstance(item, str):
            result.append(parse_ingredient_string(item))
        elif isinstance(item, dict):
            result.append(normalise_ingredient(item))
    return [r for r in result if r.get("name")]
