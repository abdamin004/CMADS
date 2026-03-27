"""
generate_architecture_figure.py
Clinical AI Data Lake — Thesis Architecture Figure

Produces a publication-quality pipeline diagram saved to:
  notebooks/architecture_figure.png
"""

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
import matplotlib.patheffects as pe
import numpy as np
from pathlib import Path

OUT = Path(__file__).parent / "architecture_figure.png"

# ── Palette ────────────────────────────────────────────────────────────────────
C = {
    "bg"        : "#F7F9FC",
    "synthea"   : "#2E86AB",   # blue
    "bronze"    : "#CD6116",   # bronze/copper
    "silver"    : "#6B7280",   # steel grey
    "silver_p"  : "#4B5563",   # darker steel
    "synthetic" : "#7C3AED",   # purple
    "gold"      : "#B8860B",   # dark gold
    "agents"    : "#DC2626",   # red
    "portal"    : "#059669",   # emerald
    "orch"      : "#0F766E",   # teal
    "eval"      : "#B45309",   # amber
    "arrow"     : "#374151",
    "white"     : "#FFFFFF",
    "text_dark" : "#111827",
    "text_light": "#FFFFFF",
    "grid"      : "#E5E7EB",
    "header_bg" : "#1E293B",
}

# ── Figure setup ───────────────────────────────────────────────────────────────
fig = plt.figure(figsize=(22, 14), dpi=150)
fig.patch.set_facecolor(C["bg"])
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, 22)
ax.set_ylim(0, 14)
ax.set_aspect("equal")
ax.axis("off")
ax.set_facecolor(C["bg"])

# ── Helpers ────────────────────────────────────────────────────────────────────
def box(ax, x, y, w, h, color, radius=0.25, alpha=1.0, lw=0, edge=None):
    ec = edge if edge else color
    p = FancyBboxPatch((x, y), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       facecolor=color, edgecolor=ec,
                       linewidth=lw, alpha=alpha, zorder=3)
    ax.add_patch(p)
    return p

def shadow(ax, x, y, w, h, radius=0.25):
    p = FancyBboxPatch((x+0.07, y-0.07), w, h,
                       boxstyle=f"round,pad=0,rounding_size={radius}",
                       facecolor="#00000018", edgecolor="none",
                       linewidth=0, zorder=2)
    ax.add_patch(p)

def label(ax, x, y, text, size=9, color=C["white"], weight="normal",
          ha="center", va="center", zorder=5, wrap=False):
    ax.text(x, y, text, fontsize=size, color=color, fontweight=weight,
            ha=ha, va=va, zorder=zorder,
            fontfamily="DejaVu Sans",
            wrap=wrap)

def arrow(ax, x0, y0, x1, y1, color=C["arrow"], lw=2.2, style="-|>",
          rad=0.0, zorder=4):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(
                    arrowstyle=style,
                    color=color,
                    lw=lw,
                    connectionstyle=f"arc3,rad={rad}",
                    mutation_scale=18,
                ),
                zorder=zorder)

def dashed_arrow(ax, x0, y0, x1, y1, color=C["arrow"], lw=1.6):
    ax.annotate("", xy=(x1, y1), xytext=(x0, y0),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=color,
                    lw=lw,
                    linestyle="dashed",
                    connectionstyle="arc3,rad=0",
                    mutation_scale=15,
                ),
                zorder=4)

# ══════════════════════════════════════════════════════════════════════════════
# TITLE BANNER
# ══════════════════════════════════════════════════════════════════════════════
box(ax, 0.3, 12.8, 21.4, 0.95, C["header_bg"], radius=0.2)
label(ax, 11.0, 13.27,
      "Clinical AI Data Lake — End-to-End Pipeline Architecture",
      size=16, weight="bold", color=C["white"])
label(ax, 11.0, 12.96,
      "Medallion Lakehouse  ·  Synthea → Bronze → Silver → Silver+ → Synthetic → Gold → Multi-Agent AI → Streamlit Portal",
      size=9.5, color="#94A3B8")

