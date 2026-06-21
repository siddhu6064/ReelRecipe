"""
app/services/pdf_service.py

Generates a printable A4 recipe card PDF using fpdf2.
Returns bytes ready to stream as a FastAPI Response.

Design:
  - Orange header with recipe title and metadata badges
  - Two-column layout: ingredients left, nutrition right
  - Numbered step list with timer badges
  - Footer with source URL and ReelRecipes branding
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.documents import RecipeDocument


# ── Colour palette ─────────────────────────────────────────────────────────

PRIMARY   = (255, 107, 53)   # #ff6b35
DARK      = (15,  15,  15)   # #0f0f0f
MID_GREY  = (80,  80,  80)
LIGHT_BG  = (245, 245, 245)
WHITE     = (255, 255, 255)
GREEN     = (109, 191, 133)
ORANGE_BG = (255, 237, 227)


def generate_recipe_pdf(recipe: "RecipeDocument") -> bytes:
    """
    Build and return the recipe card as PDF bytes.
    Caller streams this with:
        Response(content=bytes, media_type="application/pdf")
    """
    from fpdf import FPDF, XPos, YPos

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()
    pdf.set_margins(15, 15, 15)

    page_w = 180   # usable width (210 - 2*15mm margins)

    # ── Header ────────────────────────────────────────────────────────────
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, 210, 42, style="F")

    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*WHITE)
    pdf.set_xy(15, 8)
    pdf.multi_cell(page_w, 9, recipe.title, align="L")

    # Metadata badges on header
    meta_parts = []
    if recipe.cuisine:
        meta_parts.append(recipe.cuisine)
    if recipe.difficulty:
        meta_parts.append(recipe.difficulty.capitalize())
    if recipe.total_time_minutes:
        t = recipe.total_time_minutes
        meta_parts.append(f"{t}m" if t < 60 else f"{t//60}h {t%60}m")
    if recipe.servings:
        meta_parts.append(f"Serves {recipe.servings}")

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*ORANGE_BG)
    pdf.set_xy(15, 32)
    pdf.cell(0, 6, "  ·  ".join(meta_parts), align="L")

    pdf.set_y(50)

    # ── Tags ─────────────────────────────────────────────────────────────
    if recipe.tags:
        pdf.set_font("Helvetica", "I", 9)
        pdf.set_text_color(*MID_GREY)
        pdf.cell(0, 5, "  ".join(f"#{t}" for t in recipe.tags[:6]), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    # ── Two-column: Ingredients | Nutrition ──────────────────────────────
    col_w = page_w * 0.58
    nut_w = page_w * 0.38
    col_gap = page_w * 0.04

    y_start = pdf.get_y()

    # --- Left: Ingredients ---
    pdf.set_xy(15, y_start)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(col_w, 7, "Ingredients", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(0.4)
    pdf.line(15, pdf.get_y(), 15 + col_w, pdf.get_y())
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    for ing in recipe.ingredients:
        qty = ""
        if ing.quantity is not None:
            qty = f"{ing.quantity:g} {ing.unit or ''}".strip()
        label = f"{ing.name}{', ' + ing.preparation if ing.preparation else ''}"
        if ing.optional:
            label += " (opt)"

        x = pdf.get_x()
        y = pdf.get_y()
        pdf.set_xy(15, y)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*PRIMARY)
        pdf.cell(28, 5.5, qty)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*DARK)
        pdf.cell(col_w - 28, 5.5, label, new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    ing_end_y = pdf.get_y()

    # --- Right: Nutrition ---
    if recipe.nutrition:
        nut_x = 15 + col_w + col_gap
        pdf.set_xy(nut_x, y_start)
        pdf.set_font("Helvetica", "B", 12)
        pdf.set_text_color(*PRIMARY)
        pdf.cell(nut_w, 7, "Nutrition", new_x=XPos.RIGHT, new_y=YPos.NEXT)
        pdf.set_draw_color(*PRIMARY)
        pdf.line(nut_x, pdf.get_y(), nut_x + nut_w, pdf.get_y())
        pdf.ln(2)
        pdf.set_xy(nut_x, pdf.get_y())
        pdf.set_font("Helvetica", "I", 8)
        pdf.set_text_color(*MID_GREY)
        pdf.cell(nut_w, 4, "per serving", new_x=XPos.RIGHT, new_y=YPos.NEXT)
        pdf.set_xy(nut_x, pdf.get_y())
        pdf.ln(1)

        macros = [
            ("Calories",    recipe.nutrition.calories,   "kcal"),
            ("Protein",     recipe.nutrition.protein_g,  "g"),
            ("Carbs",       recipe.nutrition.carbs_g,    "g"),
            ("Fat",         recipe.nutrition.fat_g,      "g"),
            ("Fibre",       recipe.nutrition.fiber_g,    "g"),
        ]
        for label, val, unit in macros:
            if val is None:
                continue
            pdf.set_xy(nut_x, pdf.get_y())
            pdf.set_fill_color(*LIGHT_BG)
            pdf.set_font("Helvetica", "", 9)
            pdf.set_text_color(*MID_GREY)
            pdf.cell(nut_w * 0.55, 6, label, fill=True)
            pdf.set_font("Helvetica", "B", 9)
            pdf.set_text_color(*DARK)
            pdf.cell(nut_w * 0.45, 6, f"{val:g} {unit}", fill=True,
                     new_x=XPos.RIGHT, new_y=YPos.NEXT)
            pdf.ln(0.5)

    # ── Instructions ─────────────────────────────────────────────────────
    pdf.set_y(max(ing_end_y, pdf.get_y()) + 6)
    pdf.set_x(15)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*PRIMARY)
    pdf.cell(0, 7, "Instructions", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(0.4)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(3)

    for step in sorted(recipe.steps, key=lambda s: s.order):
        # Step number circle
        x = pdf.get_x()
        y = pdf.get_y()
        pdf.set_fill_color(*PRIMARY)
        pdf.set_font("Helvetica", "B", 9)
        pdf.set_text_color(*WHITE)
        pdf.circle(x + 4, y + 3.5, 3.5, style="F")
        pdf.set_xy(x + 1.5, y + 0.5)
        pdf.cell(5, 6, str(step.order), align="C")

        # Step text
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*DARK)
        pdf.set_xy(x + 10, y)
        pdf.multi_cell(page_w - 10, 5.5, step.text)

        # Timer badge
        if step.timer_seconds:
            mins = round(step.timer_seconds / 60)
            pdf.set_x(x + 10)
            pdf.set_font("Helvetica", "I", 8)
            pdf.set_text_color(*MID_GREY)
            pdf.cell(0, 4, f"Timer: {mins} min", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.ln(2)

    # ── Footer ────────────────────────────────────────────────────────────
    pdf.set_y(-18)
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(0.3)
    pdf.line(15, pdf.get_y(), 195, pdf.get_y())
    pdf.ln(2)
    pdf.set_font("Helvetica", "I", 8)
    pdf.set_text_color(*MID_GREY)
    pdf.cell(0, 5, f"Source: {recipe.source_url[:80]}", align="L")
    pdf.set_x(15)
    pdf.cell(0, 5, "Made with ReelRecipes", align="R")

    return bytes(pdf.output())
