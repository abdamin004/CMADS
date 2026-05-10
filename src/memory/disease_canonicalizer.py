"""Disease canonicalizer — collapse verbose LLM disease names into a small
set of canonical families so that memory aggregation actually accumulates
signal across runs.

Without canonicalization, Tier-3 semantic memory ends up with one entry per
LLM phrasing — e.g. "Diabetic-hypertensive chronic kidney disease (CKD stage
4)", "Diabetic nephropathy (CKD stage 4)", and "Mixed diabetic-hypertensive
chronic kidney disease (stage 4)" become three separate keys with one
observation each, instead of three observations of a single CKD family.
A 50-patient run produced 46 unique disease keys before this fix.

The 9 canonical families align with the ground-truth disease set the
LLM Evaluator scores against (per docs/progress_presentation/aggregate_160.json):
  ESRD, CKD, IHD, CHF, metabolic_syndrome, HTN, T2DM, dyslipidemia, other

The mapping is a deterministic rule-based pipeline (no LLM, no embeddings)
so it is fully testable, reproducible, and auditable. Patterns are
priority-ordered: more specific anchors (ESRD, acute MI) match before
broader umbrellas (CKD, atherosclerotic disease).
"""

from __future__ import annotations

import re
from typing import Final


# Each rule: (canonical_family, compiled_pattern). First match wins.
# Patterns are matched against lowercased disease text.
_RULES: Final[list[tuple[str, re.Pattern]]] = [
    # ── End-stage / acute events first (most specific anchors) ────────
    # ESRD = explicit ESRD, end-stage renal, kidney failure stage 5,
    # or any "stage 5" + kidney/CKD/renal token.
    ("ESRD", re.compile(
        r"\besrd\b|"
        r"end[-\s]?stage\s+renal|"
        r"kidney\s+failure\s+stage\s+5|"
        r"ckd\s*[-\s]?stage\s*5|"
        r"stage\s*5\s+(?:ckd|chronic\s+kidney)"
    )),
    # Acute coronary events trump generic atherosclerosis/coronary.
    ("IHD", re.compile(
        r"\bstemi\b|\bnstemi\b|\bami\b|"
        r"acute\s+myocardial|myocardial\s+infar"
    )),

    # ── Heart failure family ──────────────────────────────────────────
    ("CHF", re.compile(
        r"heart\s+failure|\bchf\b|hfref|hfpef|cardiomyopathy"
    )),

    # ── CKD umbrella (any stage 1-4, including diabetic / hypertensive
    #    nephropathy variants — these are kidney-system diagnoses,
    #    not pure diabetes / pure hypertension diagnoses).
    ("CKD", re.compile(
        r"\bckd\b|chronic\s+kidney|kidney\s+disease|"
        r"nephropathy|nephrosclerosis|"
        r"hypertensive\s+nephr|"
        r"diabetic[-\s]?hypertensive|"
        r"renal\s+hypoperfusion|interstitial\s+nephritis|"
        r"acute\s+kidney\s+injury|\baki\b"
    )),

    # ── Metabolic syndrome (composite) ────────────────────────────────
    ("metabolic_syndrome", re.compile(
        r"metabolic\s+syndrome|insulin[-\s]?resistance|"
        r"metabolic[-\s]?vascular|prediabetes\b"
    )),

    # ── Coronary / atherosclerotic CVD (after acute MI rule above) ───
    ("IHD", re.compile(
        r"atherosclero|coronary\s+artery|ischem(?:ic|ia)\s+heart|"
        r"\bcad\b|\bihd\b|\bascvd\b|cardiorenal"
    )),

    # ── Hypertension (essential / primary / uncontrolled) ─────────────
    # The CKD rule above already catches "hypertensive nephropathy".
    ("HTN", re.compile(
        r"essential\s+hypertension|primary\s+hypertension|"
        r"hypertension|hypertensive\b"
    )),

    # ── Type 2 diabetes mellitus (after CKD/nephropathy check) ────────
    ("T2DM", re.compile(
        r"type[-\s]?2\s+diabetes|\bt2dm\b|diabetes\s+mellitus"
    )),

    # ── Dyslipidemia / hypercholesterolemia ───────────────────────────
    ("dyslipidemia", re.compile(
        r"dyslipid|hypercholesterol|hyperlipid"
    )),
]


# Stable list of family names — used by tests and reporting.
FAMILIES: Final[tuple[str, ...]] = (
    "ESRD", "CKD", "IHD", "CHF",
    "metabolic_syndrome", "HTN", "T2DM", "dyslipidemia",
    "other",
)


def canonicalize_disease(raw: str | None) -> str:
    """Map a raw disease string into one of FAMILIES.

    Returns "other" when no rule matches (e.g. "Iron-deficiency anemia",
    "Right-sided infective endocarditis"). Returns "other" for empty /
    None / "NONE" input as well — callers should normally guard against
    NONE before consolidation but the canonicalizer is defensive.
    """
    if not raw:
        return "other"
    s = raw.strip().lower()
    if s in ("", "none", "n/a", "unknown"):
        return "other"
    for family, pattern in _RULES:
        if pattern.search(s):
            return family
    return "other"


def canonicalize_with_raw(raw: str | None) -> tuple[str, str]:
    """Convenience: return (canonical_family, original_raw_string).

    Memory writers store both so that aggregation happens by family but
    the original LLM phrasing is preserved for inspection.
    """
    return canonicalize_disease(raw), (raw or "Unknown")
