"""Aggregate evaluation results across every patient in data/gold/mas_results.

Walks each {uuid}/evaluation.json and also reads execution_trace.json for timing.
Prints a summary dict that the PPTX builder can consume.
"""

import json
from pathlib import Path
from collections import defaultdict

ROOT = Path("/Users/abdelrahmanmohamed/Desktop/Data_Clinincal_Project/data/gold/mas_results")

totals = {"DIRECT": 0, "INDIRECT": 0, "MISS": 0}
per_disease = defaultdict(lambda: {"total": 0, "DIRECT": 0, "INDIRECT": 0, "MISS": 0, "ranks": []})
per_disease_short = {
    "Essential hypertension (disorder)": "Essential hypertension",
    "Diabetes mellitus type 2 (disorder)": "Diabetes mellitus type 2",
    "Chronic kidney disease stage 3 (disorder)": "CKD stage 3",
    "End-stage renal disease (disorder)": "End-stage renal disease",
    "Ischemic heart disease (disorder)": "Ischemic heart disease",
    "Metabolic syndrome X (disorder)": "Metabolic syndrome X",
    "Chronic congestive heart failure (disorder)": "Chronic congestive heart failure",
    "Atherosclerosis of aorta (disorder)": "Atherosclerosis of aorta",
}

durations = []
ranks_when_found = []
n_patients = 0

for patient_dir in sorted(ROOT.iterdir()):
    if not patient_dir.is_dir():
        continue
    eval_path = patient_dir / "evaluation.json"
    if not eval_path.exists():
        continue
    try:
        data = json.loads(eval_path.read_text())
    except (json.JSONDecodeError, ValueError):
        continue

    target = data.get("target_disease") or data.get("target") or "unknown"
    match_type = (data.get("match_type") or "MISS").upper()
    if match_type not in totals:
        match_type = "MISS"
    rank = data.get("rank", 0) or 0

    totals[match_type] += 1
    per_disease[target]["total"] += 1
    per_disease[target][match_type] += 1
    if match_type != "MISS":
        per_disease[target]["ranks"].append(rank)
        ranks_when_found.append(rank)
    n_patients += 1

    # timing
    trace_path = patient_dir / "execution_trace.json"
    if trace_path.exists():
        try:
            t = json.loads(trace_path.read_text())
            if "duration_s" in t:
                durations.append(t["duration_s"])
        except Exception:
            pass

total = sum(totals.values())
found = totals["DIRECT"] + totals["INDIRECT"]

print(f"\n== Aggregate across {n_patients} patients ==")
print(f"  DIRECT:   {totals['DIRECT']:3d}  ({totals['DIRECT']/total*100:.1f}%)")
print(f"  INDIRECT: {totals['INDIRECT']:3d}  ({totals['INDIRECT']/total*100:.1f}%)")
print(f"  MISS:     {totals['MISS']:3d}  ({totals['MISS']/total*100:.1f}%)")
print(f"  Found:    {found:3d}  ({found/total*100:.1f}%)")

rank1 = sum(1 for r in ranks_when_found if r == 1)
print(f"\n  Rank-1 when found: {rank1}/{len(ranks_when_found)} "
      f"= {rank1/max(len(ranks_when_found),1)*100:.0f}%")

if durations:
    durations_sorted = sorted(durations)
    print(f"\n  Avg pipeline time: {sum(durations)/len(durations):.1f}s "
          f"(median {durations_sorted[len(durations)//2]:.1f}s, "
          f"n={len(durations)})")

print("\n== Per disease ==")
rows = []
for disease, d in sorted(per_disease.items(), key=lambda kv: -kv[1]["total"]):
    t = d["total"]
    direct = d["DIRECT"]; indirect = d["INDIRECT"]; miss = d["MISS"]
    found_rate = (direct + indirect) / t * 100 if t else 0
    direct_rate = direct / t * 100 if t else 0
    short = per_disease_short.get(disease, disease)
    rows.append({
        "disease": short,
        "n": t,
        "direct": direct,
        "indirect": indirect,
        "miss": miss,
        "found_rate": found_rate,
        "direct_rate": direct_rate,
    })
    print(f"  {short:35s}  n={t:3d}  D={direct:3d}  I={indirect:3d}  "
          f"M={miss:3d}  found={found_rate:.1f}%  direct={direct_rate:.1f}%")

# Emit JSON for the builder
summary = {
    "n_patients": n_patients,
    "direct": totals["DIRECT"],
    "indirect": totals["INDIRECT"],
    "miss": totals["MISS"],
    "direct_rate_pct": round(totals["DIRECT"] / total * 100, 1) if total else 0,
    "indirect_rate_pct": round(totals["INDIRECT"] / total * 100, 1) if total else 0,
    "found_rate_pct": round(found / total * 100, 1) if total else 0,
    "rank1_when_found_pct": round(rank1 / max(len(ranks_when_found), 1) * 100, 0),
    "avg_duration_s": round(sum(durations) / len(durations), 1) if durations else None,
    "per_disease": rows,
}

out = Path(__file__).with_name("aggregate_160.json")
out.write_text(json.dumps(summary, indent=2))
print(f"\nWrote {out}")