# ══════════════════════════════════════════════════════════════════════════════
# LAYER BACKGROUND BANDS  (horizontal swim lanes)
# ══════════════════════════════════════════════════════════════════════════════
bands = [
    (0.15, 11.65, 21.7, 1.0,  "#EBF4FF"),   # Synthea
    (0.15, 10.35, 21.7, 1.2,  "#FFF7ED"),   # Bronze
    (0.15,  8.95, 21.7, 1.3,  "#F3F4F6"),   # Silver
    (0.15,  7.55, 21.7, 1.3,  "#ECFDF5"),   # Silver+
    (0.15,  6.15, 21.7, 1.3,  "#F5F3FF"),   # Synthetic
    (0.15,  4.80, 21.7, 1.25, "#FFFBEB"),   # Gold
    (0.15,  2.20, 21.7, 2.50, "#FEF2F2"),   # Agents + Eval
    (0.15,  0.55, 21.7, 1.55, "#ECFDF5"),   # Orchestration + Portal
]
for bx, by, bw, bh, bc in bands:
    box(ax, bx, by, bw, bh, bc, radius=0.15, lw=0)

# Lane labels (left margin tags)
lane_meta = [
    (0.23, 12.05, C["synthea"],   "DATA\nGENERATION"),
    (0.23, 10.75, C["bronze"],    "BRONZE\nLAYER"),
    (0.23,  9.45, C["silver"],    "SILVER\nLAYER"),
    (0.23,  8.05, C["silver_p"],  "SILVER+\nLAYER"),
    (0.23,  6.65, C["synthetic"], "SYNTHETIC\nLAYER"),
    (0.23,  5.30, C["gold"],      "GOLD\nLAYER"),
    (0.23,  3.30, C["agents"],    "AI AGENTS\n& EVAL"),
    (0.23,  1.15, C["orch"],      "ORCHESTR-\nATION"),
]
for lx, ly, lc, lt in lane_meta:
    box(ax, lx, ly-0.45, 0.72, 0.92, lc, radius=0.12)
    label(ax, lx+0.36, ly, lt, size=5.8, weight="bold", color=C["white"])

# ══════════════════════════════════════════════════════════════════════════════
# ROW 1 — SYNTHEA  (y ≈ 11.65–12.65)
# ══════════════════════════════════════════════════════════════════════════════
sy = 11.72
# Synthea main block
shadow(ax, 1.1, sy, 5.2, 0.88)
box(ax, 1.1, sy, 5.2, 0.88, C["synthea"], radius=0.2)
label(ax, 3.7, sy+0.62, "SYNTHEA  (Java CLI)", size=11, weight="bold")
label(ax, 3.7, sy+0.38, "Synthetic patient generator · Open-source FHIR R4", size=8.2)
label(ax, 3.7, sy+0.18, "Disease modules: diabetes · chronic_kidney_disease · congestive_heart_failure", size=7.8)

# Config boxes beside it
for i, (cfg, detail) in enumerate([
    ("−p 10,000", "10 × 1K batches"),
    ("−p 100,000", "stress test"),
    ("FHIR R4 + CSV", "dual export"),
    ("Massachusetts", "US demographics"),
]):
    cx = 6.8 + i * 2.55
    box(ax, cx, sy+0.08, 2.3, 0.72, "#DBEAFE", radius=0.15, lw=1.2, edge="#93C5FD")
    label(ax, cx+1.15, sy+0.52, cfg, size=9, weight="bold", color="#1D4ED8")
    label(ax, cx+1.15, sy+0.25, detail, size=7.5, color="#374151")

# Output format tags
for i, (tag, sub) in enumerate([
    ("FHIR R4 JSON\nBundles", "data/raw/batch_N/fhir/"),
    ("CSV Tables\n18 files", "data/raw/batch_N/csv/"),
    ("Run Metadata\nJSON", "data/raw/batch_N/metadata/"),
]):
    ox = 17.1 + i * 1.56
    box(ax, ox, sy+0.06, 1.42, 0.76, "#EFF6FF", radius=0.12, lw=1, edge="#BFDBFE")
    label(ax, ox+0.71, sy+0.54, tag, size=7.0, weight="bold", color="#1E40AF")
    label(ax, ox+0.71, sy+0.18, sub, size=6.0, color="#6B7280")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Synthea → Bronze
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 11.72, 11.0, 11.26, color=C["bronze"], lw=2.5)
label(ax, 11.65, 11.50, "Raw data", size=7.5, color=C["bronze"])

