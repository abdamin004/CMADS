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

def slide_title(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide, PAPER)
    band = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(1.5))
    band.fill.solid(); band.fill.fore_color.rgb = NAVY; band.line.fill.background()
    add_textbox(slide, 0.6, 2.0, 12.0, 1.2,
                "CMADS — Multi-Agent Systems for AI Clinical Decisioning",
                size=36, bold=True, color=NAVY)
    add_textbox(slide, 0.6, 3.2, 12.0, 0.7,
                "via Automation Workflows",
                size=28, color=GREY_DARK)
    add_textbox(slide, 0.6, 4.3, 12.0, 0.6,
                "100-patient multi-level memory results  ·  doctor console  ·  literature comparison",
                size=16, color=TEAL)
    add_textbox(slide, 0.6, 6.4, 12.0, 0.5,
                "Abdelrahman Mohamed Amin  ·  Supervisor: Dr. Shereen Moataz Afifi  ·  GUC  ·  May 2026",
                size=13, color=GREY_MED)


def slide_what_is_cmads(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "What CMADS is",
               "7-agent LangGraph pipeline + 4-tier memory subsystem")
    sysarch = TH_IMG / "ch3_system_architecture.png"
    memdiag = TH_IMG / "ch3_multilevel_memory.png"
    if sysarch.exists():
        add_image(slide, sysarch, 0.4, 1.2, width=8.5)
    else:
        add_textbox(slide, 0.5, 1.5, 8.0, 1.0,
                    "[diagram missing: ch3_system_architecture.png]",
                    size=12, color=RED)
    if memdiag.exists():
        add_image(slide, memdiag, 9.2, 1.4, width=3.8)
    add_textbox(slide, 9.2, 5.8, 3.8, 0.4,
                "Multi-level memory (inset)",
                size=11, bold=True, color=GREY_MED, align=PP_ALIGN.CENTER)
    add_textbox(slide, 0.4, 6.8, 12.5, 0.5,
                "Stage 1 (parallel) → Diagnostic loop → Reviewer → Refiner → Evaluator → Treatment (DIRECT only) → Memory consolidation",
                size=11, color=GREY_MED, align=PP_ALIGN.CENTER)


def slide_headline(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "100-patient multi-level memory result",
               "Combined batch_3 (cold-start, 50) + batch_4 (warmed, 50)")
    c = metrics["cohorts"]["combined_100"]
    cold = metrics["cohorts"]["batch_3_cold_start"]
    warm = metrics["cohorts"]["batch_4_warmed"]
    tile_w = 2.9
    tile_h = 1.6
    gap = 0.2
    left0 = 0.6
    top0 = 1.25
    tiles = [
        (f"{c['DIRECT_pct']:.1f}%",       "DIRECT (n=100)",            NAVY),
        (f"{c['found_pct']:.1f}%",        "Found (DIRECT + INDIRECT)", GREEN),
        (f"{c['MISS_pct']:.1f}%",         "MISS",                      AMBER),
        (f"~{c['avg_duration_s']:.0f} s", "Avg time / patient",        TEAL),
    ]
    for i, (v, l, col) in enumerate(tiles):
        add_metric_tile(slide, left0 + i * (tile_w + gap), top0, tile_w, tile_h,
                        v, l, value_color=col)
    headers = ["Cohort", "N", "DIRECT", "INDIRECT", "MISS", "Found",
               "Rank-1 in found", "Time/patient"]
    rows = [
        ["batch_3 (cold-start)", cold["n"],
         f"{cold['DIRECT_pct']:.0f}%", f"{cold['INDIRECT_pct']:.0f}%",
         f"{cold['MISS_pct']:.0f}%", f"{cold['found_pct']:.0f}%",
         f"{cold['rank1_in_found_pct']:.0f}%", f"~{cold['avg_duration_s']:.0f}s"],
        ["batch_4 (warmed)",      warm["n"],
         f"{warm['DIRECT_pct']:.0f}%", f"{warm['INDIRECT_pct']:.0f}%",
         f"{warm['MISS_pct']:.0f}%", f"{warm['found_pct']:.0f}%",
         f"{warm['rank1_in_found_pct']:.0f}%", f"~{warm['avg_duration_s']:.0f}s"],
        ["Combined",              c["n"],
         f"{c['DIRECT_pct']:.0f}%", f"{c['INDIRECT_pct']:.0f}%",
         f"{c['MISS_pct']:.0f}%", f"{c['found_pct']:.0f}%",
         f"{c['rank1_in_found_pct']:.0f}%", f"~{c['avg_duration_s']:.0f}s"],
    ]
    add_table(slide, 0.6, 3.2, 12.1, 2.7, headers, rows)
    add_textbox(slide, 0.6, 6.4, 12.1, 0.8,
                "Numbers pulled from data/gold/mas_results_improved_b3/ and "
                "data/gold/mas_results_improved_50/ via compute_metrics.py.",
                size=11, color=GREY_MED)


