"""LLM Lab Verifier — Verify patient labs reflect their target disease using Qwen3 32B.

For each patient, asks the LLM: "Given these labs, could a doctor detect this disease?"
Only patients that pass go into the verified cohort.

Usage:
    python3 pipeline/lab_verifier_llm.py
    python3 pipeline/lab_verifier_llm.py --cohort data/gold/cohort_1k_patient_ids.json
    python3 pipeline/lab_verifier_llm.py --cohort data/gold/cohort_100_test_ids.json --save
"""

import argparse
import json
import os
import re
import time
from langchain_core.messages import HumanMessage
from src.llm.adapter import get_evaluator_llm
from src.config import cfg

GOLD_DIR = cfg.GOLD_DIR

VERIFY_PROMPT = """You are a senior clinical pathologist. Given a patient's lab results, vitals, medications, and active conditions, determine if the TARGET DISEASE could be diagnosed or strongly suspected from this data.

TARGET DISEASE: {target_disease}

PATIENT DATA:
{patient_data}

Answer these questions:
1. Are there lab values that are ABNORMAL in a way consistent with {target_disease}?
2. Are there medications that suggest {target_disease} (e.g., furosemide for heart failure, metformin for diabetes)?
3. Are there conditions or risk factors that strongly point to {target_disease}?
4. Could a competent physician suspect {target_disease} from this data alone?

Respond with EXACTLY this format:
VERDICT: YES or NO
CONFIDENCE: 0-100
EVIDENCE: [list the specific findings that support or contradict the disease]
REASONING: [one sentence explaining your verdict]"""


def build_patient_summary(uuid):
    """Build a concise patient summary for the LLM."""
    ehr = json.loads((GOLD_DIR / uuid / "ehr_case.json").read_text())
    lab = json.loads((GOLD_DIR / uuid / "lab_case.json").read_text())
    gt = json.loads((GOLD_DIR / uuid / "ground_truth.json").read_text())

    target = gt["target_condition"]["name"]
    demo = ehr.get("demographics", {})
    conditions = ehr.get("conditions", {})
    active = conditions.get("active", []) if isinstance(conditions, dict) else conditions
    meds = ehr.get("medications", {})
    active_meds = meds.get("active", []) if isinstance(meds, dict) else meds
    risk = ehr.get("risk_scores", {})
    comorbidity = ehr.get("comorbidity", {})
    latest_labs = lab.get("latest_labs", [])
    vitals = lab.get("recent_vitals", [])
    flags_raw = lab.get("critical_flags", {})
    flags = flags_raw.get("flags", []) if isinstance(flags_raw, dict) else flags_raw

    lines = []
    lines.append(f"Demographics: {demo.get('age', '?')}yo {demo.get('gender', '?')}, {demo.get('race', '?')}")

    # Conditions
    cond_names = []
    for c in active:
        if isinstance(c, dict):
            cond_names.append(c.get("condition", c.get("name", "?")))
    if cond_names:
        lines.append(f"Active conditions: {', '.join(cond_names[:15])}")
    else:
        lines.append("Active conditions: None")

    # Medications
    med_names = []
    for m in active_meds:
        if isinstance(m, dict):
            med_names.append(m.get("medication", m.get("name", "?")))
    if med_names:
        lines.append(f"Medications: {', '.join(med_names[:10])}")
    else:
        lines.append("Medications: None")

    # Risk scores
    risk_items = [f"{k}={v}" for k, v in risk.items() if v is not None]
    if risk_items:
        lines.append(f"Risk scores: {', '.join(risk_items[:10])}")

    # Comorbidity flags
    cflags = comorbidity.get("flags", {})
    active_flags = [k for k, v in cflags.items() if v]
    if active_flags:
        lines.append(f"Comorbidity flags: {', '.join(active_flags)}")

    # Labs
    if latest_labs:
        lines.append(f"Lab results ({len(latest_labs)}):")
        for l in latest_labs:
            if isinstance(l, dict):
                name = l.get("lab_name", l.get("name", "?"))
                value = l.get("value_latest", l.get("value", "?"))
                units = l.get("units", "")
                lines.append(f"  {name}: {value} {units}")

    # Vitals
    if vitals:
        lines.append("Vitals:")
        for v in vitals:
            if isinstance(v, dict):
                lines.append(f"  {v.get('name', '?')}: {v.get('value', '?')} {v.get('units', '')}")

    # Critical flags
    if flags:
        lines.append("Critical flags:")
        for f in flags:
            if isinstance(f, dict):
                lines.append(f"  {f.get('lab_name', '?')}: {f.get('value_latest', f.get('value', '?'))} — {f.get('flag', '?')}")

    return target, "\n".join(lines)