# ══════════════════════════════════════════════════════════════════════════════
# ROW 2 — BRONZE  (y ≈ 10.35–11.55)
# ══════════════════════════════════════════════════════════════════════════════
by_ = 10.42
shadow(ax, 1.1, by_, 5.5, 0.82)
box(ax, 1.1, by_, 5.5, 0.82, C["bronze"], radius=0.2)
label(ax, 3.85, by_+0.58, "BRONZE INGESTION  (Python + PyArrow)", size=10.5, weight="bold")
label(ax, 3.85, by_+0.36, "FHIR bundle parser · CSV ingestor · metadata stamping (batch_id, load_ts)", size=8)
label(ax, 3.85, by_+0.16, "Output: Parquet files  →  data/bronze/batch=<uuid>/", size=7.8)

# Bronze table groups
bgroups = [
    ("CSV Bronze\n13 tables", "patients · encounters\nconditions · medications\nobservations · procedures\nimmunizations · careplans\nallergies · devices\nclaims · imaging · providers", "#FEF3C7", "#D97706"),
    ("FHIR Bronze\n20 resources", "Patient · Encounter\nCondition · Observation\nMedicationRequest · DiagnosticReport\nProcedure · Immunization\nCarePlan · CareTeam · Goal\nDevice · ImagingStudy\nClaim · EOB · Coverage\nOrganization · Practitioner\nPractitionerRole · Location", "#FEF3C7", "#D97706"),
    ("Metadata\nColumns", "batch_id (UUID)\nload_timestamp\nsource_system\nbatch_size\nfhir_version\nraw_path", "#FEF3C7", "#D97706"),
]
for i, (title, detail, fc, ec) in enumerate(bgroups):
    bx2 = 7.0 + i * 4.85
    bw2 = 4.55
    box(ax, bx2, by_+0.04, bw2, 0.74, fc, radius=0.14, lw=1.3, edge=ec)
    label(ax, bx2+bw2/2, by_+0.62, title, size=8.5, weight="bold", color="#92400E")
    label(ax, bx2+bw2/2, by_+0.30, detail, size=6.5, color="#374151")

# Parquet tag
box(ax, 20.0, by_+0.18, 1.65, 0.48, "#FFF7ED", radius=0.12, lw=1, edge="#FB923C")
label(ax, 20.82, by_+0.42, "Parquet", size=8, weight="bold", color="#C2410C")
label(ax, 20.82, by_+0.22, "append-only", size=7, color="#6B7280")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Bronze → Silver
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 10.42, 11.0, 10.22, color=C["silver"], lw=2.5)
label(ax, 12.1, 10.34, "DuckDB reads Parquet  →  dbt run", size=7.5, color=C["silver"])

# ══════════════════════════════════════════════════════════════════════════════
# ROW 3 — SILVER  (y ≈ 8.95–10.25)
# ══════════════════════════════════════════════════════════════════════════════
sv_y = 9.02
shadow(ax, 1.1, sv_y, 4.8, 0.84)
box(ax, 1.1, sv_y, 4.8, 0.84, C["silver"], radius=0.2)
label(ax, 3.5, sv_y+0.60, "SILVER — OMOP CDM v5.4", size=10.5, weight="bold")
label(ax, 3.5, sv_y+0.38, "dbt-core + DuckDB · SQL transformation models", size=8)
label(ax, 3.5, sv_y+0.18, "models/silver/*.sql  ·  dbt test  ·  dbt docs", size=7.8)

# Silver OMOP tables
omop_tables = [
    ("person", "person_id\ngender_concept_id\nyear_of_birth\nrace_concept_id"),
    ("visit_occurrence", "visit_occurrence_id\nperson_id\nvisit_concept_id\nvisit_start/end_date"),
    ("condition_\noccurrence", "condition_concept_id\n(SNOMED-CT)\nonset/end dates"),
    ("measurement", "measurement_concept_id\n(LOINC)\nvalue_as_number\nrange_low/high"),
    ("drug_exposure", "drug_concept_id\n(RxNorm)\nstart/end dates\nquantity · route"),
    ("observation", "observation_concept_id\n(LOINC)\nvalue_as_string\nvalue_as_concept_id"),
]
for i, (tname, cols) in enumerate(omop_tables):
    tx = 6.2 + i * 2.62
    tw = 2.45
    shadow(ax, tx, sv_y+0.04, tw, 0.76)
    box(ax, tx, sv_y+0.04, tw, 0.76, C["white"], radius=0.14, lw=1.5, edge=C["silver"])
    box(ax, tx, sv_y+0.57, tw, 0.23, C["silver"], radius=0.14)
    label(ax, tx+tw/2, sv_y+0.685, tname, size=7.5, weight="bold", color=C["white"])
    label(ax, tx+tw/2, sv_y+0.31, cols, size=6.2, color="#374151")