def slide_regime_split(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Split by regime",
               "Cold-start (no same-cohort priors) vs warmed (50 batch_4 priors)")
    cold = metrics["cohorts"]["batch_3_cold_start"]
    warm = metrics["cohorts"]["batch_4_warmed"]
    cards = [
        ("COLD-START — batch_3 (50)",
         "0 same-cohort priors at run start.",
         cold, BLUE),
        ("WARMED — batch_4 (50)",
         "Qdrant already held 50 batch_4 patients from a prior run.",
         warm, AMBER),
    ]
    for i, (title, sub, agg, accent) in enumerate(cards):
        left = 0.7 + i * 6.1
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                      Inches(left), Inches(1.3),
                                      Inches(5.8), Inches(4.3))
        box.fill.solid(); box.fill.fore_color.rgb = WHITE
        box.line.color.rgb = accent; box.line.width = Pt(1.5)
        add_textbox(slide, left + 0.2, 1.45, 5.5, 0.5, title,
                    size=16, bold=True, color=accent)
        add_textbox(slide, left + 0.2, 1.95, 5.5, 0.5, sub,
                    size=11, color=GREY_MED)
        lines = [
            ("DIRECT",          f"{agg['DIRECT_pct']:.0f}%   ({agg['DIRECT']}/{agg['n']})"),
            ("Found",           f"{agg['found_pct']:.0f}%   ({agg['found']}/{agg['n']})"),
            ("Rank-1 in found", f"{agg['rank1_in_found_pct']:.0f}%   ({agg['rank1_in_found']}/{agg['found']})"),
        ]
        for j, (k, v) in enumerate(lines):
            top = 2.7 + j * 0.85
            add_textbox(slide, left + 0.3, top, 2.4, 0.5, k,
                        size=13, bold=True, color=GREY_DARK)
            add_textbox(slide, left + 2.8, top, 2.9, 0.5, v,
                        size=18, bold=True, color=accent)
    leak = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                   Inches(0.7), Inches(5.85),
                                   Inches(11.9), Inches(0.95))
    leak.fill.solid(); leak.fill.fore_color.rgb = GREY_LIGHT
    leak.line.fill.background()
    add_textbox(slide, 0.9, 5.95, 11.5, 0.45,
                "Cohort-leakage estimate (notes/experiments.md, 2026-05-11):",
                size=12, bold=True, color=GREY_DARK)
    add_textbox(slide, 0.9, 6.35, 11.5, 0.45,
                "~6 pp of the batch_4 DIRECT gain and ~6 pp of the Found gain "
                "come from same-cohort priors, not algorithm.",
                size=12, color=GREY_DARK)


def slide_paired_mcnemar(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Paired McNemar A/B (n = 20)",
               "Same 20 patients, memory toggled · the only controlled test in the project")
    p = metrics["paired_mcnemar"]
    c = p["contingency"]
    headers = ["", "ON · DIRECT", "ON · not-DIRECT"]
    rows = [
        ["OFF · DIRECT",     c["both_DIRECT"],    c["only_OFF_DIRECT"]],
        ["OFF · not-DIRECT", c["only_ON_DIRECT"], c["neither_DIRECT"]],
    ]
    add_table(slide, 0.7, 1.6, 6.5, 2.9, headers, rows)
    panel = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                    Inches(7.7), Inches(1.6),
                                    Inches(5.0), Inches(2.9))
    panel.fill.solid(); panel.fill.fore_color.rgb = WHITE
    panel.line.color.rgb = GREY_LIGHT
    add_textbox(slide, 7.9, 1.7, 4.6, 0.5,
                "DIRECT rate", size=13, bold=True, color=GREY_DARK)
    add_textbox(slide, 7.9, 2.2, 4.6, 0.7,
                f"{p['off_direct_rate']*100:.0f}%  →  {p['on_direct_rate']*100:.0f}%",
                size=28, bold=True, color=NAVY)
    add_textbox(slide, 7.9, 3.0, 4.6, 0.5,
                "(8/20 → 9/20 · +5 pp point estimate)",
                size=11, color=GREY_MED)
    add_textbox(slide, 7.9, 3.6, 4.6, 0.5,
                "Exact McNemar (two-sided)",
                size=13, bold=True, color=GREY_DARK)
    add_textbox(slide, 7.9, 4.0, 4.6, 0.5,
                f"p = {p['mcnemar_p_two_sided']:.1f}   ·   discordant pairs: "
                f"{c['only_OFF_DIRECT'] + c['only_ON_DIRECT']}",
                size=16, bold=True, color=RED)
    add_textbox(slide, 0.7, 5.0, 12.0, 0.5,
                "Interpretation",
                size=14, bold=True, color=GREY_DARK)
    add_textbox(slide, 0.7, 5.5, 12.0, 1.5,
                "Point estimate favours memory by 5 pp, but with only 5 "
                "discordant pairs the sample size cannot confirm or refute. "
                "A bigger paired cohort is the obvious next step. The 100-"
                "patient aggregate on slide 3 mixes cohorts and is descriptive — "
                "this is the only controlled comparison.",
                size=12, color=GREY_DARK)


