"""Single-LLM-call baseline: one prompt per patient, no orchestration.

Establishes a matched single-model baseline against the 7-agent CMADS
pipeline. For each patient:
  1. Load ehr_case.json and lab_case.json (the same Gold-layer input
     the agents see).
  2. Ask one LLM call to produce a top-5 differential.
  3. Pass through the same JUDGE_PROMPT used by the multi-agent
     evaluator.

Writes results to:
  data/gold/mas_results_single_llm_baseline/<uuid>/
    final_diagnosis.json   (the LLM output, top-5 differential)
    evaluation.json        (judge result on that differential)

Usage:
  python3 scripts/single_llm_baseline.py                       # all 20 default
  python3 scripts/single_llm_baseline.py --max 5               # smoke
  python3 scripts/single_llm_baseline.py --uuids u1 u2 u3      # specific
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from langchain_core.messages import HumanMessage  # noqa: E402
from src.llm.adapter import get_llm, get_evaluator_llm  # noqa: E402
from src.evaluation.judge_common import (  # noqa: E402
    JUDGE_PROMPT, format_differential, strip_think_tags, parse_judge_response,
)

GOLD = REPO / "data" / "gold"
PATIENT_CASES = GOLD / "patient_cases"
DEFAULT_OUT_DIR = GOLD / "mas_results_single_llm_baseline"
OUT_DIR = DEFAULT_OUT_DIR  # rebound in main() if --out-dir is passed


SINGLE_CALL_PROMPT = """You are an experienced internist. Given the following structured patient case, produce the most likely differential diagnosis as a ranked list of 5 candidates.

PATIENT CASE
============
{patient_summary}

INSTRUCTIONS
============
Return EXACTLY this format, no preamble, no extra text:

DIFFERENTIAL:
1. <disease name 1> | P=<probability 0.0-1.0> | <one-line rationale>
2. <disease name 2> | P=<probability 0.0-1.0> | <one-line rationale>
3. <disease name 3> | P=<probability 0.0-1.0> | <one-line rationale>
4. <disease name 4> | P=<probability 0.0-1.0> | <one-line rationale>
5. <disease name 5> | P=<probability 0.0-1.0> | <one-line rationale>