# dbt badge
box(ax, 20.0, sv_y+0.24, 1.65, 0.38, "#F1F5F9", radius=0.12, lw=1, edge="#64748B")
label(ax, 20.82, sv_y+0.43, "dbt tests", size=7.5, weight="bold", color="#334155")
label(ax, 20.82, sv_y+0.26, "6 models", size=7, color="#6B7280")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Silver → Silver+
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 9.02, 11.0, 8.82, color=C["silver_p"], lw=2.5)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 4 — SILVER+  (y ≈ 7.55–8.85)
# ══════════════════════════════════════════════════════════════════════════════
sp_y = 7.62
shadow(ax, 1.1, sp_y, 4.8, 0.84)
box(ax, 1.1, sp_y, 4.8, 0.84, C["silver_p"], radius=0.2)
label(ax, 3.5, sp_y+0.60, "SILVER+ — Derived Clinical Features", size=10.5, weight="bold")
label(ax, 3.5, sp_y+0.38, "dbt-core + DuckDB · Window functions · REGR_SLOPE", size=8)
label(ax, 3.5, sp_y+0.18, "models/silver_plus/*.sql  ·  seeds/critical_thresholds.csv", size=7.8)

sp_tables = [
    ("lab_trends", "REGR_SLOPE/LOINC\nRISING/FALLING\nSTABLE"),
    ("critical_\nlab_flags", "severity 1–5\nlife-threatening\nthresholds"),
    ("patient_risk_\nscores", "CKD stage\nHbA1c band\nFramingham · SOFA"),
    ("comorbidity_\nmatrix", "Binary SNOMED flags\ncase_type_label\ncomplexity score"),
    ("medication_\ntimeline", "Therapy gaps\nconcurrent meds\nguideline concordance"),
    ("encounter_\nsummary", "30-day readmission\nED/inpatient counts\nvisit frequency"),
    ("drug_condition\n_links", "Drug-indication\ncontraindication\nflags"),
    ("lab_panel_\nsummary", "Per-encounter JSON\nabnormal counts\ncompleteness %"),
    ("data_quality_\nreport", "Null rates\norphan counts\nHTML report"),
]
cols_per_row = 9
for i, (tname, cols) in enumerate(sp_tables):
    tx = 6.2 + i * 1.73
    tw = 1.60
    shadow(ax, tx, sp_y+0.04, tw, 0.76)
    box(ax, tx, sp_y+0.04, tw, 0.76, C["white"], radius=0.12, lw=1.3, edge=C["silver_p"])
    box(ax, tx, sp_y+0.57, tw, 0.23, C["silver_p"], radius=0.12)
    label(ax, tx+tw/2, sp_y+0.69, tname, size=6.3, weight="bold", color=C["white"])
    label(ax, tx+tw/2, sp_y+0.30, cols, size=5.6, color="#374151")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Silver+ → Synthetic + Gold (split)
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 7.62, 11.0, 7.40, color=C["synthetic"], lw=2.5)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 5 — SYNTHETIC  (y ≈ 6.15–7.45)
# ══════════════════════════════════════════════════════════════════════════════
syn_y = 6.22
shadow(ax, 1.1, syn_y, 4.8, 0.84)
box(ax, 1.1, syn_y, 4.8, 0.84, C["synthetic"], radius=0.2)
label(ax, 3.5, syn_y+0.60, "SYNTHETIC — LLM Clinical Text Generation", size=10.5, weight="bold")
label(ax, 3.5, syn_y+0.38, "Python + Claude Sonnet 4.6 API · Grounded in Silver OMOP data", size=8)
label(ax, 3.5, syn_y+0.18, "pipeline/generators/  ·  400–600 word narratives", size=7.8)