def slide_dashboard_overview(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Doctor dashboard — features overview",
               "Four features that make the run reviewable")
    console = REPO / "docs" / "final_presentation" / "doctor_console.png"
    if console.exists():
        add_image(slide, console, 0.4, 1.2, width=8.0)
    else:
        add_textbox(slide, 0.5, 1.5, 8.0, 1.0,
                    "[screenshot missing: docs/final_presentation/doctor_console.png]",
                    size=12, color=RED)
    items = [
        ("Agent workflow inline",
         "Every stage's output one click away, rendered as a doctor-readable narrative."),
        ("Similar past cases (Tier-4 recall)",
         "Top-K neighbours with their evaluator match type; one click switches view."),
        ("Treatment safety panel",
         "Drugs, interactions, contraindications + planner's assumptions & missing-data warnings."),
        ("Reviewer note + persistence",
         "Three-way verdict, free text, initials → data/gold/annotations/<uuid>.json."),
    ]
    left = 8.7
    top0 = 1.2
    for i, (head, body) in enumerate(items, start=1):
        top = top0 + (i - 1) * 1.25
        dia = 0.45
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                         Inches(left), Inches(top),
                                         Inches(dia), Inches(dia))
        circle.fill.solid(); circle.fill.fore_color.rgb = AMBER
        circle.line.color.rgb = WHITE; circle.line.width = Pt(1.5)
        tf = circle.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        pp = tf.paragraphs[0]; pp.alignment = PP_ALIGN.CENTER
        r = pp.add_run(); r.text = str(i)
        r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE
        add_textbox(slide, left + dia + 0.1, top - 0.05, 4.2, 0.45,
                    head, size=12, bold=True, color=NAVY)
        add_textbox(slide, left + dia + 0.1, top + 0.35, 4.2, 0.85,
                    body, size=10, color=GREY_DARK)
    add_textbox(slide, 0.4, 6.85, 12.5, 0.4,
                "URL-driven state: ?r=<set>&p=<uuid>&a=<agent> makes every view shareable and refresh-safe.",
                size=10, color=GREY_MED, align=PP_ALIGN.CENTER)


def slide_dashboard_treatment(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Treatment safety + reviewer flow",
               "What the planner did NOT know, surfaced; doctor verdict, persisted")
    shot = HERE / "dashboard_treatment.png"
    if shot.exists():
        add_image(slide, shot, 0.4, 1.2, width=8.5)
        text_left = 9.1
        text_width = 4.0
    else:
        add_textbox(slide, 0.4, 1.3, 8.5, 0.6,
                    "[treatment screenshot to be captured — drop dashboard_treatment.png next to build_pptx.py and rerun]",
                    size=11, color=RED)
        text_left = 0.4
        text_width = 12.5
    add_textbox(slide, text_left, 1.9 if not shot.exists() else 1.3,
                text_width, 0.5,
                "Surfaces what the planner did NOT know",
                size=14, bold=True, color=NAVY)
    add_textbox(slide, text_left, 2.4 if not shot.exists() else 1.8,
                text_width, 1.5,
                "• Drug dose assumptions (e.g. 'eGFR unknown — assumed normal "
                "for ACE-I dosing').\n"
                "• Missing-comorbidity warnings.\n"
                "• Interaction checks against current medication list.",
                size=11, color=GREY_DARK)
    add_textbox(slide, text_left, 4.0 if not shot.exists() else 3.6,
                text_width, 0.5,
                "Reviewer verdict persistence",
                size=14, bold=True, color=NAVY)
    add_textbox(slide, text_left, 4.5 if not shot.exists() else 4.1,
                text_width, 1.8,
                "• Three-way verdict (agree / uncertain / disagree).\n"
                "• Free text + reviewer initials.\n"
                "• Written to data/gold/annotations/<uuid>.json — the only "
                "write surface in the UI.\n"
                "• Unlocks clinician-agreement metrics beyond LLM-judge.",
                size=11, color=GREY_DARK)


