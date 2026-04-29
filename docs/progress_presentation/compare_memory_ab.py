"""Aggregate the before/after multi-level-memory A/B run on Batch 4.

Reads from the two output directories:
    data/gold/mas_results_baseline_no_mem/<uuid>/
    data/gold/mas_results_with_memory/<uuid>/

For each patient, pulls evaluation.json (match_type, rank) and the
execution_trace.json (durations). Emits a markdown comparison table that
can be dropped into the presentation.

Run:
    python3 docs/progress_presentation/compare_memory_ab.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BATCH = ROOT / "data/gold/batches/batch_4_med42_20.json"
BASELINE = ROOT / "data/gold/mas_results_baseline_no_mem"
WITH_MEM = ROOT / "data/gold/mas_results_with_memory"


def _load_one(patient_dir: Path) -> dict | None:
    """Return a dict with match_type, rank, duration_s, or None if missing."""
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
        "n": 0,
        "DIRECT": 0,
        "INDIRECT": 0,
        "MISS": 0,
        "rank1_when_found": 0,
        "found": 0,
        "duration_total_s": 0.0,
        "missing": 0,
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
    if den == 0:
        return "—"
    return f"{100 * num / den:.0f}%"


def main():
    uuids = json.loads(BATCH.read_text())
    base = _aggregate(BASELINE, uuids)
    mem = _aggregate(WITH_MEM, uuids)

    rows = [
        ("DIRECT match",
         f"{base['DIRECT']}/{base['n']} · {_pct(base['DIRECT'], base['n'])}",
         f"{mem['DIRECT']}/{mem['n']} · {_pct(mem['DIRECT'], mem['n'])}"),
        ("Found rate (D + I)",
         _pct(base['found'], base['n']),
         _pct(mem['found'], mem['n'])),
        ("Rank-1 when found",
         _pct(base['rank1_when_found'], max(base['found'], 1)),
         _pct(mem['rank1_when_found'], max(mem['found'], 1))),
        ("Avg time / patient",
         f"{base['duration_total_s'] / max(base['n'], 1):.0f}s",
         f"{mem['duration_total_s'] / max(mem['n'], 1):.0f}s"),
        ("Patients evaluated",
         str(base['n']),
         str(mem['n'])),
    ]

    print(f"Cohort: {len(uuids)} patients (Batch 4)")
    print(f"Baseline missing: {base['missing']}, Memory-on missing: {mem['missing']}")
    print()
    print("| Metric | Memory OFF | Memory ON |")
    print("|---|---|---|")
    for label, b, m in rows:
        print(f"| {label} | {b} | {m} |")

    return base, mem


if __name__ == "__main__":
    main()