syn_tables = [
    ("clinical_notes", "SOAP notes\nSubjective · Objective\nAssessment · Plan", "#EDE9FE", "#7C3AED"),
    ("radiology_\nreports", "Indication · Findings\nImpression\nstructured_findings_json", "#EDE9FE", "#7C3AED"),
    ("discharge_\nsummaries", "Hospital course\nDischarge condition\nFollow-up plan", "#EDE9FE", "#7C3AED"),
    ("patient_\nnarratives", "400–600 words/patient\nPrimary EHR Agent\ninput document", "#EDE9FE", "#7C3AED"),
    ("agent_ground\n_truth", "Expected diagnoses\nInvestigations\nTreatments · Referrals", "#EDE9FE", "#7C3AED"),
]
for i, (tname, cols, fc, ec) in enumerate(syn_tables):
    tx = 6.6 + i * 3.05
    tw = 2.80
    shadow(ax, tx, syn_y+0.04, tw, 0.76)
    box(ax, tx, syn_y+0.04, tw, 0.76, fc, radius=0.14, lw=1.3, edge=ec)
    box(ax, tx, syn_y+0.57, tw, 0.23, ec, radius=0.14)
    label(ax, tx+tw/2, syn_y+0.685, tname, size=7.5, weight="bold", color=C["white"])
    label(ax, tx+tw/2, syn_y+0.30, cols, size=6.5, color="#374151")

# Claude badge
box(ax, 20.0, syn_y+0.24, 1.65, 0.38, "#F5F3FF", radius=0.12, lw=1, edge="#8B5CF6")
label(ax, 20.82, syn_y+0.43, "Claude", size=8, weight="bold", color="#6D28D9")
label(ax, 20.82, syn_y+0.26, "Sonnet 4.6", size=7, color="#6B7280")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Synthetic → Gold
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 6.22, 11.0, 6.02, color=C["gold"], lw=2.5)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 6 — GOLD  (y ≈ 4.80–6.05)
# ══════════════════════════════════════════════════════════════════════════════
go_y = 4.87
shadow(ax, 1.1, go_y, 4.8, 0.80)
box(ax, 1.1, go_y, 4.8, 0.80, C["gold"], radius=0.2)
label(ax, 3.5, go_y+0.57, "GOLD — Case Assembler  (Python)", size=10.5, weight="bold")
label(ax, 3.5, go_y+0.35, "Joins Silver + Silver+ + Synthetic into AI-ready case objects", size=8)
label(ax, 3.5, go_y+0.15, "pipeline/gold/ehr_assembler.py  ·  lab_assembler.py", size=7.8)

gold_objects = [
    ("ehr_case.json", "person + condition_occurrence\n+ drug_exposure + encounter_summary\n+ patient_risk_scores\n+ comorbidity_matrix\n+ patient_narratives", "#FFFBEB", "#B45309"),
    ("lab_case.json", "measurement (LOINC labs)\n+ lab_trends + critical_lab_flags\n+ lab_panel_summary\n+ patient_risk_scores\n+ comorbidity_matrix (case_type)", "#FFFBEB", "#B45309"),
    ("DQ Report\n(HTML)", "dbt tests\n+ Great Expectations\nNull rates · Orphan counts\nConcept coverage · Patient loss\nMeasurement range checks", "#FFFBEB", "#B45309"),
    ("clinical.\nduckdb", "DuckDB database file\nAll Silver + Gold tables\nDirect SQL access\nPortable to S3/GCS", "#FFFBEB", "#B45309"),
]
for i, (tname, cols, fc, ec) in enumerate(gold_objects):
    tx = 6.2 + i * 3.75
    tw = 3.50
    shadow(ax, tx, go_y+0.04, tw, 0.72)
    box(ax, tx, go_y+0.04, tw, 0.72, fc, radius=0.14, lw=1.5, edge=ec)
    box(ax, tx, go_y+0.53, tw, 0.23, ec, radius=0.14)
    label(ax, tx+tw/2, go_y+0.655, tname, size=8.5, weight="bold", color=C["white"])
    label(ax, tx+tw/2, go_y+0.28, cols, size=6.5, color="#374151")

# ══════════════════════════════════════════════════════════════════════════════
# ARROW Gold → Agents
# ══════════════════════════════════════════════════════════════════════════════
arrow(ax, 11.0, 4.87, 11.0, 4.68, color=C["agents"], lw=2.5)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 7 — AI AGENTS + EVAL  (y ≈ 2.20–4.70)
# ══════════════════════════════════════════════════════════════════════════════
ag_y = 3.35

