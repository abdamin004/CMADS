"""A/B at N=50 — same 50 patients, memory ON vs the existing baseline.

The baseline runs already exist in data/gold/mas_results/ from earlier
no-memory cohort processing — same prompts, same model. Re-using them
saves an hour of compute.

  - data/gold/mas_results/                  (memory OFF · pre-existing,
                                             50 batch_4 UUIDs covered)
  - data/gold/mas_results_case_based_50/    (memory ON  · case-based Tier 4)

Run:
    python3 docs/memory_presentation/compare_memory_50ab.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BATCH = ROOT / "data/gold/batches/batch_4.json"
OFF = ROOT / "data/gold/mas_results"  # pre-existing no-memory runs
ON = ROOT / "data/gold/mas_results_case_based_50"


def _load_one(patient_dir: Path) -> dict | None:
    eval_path = patient_dir / "evaluation.json"
    trace_path = patient_dir / "execution_trace.json"
    if not eval_path.exists() or not trace_path.exists():
        return None
    try:
        ev = json.loads(eval_path.read_text())
        tr = json.loads(trace_path.read_text())
    except (json.JSONDecodeError, OSError):
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
    for uuid in uuids:
        rec = _load_one(results_dir / uuid)
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
    off = _aggregate(OFF, uuids)
    on = _aggregate(ON, uuids)

    if off["n"] == 0 and on["n"] == 0:
        print("Both result dirs are empty — nothing to compare yet.")
        sys.exit(0)

    rows = [
        ("DIRECT match",
         f"{off['DIRECT']}/{off['n']} · {_pct(off['DIRECT'], off['n'])}",
         f"{on['DIRECT']}/{on['n']} · {_pct(on['DIRECT'], on['n'])}"),
        ("Found rate (D + I)",
         _pct(off['found'], off['n']),
         _pct(on['found'], on['n'])),
        ("Rank-1 when found",
         _pct(off['rank1_when_found'], max(off['found'], 1)),
         _pct(on['rank1_when_found'], max(on['found'], 1))),
        ("Avg time / patient",
         f"{off['duration_total_s'] / max(off['n'], 1):.0f}s",
         f"{on['duration_total_s'] / max(on['n'], 1):.0f}s"),
        ("Patients evaluated",
         str(off['n']),
         str(on['n'])),
    ]

    print(f"Cohort: {len(uuids)} patients (Batch 4 — full set)")
    print(f"Missing — OFF: {off['missing']} · ON: {on['missing']}")
    print()
    print("| Metric | Memory OFF | Memory ON (case-based) | Δ |")
    print("|---|---|---|---|")
    for label, off_str, on_str in rows:
        # Compute delta in percentage points where applicable.
        delta = ""
        if "%" in off_str and "%" in on_str:
            o = int(off_str.split("%")[-2].split()[-1].rstrip("·").strip())
            n = int(on_str.split("%")[-2].split()[-1].rstrip("·").strip())
            d = n - o
            sign = "+" if d > 0 else ("" if d == 0 else "−")
            delta = f"{sign}{abs(d)} pp"
        elif label == "Avg time / patient":
            o = int(off_str.rstrip("s"))
            n = int(on_str.rstrip("s"))
            d = n - o
            delta = f"{d:+d}s"
        print(f"| {label} | {off_str} | {on_str} | {delta} |")

    # Verdict
    if on["n"] and off["n"]:
        on_direct_pct = 100 * on["DIRECT"] / on["n"]
        off_direct_pct = 100 * off["DIRECT"] / off["n"]
        on_found_pct = 100 * on["found"] / on["n"]
        off_found_pct = 100 * off["found"] / off["n"]
        print()
        print("VERDICT")
        print(f"  DIRECT:     {off_direct_pct:.0f}%  →  {on_direct_pct:.0f}%   "
              f"({on_direct_pct - off_direct_pct:+.0f} pp)")
        print(f"  Found rate: {off_found_pct:.0f}%  →  {on_found_pct:.0f}%   "
              f"({on_found_pct - off_found_pct:+.0f} pp)")
        if on_direct_pct >= off_direct_pct and on_found_pct >= off_found_pct:
            print("  ✓ POSITIVE: case-based memory does not regress on either metric.")
        else:
            print("  ✗ REGRESSION: at least one metric dropped — investigate before "
                  "publishing.")

    return off, on


if __name__ == "__main__":
    main()
