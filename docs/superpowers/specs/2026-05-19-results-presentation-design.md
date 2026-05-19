# Results & Comparison Presentation — Design Spec

**Date:** 2026-05-19
**Author:** Abdelrahman (with Claude Code)
**Purpose:** A fresh standalone presentation centred on three things — (1) the
100-patient multi-level memory result, (2) the doctor dashboard and its
important features, and (3) a literature comparison that puts other papers'
reported numbers next to CMADS numbers where they can be compared honestly.
The existing `docs/final_presentation/` deck is **not** the basis for this
work; this is a clean build.

## Scope and constraints

- 9 slides, ~7 minutes spoken at 135 wpm.
- Output: `docs/results_presentation/CMADS_Results_Presentation.pptx`.
- Built by `docs/results_presentation/build_pptx.py` (new file; do not import
  or reuse code from `docs/final_presentation/build_final_pptx.py`).
- Companion `docs/results_presentation/script.md` with full speaker notes.
- Diagrams reused (read-only) from `thesis/images/` and
  `docs/memory_presentation/`. Screenshots reused from
  `docs/final_presentation/doctor_console.png` plus one new capture of the
  treatment-review + reviewer-note view.
- All numbers must trace back to a file in the repo (per `thesis/CLAUDE.md`).
  No invented metrics. No marketing language.

## Slide map

| # | Title | Source files for numbers / visuals |
|---|---|---|
| 1 | Title — author, supervisor, date, one-sentence claim | — |
| 2 | What CMADS is, in one diagram | `thesis/images/ch3_system_architecture.png` or `ch3_agent_pipeline.png` |
| 3 | 100-patient multi-level memory — headline | `notes/experiments.md` (entries 2026-05-10 batch_3 + batch_4); `data/gold/mas_results_improved_b3/`, `data/gold/mas_results_improved_50/` |
| 4 | 100-patient — split by regime (cold-start vs warmed) | same as slide 3; the 2026-05-11 experiments entry for the cold-start delta |
| 5 | Paired McNemar A/B (n=20) | `data/gold/paired_memory_mcnemar.json`; 2026-05-15 experiments entry |
| 6 | Doctor dashboard — features overview | `docs/final_presentation/doctor_console.png`; `portal/dashboard.py`, `portal/pages/1_Memory_Trace.py` |
| 7 | Doctor dashboard — treatment safety + reviewer flow | new screenshot captured during build; `data/gold/annotations/` for verdict persistence reference |
| 8 | Literature comparison — their results vs CMADS | `thesis/bachelor.bib` plus paper abstracts where confirmable |
| 9 | Gaps I filled — four-quadrant | bib entries from slide 8 |

## Content details — slide by slide

### Slide 1 — Title

- **Title:** *Multi-Agent Systems for AI Clinical Decisioning via Automation
  Workflows*
- **Subtitle:** "100-patient multi-level memory results, doctor console, and
  where CMADS sits against the literature."
- Author / supervisor / institution / date per `thesis/CLAUDE.md`.

### Slide 2 — What CMADS is

- Single labelled diagram showing the 7-agent pipeline with the 4-tier memory
  alongside. Use `ch3_system_architecture.png` if it shows both; otherwise
  `ch3_agent_pipeline.png` for agents + `ch3_multilevel_memory.png` for
  memory as a small inset.
- One-line caption only. No bullet list. The slide is context, not content.

### Slide 3 — 100-patient memory headline

- Four metric tiles across the top:
  - **DIRECT:** combined batch_3 + batch_4 = (23 + 26) / 100 = **49.0%**.
  - **Found (DIRECT + INDIRECT):** (46 + 49) / 100 = **95.0%**.
  - **Rank-1 within Found:** weighted across cohorts ≈ **65.3%**
    (already used in the prior deck; keep as-is and cite the script that
    computed it: `docs/memory_presentation/compare_improved_b3.py` and
    `compare_improved_50.py`).
  - **Avg pipeline time:** ~**113 s/patient** (average of 113 and 112).