# EHR Agent
shadow(ax, 1.1, ag_y, 5.0, 1.28)
box(ax, 1.1, ag_y, 5.0, 1.28, "#FEE2E2", radius=0.18, lw=1.8, edge=C["agents"])
box(ax, 1.1, ag_y+1.04, 5.0, 0.24, C["agents"], radius=0.18)
label(ax, 3.60, ag_y+1.16, "EHR Agent", size=10, weight="bold", color=C["white"])
label(ax, 3.60, ag_y+0.80, "Input: ehr_case.json + patient_narratives", size=8, color="#374151")
label(ax, 3.60, ag_y+0.60, "Tools: condition lookup · drug interaction check", size=7.8, color="#374151")
label(ax, 3.60, ag_y+0.40, "Output: Pydantic-structured differential dx,", size=7.8, color="#374151")
label(ax, 3.60, ag_y+0.22, "         investigations, treatments, referrals", size=7.8, color="#374151")
label(ax, 3.60, ag_y+0.05, "LangChain + Claude Sonnet 4.6 + FAISS RAG", size=7.5, weight="bold", color="#991B1B")

# Lab Agent
shadow(ax, 6.4, ag_y, 5.0, 1.28)
box(ax, 6.4, ag_y, 5.0, 1.28, "#FEE2E2", radius=0.18, lw=1.8, edge=C["agents"])
box(ax, 6.4, ag_y+1.04, 5.0, 0.24, C["agents"], radius=0.18)
label(ax, 8.90, ag_y+1.16, "Lab Agent", size=10, weight="bold", color=C["white"])
label(ax, 8.90, ag_y+0.80, "Input: lab_case.json + critical_lab_flags", size=8, color="#374151")
label(ax, 8.90, ag_y+0.60, "Tools: lab trend analysis · critical value alert", size=7.8, color="#374151")
label(ax, 8.90, ag_y+0.40, "Output: Pydantic-structured lab interpretation,", size=7.8, color="#374151")
label(ax, 8.90, ag_y+0.22, "         urgency flags, recommended actions", size=7.8, color="#374151")
label(ax, 8.90, ag_y+0.05, "LangChain + Claude Sonnet 4.6 + FAISS RAG", size=7.5, weight="bold", color="#991B1B")

# Orchestrator
shadow(ax, 11.65, ag_y, 4.0, 1.28)
box(ax, 11.65, ag_y, 4.0, 1.28, "#FEE2E2", radius=0.18, lw=1.8, edge="#B91C1C")
box(ax, 11.65, ag_y+1.04, 4.0, 0.24, "#B91C1C", radius=0.18)
label(ax, 13.65, ag_y+1.16, "Multi-Agent Orchestrator", size=9, weight="bold", color=C["white"])
label(ax, 13.65, ag_y+0.80, "Python pipeline coordinator", size=8, color="#374151")
label(ax, 13.65, ag_y+0.60, "Sequential: EHR → Lab → Synthesis", size=7.8, color="#374151")
label(ax, 13.65, ag_y+0.40, "Conflict resolution · Pydantic", size=7.8, color="#374151")
label(ax, 13.65, ag_y+0.22, "output validation", size=7.8, color="#374151")
label(ax, 13.65, ag_y+0.05, "orchestrator/orchestrator.py", size=7.5, color="#991B1B")

# Evaluation block
shadow(ax, 15.9, ag_y, 5.8, 1.28)
box(ax, 15.9, ag_y, 5.8, 1.28, "#FFFBEB", radius=0.18, lw=1.8, edge=C["eval"])
box(ax, 15.9, ag_y+1.04, 5.8, 0.24, C["eval"], radius=0.18)
label(ax, 18.80, ag_y+1.16, "Evaluation Framework", size=9, weight="bold", color=C["white"])
label(ax, 18.80, ag_y+0.82, "Baseline vs multi-agent comparison", size=8, color="#374151")
label(ax, 18.80, ag_y+0.62, "LLM-as-judge rationale scoring", size=7.8, color="#374151")
label(ax, 18.80, ag_y+0.42, "100-case evaluation run", size=7.8, color="#374151")
label(ax, 18.80, ag_y+0.22, "Precision · Recall · F1 per domain", size=7.8, color="#374151")
label(ax, 18.80, ag_y+0.05, "evaluation/run_evaluation.py", size=7.5, color="#92400E")

# RAG tag (floating)
box(ax, 1.2, 2.60, 3.0, 0.55, "#EFF6FF", radius=0.14, lw=1.2, edge="#3B82F6")
label(ax, 2.70, 2.90, "FAISS RAG Index", size=8, weight="bold", color="#1D4ED8")
label(ax, 2.70, 2.70, "Clinical guideline PDFs  ·  rag/build_index.py", size=7, color="#374151")