The list MUST be ranked from most likely to least likely. Probabilities should sum approximately to 1.0. Use specific clinical disease names (e.g. "Essential hypertension", "End-stage renal disease", "Ischemic heart disease"), not vague labels.
"""


def _load(p: Path) -> dict | None:
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _as_list(x):
    """Coerce dict-shaped values (e.g. {'active': [...], ...}) to a flat list."""
    if isinstance(x, list):
        return x
    if isinstance(x, dict):
        out = []
        for v in x.values():
            if isinstance(v, list):
                out.extend(v)
            elif isinstance(v, dict):
                out.append(v)
        return out
    return []


def _patient_summary(ehr: dict, lab: dict) -> str:
    """Condense the Gold case files into one structured prompt block."""
    demo = ehr.get("demographics", {}) or {}
    conds = _as_list(ehr.get("conditions"))
    visits = _as_list(ehr.get("visits"))
    comorb = ehr.get("comorbidity", {}) or {}
    labs = lab.get("latest_labs", {}) or {}
    flags = lab.get("critical_flags", []) or []
    vitals = lab.get("recent_vitals", {}) or {}

    lines = []
    lines.append(f"Demographics: age {demo.get('age', '?')}, sex {demo.get('sex', '?')}, race {demo.get('race', '?')}")
    if comorb:
        lines.append(f"Comorbidity summary: {json.dumps(comorb)[:400]}")
    if conds:
        lines.append("Active conditions (top 15):")
        for c in conds[:15]:
            if isinstance(c, dict):
                name = c.get("name") or c.get("condition") or c.get("display") or "?"
                lines.append(f"  - {name}")
    if visits:
        lines.append(f"Visit count: {len(visits)}")
    if vitals:
        lines.append(f"Recent vitals: {json.dumps(vitals)[:300]}")
    if labs:
        lines.append("Latest labs (top 15):")
        if isinstance(labs, dict):
            for k, v in list(labs.items())[:15]:
                lines.append(f"  - {k}: {v}")
        elif isinstance(labs, list):
            for item in labs[:15]:
                lines.append(f"  - {item}")
    if flags:
        lines.append(f"Critical lab flags: {json.dumps(flags)[:300]}")
    return "\n".join(lines)


_RE_LINE = re.compile(r"^\s*(\d+)\.\s*(.+?)\s*\|\s*P\s*=\s*([0-9.]+)\s*\|\s*(.+?)\s*$",
                      flags=re.MULTILINE)


def _parse_diff(text: str) -> list[dict]:
    out = []
    for m in _RE_LINE.finditer(text):
        try:
            rank = int(m.group(1))
            name = m.group(2).strip()
            prob = float(m.group(3))
            rationale = m.group(4).strip()
            out.append({"rank": rank, "name": name, "probability": prob,
                        "rationale": rationale})
        except (ValueError, IndexError):
            continue
    return out[:5]


def _one_patient(uuid: str, llm, judge_llm) -> dict:
    p = PATIENT_CASES / uuid
    ehr = _load(p / "ehr_case.json")
    lab = _load(p / "lab_case.json")
    gt = _load(p / "ground_truth.json")
    if not (ehr and lab and gt):
        return {"uuid": uuid, "skipped": "missing patient_case files"}

    target = gt.get("target_condition")
    if isinstance(target, dict):
        target = target.get("name") or target.get("disease")
    if not target:
        return {"uuid": uuid, "skipped": "missing ground truth target"}

    summary = _patient_summary(ehr, lab)
    prompt = SINGLE_CALL_PROMPT.format(patient_summary=summary)

    t0 = time.time()
    resp = llm.invoke([HumanMessage(content=prompt)])
    text = strip_think_tags(resp.content)
    dt_diag = time.time() - t0
    differential = _parse_diff(text)
    if not differential:
        differential = [{"rank": 1, "name": "PARSE_FAILED", "probability": 0.0, "rationale": text[:200]}]

    final = {
        "uuid": uuid,
        "target": target,
        "differential": differential,
        "primary_diagnosis": differential[0]["name"] if differential else "?",
        "duration_diag_s": round(dt_diag, 2),
        "raw_response_first_300": text[:300],
    }
    out_pat = OUT_DIR / uuid
    out_pat.mkdir(exist_ok=True)
    (out_pat / "final_diagnosis.json").write_text(json.dumps(final, indent=2))

    diff_text = format_differential(differential)
    judge_prompt = JUDGE_PROMPT.format(target_disease=target, differential=diff_text)
    t1 = time.time()
    judge_resp = judge_llm.invoke([HumanMessage(content=judge_prompt)])
    judge_text = strip_think_tags(judge_resp.content)
    dt_judge = time.time() - t1
    judge_result = parse_judge_response(judge_text)

    eval_blob = {
        "uuid": uuid, "target": target,
        **judge_result,
        "primary_diagnosis": differential[0]["name"] if differential else "?",
        "duration_judge_s": round(dt_judge, 2),
        "duration_total_s": round(dt_diag + dt_judge, 2),
    }
    (out_pat / "evaluation.json").write_text(json.dumps(eval_blob, indent=2))
    return eval_blob


def _default_pool(seed: int = 42, n: int | None = None) -> list[str]:
    """Controlled selection: shuffled UUIDs from data/gold/mas_results/
    so the single-LLM baseline can be paired against the 7-agent
    pipeline's headline result on identical patients."""
    import random
    pool = sorted([d.name for d in (GOLD / "mas_results").iterdir()
                   if d.is_dir() and (d / "evaluation.json").exists()
                                  and (d / "final_diagnosis.json").exists()])
    rng = random.Random(seed)
    rng.shuffle(pool)
    return pool if n is None else pool[:n]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uuids", nargs="*", default=None)
    ap.add_argument("--max", type=int, default=None,
                    help="cap the patient count (default: all available in mas_results/)")
    ap.add_argument("--out-dir", type=str, default=None,
                    help="output dir under data/gold/ (default: mas_results_single_llm_baseline)")
    args = ap.parse_args()

    global OUT_DIR
    if args.out_dir:
        OUT_DIR = GOLD / args.out_dir if not args.out_dir.startswith("/") else Path(args.out_dir)
        OUT_DIR.mkdir(parents=True, exist_ok=True)
    else:
        OUT_DIR.mkdir(parents=True, exist_ok=True)

    uuids = args.uuids or _default_pool(n=None)
    uuids = uuids[:args.max] if args.max else uuids
    print(f"Single-LLM baseline on {len(uuids)} patients")

    llm = get_llm(temperature=0.1)
    judge_llm = get_evaluator_llm()

    results = []
    for i, u in enumerate(uuids, 1):
        print(f"[{i}/{len(uuids)}] {u[:12]} ...", end=" ", flush=True)
        try:
            r = _one_patient(u, llm, judge_llm)
            mt = r.get("match_type", "?")
            print(f"{mt:<10} primary='{r.get('primary_diagnosis','')[:50]}'")
            results.append(r)
        except Exception as e:
            print(f"ERROR: {e}")
            results.append({"uuid": u, "error": str(e)})

    # Summary
    n = sum(1 for r in results if r.get("match_type"))
    d = sum(1 for r in results if r.get("match_type") == "DIRECT")
    i = sum(1 for r in results if r.get("match_type") == "INDIRECT")
    m = sum(1 for r in results if r.get("match_type") == "MISS")
    f = d + i
    print()
    print(f"=== Single-LLM baseline summary ({n}/{len(uuids)} usable) ===")
    if n:
        print(f"  DIRECT:   {d:>3}/{n}  ({100*d/n:.1f}%)")
        print(f"  INDIRECT: {i:>3}/{n}  ({100*i/n:.1f}%)")
        print(f"  MISS:     {m:>3}/{n}  ({100*m/n:.1f}%)")
        print(f"  Found:    {f:>3}/{n}  ({100*f/n:.1f}%)")
    summary = {"n": n, "DIRECT": d, "INDIRECT": i, "MISS": m, "found": f,
               "uuids": [r.get("uuid") for r in results]}
    (OUT_DIR / "run_summary.json").write_text(json.dumps(summary, indent=2))
    print(f"Summary written to {OUT_DIR}/run_summary.json")

    # Paired comparison against 7-agent pipeline on the same UUIDs
    print()
    print("=== Paired comparison vs 7-agent pipeline (same UUIDs) ===")
    rows = []
    counts = {"both_DIRECT": 0, "only_7agent_DIRECT": 0,
              "only_singleLLM_DIRECT": 0, "neither_DIRECT": 0}
    counts_found = {"both_found": 0, "only_7agent_found": 0,
                    "only_singleLLM_found": 0, "neither_found": 0}
    for r in results:
        uuid = r.get("uuid")
        if not uuid or "match_type" not in r:
            continue
        seven_ev = _load(GOLD / "mas_results" / uuid / "evaluation.json")
        if not seven_ev:
            continue
        sl_mt = r["match_type"]
        ma_mt = seven_ev.get("match_type")
        rows.append({"uuid": uuid, "single_llm": sl_mt, "7_agent": ma_mt,
                     "target": seven_ev.get("target")})
        ma_d = ma_mt == "DIRECT"
        sl_d = sl_mt == "DIRECT"
        ma_f = ma_mt in ("DIRECT", "INDIRECT")
        sl_f = sl_mt in ("DIRECT", "INDIRECT")
        key = ("both_DIRECT" if (ma_d and sl_d) else
               "only_7agent_DIRECT" if ma_d else
               "only_singleLLM_DIRECT" if sl_d else "neither_DIRECT")
        counts[key] += 1
        keyf = ("both_found" if (ma_f and sl_f) else
                "only_7agent_found" if ma_f else
                "only_singleLLM_found" if sl_f else "neither_found")
        counts_found[keyf] += 1

    n_pair = len(rows)
    if n_pair:
        ma_d = sum(1 for r in rows if r["7_agent"] == "DIRECT")
        sl_d = sum(1 for r in rows if r["single_llm"] == "DIRECT")
        ma_f = sum(1 for r in rows if r["7_agent"] in ("DIRECT", "INDIRECT"))
        sl_f = sum(1 for r in rows if r["single_llm"] in ("DIRECT", "INDIRECT"))
        print(f"  N paired:               {n_pair}")
        print(f"  7-agent DIRECT:         {ma_d}/{n_pair}  ({100*ma_d/n_pair:.1f}%)")
        print(f"  single-LLM DIRECT:      {sl_d}/{n_pair}  ({100*sl_d/n_pair:.1f}%)")
        print(f"  Δ DIRECT (7-agent − single-LLM): {(ma_d-sl_d)/n_pair*100:+.1f} pp")
        print(f"  7-agent Found:          {ma_f}/{n_pair}  ({100*ma_f/n_pair:.1f}%)")
        print(f"  single-LLM Found:       {sl_f}/{n_pair}  ({100*sl_f/n_pair:.1f}%)")
        print(f"  Δ Found (7-agent − single-LLM):  {(ma_f-sl_f)/n_pair*100:+.1f} pp")
        print()
        print(f"  Paired DIRECT contingency:")
        print(f"    both DIRECT:                 {counts['both_DIRECT']}")
        print(f"    only 7-agent DIRECT:         {counts['only_7agent_DIRECT']}")
        print(f"    only single-LLM DIRECT:      {counts['only_singleLLM_DIRECT']}")
        print(f"    neither DIRECT:              {counts['neither_DIRECT']}")

        # Exact McNemar on DIRECT
        try:
            from scipy.stats import binomtest
            b = counts['only_7agent_DIRECT']
            c = counts['only_singleLLM_DIRECT']
            disc = b + c
            if disc:
                pval = float(binomtest(min(b, c), disc, 0.5, alternative="two-sided").pvalue)
            else:
                pval = 1.0
            print(f"  Exact McNemar on DIRECT: p = {pval:.4f}  ({disc} discordant)")
        except Exception as e:
            pval = None
            print(f"  McNemar skipped ({e})")

        paired = {
            "n_paired": n_pair,
            "seven_agent_DIRECT": ma_d, "single_llm_DIRECT": sl_d,
            "seven_agent_found": ma_f, "single_llm_found": sl_f,
            "DIRECT_contingency": counts,
            "Found_contingency": counts_found,
            "mcnemar_p_two_sided_on_DIRECT": pval,
            "pairs": rows,
        }
        (OUT_DIR / "paired_vs_7agent.json").write_text(json.dumps(paired, indent=2))
        print(f"  Paired analysis written to {OUT_DIR}/paired_vs_7agent.json")


if __name__ == "__main__":
    main()
