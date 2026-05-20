"""Re-run the LLM judge on all patient outputs with the updated JUDGE_PROMPT.

Backs up each existing evaluation.json -> evaluation_strict.json (the
historical/strict judgement under the original prompt), then overwrites
evaluation.json with the new (relaxed) judgement. Re-running this
script is idempotent — once evaluation_strict.json exists, it is NOT
overwritten on subsequent invocations.

The relaxed prompt counts diagnoses like "X leading to Y" or
"Combined X-Y leading to Z" as DIRECT for the target disease when the
target is explicitly named in the system's diagnosis string.

Usage:
    python3 scripts/rerun_judge.py                 # all configured dirs
    python3 scripts/rerun_judge.py --dirs DIR1 DIR2
    python3 scripts/rerun_judge.py --dry-run       # show counts, do not call LLM
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from langchain_core.messages import HumanMessage

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from src.evaluation.judge_common import (
    JUDGE_PROMPT, format_differential, strip_think_tags, parse_judge_response,
)
from src.llm.adapter import get_evaluator_llm

GOLD = REPO / "data" / "gold"
PATIENT_CASES = GOLD / "patient_cases"

DEFAULT_DIRS = [
    "mas_results",
    "mas_results_paired95_single_level",
    "mas_results_improved_b3",
    "mas_results_improved_50",
    "mas_results_improved_extra60",
]


def _load(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _target_for(uuid: str) -> str | None:
    gt = _load(PATIENT_CASES / uuid / "ground_truth.json")
    if not gt:
        return None
    tc = gt.get("target_condition")
    if isinstance(tc, dict):
        return tc.get("name") or tc.get("disease")
    return tc


def _differential_for(patient_dir: Path) -> list[dict] | None:
    final = _load(patient_dir / "final_diagnosis.json")
    if final and isinstance(final.get("differential"), list):
        return final["differential"]
    refiner = _load(patient_dir / "diagnostic_refiner.json")
    if refiner and isinstance(refiner.get("differential"), list):
        return refiner["differential"]
    diag = _load(patient_dir / "diagnostic_reasoning.json")
    if diag and isinstance(diag.get("differential"), list):
        return diag["differential"]
    return None


def _judge_one(uuid: str, target: str, differential: list[dict], llm) -> dict:
    diff_text = format_differential(differential)
    prompt = JUDGE_PROMPT.format(target_disease=target, differential=diff_text)
    response = llm.invoke([HumanMessage(content=prompt)])
    text = strip_think_tags(response.content)
    result = parse_judge_response(text)
    primary = "?"
    if differential and isinstance(differential[0], dict):
        primary = differential[0].get("name", "?")
    return {"uuid": uuid, "target": target, **result, "primary_diagnosis": primary}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dirs", nargs="*", default=DEFAULT_DIRS,
                   help="result-set subdirectories under data/gold/")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max", type=int, default=None,
                   help="limit per-directory (smoke test)")
    args = p.parse_args()

    llm = None if args.dry_run else get_evaluator_llm()

    tot_all = tot_reev = tot_skip_already = tot_skip_no_diff = 0
    for d_name in args.dirs:
        d = GOLD / d_name
        if not d.exists():
            print(f"[skip] {d_name}: not found")
            continue
        patients = sorted([p for p in d.iterdir() if p.is_dir()])
        if args.max:
            patients = patients[:args.max]
        print(f"\n=== {d_name} — {len(patients)} patient dirs ===")
        n_reev = n_skip_already = n_skip_no_diff = 0
        for i, pat in enumerate(patients, 1):
            uuid = pat.name
            ev_p = pat / "evaluation.json"
            strict_p = pat / "evaluation_strict.json"
            if not ev_p.exists():
                continue
            if strict_p.exists():
                # already re-run once; skip
                n_skip_already += 1
                continue
            differential = _differential_for(pat)
            if not differential:
                n_skip_no_diff += 1
                continue
            target = _target_for(uuid)
            if not target:
                n_skip_no_diff += 1
                continue

            if args.dry_run:
                n_reev += 1
                continue

            # Back up the strict judgement first
            strict_p.write_text(ev_p.read_text())

            # Call LLM with the new prompt
            attempt = 0
            while True:
                attempt += 1
                try:
                    res = _judge_one(uuid, target, differential, llm)
                    break
                except Exception as e:
                    if attempt >= 3:
                        print(f"  [{i}/{len(patients)}] {uuid[:8]} FAILED after 3 attempts: {e}")
                        res = None
                        break
                    wait = 2 ** attempt
                    print(f"  [{i}/{len(patients)}] {uuid[:8]} attempt {attempt} error: {e}; retry in {wait}s")
                    time.sleep(wait)

            if res is None:
                continue
            ev_p.write_text(json.dumps(res, indent=2, default=str))
            n_reev += 1
            if i % 10 == 0:
                print(f"  [{i}/{len(patients)}] re-evaluated {n_reev}")

        print(f"   re-evaluated: {n_reev}")
        print(f"   skipped (already re-run): {n_skip_already}")
        print(f"   skipped (no differential): {n_skip_no_diff}")
        tot_all += len(patients)
        tot_reev += n_reev
        tot_skip_already += n_skip_already
        tot_skip_no_diff += n_skip_no_diff

    print(f"\n=== Totals ===")
    print(f"  patient dirs walked:      {tot_all}")
    print(f"  re-evaluated:             {tot_reev}")
    print(f"  skipped (already re-run): {tot_skip_already}")
    print(f"  skipped (no differential): {tot_skip_no_diff}")


if __name__ == "__main__":
    main()