dashed_arrow(ax, 2.70, 3.15, 2.70, 3.35, color="#3B82F6", lw=1.5)
dashed_arrow(ax, 5.30, 2.90, 6.50, 3.70, color="#3B82F6", lw=1.5)

# Agent inter-arrows
arrow(ax, 6.1, ag_y+0.64, 6.4, ag_y+0.64, color=C["agents"], lw=2)
arrow(ax, 11.4, ag_y+0.64, 11.65, ag_y+0.64, color="#B91C1C", lw=2)
arrow(ax, 15.65, ag_y+0.64, 15.9, ag_y+0.64, color=C["eval"], lw=2)

# ══════════════════════════════════════════════════════════════════════════════
# ROW 8 — ORCHESTRATION + PORTAL  (y ≈ 0.55–2.10)
# ══════════════════════════════════════════════════════════════════════════════
or_y = 0.68

# Prefect
shadow(ax, 1.1, or_y, 5.5, 1.30)
box(ax, 1.1, or_y, 5.5, 1.30, "#ECFDF5", radius=0.18, lw=1.8, edge=C["orch"])
box(ax, 1.1, or_y+1.06, 5.5, 0.24, C["orch"], radius=0.18)
label(ax, 3.85, or_y+1.18, "Prefect Orchestration  (local)", size=10, weight="bold", color=C["white"])
label(ax, 3.85, or_y+0.82, "7-task sequential flow  ·  DAG orchestration", size=8, color="#374151")
pref_tasks = [
    "1. generate_synthea.map()",
    "2. ingest_bronze.map()",
    "3. run_dbt(silver.*)",
    "4. run_dbt(silver_plus.*)",
    "5. generate_synthetic_text()",
    "6. assemble_gold_cases()",
    "7. run_dq_checks()",
]
for j, pt in enumerate(pref_tasks):
    col = C["orch"] if j % 2 == 0 else "#134E4A"
    label(ax, 3.85, or_y+0.63 - j*0.082, pt, size=7.0, color=col)

# Streamlit portal
shadow(ax, 6.9, or_y, 6.2, 1.30)
box(ax, 6.9, or_y, 6.2, 1.30, "#ECFDF5", radius=0.18, lw=1.8, edge=C["portal"])
box(ax, 6.9, or_y+1.06, 6.2, 0.24, C["portal"], radius=0.18)
label(ax, 10.0, or_y+1.18, "Streamlit Portal  (localhost:8501)", size=10, weight="bold", color=C["white"])
label(ax, 10.0, or_y+0.82, "Python web app · Reads clinical.duckdb directly", size=8, color="#374151")
port_features = [
    ("Case Viewer", "Patient summary · EHR timeline · Agent output"),
    ("DQ Dashboard", "dbt test results · GX profile · null rate charts"),
    ("Lab Explorer", "Trend charts · Critical flags · Panel summaries"),
    ("Agent Eval Panel", "Baseline vs agent · Score comparison table"),
]
for j, (title, detail) in enumerate(port_features):
    fy = or_y + 0.63 - j * 0.155
    label(ax, 7.4, fy, f"▸ {title}", size=7.5, weight="bold", color=C["portal"], ha="left")
    label(ax, 10.7, fy, detail, size=7.0, color="#374151", ha="left")

# DuckDB central block
shadow(ax, 13.35, or_y, 4.0, 1.30)
box(ax, 13.35, or_y, 4.0, 1.30, "#F0FDF4", radius=0.18, lw=2, edge="#22C55E")
box(ax, 13.35, or_y+1.06, 4.0, 0.24, "#22C55E", radius=0.18)
label(ax, 15.35, or_y+1.18, "DuckDB Engine", size=10, weight="bold", color=C["white"])
label(ax, 15.35, or_y+0.82, "clinical.duckdb  ·  in-process SQL", size=8, color="#374151")
label(ax, 15.35, or_y+0.62, "Reads Parquet natively", size=7.8, color="#374151")
label(ax, 15.35, or_y+0.44, "Window functions · REGR_SLOPE", size=7.8, color="#374151")
label(ax, 15.35, or_y+0.26, "<1s query · 100K patients", size=7.8, weight="bold", color="#166534")
label(ax, 15.35, or_y+0.09, "Portable → S3 / GCS", size=7.5, color="#374151")