- Below the tiles, the per-cohort row table:

  | Cohort | N | DIRECT | INDIRECT | MISS | Found | Rank-1-in-found | Time/patient |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | batch_3 (cold-start) | 50 | 46% | 46% | 8% | 92% | 37% | 113 s |
  | batch_4 (warmed) | 50 | 52% | 46% | 2% | 98% | 27% | 112 s |
  | **Combined** | **100** | **49%** | **46%** | **5%** | **95%** | **~33%** | **113 s** |

  *(Rank-1-in-found "combined" is the weighted average; double-check at build
  time by reading `compare_improved_b3.py` + `compare_improved_50.py` rather
  than hand-computing.)*

### Slide 4 — Split by regime

- Two side-by-side cards: **Cold-start (batch_3)** vs **Warmed (batch_4)**.
- For each: DIRECT, Found, Rank-1, and one sentence explaining the regime.
- Bottom strip: the honest delta from the 2026-05-11 entry — "**~6 pp of the
  batch_4 DIRECT gain is cohort leakage**, not algorithm improvement."
- Single takeaway line: "Memory broadens recall (+Found) but the DIRECT gain
  is regime-dependent."

### Slide 5 — Paired McNemar A/B (n=20)

- 2×2 contingency square from `paired_memory_mcnemar.json`:
  - 6 both DIRECT
  - 9 both non-DIRECT
  - 2 OFF-only DIRECT
  - 3 ON-only DIRECT
- Below: **DIRECT 40% → 45%**; **Exact McNemar p = 1.0**.
- One-line interpretation: "Point estimate favours memory; sample size
  cannot confirm or refute. Larger paired cohort is the obvious next step."

### Slide 6 — Doctor dashboard — features overview

- Annotated screenshot of `doctor_console.png`. Four numbered callouts on
  top of the image:
  1. **Agent workflow inline** — every stage's output one click away,
     rendered as a doctor-readable narrative.
  2. **Similar past cases (Tier-4 recall)** — top-K neighbours with their
     evaluator match type; one click switches view.
  3. **Treatment safety panel** — drugs, interactions, contraindications,
     **plus assumptions & missing-data warnings**.
  4. **Reviewer note + persistence** — three-way verdict (agree / uncertain
     / disagree), free text, initials, written to
     `data/gold/annotations/<uuid>.json`. Sidebar shows coloured dot per
     annotated patient.
- Footer: "URL-driven state — `?r=<set>&p=<uuid>&a=<agent>` makes every
  view shareable and refresh-safe."

### Slide 7 — Dashboard — treatment safety + reviewer flow

- New screenshot of: treatment-review panel expanded **and** reviewer-note
  panel visible underneath. Captured during build.
- Two short bullet blocks:
  - **Surfaces what the planner did NOT know.** Example: "eGFR unknown —
    assumed normal for ACE-I dosing."
  - **Persists clinical judgement.** Three-way verdict + free text +
    initials. The only write-side persistence in the entire UI.
- One closing line tying it to evaluation: "This is what unlocks
  clinician-agreement metrics beyond LLM-judge agreement."

### Slide 8 — Literature comparison — their results vs CMADS

- Table — one row per paper, columns:
  *Paper · Cohort · Their reported headline · CMADS comparable · A/A flag*.
- A/A flag legend:
  - ✓ = same evaluation family (real cases, primary-diagnosis accuracy).
  - ◐ = related but different cohort or metric.
  - ✗ = different metric / not comparable.
- Sourcing rule (per user choice): pull each headline number from the
  paper's bib entry or its publicly available abstract. If a number cannot
  be confirmed within one or two fetches, **keep the row but write
  "(qualitative)" in the headline column** rather than invent a figure.
- Rows to populate (numbers to be verified at build time):
  1. **MDAgents (Kim, NeurIPS 2024)** — 10 medical reasoning benchmarks,
     mostly MCQ → CMADS 49–74% DIRECT on real EHR cases → flag **✗** (MCQ
     vs differential diagnosis on EHR).
  2. **ZODIAC (Zhou, 2024)** — cardiology cases, F1-like score → CMADS 49%
     DIRECT, 95% Found across 8 disease families → flag **◐** (one
     specialty vs eight; different metric).
  3. **ClinicalLab (Yan, 2024)** — 1,500 real cases, 11 departments →
     CMADS 100 real-shaped EHR cases, 8 families → flag **◐**.
  4. **MAC Framework (2025)** — 302 rare-disease cases, accuracy →
     CMADS 49% DIRECT on common chronic disease → flag **✗** (rare vs
     common).
  5. **RareAgents (Chen, 2024)** — RareBench + MIMIC-IV-Ext-Rare, Hit@K →
     CMADS uses DIRECT/INDIRECT/MISS, not Hit@K → flag **✗** but worth
     noting both use open-source backbones.
