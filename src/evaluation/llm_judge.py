"""LLM-as-Judge Evaluator — Compare MAS differential against ground truth.

Uses Qwen3 32B to judge if the MAS found the target disease.

Output per patient:
  FOUND: YES/NO
  MATCH TYPE: DIRECT / INDIRECT / MISS
  RANK: #1-5 (where the match appeared)
  MATCHED DIAGNOSIS: the diagnosis name that matched

Usage:
    from src.evaluation.llm_judge import evaluate_patient, evaluate_cohort
"""

import json
import time
from langchain_core.messages import HumanMessage

from src.llm.adapter import get_evaluator_llm
from src.config import cfg
from src.evaluation.judge_common import (
    JUDGE_PROMPT, format_differential, strip_think_tags, parse_judge_response,
)

GOLD_DIR = cfg.GOLD_DIR
MAS_RESULTS_DIR = cfg.MAS_RESULTS_DIR


def evaluate_patient(uuid, mas_output):
    """Evaluate MAS output for a single patient.

    Returns: dict with found, match_type, rank, matched_diagnosis, reason
    """
    gt = json.loads((GOLD_DIR / uuid / "ground_truth.json").read_text())
    target = gt["target_condition"]["name"]

    differential = mas_output.get("differential", [])
    if not differential:
        return {
            "uuid": uuid, "target": target,
            "found": "NO", "match_type": "MISS", "rank": 0,
            "matched_diagnosis": "NONE", "reason": "No differential produced",
        }

    diff_text = format_differential(differential)
    prompt = JUDGE_PROMPT.format(target_disease=target, differential=diff_text)

    llm = get_evaluator_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    text = strip_think_tags(response.content)
    result = parse_judge_response(text)

    eval_result = {
        "uuid": uuid, "target": target,
        **result,
        "primary_diagnosis": mas_output.get("primary_diagnosis", "?"),
    }

    # Save evaluation to patient results folder
    eval_dir = MAS_RESULTS_DIR / uuid
    if eval_dir.exists():
        (eval_dir / "evaluation.json").write_text(
            json.dumps(eval_result, indent=2, default=str)
        )

    return eval_result


