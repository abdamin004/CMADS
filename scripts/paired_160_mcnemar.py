"""Paired McNemar test on memory ON vs OFF over 160 identical UUIDs.

Supersedes scripts/paired_memory_mcnemar.py (n=20). Pairs each multi-level
patient with the same-UUID single-level run, then runs an exact McNemar
(binomial on the off-diagonal).

  Multi-level (memory ON) sources, by batch:
    mas_results_improved_b3/         (batch_3, 50)
    mas_results_improved_50/         (batch_4, 50)
    mas_results_improved_extra60/    (batch_extra60, 60)

  Single-level (memory OFF) sources:
    mas_results/                            (the original baseline)
    mas_results_paired95_single_level/      (95 fills targeted at the gap)
"""

from __future__ import annotations

import json
from pathlib import Path

from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "data/gold"
JUDGE_FILE = "evaluation.json"

BATCH_FILES = [
    GOLD / "batches/batch_3.json",
    GOLD / "batches/batch_4.json",
    GOLD / "batches/batch_extra60_for_160_vs_160.json",
]

ON_DIRS = [
    GOLD / "mas_results_improved_b3",
    GOLD / "mas_results_improved_50",
    GOLD / "mas_results_improved_extra60",
]

OFF_DIRS = [
    GOLD / "mas_results_paired65_relaxed_judge",
    GOLD / "mas_results_paired95_single_level",
]

OUT = GOLD / "paired_160_mcnemar.json"


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _find_judgment(dirs: list[Path], uuid: str) -> dict | None:
    for d in dirs:
        j = _load(d / uuid / JUDGE_FILE)
        if j is not None:
            return j
    return None


def _is_direct(judgment: dict | None) -> bool | None:
    if judgment is None:
        return None
    return judgment.get("match_type") == "DIRECT"


def main() -> None:
    uuids: list[str] = []
    for bf in BATCH_FILES:
        uuids.extend(json.loads(bf.read_text()))
    seen: set[str] = set()
    ordered_uuids: list[str] = []
    for u in uuids:
        if u not in seen:
            ordered_uuids.append(u)
            seen.add(u)

    pairs = []
    for u in ordered_uuids:
        off = _is_direct(_find_judgment(OFF_DIRS, u))
        on = _is_direct(_find_judgment(ON_DIRS, u))
        pairs.append({"uuid": u, "off_direct": off, "on_direct": on})

    usable = [p for p in pairs if p["off_direct"] is not None and p["on_direct"] is not None]

    both = sum(1 for p in usable if p["off_direct"] and p["on_direct"])
    only_off = sum(1 for p in usable if p["off_direct"] and not p["on_direct"])
    only_on = sum(1 for p in usable if not p["off_direct"] and p["on_direct"])
    neither = sum(1 for p in usable if not p["off_direct"] and not p["on_direct"])

    n_discordant = only_off + only_on
    if n_discordant > 0:
        b = min(only_off, only_on)
        test = binomtest(b, n_discordant, p=0.5, alternative="two-sided")
        p_value = float(test.pvalue)
    else:
        p_value = 1.0

    off_rate = sum(1 for p in usable if p["off_direct"]) / max(len(usable), 1)
    on_rate = sum(1 for p in usable if p["on_direct"]) / max(len(usable), 1)

    summary = {
        "n_paired": len(usable),
        "n_total_uuids": len(pairs),
        "n_dropped_missing_judgment": len(pairs) - len(usable),
        "off_direct_rate": round(off_rate, 4),
        "on_direct_rate": round(on_rate, 4),
        "contingency_2x2": {
            "both_DIRECT": both,
            "only_OFF_DIRECT": only_off,
            "only_ON_DIRECT": only_on,
            "neither_DIRECT": neither,
        },
        "mcnemar_exact": {
            "discordant_pairs": n_discordant,
            "p_value_two_sided": p_value,
            "method": "binomial exact on off-diagonal",
        },
        "pairs": pairs,
    }

    OUT.write_text(json.dumps(summary, indent=2))
    print(f"wrote {OUT}")
    print(f"  N paired              = {len(usable)}")
    print(f"  OFF DIRECT rate       = {off_rate*100:.1f}%")
    print(f"  ON  DIRECT rate       = {on_rate*100:.1f}%")
    print(f"  contingency           = both={both}  only_off={only_off}  "
          f"only_on={only_on}  neither={neither}")
    print(f"  discordant pairs      = {n_discordant}")
    print(f"  exact McNemar p value = {p_value:.4f}")


if __name__ == "__main__":
    main()
