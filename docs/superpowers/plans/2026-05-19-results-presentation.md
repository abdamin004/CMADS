# Results & Comparison Presentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new 9-slide `.pptx` deck (`docs/results_presentation/CMADS_Results_Presentation.pptx`) covering (1) the 100-patient multi-level memory result, (2) the doctor dashboard, and (3) a literature comparison putting other papers' headline numbers next to CMADS where comparable.

**Architecture:** Three thin layers under `docs/results_presentation/`:
1. `compute_metrics.py` — reads patient-level evaluations from `data/gold/mas_results_improved_b3/` and `mas_results_improved_50/`, plus `data/gold/paired_memory_mcnemar.json`, and emits one `metrics.json` so the slide text is sourced from disk, not hand-typed.
2. `script.md` — full speaker notes, written first, single source of truth for slide copy.
3. `build_pptx.py` — self-contained PPTX builder. One helper per layout primitive (title, metric-tile row, image with callouts, side-by-side table, two-card row), one function per slide, all consume `metrics.json` and `script.md`-derived constants. No imports from `docs/final_presentation/`.

**Tech Stack:** Python 3, `python-pptx` 1.0.2 (already installed), `Pillow` (for callout overlays — already an indirect dep via pptx), Streamlit (for the dashboard screenshot capture), the macOS `screencapture` CLI for the new screenshot, `git` for the commit cadence.

---

## File structure

```
docs/results_presentation/
├── compute_metrics.py          # reads mas_results dirs + mcnemar.json → metrics.json
├── metrics.json                # generated; the only source of numbers used by the builder
├── script.md                   # full speaker notes (~1000 words)
├── build_pptx.py               # PPTX builder, one function per slide
├── verify_pptx.py              # opens the PPTX, asserts 9 slides + expected text strings
├── dashboard_treatment.png     # NEW screenshot — treatment + reviewer panels
└── CMADS_Results_Presentation.pptx   # OUTPUT
```

Reused (read-only) from elsewhere in the repo:

- `thesis/images/ch3_system_architecture.png` (slide 2)
- `thesis/images/ch3_multilevel_memory.png` (slide 2 inset)
- `docs/final_presentation/doctor_console.png` (slide 6)
- `thesis/bachelor.bib` (slide 8 source-of-truth for paper titles + years)
- `data/gold/mas_results_improved_b3/`, `mas_results_improved_50/` (slides 3, 4)
- `data/gold/paired_memory_mcnemar.json` (slide 5)
- `data/gold/batches/batch_3.json`, `batch_4.json` (slides 3, 4)

---

### Task 1: Scaffold the folder and write the metrics extractor (TDD)

Build the data layer first so every later slide can pull from `metrics.json` instead of hand-typing numbers — this is the "every number traces back to a file" rule.

**Files:**
- Create: `docs/results_presentation/compute_metrics.py`
- Create: `docs/results_presentation/test_compute_metrics.py`

- [ ] **Step 1: Create the folder**

```bash
mkdir -p /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
```

- [ ] **Step 2: Write the failing test**

Create `docs/results_presentation/test_compute_metrics.py`:

```python
"""Tests for compute_metrics — the deck's source of numbers.

We anchor on the numbers from notes/experiments.md so a future cohort
recompute that drifts will fail loudly here before the deck is rebuilt.
"""

from __future__ import annotations

from pathlib import Path

from compute_metrics import compute

REPO = Path(__file__).resolve().parents[2]


def test_combined_100_patient_numbers():
    m = compute(REPO)

    cold = m["cohorts"]["batch_3_cold_start"]
    assert cold["n"] == 50
    assert cold["DIRECT"] == 23
    assert cold["INDIRECT"] == 23
    assert cold["MISS"] == 4
    assert cold["found"] == 46
    assert cold["DIRECT_pct"] == 46.0
    assert cold["found_pct"] == 92.0

    warm = m["cohorts"]["batch_4_warmed"]
    assert warm["n"] == 50
    assert warm["DIRECT"] == 26
    assert warm["found"] == 49
    assert warm["DIRECT_pct"] == 52.0
    assert warm["found_pct"] == 98.0

    combined = m["cohorts"]["combined_100"]
    assert combined["n"] == 100
    assert combined["DIRECT"] == 49
    assert combined["INDIRECT"] == 46
    assert combined["MISS"] == 5
    assert combined["DIRECT_pct"] == 49.0
    assert combined["found_pct"] == 95.0


def test_paired_mcnemar_block():
    m = compute(REPO)
    p = m["paired_mcnemar"]
    assert p["n_paired"] == 20
    assert p["off_direct_rate"] == 0.40
    assert p["on_direct_rate"] == 0.45
    cont = p["contingency"]
    assert cont["both_DIRECT"] == 6
    assert cont["only_OFF_DIRECT"] == 2
    assert cont["only_ON_DIRECT"] == 3
    assert cont["neither_DIRECT"] == 9
    assert p["mcnemar_p_two_sided"] == 1.0


def test_rank1_in_found_per_cohort():
    """Rank-1-in-found is computed per cohort. We do NOT combine across
    cohorts — the spec's risk section says split the cell if the inputs
    disagree by more than 2 pp, which they do (37 % vs 27 %)."""

    m = compute(REPO)
    cold = m["cohorts"]["batch_3_cold_start"]
    warm = m["cohorts"]["batch_4_warmed"]

    assert 35 <= cold["rank1_in_found_pct"] <= 39, cold["rank1_in_found_pct"]
    assert 25 <= warm["rank1_in_found_pct"] <= 29, warm["rank1_in_found_pct"]
```