- One-line caption: "Apples-to-apples is rare in this literature — the
  contribution is the *composition*, not winning any single metric."

### Slide 9 — Gaps I filled

- Four quadrants. Each names a CMADS choice + the paper it differentiates
  against:
  1. **End-to-end pipeline (Synthea → differential → NICE plan → doctor
     review)** — vs MDAgents/ClinicalLab (benchmark accuracy only).
  2. **Open-source reasoning backbone (GPT-OSS-120B + Qwen3-32B judge)** —
     vs MDAgents/ClinicalLab/ZODIAC (GPT-4 family).
  3. **Inspectable 4-tier memory with controlled A/B** — vs all five
     (memory is implicit or absent).
  4. **Doctor-facing console with persisted clinician verdicts** —
     vs all five (none ship a clinician annotation surface).
- Single closing line, used as the talk's verbal close: "The composition is
  the contribution."

## Data sourcing & honesty rules

- Every number on slides 3–5 must read from a file in `data/gold/` or
  `notes/experiments.md`. The build script will pull them programmatically
  where feasible (`compare_improved_*.py` patterns); otherwise the spec
  lists the exact entry to copy from.
- Slide 8 numbers must be traceable to the paper. If a number cannot be
  confirmed from the bib entry or the abstract, write `(qualitative)`
  rather than invent. The flag column tells the reader why direct comparison
  is restricted.
- No marketing words ("breakthrough", "unprecedented", etc.). Match the
  tone of `thesis/results.tex` once it exists.

## Implementation outline (for the writing-plans hand-off)

1. **`docs/results_presentation/`** — new folder.
2. **`docs/results_presentation/script.md`** — full speaker notes,
   slide-by-slide, ~1000 words. Drafted first so the PPTX builder has
   stable copy to consume.
3. **`docs/results_presentation/build_pptx.py`** — self-contained builder
   (≤500 lines), one helper per layout (title, metric-tile grid, image
   with callouts, side-by-side table). Outputs
   `CMADS_Results_Presentation.pptx` next to itself.
4. **Screenshot capture** — start `streamlit run portal/dashboard.py`
   in the background, take a screenshot of the treatment+review view with
   `mcp__computer-use__screenshot`, save as
   `docs/results_presentation/dashboard_treatment.png`. If a known-good
   annotated patient UUID is needed, use one referenced in
   `data/gold/annotations/`.
5. **Verification pass** — before declaring done: open the PPTX (or use
   `python-pptx` to introspect) and confirm 9 slides exist, all images
   resolved, all metric numbers match the source files.

## Out of scope (explicitly)

- Editing or reusing `docs/final_presentation/`.
- Updating `thesis/results.tex` (separate task).
- Re-running the 100-patient experiment.
- Adding new analyses beyond what `notes/experiments.md` already records.
- Building a parallel HTML or reveal.js deck.

## Open questions resolved during brainstorming

- Format → PPTX.
- Competitor numbers → from bib + abstracts; fall back to qualitative if
  unverifiable.
- Screenshots → existing `doctor_console.png` + one new capture.

## Risks

- **Competitor numbers may not be quotable.** Mitigation: the
  "(qualitative)" fallback rule is part of the spec, not an escape hatch.
- **Screenshot capture flakiness.** Mitigation: if the dashboard can't be
  brought up cleanly, fall back to schema-based bullets on slide 7 and
  note the limitation.
- **Rank-1-in-found "combined" number is a weighted average across
  cohorts that compute it differently** (Round-A-only vs full-trace).
  Mitigation: read both `compare_improved_*` scripts at build time and
  if they disagree by more than 2 pp, split the cell instead of averaging.