def evaluate_cohort(results_list):
    """Evaluate MAS results for multiple patients.

    Args:
        results_list: List of dicts with 'patient_uuid' and 'result' (pipeline output)

    Returns:
        evaluations list, summary dict
    """
    evaluations = []
    start = time.time()

    for i, r in enumerate(results_list):
        uuid = r["patient_uuid"]
        result = r.get("result", {})
        outputs = result.get("agent_outputs", {})
        final = outputs.get("final_diagnosis", {}) or outputs.get("diagnostic_reasoning", {})

        if not final or not final.get("differential"):
            ev = {
                "uuid": uuid, "target": "?", "found": "NO",
                "match_type": "MISS", "rank": 0,
                "matched_diagnosis": "NONE", "reason": "No output",
                "primary_diagnosis": "?",
            }
            evaluations.append(ev)
            print(f"  [{i+1}/{len(results_list)}] SKIP — no output")
            continue

        gt = json.loads((GOLD_DIR / uuid / "ground_truth.json").read_text())
        target_short = gt["target_condition"]["name"][:30]
        print(f"  [{i+1}/{len(results_list)}] {target_short}...", end=" ", flush=True)

        ev = evaluate_patient(uuid, final)
        evaluations.append(ev)

        # Print result
        if ev["found"] == "YES":
            print(f"{ev['match_type']} at #{ev['rank']} → {ev['matched_diagnosis'][:40]}")
        else:
            print(f"MISS")

    duration = time.time() - start

    # Summary
    direct = sum(1 for e in evaluations if e["match_type"] == "DIRECT")
    indirect = sum(1 for e in evaluations if e["match_type"] == "INDIRECT")
    miss = sum(1 for e in evaluations if e["match_type"] == "MISS")
    total = len(evaluations)

    # Print formatted summary
    print(f"\n{'='*65}")
    print(f"  EVALUATION RESULTS")
    print(f"{'='*65}")
    print(f"  {'Patient':<14} {'Target':<28} {'Found':<6} {'Type':<9} {'Rank':<5} {'Matched Diagnosis'}")
    print(f"  {'─'*90}")
    for ev in evaluations:
        found_marker = "YES" if ev["found"] == "YES" else "---"
        print(f"  {ev['uuid'][:12]:<14} {ev['target'][:26]:<28} {found_marker:<6} {ev['match_type']:<9} #{ev['rank']:<4} {ev.get('matched_diagnosis','')[:35]}")

    print(f"  {'─'*90}")
    print(f"  DIRECT:   {direct}/{total} ({direct*100//max(total,1)}%)")
    print(f"  INDIRECT: {indirect}/{total} ({indirect*100//max(total,1)}%)")
    print(f"  MISS:     {miss}/{total} ({miss*100//max(total,1)}%)")
    print(f"  TOTAL FOUND: {direct+indirect}/{total} ({(direct+indirect)*100//max(total,1)}%)")
    print(f"  Time: {duration:.0f}s")

    summary = {
        "total": total,
        "direct": direct,
        "indirect": indirect,
        "miss": miss,
        "found_rate": f"{(direct+indirect)*100//max(total,1)}%",
        "direct_rate": f"{direct*100//max(total,1)}%",
        "duration_s": round(duration, 1),
    }

    # Per-disease breakdown
    disease_stats = {}
    for ev in evaluations:
        d = ev.get("target", "?")
        if d not in disease_stats:
            disease_stats[d] = {"direct": 0, "indirect": 0, "miss": 0, "total": 0, "ranks": []}
        disease_stats[d]["total"] += 1
        if ev["match_type"] == "DIRECT":
            disease_stats[d]["direct"] += 1
            disease_stats[d]["ranks"].append(ev["rank"])
        elif ev["match_type"] == "INDIRECT":
            disease_stats[d]["indirect"] += 1
            disease_stats[d]["ranks"].append(ev["rank"])
        else:
            disease_stats[d]["miss"] += 1

    print(f"\n  Per Disease:")
    print(f"  {'Disease':<40} {'Total':>5} {'Direct':>7} {'Indirect':>9} {'Miss':>5} {'Found%':>7} {'AvgRank':>8}")
    print(f"  {'─'*82}")
    for d in sorted(disease_stats.keys(), key=lambda x: -disease_stats[x]["total"]):
        s = disease_stats[d]
        found = s["direct"] + s["indirect"]
        pct = found * 100 // max(s["total"], 1)
        avg_rank = sum(s["ranks"]) / max(len(s["ranks"]), 1)
        print(f"  {d[:38]:<40} {s['total']:>5} {s['direct']:>7} {s['indirect']:>9} {s['miss']:>5} {pct:>6}% {avg_rank:>7.1f}")

    summary["per_disease"] = {
        d: {
            "total": s["total"],
            "direct": s["direct"],
            "indirect": s["indirect"],
            "miss": s["miss"],
            "found_rate": f"{(s['direct']+s['indirect'])*100//max(s['total'],1)}%",
            "avg_rank": round(sum(s["ranks"]) / max(len(s["ranks"]), 1), 1),
        }
        for d, s in disease_stats.items()
    }

    # Save JSON
    MAS_RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (MAS_RESULTS_DIR / "evaluation_summary.json").write_text(
        json.dumps({"summary": summary, "evaluations": evaluations}, indent=2, default=str)
    )

    # Save CSV for thesis tables
    csv_lines = ["Patient UUID,Target Disease,MAS Primary Diagnosis,Found,Match Type,Rank,Matched Diagnosis,Reason"]
    for ev in evaluations:
        csv_lines.append(
            f"{ev['uuid']},"
            f"\"{ev.get('target','?')}\","
            f"\"{ev.get('primary_diagnosis','?')}\","
            f"{ev['found']},"
            f"{ev['match_type']},"
            f"{ev['rank']},"
            f"\"{ev.get('matched_diagnosis','NONE')}\","
            f"\"{ev.get('reason','')}\""
        )
    (MAS_RESULTS_DIR / "evaluation_results.csv").write_text("\n".join(csv_lines))

    # Save disease summary CSV
    disease_csv = ["Disease,Total,Direct,Indirect,Miss,Found Rate,Avg Rank"]
    for d in sorted(disease_stats.keys(), key=lambda x: -disease_stats[x]["total"]):
        s = disease_stats[d]
        found = s["direct"] + s["indirect"]
        pct = found * 100 // max(s["total"], 1)
        avg_rank = sum(s["ranks"]) / max(len(s["ranks"]), 1)
        disease_csv.append(f"\"{d}\",{s['total']},{s['direct']},{s['indirect']},{s['miss']},{pct}%,{avg_rank:.1f}")
    (MAS_RESULTS_DIR / "evaluation_by_disease.csv").write_text("\n".join(disease_csv))

    print(f"\n  Saved:")
    print(f"    {MAS_RESULTS_DIR}/evaluation_summary.json")
    print(f"    {MAS_RESULTS_DIR}/evaluation_results.csv")
    print(f"    {MAS_RESULTS_DIR}/evaluation_by_disease.csv")

    return evaluations, summary