def slide_literature(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Literature comparison — their results vs CMADS",
               "A/A: ✓ same metric/cohort family · ◐ related but different · ✗ different metric")
    c = metrics["cohorts"]["combined_100"]
    cmads_headline = (f"{c['DIRECT_pct']:.0f}% DIRECT  ·  "
                      f"{c['found_pct']:.0f}% Found  (n={c['n']}, 8 disease families)")
    headers = ["Paper", "Cohort", "Their reported headline",
               "CMADS comparable", "A/A"]
    rows = [
        ["AMIE (Tu 2024)",          "149 OSCE scenarios · 20 PCPs",
         "Beat PCPs on 28/32 specialist axes; 24/26 patient-actor axes",
         cmads_headline, "◐"],
        ["MedAgents (Tang 2024)",   "9 medical-reasoning benchmarks",
         "86.7% avg with GPT-4 (MedQA 83.7%, PubMedQA 94.3%)",
         cmads_headline, "✗"],
        ["AgentClinic (Schmidgall 2024)", "215 USMLE + 260 specialist + 749 multilingual",
         "Claude-3.5: 62.1% on AgentClinic-MedQA; PCPs 54% ±28.5",
         cmads_headline, "◐"],
        ["ZODIAC (Zhou 2024)",      "Cardiology, 8 metrics",
         "(qualitative) Cardiologist-level on 7/8",
         cmads_headline, "◐"],
        ["ClinicalLab (Yan 2024)",  "1,500 real cases, 11 depts",
         "(qualitative) Within ~5% of senior physicians",
         cmads_headline, "◐"],
    ]
    add_table(slide, 0.4, 1.2, 12.5, 4.6, headers, rows, first_col_bold=True)
    add_textbox(slide, 0.4, 6.0, 12.5, 1.1,
                "Bold-style numbers are citable from the paper's abstract or experiments section. "
                "AMIE and AgentClinic share the closest evaluation shape (real-case differential "
                "diagnosis with a clinician baseline). MedAgents reports MCQ accuracy, included as "
                "a different-metric reference. (qualitative) marks the strongest non-numeric claim.",
                size=11, color=GREY_MED)


def slide_gaps(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Gaps I filled",
               "Each gap is small. Nobody closes all four in one system — that's the contribution.")
    quads = [
        ("1. End-to-end pipeline",
         "Synthea → differential → NICE plan → doctor review.",
         "vs MDAgents, ClinicalLab (benchmark accuracy only).",
         BLUE),
        ("2. Open-source backbone",
         "GPT-OSS-120B reasoning + Qwen3-32B judge, reproducible.",
         "vs MDAgents, ClinicalLab, ZODIAC (GPT-4 family).",
         TEAL),
        ("3. Inspectable 4-tier memory + controlled A/B",
         "Working / Episodic / Semantic / Case-based, with paired test.",
         "vs all five (memory implicit or absent).",
         AMBER),
        ("4. Doctor console + persisted verdicts",
         "Agent inspector, similar cases, treatment safety, annotation.",
         "vs all five (none ship a clinician annotation surface).",
         GREEN),
    ]
    card_w = 5.9
    card_h = 2.6
    positions = [(0.6, 1.3), (6.8, 1.3), (0.6, 4.1), (6.8, 4.1)]
    for (head, body, contrast, color), (left, top) in zip(quads, positions):
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                      Inches(left), Inches(top),
                                      Inches(card_w), Inches(card_h))
        box.fill.solid(); box.fill.fore_color.rgb = WHITE
        box.line.color.rgb = color; box.line.width = Pt(2)
        add_textbox(slide, left + 0.2, top + 0.15, card_w - 0.3, 0.55,
                    head, size=16, bold=True, color=color)
        add_textbox(slide, left + 0.2, top + 0.85, card_w - 0.3, 0.85,
                    body, size=12, color=GREY_DARK)
        add_textbox(slide, left + 0.2, top + 1.85, card_w - 0.3, 0.55,
                    contrast, size=11, color=GREY_MED)
    add_textbox(slide, 0.6, 6.85, 12.1, 0.45,
                "The composition is the contribution.",
                size=14, bold=True, color=NAVY, align=PP_ALIGN.CENTER)


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