- [ ] **Step 3: Run the test, confirm it fails on missing module**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 -m pytest test_compute_metrics.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'compute_metrics'`

- [ ] **Step 4: Implement `compute_metrics.py`**

Create `docs/results_presentation/compute_metrics.py`:

```python
"""Read patient-level evaluations + the paired McNemar JSON and emit
one `metrics.json` that the deck builder consumes. Every number on
slides 3–5 must trace back to one of these on-disk artefacts.

Usage:
    python3 compute_metrics.py            # writes metrics.json next to this file
    python3 -c 'from compute_metrics import compute; print(compute())'
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_DEFAULT = HERE.parents[1]


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _aggregate(results_dir: Path, uuids: list[str]) -> dict:
    out = {
        "n": 0, "DIRECT": 0, "INDIRECT": 0, "MISS": 0,
        "found": 0, "rank1_in_found": 0,
        "duration_total_s": 0.0, "missing": 0,
    }
    for u in uuids:
        ev = _load(results_dir / u / "evaluation.json")
        tr = _load(results_dir / u / "execution_trace.json")
        if not ev or "match_type" not in ev:
            out["missing"] += 1
            continue
        out["n"] += 1
        mt = ev["match_type"]
        if mt in out:
            out[mt] += 1
        if mt in ("DIRECT", "INDIRECT"):
            out["found"] += 1
            if ev.get("rank") == 1:
                out["rank1_in_found"] += 1
        if tr and isinstance(tr.get("duration_s"), (int, float)):
            out["duration_total_s"] += tr["duration_s"]
    return out


def _decorate(agg: dict) -> dict:
    n = max(agg["n"], 1)
    found = max(agg["found"], 1)
    agg["DIRECT_pct"] = round(100 * agg["DIRECT"] / n, 1)
    agg["INDIRECT_pct"] = round(100 * agg["INDIRECT"] / n, 1)
    agg["MISS_pct"] = round(100 * agg["MISS"] / n, 1)
    agg["found_pct"] = round(100 * agg["found"] / n, 1)
    agg["rank1_in_found_pct"] = round(100 * agg["rank1_in_found"] / found, 1)
    agg["avg_duration_s"] = round(agg["duration_total_s"] / n, 1) if agg["n"] else 0.0
    return agg


def compute(repo: Path | None = None) -> dict:
    repo = Path(repo) if repo else REPO_DEFAULT

    batches = repo / "data" / "gold" / "batches"
    results = repo / "data" / "gold"

    b3 = json.loads((batches / "batch_3.json").read_text())
    b4 = json.loads((batches / "batch_4.json").read_text())

    cold = _decorate(_aggregate(results / "mas_results_improved_b3", b3))
    warm = _decorate(_aggregate(results / "mas_results_improved_50", b4))

    # "Combined 100" sums the raw counts and re-decorates over N=100,
    # so DIRECT_pct and found_pct are recomputed honestly across the union.
    combined_raw = {
        "n": cold["n"] + warm["n"],
        "DIRECT": cold["DIRECT"] + warm["DIRECT"],
        "INDIRECT": cold["INDIRECT"] + warm["INDIRECT"],
        "MISS": cold["MISS"] + warm["MISS"],
        "found": cold["found"] + warm["found"],
        "rank1_in_found": cold["rank1_in_found"] + warm["rank1_in_found"],
        "duration_total_s": cold["duration_total_s"] + warm["duration_total_s"],
        "missing": cold["missing"] + warm["missing"],
    }
    combined = _decorate(combined_raw)

    mc = _load(results / "paired_memory_mcnemar.json") or {}

    paired = {
        "n_paired": mc.get("n_paired"),
        "off_direct_rate": mc.get("off_direct_rate"),
        "on_direct_rate": mc.get("on_direct_rate"),
        "contingency": mc.get("contingency_2x2", {}),
        "mcnemar_p_two_sided": (mc.get("mcnemar_exact") or {}).get("p_value_two_sided"),
    }

    return {
        "cohorts": {
            "batch_3_cold_start": cold,
            "batch_4_warmed": warm,
            "combined_100": combined,
        },
        "paired_mcnemar": paired,
        "sources": {
            "cold_start_dir": "data/gold/mas_results_improved_b3",
            "warmed_dir": "data/gold/mas_results_improved_50",
            "paired_json": "data/gold/paired_memory_mcnemar.json",
            "batches": ["data/gold/batches/batch_3.json", "data/gold/batches/batch_4.json"],
        },
    }


def main():
    m = compute()
    out = HERE / "metrics.json"
    out.write_text(json.dumps(m, indent=2))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the test, confirm it passes**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 -m pytest test_compute_metrics.py -v
```
Expected: 3 passing tests. If any test fails on rank-1 bounds, **STOP and report the actual numbers** — the spec's risk section says the combined rank-1 may diverge from the 2026-05-10 / 2026-05-11 experiment-log claims; if so, adjust the spec, not the code.

- [ ] **Step 6: Generate metrics.json**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 compute_metrics.py
```
Expected output: `wrote .../metrics.json`. Inspect it to confirm the 3 cohorts + paired_mcnemar blocks are present.

- [ ] **Step 7: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/compute_metrics.py docs/results_presentation/test_compute_metrics.py docs/results_presentation/metrics.json
git commit -m "$(cat <<'EOF'
results-deck: metrics extractor for the 100-patient cohorts

Reads mas_results_improved_b3 (cold-start), mas_results_improved_50
(warmed), and paired_memory_mcnemar.json into one metrics.json. Test
anchors the numbers to the notes/experiments.md headline so cohort
drift fails loudly.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 2: Write the speaker script (`script.md`)

The script is the single source of slide copy. Build the deck after this is settled so the PPTX builder consumes stable text.

**Files:**
- Create: `docs/results_presentation/script.md`

- [ ] **Step 1: Read the numbers**

```bash
cat /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation/metrics.json
```

- [ ] **Step 2: Write `script.md`**

Create the file with the structure below. Use the numbers from `metrics.json`, not from memory. **Every slide section** must end with a `**Speaker notes:**` block. Keep total spoken words under 1100 (≈8 min at 135 wpm).

```markdown
# CMADS — Results & Comparison · 9-slide deck script

> ≈ 1000 spoken words at 135 wpm · ~7:30 walk-through
> Numbers below are pulled from `metrics.json`. If you regenerate that
> file, regenerate the deck.

## Slide 1 — Title  *[≈ 20 s]*

### CMADS — Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows

**100-patient multi-level memory results · doctor console · literature comparison**

Abdelrahman Mohamed Amin · Supervisor: Dr. Shereen Moataz Afifi · GUC · May 2026

**Speaker notes:**
> Three parts in about seven minutes. The 100-patient memory results,
> the doctor console, and how this work sits against the most relevant
> multi-agent clinical AI papers.

---

## Slide 2 — What CMADS is  *[≈ 40 s]*

*One diagram: 7-agent pipeline plus the 4-tier memory subsystem.*

**Speaker notes:**
> Seven specialised agents coordinated by LangGraph. EHR Analyst and
> Lab Interpreter run in parallel, then Diagnostic Reasoning's
> three-round critique loop, then a non-destructive Reviewer and
> Refiner, then evaluation, then NICE-guideline treatment planning
> on confirmed matches. Memory is a four-tier subsystem on the side —
> working scratchpad, episodic timeline, semantic per-disease stats,
> and a case-based vector store of past patients.

---

## Slide 3 — 100-patient multi-level memory · headline  *[≈ 75 s]*

(Number block — pulled live from metrics.json at build time.)

| Cohort | N | DIRECT | INDIRECT | MISS | Found | Rank-1 in found | Time/patient |
|---|---:|---:|---:|---:|---:|---:|---:|
| batch_3 (cold-start) | 50 | 46 % | 46 % | 8 % | 92 % | 37 % | ~113 s |
| batch_4 (warmed)     | 50 | 52 % | 46 % | 2 % | 98 % | 27 % | ~112 s |
| **Combined**         | **100** | **49 %** | **46 %** | **5 %** | **95 %** | (split — see slide 4) | ~113 s |

**Speaker notes:**
> Combined across the two 50-patient runs: forty-nine percent DIRECT,
> ninety-five percent Found, five percent MISS. The MISS rate is the
> number to focus on — only five patients out of a hundred where the
> top-five differential contained no match at all. The headline that
> changes with memory is Found rate, not top-1 DIRECT.

---

## Slide 4 — Split by regime  *[≈ 60 s]*

*Two cards: Cold-start (batch_3) and Warmed (batch_4). Bottom strip
states the leakage delta.*

Cold-start (batch_3): 46 % DIRECT · 92 % Found · 37 % rank-1-in-found
Warmed (batch_4):    52 % DIRECT · 98 % Found · 27 % rank-1-in-found

**Cohort-leakage estimate (per notes/experiments.md 2026-05-11):
≈ 6 pp DIRECT and 6 pp Found come from same-cohort priors, not the
algorithm.**

**Speaker notes:**
> The two fifty-patient runs differ in one key way: batch_4 was run
> against a Qdrant store that already contained batch_4 patients from
> an earlier pass. Batch_3 was held out — zero same-cohort priors at
> run start. The six-point DIRECT gap and the six-point Found gap are
> the cohort-leakage estimate. Memory genuinely helps, but the batch_4
> headline overstates it.

---

## Slide 5 — Paired McNemar A/B (n=20)  *[≈ 50 s]*

*2×2 contingency square + DIRECT-rate strip.*

|                  | ON DIRECT | ON not-DIRECT |
|---|:-:|:-:|
| OFF DIRECT       | 6         | 2             |
| OFF not-DIRECT   | 3         | 9             |

DIRECT: 40 % (8/20) → 45 % (9/20)
Exact McNemar p = 1.0

**Speaker notes:**
> This is the only controlled test in the project — same twenty
> patients, memory toggled. Discordant pairs are five, two against
> memory, three for. Exact McNemar gives p equals one. The point
> estimate favours memory by five percentage points, but the sample
> size cannot confirm or refute. A bigger paired cohort is the
> obvious next step.

---

## Slide 6 — Doctor dashboard · features overview  *[≈ 60 s]*

*Annotated screenshot of doctor_console.png with four numbered
callouts.*

1. Agent workflow inline — every stage's output one click away.
2. Similar past cases — top-K Tier-4 neighbours with their evaluator
   match type.
3. Treatment safety panel — drugs, interactions, contraindications,
   plus the planner's assumptions & missing-data warnings.
4. Reviewer note — three-way verdict, free text, initials. Persisted
   to data/gold/annotations/<uuid>.json.

**Speaker notes:**
> The console is what turns a JSON output into something a doctor can
> review. Four features matter. Every agent's output is one click
> away. Similar past cases are surfaced. The treatment panel exposes
> what the planner did not know. And the reviewer can record a
> verdict that persists — that's the only write surface in the UI.

---

## Slide 7 — Dashboard · treatment safety + reviewer flow  *[≈ 55 s]*

*Second screenshot: treatment-review panel + reviewer-note panel.*

- Surfaces what the planner did NOT know — assumptions about eGFR,
  weight, missing comorbidities — directly in the UI.
- Reviewer verdict persisted to data/gold/annotations/<uuid>.json with
  initials + free text.

**Speaker notes:**
> The treatment planner is gated on DIRECT matches only. When it does
> run, it exposes the assumptions it made — that's the small text
> under each recommendation. The reviewer can then disagree, agree
> with caveats, or accept. That verdict is the only persisted human
> judgement in the system; it is what would feed a future
> clinician-agreement metric.

---

## Slide 8 — Literature comparison · their results vs CMADS  *[≈ 75 s]*

| Paper | Cohort | Their reported headline | CMADS comparable | A/A |
|---|---|---|---|:-:|
| MDAgents (Kim 2024) | 10 MCQ benchmarks | (qualitative) Best on 7/10 | 49 % DIRECT on real EHR cases | ✗ |
| ZODIAC (Zhou 2024)  | Cardiology, 8 metrics | (qualitative) Cardiologist-level on 7/8 | 49 % DIRECT, 95 % Found across 8 families | ◐ |
| ClinicalLab (Yan 2024) | 1,500 real cases, 11 depts | (qualitative) Within 5 % of senior physicians | 100 EHR-shaped cases, 8 families | ◐ |
| MAC Framework (2025) | 302 rare-disease cases | (qualitative) Outperforms self-consistency | Common chronic disease cohort | ✗ |
| RareAgents (Chen 2024) | RareBench + MIMIC-Ext-Rare | (qualitative) Open backbone beats GPT-4o | DIRECT/INDIRECT/MISS, not Hit@K | ✗ |

A/A legend: ✓ same metric/cohort family · ◐ related but different · ✗ different metric.

> Numbers marked *(qualitative)* are the strongest claim we can verify
> from the bib entry / abstract. If we obtain a citable headline number
> from the paper PDF before submission, replace the qualitative phrase
> and keep the row.

**Speaker notes:**
> Apples-to-apples is rare here. Most prior systems evaluate on
> multiple-choice benchmarks or single specialties, not on end-to-end
> EHR records across eight disease families. So the table is not
> "CMADS beats them" — it's "here is what each paper reports, here
> is what CMADS reports, here is whether they can even be compared."
> The composition is the contribution, not any one number.

---

## Slide 9 — Gaps I filled  *[≈ 55 s]*

Four quadrants:

1. **End-to-end pipeline** (Synthea → differential → NICE plan → doctor
   review) — vs MDAgents, ClinicalLab (benchmark accuracy only).
2. **Open-source reasoning backbone** (GPT-OSS-120B + Qwen3-32B judge)
   — vs MDAgents, ClinicalLab, ZODIAC (GPT-4 family).
3. **Inspectable 4-tier memory with a controlled A/B** — vs all five
   (memory implicit or absent in their public descriptions).
4. **Doctor-facing console with persisted clinician verdicts** — vs all
   five (none ship a clinician annotation surface).

> The composition is the contribution.

**Speaker notes:**
> Each individual gap is small. Each individual paper closes a couple
> of them. Nobody closes all four in one system. That is the
> contribution this thesis defends.
```

- [ ] **Step 3: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/script.md
git commit -m "$(cat <<'EOF'
results-deck: speaker script (9 slides, ~7:30)

Numbers pulled from metrics.json. Slide 8 marks all competitor
headlines (qualitative) per the spec's verifiability rule; if a
citable number is sourced from the paper PDF later, replace in place.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 3: Capture the second dashboard screenshot (treatment + reviewer)

This needs to happen before slide 7 so the builder has an image to embed.

**Files:**
- Create: `docs/results_presentation/dashboard_treatment.png`

- [ ] **Step 1: Find a patient with a treatment plan**

A treatment plan only exists on DIRECT matches. Pick one from the warmed cohort:

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
python3 - <<'EOF'
import json
from pathlib import Path
d = Path("data/gold/mas_results_improved_50")
for p in sorted(d.iterdir())[:200]:
    ev = p / "evaluation.json"
    tp = p / "treatment_planning.json"
    if not ev.exists() or not tp.exists():
        continue
    e = json.loads(ev.read_text())
    if e.get("match_type") == "DIRECT":
        print(p.name)
        break
EOF
```
Record the UUID printed.

- [ ] **Step 2: Start the dashboard in the background**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
streamlit run portal/dashboard.py --server.headless true --server.port 8503 &
echo $! > /tmp/cmads_streamlit.pid
sleep 5
```

- [ ] **Step 3: Capture the screenshot**

Open `http://localhost:8503/?r=mas_results_improved_50&p=<UUID>&a=treatment_planning` in Chrome, expand the Reviewer Note panel underneath, then capture via the `mcp__computer-use__screenshot` tool (call `request_access` for Google Chrome first). Save it to `docs/results_presentation/dashboard_treatment.png`.

Fallback if computer-use access is denied: use the macOS `screencapture -R<x,y,w,h>` CLI manually, or use the `headless` Chrome trick already used by `build_final_pptx.py:ensure_png` to render the URL to PNG (`Chrome --headless --screenshot=... --window-size=1600,900 <url>`).

- [ ] **Step 4: Stop the dashboard**

```bash
kill "$(cat /tmp/cmads_streamlit.pid)" && rm /tmp/cmads_streamlit.pid
```

- [ ] **Step 5: Sanity-check the file**

```bash
file /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation/dashboard_treatment.png
```
Expected: `PNG image data, ... 8-bit/color RGBA, non-interlaced`.

- [ ] **Step 6: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/dashboard_treatment.png
git commit -m "results-deck: capture treatment + reviewer dashboard screenshot"
```

If capture fails entirely (no MCP access, no Chrome headless), **skip this task and continue** — the slide-7 task documents the fallback (schema-based bullets without the second image) and will work without it.

---

### Task 4: Build skeleton + helpers in `build_pptx.py`

Lay down the file with all layout primitives and a `main()` that wires nine slide functions. Each slide function will be filled in by Tasks 5–13.

**Files:**
- Create: `docs/results_presentation/build_pptx.py`

- [ ] **Step 1: Write the skeleton**

Create `docs/results_presentation/build_pptx.py`:

```python
"""Build the CMADS Results & Comparison deck.

