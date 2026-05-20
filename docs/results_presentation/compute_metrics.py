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


def _aggregate_dir(results_dir: Path, repo: Path | None = None) -> dict:
    """Aggregate every evaluated patient under results_dir (no batch filter).
    `repo` is accepted for API symmetry with _aggregate but is not used:
    the judge's match_type is read directly from evaluation.json with no
    post-hoc relabeling. Re-run the LLM judge (scripts/rerun_judge.py)
    to change DIRECT/INDIRECT classification."""
    _ = repo  # unused
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


def _aggregate(results_dir: Path, uuids: list[str], repo: Path | None = None) -> dict:
    _ = repo  # unused; see _aggregate_dir
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

    cold = _decorate(_aggregate(results / "mas_results_improved_b3", b3, repo))
    warm = _decorate(_aggregate(results / "mas_results_improved_50", b4, repo))

    # Optional third multi-level slice: the +60 patients run to reach
    # N=160 parity with the single-level baseline. Aggregates over the
    # custom batch file `batch_extra60_for_160_vs_160.json` (50 from
    # batch_5 + 10 from batch_1). If the run is incomplete or the dir
    # doesn't exist, `extra60` is just an empty aggregate.
    extra60_batch = batches / "batch_extra60_for_160_vs_160.json"
    if extra60_batch.exists():
        b60 = json.loads(extra60_batch.read_text())
    else:
        b60 = []
    extra60 = _decorate(_aggregate(results / "mas_results_improved_extra60", b60, repo))

    def _sum_decorate(parts: list[dict]) -> dict:
        keys = ("n", "DIRECT", "INDIRECT", "MISS", "found",
                "rank1_in_found", "duration_total_s", "missing")
        raw = {k: sum(p.get(k, 0) for p in parts) for k in keys}
        return _decorate(raw)

    # "Combined 100" is the original two-cohort union (always available).
    combined = _sum_decorate([cold, warm])

    # "Combined 160" is only meaningful when the extra60 run has finished.
    combined_160 = _sum_decorate([cold, warm, extra60]) if extra60["n"] >= 60 else None

    baseline = _decorate(_aggregate_dir(results / "mas_results", repo))
    # Single-LLM controlled baseline (one prompt per patient, no orchestration).
    single_llm = _decorate(_aggregate_dir(results / "mas_results_single_llm_baseline", repo))

    # Paired-160 cohorts: same 160 UUIDs in both arms. Single-level
    # arm draws from mas_results/ (65 overlap UUIDs) and
    # mas_results_paired95_single_level/ (95 fills). Multi-level arm is
    # the same as combined_160.
    def _aggregate_multi_dir(dirs: list[Path], uuids: list[str]) -> dict:
        out = {"n": 0, "DIRECT": 0, "INDIRECT": 0, "MISS": 0,
               "found": 0, "rank1_in_found": 0,
               "duration_total_s": 0.0, "missing": 0}
        for u in uuids:
            ev = None
            tr = None
            for d in dirs:
                ev = _load(d / u / "evaluation.json")
                if ev:
                    tr = _load(d / u / "execution_trace.json")
                    break
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

    paired_uuids = list({u for u in b3 + b4 + b60})  # 160 distinct
    # All evaluations use the original (strict) judge prompt. The 65
    # paired-overlap UUIDs are read from mas_results/ (same as the
    # headline baseline); the 95 fresh single-level runs from
    # mas_results_paired95_single_level/.
    single_dirs = [results / "mas_results",
                   results / "mas_results_paired95_single_level"]
    multi_dirs = [results / "mas_results_improved_b3",
                  results / "mas_results_improved_50",
                  results / "mas_results_improved_extra60"]
    paired_single = _decorate(_aggregate_multi_dir(single_dirs, paired_uuids))
    paired_multi = _decorate(_aggregate_multi_dir(multi_dirs, paired_uuids))

    mc = _load(results / "paired_memory_mcnemar.json") or {}

    paired = {
        "n_paired": mc.get("n_paired"),
        "off_direct_rate": mc.get("off_direct_rate"),
        "on_direct_rate": mc.get("on_direct_rate"),
        "contingency": mc.get("contingency_2x2", {}),
        "mcnemar_p_two_sided": (mc.get("mcnemar_exact") or {}).get("p_value_two_sided"),
    }

    # Paired-160 (supersedes the n=20 paired test): same 160 UUIDs,
    # memory OFF vs memory ON. Loaded from data/gold/paired_160_mcnemar.json
    # produced by scripts/paired_160_mcnemar.py.
    mc160 = _load(results / "paired_160_mcnemar.json") or {}
    paired_160 = {
        "n_paired": mc160.get("n_paired"),
        "off_direct_rate": mc160.get("off_direct_rate"),
        "on_direct_rate": mc160.get("on_direct_rate"),
        "contingency": mc160.get("contingency_2x2", {}),
        "mcnemar_p_two_sided": (mc160.get("mcnemar_exact") or {}).get("p_value_two_sided"),
        "discordant_pairs": (mc160.get("mcnemar_exact") or {}).get("discordant_pairs"),
    } if mc160 else None

    return {
        "cohorts": {
            "batch_3_cold_start": cold,
            "batch_4_warmed": warm,
            "extra60": extra60,
            "combined_100": combined,
            "combined_160": combined_160,
            "single_level_baseline": baseline,
            "paired_single_level_160": paired_single,
            "paired_multi_level_160": paired_multi,
            "single_llm_baseline": single_llm,
        },
        "paired_mcnemar": paired,
        "paired_160": paired_160,
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
