"""Count how often the Diagnostic Refiner changed the primary diagnosis.

For each patient in data/gold/mas_results/, compares the rank-1
diagnosis name between diagnostic_reasoning.json (the Diagnostic
agent's pre-refinement output) and final_diagnosis.json (the
Refiner's post-review output). The Refiner is considered to have
changed the primary when the two rank-1 names differ (case-insensitive,
whitespace-stripped).

Replaces the descriptive 'about three out of five' claim in
results.tex Section 4.6 with a measured number.

Usage:
    python3 scripts/refiner_changed_primary.py
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLD = ROOT / "data" / "gold" / "mas_results"


def _primary(p: Path, file_name: str) -> str | None:
    f = p / file_name
    if not f.exists():
        return None
    try:
        d = json.loads(f.read_text())
    except (json.JSONDecodeError, OSError):
        return None
    diff = d.get("differential") or []
    if not isinstance(diff, list) or not diff:
        return None
    top = diff[0] if isinstance(diff[0], dict) else {}
    return (top.get("name") or top.get("diagnosis") or "").strip().lower()


def main() -> None:
    changed = same = missing = 0
    for p in sorted(GOLD.iterdir()):
        if not p.is_dir():
            continue
        dr = _primary(p, "diagnostic_reasoning.json")
        fd = _primary(p, "final_diagnosis.json")
        if dr is None or fd is None:
            missing += 1
            continue
        if dr == fd:
            same += 1
        else:
            changed += 1
    total = changed + same
    print(f"Refiner CHANGED primary diagnosis: {changed}/{total} "
          f"({100 * changed / max(total, 1):.1f}%)")
    print(f"Refiner KEPT primary diagnosis:     {same}/{total} "
          f"({100 * same / max(total, 1):.1f}%)")
    print(f"Skipped (missing files):            {missing}")


if __name__ == "__main__":
    main()
