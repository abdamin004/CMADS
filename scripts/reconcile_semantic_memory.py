"""Rebuild a semantic_memory.json from per-patient mas_results outputs.

The judge writes matched_diagnosis="NONE" for MISS cases, and an early
version of memory_consolidator.py picked that value first — so MISSes
were silently aggregated under a fake disease "NONE" instead of under
the model's predicted primary diagnosis. The bug is fixed in the
consolidator (commit ...), but existing on-disk Tier-3 files are still
corrupted.

This script regenerates a clean semantic_memory.json by replaying the
fixed consolidation logic over each patient's saved final_diagnosis.json
+ evaluation.json. No LLM calls. Idempotent.

Usage:
    python3 scripts/reconcile_semantic_memory.py \\
        --results data/gold/mas_results_case_based_50 \\
        --out     data/gold/memory_case_based_50/semantic_memory.json \\
        --backup
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.memory.semantic_memory import SemanticMemory  # noqa: E402


def _resolve_disease(evaluation: dict, final: dict) -> str:
    """Same logic the fixed consolidator uses."""
    raw = (evaluation.get("matched_diagnosis") or "").strip()
    if raw.upper() in ("", "NONE", "N/A"):
        raw = ""
    return raw or final.get("primary_diagnosis") or "Unknown"


def _extract_evidence_patterns(final: dict) -> list[str]:
    patterns: list[str] = []
    diff = final.get("differential") or []
    if not diff:
        return patterns
    top = diff[0] if isinstance(diff[0], dict) else {}
    for ev in top.get("supporting_evidence") or []:
        if isinstance(ev, dict):
            f = (ev.get("finding") or "").strip()
            if f:
                patterns.append(f[:80])
        elif isinstance(ev, str):
            patterns.append(ev[:80])
    return patterns[:4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", required=True, type=Path,
                    help="mas_results dir to replay")
    ap.add_argument("--out", required=True, type=Path,
                    help="semantic_memory.json to rebuild")
    ap.add_argument("--backup", action="store_true",
                    help="copy existing --out to --out.bak before overwriting")
    args = ap.parse_args()

    results_dir: Path = args.results
    out_path: Path = args.out

    if not results_dir.exists():
        sys.exit(f"results dir missing: {results_dir}")

    if args.backup and out_path.exists():
        bak = out_path.with_suffix(out_path.suffix + ".bak")
        shutil.copy2(out_path, bak)
        print(f"  backed up: {bak}")

    # Wipe and rebuild
    if out_path.exists():
        out_path.unlink()

    store = SemanticMemory(out_path)

    n_patients = 0
    n_skipped = 0
    none_before = 0  # how many would have ended up as "NONE" under the bug
    for patient_dir in sorted(p for p in results_dir.iterdir() if p.is_dir()):
        ev_path = patient_dir / "evaluation.json"
        fd_path = patient_dir / "final_diagnosis.json"
        if not ev_path.exists() or not fd_path.exists():
            n_skipped += 1
            continue
        try:
            evaluation = json.loads(ev_path.read_text())
            final = json.loads(fd_path.read_text())
        except (json.JSONDecodeError, OSError):
            n_skipped += 1
            continue

        match_type = evaluation.get("match_type") or "MISS"
        rank = evaluation.get("rank")

        if (evaluation.get("matched_diagnosis") or "").strip().upper() in ("", "NONE", "N/A"):
            none_before += 1

        disease = _resolve_disease(evaluation, final)

        primary_confidence: float | None = None
        diff = final.get("differential") or []
        if diff and isinstance(diff[0], dict):
            prob = diff[0].get("probability")
            if isinstance(prob, (int, float)):
                primary_confidence = float(prob) * 100.0

        store.consolidate(
            disease=disease,
            match_type=match_type,
            rank_when_found=rank,
            primary_confidence=primary_confidence,
            evidence_patterns=_extract_evidence_patterns(final),
        )
        n_patients += 1

    rebuilt = json.loads(out_path.read_text()) if out_path.exists() else {}
    print(f"\nReconciled {results_dir}:")
    print(f"  patients consolidated: {n_patients}")
    print(f"  patients skipped:      {n_skipped}")
    print(f"  diseases in new store: {len(rebuilt)}")
    print(f"  MISSes that would have aggregated under NONE: {none_before}")
    if "NONE" in rebuilt:
        print("  ✗ still contains NONE entry — bug not fully fixed")
    else:
        print("  ✓ no NONE entry in rebuilt store")


if __name__ == "__main__":
    main()