def parse_verdict(response_text):
    """Extract VERDICT, CONFIDENCE, EVIDENCE, REASONING from LLM response."""
    text = re.sub(r"<think>.*?</think>", "", response_text, flags=re.DOTALL).strip()

    verdict = None
    confidence = 0
    evidence = []
    reasoning = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("VERDICT:"):
            v = line.split(":", 1)[1].strip().upper()
            verdict = "YES" if "YES" in v else "NO"
        elif line.upper().startswith("CONFIDENCE:"):
            try:
                confidence = int(re.search(r"\d+", line.split(":", 1)[1]).group())
            except (AttributeError, ValueError):
                confidence = 0
        elif line.upper().startswith("EVIDENCE:"):
            evidence_text = line.split(":", 1)[1].strip()
            evidence = [e.strip().strip("-•") for e in evidence_text.split(",") if e.strip()]
        elif line.upper().startswith("REASONING:"):
            reasoning = line.split(":", 1)[1].strip()

    return verdict, confidence, evidence, reasoning


def verify_cohort(cohort_file, save=False):
    """Verify all patients in a cohort using LLM."""
    with open(cohort_file) as f:
        uuids = json.load(f)

    llm = get_evaluator_llm(temperature=0.1, max_tokens=1024)

    results = []
    passed = []
    failed = []
    errors = []

    print(f"Verifying {len(uuids)} patients with {MODEL}...\n")
    start_time = time.time()

    for i, uuid in enumerate(uuids):
        try:
            target, summary = build_patient_summary(uuid)
            prompt = VERIFY_PROMPT.format(
                target_disease=target,
                patient_data=summary,
            )

            response = llm.invoke([HumanMessage(content=prompt)])
            verdict, confidence, evidence, reasoning = parse_verdict(response.content)

            entry = {
                "uuid": uuid,
                "target": target,
                "verdict": verdict,
                "confidence": confidence,
                "evidence": evidence,
                "reasoning": reasoning,
            }
            results.append(entry)

            if verdict == "YES":
                passed.append(entry)
                status = f"YES (conf={confidence})"
            else:
                failed.append(entry)
                status = f"NO  (conf={confidence})"

            print(f"  [{i+1}/{len(uuids)}] {status} | {target[:35]} | {reasoning[:50]}")

        except Exception as e:
            print(f"  [{i+1}/{len(uuids)}] ERROR: {e}")
            errors.append({"uuid": uuid, "error": str(e)})

    total_time = time.time() - start_time

    # Summary
    print(f"\n{'='*60}")
    print(f"VERIFICATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Passed (YES):  {len(passed)}")
    print(f"  Failed (NO):   {len(failed)}")
    print(f"  Errors:        {len(errors)}")
    print(f"  Time:          {total_time:.0f}s ({total_time/max(len(uuids),1):.1f}s/patient)")

    # By disease
    print(f"\nBy disease:")
    disease_stats = {}
    for r in results:
        d = r["target"]
        if d not in disease_stats:
            disease_stats[d] = {"yes": 0, "no": 0}
        if r["verdict"] == "YES":
            disease_stats[d]["yes"] += 1
        else:
            disease_stats[d]["no"] += 1

    print(f"  {'Disease':<45} {'YES':>5} {'NO':>5} {'Rate':>6}")
    print(f"  {'─'*65}")
    for d in sorted(disease_stats.keys(), key=lambda x: -disease_stats[x]["yes"]):
        s = disease_stats[d]
        total = s["yes"] + s["no"]
        rate = s["yes"] * 100 // max(total, 1)
        print(f"  {d[:43]:<45} {s['yes']:>5} {s['no']:>5} {rate:>5}%")

    # Show some failed examples
    if failed:
        print(f"\nSample failures:")
        for f in failed[:5]:
            print(f"  {f['uuid'][:12]}... {f['target'][:30]}")
            print(f"    Reasoning: {f['reasoning'][:80]}")

    # Save
    if save:
        verified_uuids = [r["uuid"] for r in passed]
        out_path = cohort_file.replace(".json", "_llm_verified.json")
        with open(out_path, "w") as f_out:
            json.dump(verified_uuids, f_out, indent=2)
        print(f"\nVerified cohort: {out_path} ({len(verified_uuids)} patients)")

        # Also save full results
        results_path = cohort_file.replace(".json", "_verification_results.json")
        with open(results_path, "w") as f_out:
            json.dump(results, f_out, indent=2, default=str)
        print(f"Full results:   {results_path}")

    return passed, failed, errors


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LLM Lab Verifier")
    parser.add_argument("--cohort", default="data/gold/cohort_100_test_ids.json")
    parser.add_argument("--save", action="store_true")
    args = parser.parse_args()

    verify_cohort(args.cohort, save=args.save)
