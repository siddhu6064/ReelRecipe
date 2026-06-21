"""
tests/test_parser.py

Unit tests for parse_ingredient_string() and normalise_ingredient().
"""

from __future__ import annotations

import pytest

from app.services.extraction.parser import (
    normalise_ingredient,
    normalise_ingredients,
    parse_ingredient_string,
)


class TestParseIngredientString:
    def test_simple_quantity_unit_name(self):
        result = parse_ingredient_string("2 cups flour")
        assert result["name"] == "flour"
        assert result["quantity"] == 2.0
        assert result["unit"] == "cup"

    def test_fractional_quantity(self):
        result = parse_ingredient_string("1/2 tsp salt")
        assert result["quantity"] == pytest.approx(0.5)
        assert result["unit"] == "tsp"
        assert result["name"] == "salt"

    def test_mixed_fraction(self):
        result = parse_ingredient_string("1 1/2 cups milk")
        assert result["quantity"] == pytest.approx(1.5)
        assert result["unit"] == "cup"

    def test_unicode_fraction(self):
        result = parse_ingredient_string("¾ cup sugar")
        assert result["quantity"] == pytest.approx(0.75)
        assert result["unit"] == "cup"
        assert result["name"] == "sugar"

    def test_preparation_after_comma(self):
        result = parse_ingredient_string("3 garlic cloves, minced")
        assert result["name"] == "garlic cloves"
        assert result["preparation"] == "minced"
        assert result["quantity"] == 3.0

    def test_preparation_finely_diced(self):
        result = parse_ingredient_string("1 onion, finely diced")
        assert "onion" in result["name"]
        assert result["preparation"] is not None

    def test_optional_flag(self):
        result = parse_ingredient_string("1 tbsp capers (optional)")
        assert result["optional"] is True
        assert result["name"] == "capers"

    def test_no_unit_whole_item(self):
        result = parse_ingredient_string("2 eggs")
        assert result["quantity"] == 2.0
        assert result["name"] == "eggs"

    def test_to_taste(self):
        result = parse_ingredient_string("salt and pepper to taste")
        assert result["quantity"] is None
        assert result["name"] is not None

    def test_empty_string(self):
        result = parse_ingredient_string("")
        # Should not crash
        assert isinstance(result, dict)

    def test_gram_weight(self):
        result = parse_ingredient_string("200g spaghetti")
        # "200g" is harder to parse without a space — quantity may be None
        # but name should have content
        assert result["name"] is not None

    def test_weight_with_space(self):
        result = parse_ingredient_string("200 g spaghetti")
        assert result["quantity"] == 200.0
        assert result["unit"] == "g"
        assert result["name"] == "spaghetti"


class TestNormaliseIngredient:
    def test_already_structured(self):
        ing = {"name": "flour", "quantity": 2, "unit": "cups", "preparation": None, "optional": False}
        result = normalise_ingredient(ing)
        assert result["quantity"] == 2.0
        assert result["unit"] == "cup"   # synonym normalised

    def test_string_quantity_fraction(self):
        ing = {"name": "butter", "quantity": "1/2", "unit": "cup"}
        result = normalise_ingredient(ing)
        assert result["quantity"] == pytest.approx(0.5)

    def test_string_quantity_whole_number(self):
        ing = {"name": "eggs", "quantity": "3", "unit": None}
        result = normalise_ingredient(ing)
        assert result["quantity"] == 3.0

    def test_none_quantity_preserved(self):
        ing = {"name": "salt", "quantity": None, "unit": None, "preparation": "to taste"}
        result = normalise_ingredient(ing)
        assert result["quantity"] is None

    def test_unit_synonym_tablespoon(self):
        ing = {"name": "olive oil", "quantity": 2, "unit": "tablespoons"}
        result = normalise_ingredient(ing)
        assert result["unit"] == "tbsp"

    def test_empty_name_excluded_by_normalise_list(self):
        items = [
            {"name": "flour", "quantity": 1, "unit": "cup"},
            {"name": "", "quantity": 2, "unit": "g"},
        ]
        result = normalise_ingredients(items)
        assert len(result) == 1
        assert result[0]["name"] == "flour"


class TestNormaliseIngredients:
    def test_mixed_list(self):
        items = [
            "2 cups flour",
            {"name": "sugar", "quantity": 1, "unit": "cup"},
            "1/2 tsp baking powder",
        ]
        result = normalise_ingredients(items)
        assert len(result) == 3
        names = [r["name"] for r in result]
        assert "flour" in names
        assert "sugar" in names
        assert "baking powder" in names

    def test_empty_list(self):
        assert normalise_ingredients([]) == []

    def test_all_strings(self):
        items = ["3 eggs", "100 g butter", "1 cup milk"]
        result = normalise_ingredients(items)
        assert len(result) == 3
