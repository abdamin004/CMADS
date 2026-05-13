"""Compare the improved-memory 10-patient run against the original
single-level baseline runs in mas_results/.

Memory-on (improved) lives at: data/gold/mas_results_improved_10/
Memory-off (baseline)  lives at: data/gold/mas_results/  (subset of 10)

Headline metrics: DIRECT, INDIRECT, MISS, found rate, rank-1 when found,
avg time/patient, plus a per-patient diff so you can see which patients
flipped which way.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

BATCH = ROOT / "data/gold/batches/batch_improved10.json"
OFF = ROOT / "data/gold/mas_results"                    # original single-level baseline
ON = ROOT / "data/gold/mas_results_improved_10"         # improved (3-phase + canonicalised)


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
    off = _aggregate(OFF, uuids)
    on = _aggregate(ON, uuids)

    if on["n"] == 0:
        print("ON dir empty — run not yet complete")
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
        ("Patients evaluated", str(off['n']), str(on['n'])),
    ]

    print(f"Cohort: {len(uuids)} patients  ·  OFF missing: {off['missing']}  ·  ON missing: {on['missing']}")
    print()
    print("| Metric | Single-level (baseline) | Multi-level (improved) | Δ |")
    print("|---|---|---|---|")
    for label, off_str, on_str in rows:
        delta = ""
        if "%" in off_str and "%" in on_str:
            try:
                o = int(off_str.split("%")[-2].split()[-1].rstrip("·").strip())
                n = int(on_str.split("%")[-2].split()[-1].rstrip("·").strip())
                d = n - o
                sign = "+" if d > 0 else ("" if d == 0 else "−")
                delta = f"{sign}{abs(d)} pp"
            except ValueError:
                pass
        print(f"| {label} | {off_str} | {on_str} | {delta} |")

    # Per-patient flip table — what changed
    print()
    print("PER-PATIENT FLIPS")
    print(f"{'UUID':14} | {'OFF':9} | {'ON':9} | {'flip':10}")
    print("-" * 55)
    flipped_better = 0
    flipped_worse = 0
    same = 0
    rank = {"DIRECT": 2, "INDIRECT": 1, "MISS": 0, None: -1}
    for u in uuids:
        o = off["per_patient"].get(u, {}).get("match_type")
        n = on["per_patient"].get(u, {}).get("match_type")
        ro, rn = rank.get(o, -1), rank.get(n, -1)
        if rn > ro:
            flipped_better += 1
            flip = "↑ better"
        elif rn < ro:
            flipped_worse += 1
            flip = "↓ worse"
        else:
            same += 1
            flip = "= same"
        print(f"{u[:12]+'…':14} | {str(o):9} | {str(n):9} | {flip}")

    print()
    print(f"Improved: {flipped_better}  ·  Regressed: {flipped_worse}  ·  Unchanged: {same}")

    # Verdict
    if on["n"] and off["n"]:
        on_d = 100 * on["DIRECT"] / on["n"]
        off_d = 100 * off["DIRECT"] / off["n"]
        on_f = 100 * on["found"] / on["n"]
        off_f = 100 * off["found"] / off["n"]
        print()
        print("VERDICT")
        print(f"  DIRECT:     {off_d:.0f}%  →  {on_d:.0f}%   ({on_d - off_d:+.0f} pp)")
        print(f"  Found rate: {off_f:.0f}%  →  {on_f:.0f}%   ({on_f - off_f:+.0f} pp)")
        if on_d >= off_d and on_f >= off_f:
            print("  ✓ POSITIVE: hardened multi-level memory does not regress on either metric.")
        elif on_d >= off_d or on_f >= off_f:
            print("  ~ MIXED: one metric improved, the other did not. Review per-patient flips.")
        else:
            print("  ✗ REGRESSED on both metrics.")


if __name__ == "__main__":
    main()