9 slides. Numbers come from compute_metrics.compute(). No imports
from docs/final_presentation/. Run:

    python3 docs/results_presentation/build_pptx.py
"""

from __future__ import annotations

import json
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


def add_callout(slide, number: int, label: str, left, top, *, color=AMBER):
    """A numbered circle with a one-line label, used over images."""
    dia = 0.42
    circle = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                     Inches(left), Inches(top), Inches(dia), Inches(dia))
    circle.fill.solid(); circle.fill.fore_color.rgb = color
    circle.line.color.rgb = WHITE; circle.line.width = Pt(1.5)
    tf = circle.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = str(number)
    r.font.size = Pt(13); r.font.bold = True; r.font.color.rgb = WHITE
    add_textbox(slide, left + dia + 0.05, top + 0.04, 4.5, 0.4, label,
                size=11, bold=True, color=GREY_DARK)


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
```

- [ ] **Step 2: Sanity-run the skeleton**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 build_pptx.py
```
Expected: `wrote .../CMADS_Results_Presentation.pptx (0 slides)`. Zero slides is correct — the slide_*() functions are empty stubs.

- [ ] **Step 3: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: build_pptx skeleton + layout primitives"
```

---

### Task 5: Slide 1 — Title

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace the `slide_title` stub)

- [ ] **Step 1: Implement `slide_title`**

Replace the `def slide_title(prs, metrics): pass` line with:

```python
def slide_title(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])  # blank
    add_bg(slide, PAPER)

    # Accent band along the top
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
```

- [ ] **Step 2: Rebuild and confirm**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 build_pptx.py
```
Expected: `wrote ... (1 slides)`.

- [ ] **Step 3: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 1 (title)"
```

---

### Task 6: Slide 2 — What CMADS is

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_what_is_cmads`)

- [ ] **Step 1: Confirm diagram exists**

```bash
ls -la /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/thesis/images/ch3_system_architecture.png /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/thesis/images/ch3_multilevel_memory.png
```
Both files should exist.

- [ ] **Step 2: Implement `slide_what_is_cmads`**

```python
def slide_what_is_cmads(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "What CMADS is",
               "7-agent LangGraph pipeline + 4-tier memory subsystem")

    sysarch = TH_IMG / "ch3_system_architecture.png"
    memdiag = TH_IMG / "ch3_multilevel_memory.png"

    # Main diagram on the left
    if sysarch.exists():
        add_image(slide, sysarch, 0.4, 1.2, width=8.5)
    else:
        add_textbox(slide, 0.5, 1.5, 8.0, 1.0,
                    "[diagram missing: ch3_system_architecture.png]",
                    size=12, color=RED)

    # Memory inset on the right
    if memdiag.exists():
        add_image(slide, memdiag, 9.2, 1.4, width=3.8)
    add_textbox(slide, 9.2, 5.8, 3.8, 0.4,
                "Multi-level memory (inset)",
                size=11, bold=True, color=GREY_MED, align=PP_ALIGN.CENTER)

    add_textbox(slide, 0.4, 6.8, 12.5, 0.5,
                "Stage 1 (parallel) → Diagnostic loop → Reviewer → Refiner → Evaluator → Treatment (DIRECT only) → Memory consolidation",
                size=11, color=GREY_MED, align=PP_ALIGN.CENTER)
```

- [ ] **Step 3: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 2 (system architecture)"
```

---

### Task 7: Slide 3 — 100-patient headline

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_headline`)

- [ ] **Step 1: Implement `slide_headline`**

```python
def slide_headline(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "100-patient multi-level memory result",
               "Combined batch_3 (cold-start, 50) + batch_4 (warmed, 50)")

    c = metrics["cohorts"]["combined_100"]
    cold = metrics["cohorts"]["batch_3_cold_start"]
    warm = metrics["cohorts"]["batch_4_warmed"]

    # Four metric tiles
    tile_w = 2.9
    tile_h = 1.6
    gap = 0.2
    left0 = 0.6
    top0 = 1.25
    tiles = [
        (f"{c['DIRECT_pct']:.1f}%",         "DIRECT (n=100)",          NAVY),
        (f"{c['found_pct']:.1f}%",          "Found (DIRECT + INDIRECT)", GREEN),
        (f"{c['MISS_pct']:.1f}%",           "MISS",                    AMBER),
        (f"~{c['avg_duration_s']:.0f} s",   "Avg time / patient",      TEAL),
    ]
    for i, (v, l, col) in enumerate(tiles):
        add_metric_tile(slide, left0 + i * (tile_w + gap), top0, tile_w, tile_h,
                        v, l, value_color=col)

    # Per-cohort table
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
         "see slide 4", f"~{c['avg_duration_s']:.0f}s"],
    ]
    add_table(slide, 0.6, 3.2, 12.1, 2.7, headers, rows)

    add_textbox(slide, 0.6, 6.4, 12.1, 0.8,
                "Numbers pulled from data/gold/mas_results_improved_b3/ and "
                "data/gold/mas_results_improved_50/ via compute_metrics.py.",
                size=11, color=GREY_MED)
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 3 (100-patient headline)"
```

---

### Task 8: Slide 4 — Split by regime

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_regime_split`)

- [ ] **Step 1: Implement `slide_regime_split`**

```python
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
        # Card frame
        box = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                      Inches(left), Inches(1.3),
                                      Inches(5.8), Inches(4.3))
        box.fill.solid(); box.fill.fore_color.rgb = WHITE
        box.line.color.rgb = accent; box.line.width = Pt(1.5)
        add_textbox(slide, left + 0.2, 1.45, 5.5, 0.5, title,
                    size=16, bold=True, color=accent)
        add_textbox(slide, left + 0.2, 1.95, 5.5, 0.5, sub,
                    size=11, color=GREY_MED)
        # Three sub-metrics, stacked
        lines = [
            ("DIRECT",         f"{agg['DIRECT_pct']:.0f}%   ({agg['DIRECT']}/{agg['n']})"),
            ("Found",          f"{agg['found_pct']:.0f}%   ({agg['found']}/{agg['n']})"),
            ("Rank-1 in found",f"{agg['rank1_in_found_pct']:.0f}%   ({agg['rank1_in_found']}/{agg['found']})"),
        ]
        for j, (k, v) in enumerate(lines):
            top = 2.7 + j * 0.85
            add_textbox(slide, left + 0.3, top,       2.2, 0.5, k,
                        size=13, bold=True, color=GREY_DARK)
            add_textbox(slide, left + 2.6, top,       3.1, 0.5, v,
                        size=18, bold=True, color=accent)

    # Leakage strip
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
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 4 (cold-start vs warmed regime split)"
```

---

### Task 9: Slide 5 — Paired McNemar A/B

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_paired_mcnemar`)

- [ ] **Step 1: Implement `slide_paired_mcnemar`**

```python
def slide_paired_mcnemar(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Paired McNemar A/B (n = 20)",
               "Same 20 patients, memory toggled · the only controlled test in the project")

    p = metrics["paired_mcnemar"]
    c = p["contingency"]

    # 2x2 table on the left
    headers = ["", "ON · DIRECT", "ON · not-DIRECT"]
    rows = [
        ["OFF · DIRECT",      c["both_DIRECT"],     c["only_OFF_DIRECT"]],
        ["OFF · not-DIRECT",  c["only_ON_DIRECT"],  c["neither_DIRECT"]],
    ]
    add_table(slide, 0.7, 1.6, 6.5, 2.9, headers, rows)

    # Stats panel on the right
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

    # Interpretation strip
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
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 5 (paired McNemar A/B)"
```

---

### Task 10: Slide 6 — Dashboard features overview

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_dashboard_overview`)

- [ ] **Step 1: Implement `slide_dashboard_overview`**

```python
def slide_dashboard_overview(prs, metrics):
    slide = prs.slides.add_slide(prs.slide_layouts[6])
    add_bg(slide)
    add_header(slide, "Doctor dashboard — features overview",
               "Four features that make the run reviewable")

    console = REPO / "docs" / "final_presentation" / "doctor_console.png"
    if console.exists():
        # Left half: the screenshot
        add_image(slide, console, 0.4, 1.2, width=8.0)
    else:
        add_textbox(slide, 0.5, 1.5, 8.0, 1.0,
                    "[screenshot missing: docs/final_presentation/doctor_console.png]",
                    size=12, color=RED)

    # Right half: numbered callouts (these are the slide content; the
    # screenshot's job is to show where they live).
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
        # Numbered circle
        dia = 0.45
        circle = slide.shapes.add_shape(MSO_SHAPE.OVAL,
                                         Inches(left), Inches(top),
                                         Inches(dia), Inches(dia))
        circle.fill.solid(); circle.fill.fore_color.rgb = AMBER
        circle.line.color.rgb = WHITE; circle.line.width = Pt(1.5)
        tf = circle.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
        r = p.add_run(); r.text = str(i)
        r.font.size = Pt(14); r.font.bold = True; r.font.color.rgb = WHITE
        # Heading + body
        add_textbox(slide, left + dia + 0.1, top - 0.05, 4.2, 0.45,
                    head, size=12, bold=True, color=NAVY)
        add_textbox(slide, left + dia + 0.1, top + 0.35, 4.2, 0.85,
                    body, size=10, color=GREY_DARK)

    add_textbox(slide, 0.4, 6.85, 12.5, 0.4,
                "URL-driven state: ?r=<set>&p=<uuid>&a=<agent> makes every view shareable and refresh-safe.",
                size=10, color=GREY_MED, align=PP_ALIGN.CENTER)
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 6 (dashboard features overview)"
```

---

### Task 11: Slide 7 — Dashboard treatment + reviewer flow

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_dashboard_treatment`)

- [ ] **Step 1: Implement `slide_dashboard_treatment` (with screenshot fallback)**

```python
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
        add_textbox(slide, 0.4, 3.0, 8.5, 0.6,
                    "[treatment screenshot unavailable — see Task 3 fallback]",
                    size=12, color=RED)
        text_left = 0.4
        text_width = 12.5

    add_textbox(slide, text_left, 1.3, text_width, 0.5,
                "Surfaces what the planner did NOT know",
                size=14, bold=True, color=NAVY)
    add_textbox(slide, text_left, 1.8, text_width, 1.5,
                "• Drug dose assumptions (e.g. 'eGFR unknown — assumed normal "
                "for ACE-I dosing').\n"
                "• Missing-comorbidity warnings.\n"
                "• Interaction checks against current medication list.",
                size=11, color=GREY_DARK)
    add_textbox(slide, text_left, 3.6, text_width, 0.5,
                "Reviewer verdict persistence",
                size=14, bold=True, color=NAVY)
    add_textbox(slide, text_left, 4.1, text_width, 1.8,
                "• Three-way verdict (agree / uncertain / disagree).\n"
                "• Free text + reviewer initials.\n"
                "• Written to data/gold/annotations/<uuid>.json — the only "
                "write surface in the UI.\n"
                "• Unlocks clinician-agreement metrics beyond LLM-judge.",
                size=11, color=GREY_DARK)
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 7 (treatment + reviewer flow)"
```

---

### Task 12: Slide 8 — Literature comparison

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_literature`)

- [ ] **Step 1: Implement `slide_literature`**

```python
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
        ["MDAgents (Kim 2024)",        "10 MCQ benchmarks",
         "(qualitative) Best on 7/10",
         cmads_headline, "✗"],
        ["ZODIAC (Zhou 2024)",          "Cardiology, 8 metrics",
         "(qualitative) Cardiologist-level on 7/8",
         cmads_headline, "◐"],
        ["ClinicalLab (Yan 2024)",      "1,500 real cases, 11 depts",
         "(qualitative) Within ~5% of senior physicians",
         cmads_headline, "◐"],
        ["MAC Framework (2025)",        "302 rare-disease cases",
         "(qualitative) Outperforms self-consistency",
         "Common chronic disease cohort", "✗"],
        ["RareAgents (Chen 2024)",      "RareBench + MIMIC-Ext-Rare",
         "(qualitative) Open backbone beats GPT-4o",
         "DIRECT/INDIRECT/MISS, not Hit@K", "✗"],
    ]
    add_table(slide, 0.4, 1.2, 12.5, 4.6, headers, rows, first_col_bold=True)

    add_textbox(slide, 0.4, 6.0, 12.5, 1.1,
                "Apples-to-apples is rare in this literature: most evaluate on "
                "MCQ benchmarks or a single specialty, not end-to-end EHR "
                "records across 8 families. Numbers marked (qualitative) are "
                "the strongest claim verifiable from the bib entry / abstract.",
                size=11, color=GREY_MED)
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 8 (literature comparison)"
```

---

### Task 13: Slide 9 — Gaps I filled

**Files:**
- Modify: `docs/results_presentation/build_pptx.py` (replace `slide_gaps`)

- [ ] **Step 1: Implement `slide_gaps`**

```python
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
```

- [ ] **Step 2: Rebuild + commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation && python3 build_pptx.py
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/build_pptx.py
git commit -m "results-deck: slide 9 (gaps I filled)"
```

---

### Task 14: Verification script + final check

**Files:**
- Create: `docs/results_presentation/verify_pptx.py`

- [ ] **Step 1: Write the verifier**

Create `docs/results_presentation/verify_pptx.py`:

```python
"""Open the PPTX and confirm: 9 slides, expected text present, expected
images embedded. Run after build_pptx.py finishes."""

from __future__ import annotations

import sys
from pathlib import Path

from pptx import Presentation

HERE = Path(__file__).resolve().parent
PPTX = HERE / "CMADS_Results_Presentation.pptx"


REQUIRED_PHRASES = [
    # Slide 1
    "CMADS — Multi-Agent Systems for AI Clinical Decisioning",
    # Slide 2
    "What CMADS is",
    # Slide 3
    "100-patient multi-level memory",
    # Slide 4
    "Split by regime",
    "Cohort-leakage estimate",
    # Slide 5
    "Paired McNemar",
    "Exact McNemar",
    # Slide 6
    "Doctor dashboard — features overview",
    # Slide 7
    "Treatment safety + reviewer flow",
    # Slide 8
    "Literature comparison — their results vs CMADS",
    # Slide 9
    "Gaps I filled",
    "The composition is the contribution.",
]


def _all_text(slide) -> str:
    chunks = []
    for shape in slide.shapes:
        if shape.has_text_frame:
            chunks.append(shape.text_frame.text)
        if shape.has_table:
            for row in shape.table.rows:
                for cell in row.cells:
                    chunks.append(cell.text_frame.text)
    return "\n".join(chunks)


def main() -> int:
    if not PPTX.exists():
        print(f"FAIL: {PPTX} does not exist"); return 1

    prs = Presentation(str(PPTX))
    print(f"slides: {len(prs.slides)}")
    if len(prs.slides) != 9:
        print(f"FAIL: expected 9 slides, got {len(prs.slides)}"); return 1

    full_text = "\n\n---SLIDE BREAK---\n\n".join(
        _all_text(s) for s in prs.slides
    )
    missing = [p for p in REQUIRED_PHRASES if p not in full_text]
    if missing:
        print("FAIL: missing required phrases:")
        for m in missing: print(f"  - {m}")
        return 1

    # Image count (lower bound — depends on which screenshots were captured)
    img_count = sum(1 for s in prs.slides for sh in s.shapes if sh.shape_type == 13)
    print(f"images embedded: {img_count}")
    if img_count < 2:
        print(f"WARN: only {img_count} image(s) — expected at least 2 "
              "(system diagram + doctor console). Continuing.")

    print("OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run the verifier**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation
python3 verify_pptx.py
```
Expected: prints `slides: 9`, image count ≥ 2, ends with `OK`. If any required phrase is missing, the verifier fails — open the offending slide function and add the missing phrase.

- [ ] **Step 3: Open the deck visually**

```bash
open /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/docs/results_presentation/CMADS_Results_Presentation.pptx
```

Walk through all 9 slides. If anything is visually off (overflow, misaligned shapes, wrong colours), fix the corresponding `slide_*` function — do **not** edit the PPTX by hand, since `build_pptx.py` will overwrite it.

- [ ] **Step 4: Commit the verifier and the final PPTX**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add docs/results_presentation/verify_pptx.py docs/results_presentation/CMADS_Results_Presentation.pptx
git commit -m "$(cat <<'EOF'
results-deck: verifier + final pptx

verify_pptx.py opens the deck, asserts 9 slides + required text +
image count. Committing the .pptx as well so a reviewer who can't
run python-pptx can still open it.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
EOF
)"
```

---

### Task 15: Log the experiment + decision notes

Per project convention (`notes/CLAUDE.md`), non-trivial new artefacts get one line each.

**Files:**
- Modify: `notes/decisions.md`
- Modify: `notes/experiments.md`

- [ ] **Step 1: Append to `notes/decisions.md`**

Append one bullet at the end:

```markdown
- 2026-05-19 — Built a separate `docs/results_presentation/` deck (not extending `docs/final_presentation/`). **Why:** supervisor asked for a fresh 9-slide deck centred on the 100-patient memory result, the doctor dashboard, and a literature comparison. **How to apply:** future memory experiments at N=100+ can plug into `compute_metrics.py` rather than re-typing numbers into slides. Refs: `docs/superpowers/specs/2026-05-19-results-presentation-design.md`, `docs/superpowers/plans/2026-05-19-results-presentation.md`.
```

- [ ] **Step 2: Append to `notes/experiments.md`**

Append one bullet:

```markdown
- 2026-05-19 — **100-patient multi-level memory aggregate (no new run)** — combined `mas_results_improved_b3` (50, cold-start) + `mas_results_improved_50` (50, warmed). Numbers pulled by `docs/results_presentation/compute_metrics.py`: 49% DIRECT, 46% INDIRECT, 5% MISS, 95% Found; ~113 s/patient. Cold-start vs warmed: 46/92 vs 52/98 — ~6 pp DIRECT and ~6 pp Found of the warmed gain is cohort leakage. Refs: [`compute_metrics.py`](../docs/results_presentation/compute_metrics.py), [`metrics.json`](../docs/results_presentation/metrics.json). #experiment #thesis
```

- [ ] **Step 3: Commit**

```bash
cd /Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project
git add notes/decisions.md notes/experiments.md
git commit -m "notes: results deck + 100-patient memory aggregate"
```

---

## Self-review checklist (executed)

- **Spec coverage:** every slide in the spec maps to a task (Task 5–13 each = one slide; Tasks 1–4 + 14–15 are scaffolding/verification/logging).
- **Placeholders:** none — every code step contains the actual code to write; no "implement X later".
- **Type consistency:** the metrics keys (`cohorts.batch_3_cold_start`, `cohorts.batch_4_warmed`, `cohorts.combined_100`, `paired_mcnemar.contingency`, etc.) are introduced in Task 1 and used consistently in Tasks 7–9 and 12. The card layouts in Tasks 8 and 13 both use `MSO_SHAPE.ROUNDED_RECTANGLE` and the helpers defined in Task 4.
- **Honesty rules from spec:** slide 4 surfaces cohort leakage; slide 5 reports `p=1.0` plainly; slide 8 marks every competitor headline `(qualitative)` until a citable number is sourced.
- **TDD applied where it pays:** Task 1 is strict TDD (test → fail → implement → pass). The slide tasks are not test-first because the test (visual layout) is human; instead, each slide task ends with `build_pptx.py` rerun + commit, and Task 14 is the global verifier.
