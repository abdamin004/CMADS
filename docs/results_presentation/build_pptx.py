"""Build the CMADS Results & Comparison deck.

9 slides. Numbers come from compute_metrics.compute(). No imports
from docs/final_presentation/. Run:

    python3 docs/results_presentation/build_pptx.py
"""

from __future__ import annotations

from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt

import compute_metrics

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
TH_IMG = REPO / "thesis" / "images"
OUT = HERE / "CMADS_Results_Presentation.pptx"

# ── Palette ─────────────────────────────────────────────────────────
NAVY = RGBColor(0x14, 0x2B, 0x4A)
BLUE = RGBColor(0x1F, 0x4E, 0x79)
TEAL = RGBColor(0x16, 0xA0, 0x85)
AMBER = RGBColor(0xD3, 0x54, 0x00)
GREEN = RGBColor(0x27, 0xAE, 0x60)
RED = RGBColor(0xC0, 0x39, 0x2B)
GREY_DARK = RGBColor(0x34, 0x49, 0x5E)
GREY_MED = RGBColor(0x7F, 0x8C, 0x8D)
GREY_LIGHT = RGBColor(0xEC, 0xF0, 0xF1)
PAPER = RGBColor(0xF7, 0xF9, 0xFC)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)


# ── Layout primitives ───────────────────────────────────────────────

def add_bg(slide, color=PAPER):
    bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
    bg.fill.solid(); bg.fill.fore_color.rgb = color
    bg.line.fill.background(); bg.shadow.inherit = False


def add_header(slide, title: str, subtitle: str | None = None, accent=NAVY):
    bar = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(0.95))
    bar.fill.solid(); bar.fill.fore_color.rgb = accent
    bar.line.fill.background()
    tb = slide.shapes.add_textbox(Inches(0.45), Inches(0.18), Inches(12.4), Inches(0.7))
    tf = tb.text_frame; tf.margin_left = tf.margin_right = 0
    p = tf.paragraphs[0]; r = p.add_run(); r.text = title
    r.font.size = Pt(26); r.font.bold = True; r.font.color.rgb = WHITE
    if subtitle:
        p2 = tf.add_paragraph(); r2 = p2.add_run(); r2.text = subtitle
        r2.font.size = Pt(13); r2.font.color.rgb = GREY_LIGHT


def add_textbox(slide, left, top, width, height, text, *, size=14, bold=False,
                color=GREY_DARK, align=PP_ALIGN.LEFT):
    tb = slide.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(height))
    tf = tb.text_frame; tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.05)
    p = tf.paragraphs[0]; p.alignment = align
    r = p.add_run(); r.text = text
    r.font.size = Pt(size); r.font.bold = bold; r.font.color.rgb = color
    return tb


def add_metric_tile(slide, left, top, width, height, value: str, label: str,
                    value_color=NAVY, bg=WHITE):
    """A big-number tile: value on top, small label under it."""
    box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                  Inches(left), Inches(top), Inches(width), Inches(height))
    box.fill.solid(); box.fill.fore_color.rgb = bg
    box.line.color.rgb = GREY_LIGHT; box.line.width = Pt(1)
    box.shadow.inherit = False
    tb = box.text_frame; tb.word_wrap = True
    tb.margin_left = tb.margin_right = Inches(0.05)
    p1 = tb.paragraphs[0]; p1.alignment = PP_ALIGN.CENTER
    r1 = p1.add_run(); r1.text = value
    r1.font.size = Pt(34); r1.font.bold = True; r1.font.color.rgb = value_color
    p2 = tb.add_paragraph(); p2.alignment = PP_ALIGN.CENTER
    r2 = p2.add_run(); r2.text = label
    r2.font.size = Pt(11); r2.font.color.rgb = GREY_MED


def add_table(slide, left, top, width, height, headers, rows,
              *, header_bg=NAVY, header_fg=WHITE, body_fg=GREY_DARK,
              first_col_bold=True):
    """Plain table with a coloured header row."""
    n_cols = len(headers)
    n_rows = len(rows) + 1
    tbl_shape = slide.shapes.add_table(n_rows, n_cols,
                                        Inches(left), Inches(top),
                                        Inches(width), Inches(height))
    table = tbl_shape.table
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.fill.solid(); cell.fill.fore_color.rgb = header_bg
        tf = cell.text_frame; tf.text = ""
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = h
        r.font.size = Pt(12); r.font.bold = True; r.font.color.rgb = header_fg
    for i, row in enumerate(rows, start=1):
        for j, val in enumerate(row):
            cell = table.cell(i, j)
            cell.fill.solid(); cell.fill.fore_color.rgb = WHITE if i % 2 else PAPER
            tf = cell.text_frame; tf.text = ""
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.CENTER
            r = p.add_run(); r.text = str(val)
            r.font.size = Pt(11); r.font.color.rgb = body_fg
            r.font.bold = first_col_bold and j == 0
    return table


def add_image(slide, path: Path, left, top, *, width=None, height=None):
    kwargs = {}
    if width: kwargs["width"] = Inches(width)
    if height: kwargs["height"] = Inches(height)
    return slide.shapes.add_picture(str(path), Inches(left), Inches(top), **kwargs)


# ── Slide functions (filled in by later tasks) ──────────────────────

def slide_title(prs, metrics): pass
def slide_what_is_cmads(prs, metrics): pass
def slide_headline(prs, metrics): pass
def slide_regime_split(prs, metrics): pass
def slide_paired_mcnemar(prs, metrics): pass
def slide_dashboard_overview(prs, metrics): pass
def slide_dashboard_treatment(prs, metrics): pass
def slide_literature(prs, metrics): pass
def slide_gaps(prs, metrics): pass


def main():
    metrics = compute_metrics.compute(REPO)

    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)

    for fn in (slide_title, slide_what_is_cmads, slide_headline,
               slide_regime_split, slide_paired_mcnemar,
               slide_dashboard_overview, slide_dashboard_treatment,
               slide_literature, slide_gaps):
        fn(prs, metrics)

    prs.save(str(OUT))
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
