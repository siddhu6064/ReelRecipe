"""
tests/test_unit_normaliser.py

Unit tests for parse_quantity() and normalise_unit().
No mocks, no I/O — pure function testing.
"""

from __future__ import annotations

import pytest

from app.services.extraction.unit_normaliser import normalise_unit, parse_quantity


# ── parse_quantity ─────────────────────────────────────────────────────────


class TestParseQuantity:
    def test_integer(self):
        assert parse_quantity("2") == 2.0

    def test_float(self):
        assert parse_quantity("1.5") == 1.5

    def test_simple_fraction(self):
        assert parse_quantity("1/2") == pytest.approx(0.5)

    def test_mixed_fraction(self):
        assert parse_quantity("1 1/2") == pytest.approx(1.5)

    def test_mixed_fraction_three_halves(self):
        assert parse_quantity("2 1/2") == pytest.approx(2.5)

    def test_three_quarters_fraction(self):
        assert parse_quantity("3/4") == pytest.approx(0.75)

    def test_one_third(self):
        assert parse_quantity("1/3") == pytest.approx(1 / 3, rel=1e-3)

    def test_unicode_half(self):
        assert parse_quantity("½") == pytest.approx(0.5)

    def test_unicode_quarter(self):
        assert parse_quantity("¼") == pytest.approx(0.25)

    def test_unicode_three_quarters(self):
        assert parse_quantity("¾") == pytest.approx(0.75)

    def test_unicode_mixed(self):
        assert parse_quantity("1½") == pytest.approx(1.5)

    def test_unicode_eighth(self):
        assert parse_quantity("⅛") == pytest.approx(0.125)

    def test_range_returns_midpoint(self):
        result = parse_quantity("2-3")
        assert result == pytest.approx(2.5)

    def test_range_with_space(self):
        result = parse_quantity("2 - 4")
        assert result == pytest.approx(3.0)

    def test_to_taste_returns_none(self):
        assert parse_quantity("to taste") is None

    def test_as_needed_returns_none(self):
        assert parse_quantity("as needed") is None

    def test_pinch_returns_none(self):
        assert parse_quantity("a pinch") is None

    def test_empty_string_returns_none(self):
        assert parse_quantity("") is None

    def test_none_input_returns_none(self):
        assert parse_quantity(None) is None  # type: ignore[arg-type]

    def test_large_number(self):
        assert parse_quantity("500") == 500.0

    def test_decimal_with_fraction(self):
        # e.g. "0.5" is already a decimal
        assert parse_quantity("0.5") == pytest.approx(0.5)


# ── normalise_unit ─────────────────────────────────────────────────────────


class TestNormaliseUnit:
    def test_tablespoon_variants(self):
        assert normalise_unit("tablespoon") == "tbsp"
        assert normalise_unit("tablespoons") == "tbsp"
        assert normalise_unit("tbsp") == "tbsp"
        assert normalise_unit("Tbsp") == "tbsp"

    def test_teaspoon_variants(self):
        assert normalise_unit("teaspoon") == "tsp"
        assert normalise_unit("teaspoons") == "tsp"
        assert normalise_unit("tsp") == "tsp"

    def test_cup_variants(self):
        assert normalise_unit("cup") == "cup"
        assert normalise_unit("cups") == "cup"

    def test_gram_variants(self):
        assert normalise_unit("gram") == "g"
        assert normalise_unit("grams") == "g"
        assert normalise_unit("g") == "g"

    def test_kilogram_variants(self):
        assert normalise_unit("kilogram") == "kg"
        assert normalise_unit("kilograms") == "kg"
        assert normalise_unit("kg") == "kg"

    def test_ounce_variants(self):
        assert normalise_unit("ounce") == "oz"
        assert normalise_unit("ounces") == "oz"
        assert normalise_unit("oz") == "oz"

    def test_pound_variants(self):
        assert normalise_unit("pound") == "lb"
        assert normalise_unit("pounds") == "lb"
        assert normalise_unit("lbs") == "lb"

    def test_milliliter_variants(self):
        assert normalise_unit("milliliter") == "ml"
        assert normalise_unit("milliliters") == "ml"
        assert normalise_unit("ml") == "ml"

    def test_liter_variants(self):
        assert normalise_unit("liter") == "l"
        assert normalise_unit("litre") == "l"
        assert normalise_unit("l") == "l"

    def test_clove_variants(self):
        assert normalise_unit("clove") == "clove"
        assert normalise_unit("cloves") == "clove"

    def test_pinch_variants(self):
        assert normalise_unit("pinch") == "pinch"
        assert normalise_unit("pinches") == "pinch"

    def test_fluid_ounce(self):
        assert normalise_unit("fluid ounce") == "fl oz"
        assert normalise_unit("fl oz") == "fl oz"

    def test_none_returns_none(self):
        assert normalise_unit(None) is None

    def test_empty_returns_none(self):
        assert normalise_unit("") is None

    def test_unknown_short_word_passthrough(self):
        # Short unknown units are passed through (e.g. "head", "ear")
        result = normalise_unit("head")
        assert result == "head"

    def test_can_variants(self):
        assert normalise_unit("can") == "can"
        assert normalise_unit("cans") == "can"
