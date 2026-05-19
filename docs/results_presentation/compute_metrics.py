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


def _aggregate_dir(results_dir: Path) -> dict:
    """Aggregate every evaluated patient under results_dir (no batch filter)."""
    out = {
        "n": 0, "DIRECT": 0, "INDIRECT": 0, "MISS": 0,
        "found": 0, "rank1_in_found": 0,
        "duration_total_s": 0.0,
    }
    if not results_dir.exists():
        return out
    for p in sorted(results_dir.iterdir()):
        if not p.is_dir():
            continue
        ev = _load(p / "evaluation.json")
        if not ev or "match_type" not in ev:
            continue
        mt = ev["match_type"]
        if mt not in ("DIRECT", "INDIRECT", "MISS"):
            continue
        out["n"] += 1
        out[mt] += 1
        if mt in ("DIRECT", "INDIRECT"):
            out["found"] += 1
            if ev.get("rank") == 1:
                out["rank1_in_found"] += 1
        tr = _load(p / "execution_trace.json")
        if tr and isinstance(tr.get("duration_s"), (int, float)):
            out["duration_total_s"] += tr["duration_s"]
    return out


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

    baseline = _decorate(_aggregate_dir(results / "mas_results"))

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
            "single_level_baseline": baseline,
        },
        "paired_mcnemar": paired,
        "sources": {
            "cold_start_dir": "data/gold/mas_results_improved_b3",
            "warmed_dir": "data/gold/mas_results_improved_50",
            "baseline_dir": "data/gold/mas_results",
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