# Great Expectations block
shadow(ax, 17.6, or_y, 4.0, 1.30)
box(ax, 17.6, or_y, 4.0, 1.30, "#F0FDF4", radius=0.18, lw=2, edge="#16A34A")
box(ax, 17.6, or_y+1.06, 4.0, 0.24, "#16A34A", radius=0.18)
label(ax, 19.6, or_y+1.18, "Data Quality (DQ)", size=10, weight="bold", color=C["white"])
label(ax, 19.6, or_y+0.82, "dbt tests + Great Expectations", size=8, color="#374151")
label(ax, 19.6, or_y+0.62, "dbt: unique · not_null · relationships", size=7.8, color="#374151")
label(ax, 19.6, or_y+0.44, "GX: statistical profile · HTML report", size=7.8, color="#374151")
label(ax, 19.6, or_y+0.26, "Concept coverage  < 5% NULL", size=7.8, color="#374151")
label(ax, 19.6, or_y+0.09, "Lab range validity > 95%", size=7.5, color="#374151")

# Orchestration arrows
arrow(ax, 4.0, 2.20, 4.0, 1.98, color=C["orch"], lw=2)
arrow(ax, 10.0, 2.20, 10.0, 1.98, color=C["portal"], lw=2)
dashed_arrow(ax, 11.4, 1.33, 13.35, 1.33, color="#22C55E", lw=1.5)
dashed_arrow(ax, 17.35, 1.33, 17.6, 1.33, color="#16A34A", lw=1.5)

# ══════════════════════════════════════════════════════════════════════════════
# SCALE TARGET CALLOUTS  (right margin)
# ══════════════════════════════════════════════════════════════════════════════
box(ax, 20.95, 6.80, 0.90, 4.85, "#1E293B", radius=0.15)
label(ax, 21.40, 11.30, "SCALE\nTARGETS", size=7.5, weight="bold", color="#94A3B8")
targets = [
    ("10K pts", "evaluation"),
    ("100K pts", "stress test"),
    ("65 tables", "total pipeline"),
    ("43 Bronze", "tables"),
    ("6 Silver", "OMOP tables"),
    ("9 Silver+", "derived tables"),
    ("5 Synthetic", "LLM tables"),
    ("2 Gold", "JSON objects"),
    ("<1s query", "@100K pts"),
    ("<5% NULL", "concept_id"),
    (">95%", "lab validity"),
]
for j, (val, sub2) in enumerate(targets):
    ty = 11.10 - j * 0.43
    label(ax, 21.40, ty, val, size=8.5, weight="bold", color="#34D399")
    label(ax, 21.40, ty-0.175, sub2, size=6.5, color="#94A3B8")

# ══════════════════════════════════════════════════════════════════════════════
# LEGEND / LAYER COUNT BAR  (bottom strip)
# ══════════════════════════════════════════════════════════════════════════════
legend_items = [
    (C["synthea"],   "Synthea Generator"),
    (C["bronze"],    "Bronze (Python+PyArrow)  43 tables"),
    (C["silver"],    "Silver OMOP CDM v5.4  6 tables"),
    (C["silver_p"],  "Silver+ Derived  9 tables"),
    (C["synthetic"], "Synthetic LLM Text  5 tables"),
    (C["gold"],      "Gold Assembler  2 objects"),
    (C["agents"],    "AI Agents (LangChain+Claude)"),
    (C["orch"],      "Prefect + Streamlit + DuckDB"),
]
box(ax, 0.15, 0.03, 20.65, 0.45, "#1E293B", radius=0.12)
for j, (lc, lt) in enumerate(legend_items):
    lx = 0.4 + j * 2.58
    box(ax, lx, 0.12, 0.28, 0.28, lc, radius=0.05)
    label(ax, lx+0.35, 0.26, lt, size=6.5, color="#E2E8F0", ha="left")

# Footnote
label(ax, 21.60, 0.26, "Figure 1 · Clinical AI Data Lake Architecture\nThesis 2026",
      size=6.5, color="#64748B", ha="right")

# ══════════════════════════════════════════════════════════════════════════════
# SAVE
# ══════════════════════════════════════════════════════════════════════════════
fig.savefig(OUT, dpi=180, bbox_inches="tight",
            facecolor=C["bg"], edgecolor="none")
plt.close()
print(f"Saved → {OUT}")
