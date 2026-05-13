"""Cold-start measurement: improved memory on batch_3.

batch_3 is held out — Qdrant `patient_cases` has zero overlap with it
when the run starts (it does contain the 50 batch_4 vectors from a
prior run, which act as cross-cohort priors but never as same-cohort
or self priors).

This script reports the headline metrics for the improved_b3 run and
contrasts them with the cohort-warmed batch_4 numbers (which are biased
by same-cohort priors), so the thesis can claim the cold-start delta
honestly.

  cohort-warmed (batch_4):
    case_based_50  → 40 % DIRECT, 84 % Found, 31 % rank-1-within-found
    improved_50    → 52 % DIRECT, 98 % Found, 27 % rank-1-within-found
  cold-start (batch_3):
    improved_b3    → reported below
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BATCH = ROOT / "data/gold/batches/batch_3.json"
RESULTS = ROOT / "data/gold/mas_results_improved_b3"
# OFF coverage is partial in mas_results/ — used only for the patients
# we actually have a comparable evaluation for.
OFF_RESULTS = ROOT / "data/gold/mas_results"


def _load(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _summary(patient_dir: Path) -> dict | None:
    ev = _load(patient_dir / "evaluation.json")
    tr = _load(patient_dir / "execution_trace.json")
    if not ev or not tr:
        return None
    return {
        "match_type": ev.get("match_type"),
        "rank": ev.get("rank"),
        "matched_diagnosis": ev.get("matched_diagnosis"),
        "duration_s": tr.get("duration_s"),
    }


def _aggregate(results_dir: Path, uuids: list[str]) -> dict:
    out = {
        "n": 0, "DIRECT": 0, "INDIRECT": 0, "MISS": 0,
        "rank1_when_found": 0, "found": 0,
        "duration_total_s": 0.0, "missing": 0,
    }
    for u in uuids:
        rec = _summary(results_dir / u)
        if rec is None:
            out["missing"] += 1
            continue
        out["n"] += 1
        m = rec["match_type"]
        if m == "DIRECT":
            out["DIRECT"] += 1
            out["found"] += 1
            if rec["rank"] == 1:
                out["rank1_when_found"] += 1
        elif m == "INDIRECT":
            out["INDIRECT"] += 1
            out["found"] += 1
        else:
            out["MISS"] += 1
        if rec["duration_s"] is not None:
            out["duration_total_s"] += float(rec["duration_s"])
    return out


def _pct(num: int, den: int) -> str:
    return "—" if den == 0 else f"{100 * num / den:.0f}%"


def main():
    uuids = json.loads(BATCH.read_text())
    on = _aggregate(RESULTS, uuids)
    off = _aggregate(OFF_RESULTS, uuids)

    if on["n"] == 0:
        sys.exit("improved_b3 dir empty")

    print(f"Cohort: batch_3 (held out)  ·  N = {len(uuids)}")
    print(f"  improved_b3 evaluated: {on['n']}/{len(uuids)}  ·  missing: {on['missing']}")
    print(f"  off-baseline overlap:  {off['n']}/{len(uuids)}  ·  missing: {off['missing']}")
    print()

    print("== Improved memory · cold-start on batch_3 ==")
    print(f"  DIRECT:            {on['DIRECT']}/{on['n']} · {_pct(on['DIRECT'], on['n'])}")
    print(f"  INDIRECT:          {on['INDIRECT']}/{on['n']} · {_pct(on['INDIRECT'], on['n'])}")
    print(f"  MISS:              {on['MISS']}/{on['n']} · {_pct(on['MISS'], on['n'])}")
    print(f"  Found (D + I):     {_pct(on['found'], on['n'])}")
    print(f"  Rank-1 when found: {_pct(on['rank1_when_found'], max(on['found'], 1))}")
    print(f"  Avg time/patient:  {on['duration_total_s'] / max(on['n'], 1):.0f}s")

    if off["n"] > 0:
        print()
        print(f"== OFF baseline on the same {off['n']} patients (memory disabled) ==")
        print(f"  DIRECT:            {off['DIRECT']}/{off['n']} · {_pct(off['DIRECT'], off['n'])}")
        print(f"  Found:             {_pct(off['found'], off['n'])}")
        # Restrict on to the same patients as off for a fair A/B
        # (the existing OFF coverage is a subset of batch_3)
        off_uuids = [u for u in uuids if (OFF_RESULTS / u / "evaluation.json").exists()]
        on_subset = _aggregate(RESULTS, off_uuids)
        print()
        print(f"== Improved memory restricted to the same {on_subset['n']} patients ==")
        print(f"  DIRECT:            {_pct(on_subset['DIRECT'], on_subset['n'])}")
        print(f"  Found:             {_pct(on_subset['found'], on_subset['n'])}")
        d_off = 100 * off['DIRECT'] / max(off['n'], 1)
        d_on = 100 * on_subset['DIRECT'] / max(on_subset['n'], 1)
        f_off = 100 * off['found'] / max(off['n'], 1)
        f_on = 100 * on_subset['found'] / max(on_subset['n'], 1)
        print()
        print("VERDICT (small N — not significant on its own)")
        print(f"  DIRECT: {d_off:.0f}% → {d_on:.0f}%   ({d_on - d_off:+.0f} pp)")
        print(f"  Found:  {f_off:.0f}% → {f_on:.0f}%   ({f_on - f_off:+.0f} pp)")

    print()
    print("== Cohort-leakage check ==")
    print("  cohort-warmed (batch_4):")
    print("    case_based_50 → 40% DIRECT, 84% Found")
    print("    improved_50   → 52% DIRECT, 98% Found")
    print("  cold-start (batch_3):")
    a_d = 100 * on['DIRECT'] / on['n']
    a_f = 100 * on['found'] / on['n']
    print(f"    improved_b3   → {a_d:.0f}% DIRECT, {a_f:.0f}% Found")
    if a_d < 52 or a_f < 98:
        print()
        print(f"  Δ (cohort-warmed - cold) = {52 - a_d:+.0f} pp DIRECT, {98 - a_f:+.0f} pp Found.")
        print("  This delta is the cohort-leakage contribution to the batch_4 numbers.")


if __name__ == "__main__":
    main()
