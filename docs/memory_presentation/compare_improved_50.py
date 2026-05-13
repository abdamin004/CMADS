"""Compare the improved-memory 50-patient run against the prior
case-based 50-patient run.

Both runs use multi-level memory; the difference is the Diagnostic
agent's 3-phase split (with-prior / clean-room / synthesise) and the
disease canonicaliser introduced after the Codex review.

  - data/gold/mas_results_case_based_50/   (50 patients · prior Tier-4 design)
  - data/gold/mas_results_improved_50/     (50 patients · 3-phase + canon)

Both runs use the same batch (data/gold/batches/batch_4.json) so
per-patient deltas are meaningful.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BATCH = ROOT / "data/gold/batches/batch_4.json"
BEFORE = ROOT / "data/gold/mas_results_case_based_50"
AFTER = ROOT / "data/gold/mas_results_improved_50"


def _load(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _patient_summary(patient_dir: Path) -> dict | None:
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
        "per_patient": {},
    }
    for u in uuids:
        rec = _patient_summary(results_dir / u)
        if rec is None:
            out["missing"] += 1
            continue
        out["n"] += 1
        out["per_patient"][u] = rec
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
    before = _aggregate(BEFORE, uuids)
    after = _aggregate(AFTER, uuids)

    if after["n"] == 0:
        sys.exit("AFTER dir empty — run not yet complete")

    rows = [
        ("DIRECT match",
         f"{before['DIRECT']}/{before['n']} · {_pct(before['DIRECT'], before['n'])}",
         f"{after['DIRECT']}/{after['n']} · {_pct(after['DIRECT'], after['n'])}"),
        ("Found rate (D + I)",
         _pct(before['found'], before['n']),
         _pct(after['found'], after['n'])),
        ("Rank-1 when found",
         _pct(before['rank1_when_found'], max(before['found'], 1)),
         _pct(after['rank1_when_found'], max(after['found'], 1))),
        ("Avg time / patient",
         f"{before['duration_total_s'] / max(before['n'], 1):.0f}s",
         f"{after['duration_total_s'] / max(after['n'], 1):.0f}s"),
        ("Patients evaluated", str(before['n']), str(after['n'])),
    ]

    print(f"Cohort: {len(uuids)} patients (batch_4.json)")
    print(f"BEFORE missing: {before['missing']}  ·  AFTER missing: {after['missing']}")
    print()
    print("| Metric | case-based 50 (BEFORE) | improved 50 (AFTER) | Δ |")
    print("|---|---|---|---|")
    for label, b_str, a_str in rows:
        delta = ""
        if "%" in b_str and "%" in a_str:
            try:
                # split on '·' to isolate the trailing percentage when present
                b_pct = b_str.split("·")[-1].strip().rstrip("%").strip()
                a_pct = a_str.split("·")[-1].strip().rstrip("%").strip()
                d = int(a_pct) - int(b_pct)
                sign = "+" if d > 0 else ("" if d == 0 else "−")
                delta = f"{sign}{abs(d)} pp"
            except ValueError:
                pass
        print(f"| {label} | {b_str} | {a_str} | {delta} |")

    # Per-patient flip table
    print()
    print("PER-PATIENT FLIPS")
    print(f"{'UUID':14} | {'BEFORE':9} | {'AFTER':9} | {'flip':10}")
    print("-" * 55)
    flipped_better = 0
    flipped_worse = 0
    same = 0
    rank = {"DIRECT": 2, "INDIRECT": 1, "MISS": 0, None: -1}
    for u in uuids:
        b = before["per_patient"].get(u, {}).get("match_type")
        a = after["per_patient"].get(u, {}).get("match_type")
        rb, ra = rank.get(b, -1), rank.get(a, -1)
        if ra > rb:
            flipped_better += 1
            flip = "↑ better"
        elif ra < rb:
            flipped_worse += 1
            flip = "↓ worse"
        else:
            same += 1
            flip = "= same"
        print(f"{u[:12]+'…':14} | {str(b):9} | {str(a):9} | {flip}")

    print()
    print(f"Improved: {flipped_better}  ·  Regressed: {flipped_worse}  ·  Unchanged: {same}")

    if after["n"] and before["n"]:
        a_d = 100 * after["DIRECT"] / after["n"]
        b_d = 100 * before["DIRECT"] / before["n"]
        a_f = 100 * after["found"] / after["n"]
        b_f = 100 * before["found"] / before["n"]
        a_r = 100 * after["rank1_when_found"] / max(after["found"], 1)
        b_r = 100 * before["rank1_when_found"] / max(before["found"], 1)
        print()
        print("VERDICT")
        print(f"  DIRECT:            {b_d:.0f}%  →  {a_d:.0f}%   ({a_d - b_d:+.0f} pp)")
        print(f"  Found rate:        {b_f:.0f}%  →  {a_f:.0f}%   ({a_f - b_f:+.0f} pp)")
        print(f"  Rank-1 when found: {b_r:.0f}%  →  {a_r:.0f}%   ({a_r - b_r:+.0f} pp)")
        if a_d >= b_d and a_f >= b_f and a_r >= b_r:
            print("  ✓ POSITIVE: improved memory holds at N=50 on all three metrics.")
        elif a_d >= b_d or a_f >= b_f or a_r >= b_r:
            print("  ~ MIXED: at least one metric improved — review per-patient flips.")
        else:
            print("  ✗ REGRESSED on all three metrics.")


if __name__ == "__main__":
    main()
