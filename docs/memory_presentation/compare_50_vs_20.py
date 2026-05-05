"""Compare the 50-patient case-based memory run against the original 20-patient A/B.

Reads from three result directories:
  - data/gold/mas_results_baseline_no_mem/  (20 patients · memory OFF · old code)
  - data/gold/mas_results_with_memory/      (20 patients · memory ON · old Tier 4)
  - data/gold/mas_results_case_based_50/    (50 patients · memory ON · new Tier 4)

Emits a markdown table with three columns and a verdict on whether the
case-based redesign holds at higher N.

Run:
    python3 docs/memory_presentation/compare_50_vs_20.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BATCH_50 = ROOT / "data/gold/batches/batch_4.json"
BATCH_20 = ROOT / "data/gold/batches/batch_4_med42_20.json"
BASELINE_20 = ROOT / "data/gold/mas_results_baseline_no_mem"
TREATMENT_20 = ROOT / "data/gold/mas_results_with_memory"
TREATMENT_50 = ROOT / "data/gold/mas_results_case_based_50"


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


def _row(label: str, agg: dict) -> dict:
    n = agg["n"] or 1
    return {
        "label": label,
        "n_runs": agg["n"],
        "direct": f"{agg['DIRECT']}/{agg['n']} · {_pct(agg['DIRECT'], agg['n'])}",
        "found": _pct(agg['found'], agg['n']),
        "rank1": _pct(agg['rank1_when_found'], max(agg['found'], 1)),
        "time": f"{agg['duration_total_s'] / n:.0f}s",
        "missing": agg["missing"],
        "_raw": agg,
    }


def main():
    uuids_50 = json.loads(BATCH_50.read_text())
    uuids_20 = json.loads(BATCH_20.read_text())

    base_20 = _aggregate(BASELINE_20, uuids_20)
    treat_20 = _aggregate(TREATMENT_20, uuids_20)
    treat_50 = _aggregate(TREATMENT_50, uuids_50)
    # Apples-to-apples: project the 50-patient run onto the 20 patients
    # in the original A/B subset.
    treat_50_subset = _aggregate(TREATMENT_50, uuids_20)

    rows = [
        _row("memory OFF · 20 patients (orig baseline)", base_20),
        _row("memory ON  · 20 patients (orig, old Tier-4)", treat_20),
        _row("memory ON  · 50 patients (NEW · case-based Tier-4)", treat_50),
        _row("memory ON  · same 20-patient subset (NEW code)", treat_50_subset),
    ]

    print(f"Cohort sizes: full batch_4 = {len(uuids_50)} · A/B subset = {len(uuids_20)}")
    print()
    print("| Run | n | DIRECT | Found rate | Rank-1 when found | Avg time / patient |")
    print("|---|---:|:---:|:---:|:---:|:---:|")
    for r in rows:
        print(
            f"| {r['label']} | {r['n_runs']} | {r['direct']} | "
            f"{r['found']} | {r['rank1']} | {r['time']} |"
        )

    # Verdict on the case-based redesign:
    base_direct_pct = 100 * base_20['DIRECT'] / max(base_20['n'], 1)
    treat20_direct_pct = 100 * treat_20['DIRECT'] / max(treat_20['n'], 1)
    treat50_direct_pct = 100 * treat_50['DIRECT'] / max(treat_50['n'], 1)
    treat20s_direct_pct = 100 * treat_50_subset['DIRECT'] / max(treat_50_subset['n'], 1)

    print()
    print("VERDICT")
    print(f"  Original A/B (20 patients):  baseline {base_direct_pct:.0f}% → memory ON {treat20_direct_pct:.0f}%  "
          f"(Δ {treat20_direct_pct - base_direct_pct:+.0f} pp)")
    print(f"  Case-based at full batch (50): memory ON {treat50_direct_pct:.0f}%")
    print(f"  Case-based on the same 20 subset: memory ON {treat20s_direct_pct:.0f}%  "
          f"(Δ vs baseline {treat20s_direct_pct - base_direct_pct:+.0f} pp)")

    if treat20s_direct_pct >= treat20_direct_pct:
        print("  → case-based redesign matches or exceeds the original memory-on result.")
    else:
        print("  → case-based redesign regressed vs the original memory-on result. Investigate.")

    return rows


if __name__ == "__main__":
    main()
