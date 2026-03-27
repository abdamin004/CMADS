"""Compare GPT-oss 120B: Local Ollama vs Groq API

Runs both generators on the SAME patients, evaluates both with DeepSeek R1 70B,
and produces a side-by-side comparison.

Usage:
    python3 pipeline/compare_generators.py --patients 10
"""

import argparse
import json
import os
import re
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path

import requests as _requests
from langchain_ollama import ChatOllama
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, SystemMessage

# ── Import shared components from radiology_agents ──────────────────────
from radiology_agents import (
    query_imaging_cases,
    GENERATOR_SYSTEM,
    EVAL_PROMPT_TEMPLATE,
    _calc_age,
    _extract_json,
    OLLAMA_BASE_URL,
    EVALUATOR_MODEL,
)

GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
OUTPUT_DIR = Path("data/gold/comparison_results")


def _build_user_prompt(case):
    """Build generation prompt for a case."""
    age = _calc_age(case["birthdate"], case["scan_date"])
    gender = "Male" if case["gender"] == "M" else "Female"
    conditions = case.get("active_conditions", [])
    cond_text = "\n".join(f"  - {c}" for c in conditions) if conditions else "  None documented"

    obs_text = ""
    observations = case.get("observations", [])
    if observations:
        obs_text = "\nRelevant lab values and vitals from same visit:\n"
        for o in observations:
            obs_text += f"  - {o['test']}: {o['value']} {o['units']}\n"

    return f"""Generate a radiology report for the following study:

Study: {case['modality']} of {case['body_site']}
Clinical setting: {case['encounter_class']}
Patient: {age}-year-old {gender}

Active medical history (do NOT add these as diagnoses, use only for clinical context):
{cond_text}
{obs_text}
The patient has been diagnosed with: {case['ground_truth_disease']}

Write a realistic radiology report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report."""


def generate_with_ollama(case, idx, total):
    """Generate report using local Ollama."""
    llm = ChatOllama(
        model="gpt-oss:120b",
        base_url=OLLAMA_BASE_URL,
        temperature=0.7,
        num_predict=1024,
        keep_alive="30m",
    )
    prompt = _build_user_prompt(case)

    print(f"  [OLLAMA GEN {idx+1}/{total}] {case['patient_name'][:25]}...", end=" ", flush=True)
    start = time.time()
    response = llm.invoke([
        SystemMessage(content=GENERATOR_SYSTEM),
        HumanMessage(content=prompt),
    ])
    duration = time.time() - start
    tokens = response.response_metadata.get("eval_count", 0)
    print(f"done ({duration:.1f}s, {tokens} tok)")

    return {
        "report": response.content.strip(),
        "duration_s": round(duration, 1),
        "tokens": tokens,
        "provider": "ollama",
        "model": "gpt-oss:120b",
    }


def generate_with_groq(case, idx, total):
    """Generate report using Groq API."""
    llm = ChatGroq(
        model="openai/gpt-oss-120b",
        api_key=GROQ_API_KEY,
        temperature=0.7,
        max_tokens=1024,
    )
    prompt = _build_user_prompt(case)

    print(f"  [GROQ  GEN {idx+1}/{total}] {case['patient_name'][:25]}...", end=" ", flush=True)
    start = time.time()
    response = llm.invoke([
        SystemMessage(content=GENERATOR_SYSTEM),
        HumanMessage(content=prompt),
    ])
    duration = time.time() - start
    usage = response.response_metadata.get("token_usage", {})
    tokens = usage.get("completion_tokens", 0)
    print(f"done ({duration:.1f}s, {tokens} tok)")

    return {
        "report": response.content.strip(),
        "duration_s": round(duration, 1),
        "tokens": tokens,
        "provider": "groq",
        "model": "openai/gpt-oss-120b",
    }


def evaluate_report(report_text, case, provider_label):
    """Evaluate a report using DeepSeek R1 70B (local Ollama)."""
    conditions = case.get("active_conditions", [])
    prompt = EVAL_PROMPT_TEMPLATE.format(
        ground_truth_disease=case["ground_truth_disease"],
        modality=case["modality"],
        body_site=case["body_site"],
        conditions=", ".join(conditions) if conditions else "None",
        observations_count=len(case.get("observations", [])),
        report_text=report_text,
    )

    llm = ChatOllama(
        model=EVALUATOR_MODEL,
        base_url=OLLAMA_BASE_URL,
        temperature=0.3,
        top_p=0.9,
        num_predict=8192,
        keep_alive="30m",
    )

    print(f"    [EVAL {provider_label}]...", end=" ", flush=True)
    start = time.time()
    response = llm.invoke([HumanMessage(content=prompt)])
    duration = time.time() - start

    evaluation = _extract_json(response.content)
    scores = {
        "clinical_accuracy": evaluation["clinical_accuracy"]["score"],
        "no_diagnosis_leakage": evaluation["no_diagnosis_leakage"]["score"],
        "completeness": evaluation["completeness"]["score"],
        "internal_consistency": evaluation["internal_consistency"]["score"],
        "report_quality": evaluation["report_quality"]["score"],
        "overall": evaluation["overall_score"],
    }
    print(f"{scores['overall']}/5.0 ({duration:.0f}s)")

    return {
        "scores": scores,
        "details": evaluation,
        "eval_duration_s": round(duration, 1),
    }


def print_comparison(results):
    """Print side-by-side comparison."""
    print(f"\n{'═'*80}")
    print(f"COMPARISON RESULTS — Same model, same patients, different inference")
    print(f"{'═'*80}")
    print(f"  Generator model: GPT-oss 120B")
    print(f"  Evaluator model: {EVALUATOR_MODEL} (local Ollama)")
    print(f"  Patients tested: {len(results)}")

    # Collect stats per provider
    ollama_scores = []
    groq_scores = []
    ollama_times = []
    groq_times = []
    ollama_tokens = []
    groq_tokens = []
    ollama_report_lens = []
    groq_report_lens = []

    criteria_ollama = {c: [] for c in ["clinical_accuracy", "no_diagnosis_leakage", "completeness", "internal_consistency", "report_quality"]}
    criteria_groq = {c: [] for c in criteria_ollama}

    for r in results:
        o = r["ollama"]
        g = r["groq"]
        ollama_scores.append(o["eval"]["scores"]["overall"])
        groq_scores.append(g["eval"]["scores"]["overall"])
        ollama_times.append(o["gen"]["duration_s"])
        groq_times.append(g["gen"]["duration_s"])
        ollama_tokens.append(o["gen"]["tokens"])
        groq_tokens.append(g["gen"]["tokens"])
        ollama_report_lens.append(len(o["gen"]["report"]))
        groq_report_lens.append(len(g["gen"]["report"]))
        for c in criteria_ollama:
            criteria_ollama[c].append(o["eval"]["scores"][c])
            criteria_groq[c].append(g["eval"]["scores"][c])

    # Speed comparison
    print(f"\n{'─'*80}")
    print(f"  GENERATION SPEED")
    print(f"{'─'*80}")
    print(f"  {'Metric':<20} {'Ollama (local)':>16} {'Groq (cloud)':>16} {'Diff':>12}")
    print(f"  {'─'*64}")
    o_mean = statistics.mean(ollama_times)
    g_mean = statistics.mean(groq_times)
    print(f"  {'Mean time':<20} {o_mean:>14.1f}s {g_mean:>14.1f}s {o_mean/g_mean:>10.1f}x")
    print(f"  {'Median time':<20} {statistics.median(ollama_times):>14.1f}s {statistics.median(groq_times):>14.1f}s")
    print(f"  {'Min time':<20} {min(ollama_times):>14.1f}s {min(groq_times):>14.1f}s")
    print(f"  {'Max time':<20} {max(ollama_times):>14.1f}s {max(groq_times):>14.1f}s")
    if len(ollama_times) > 1:
        print(f"  {'Std dev':<20} {statistics.stdev(ollama_times):>14.1f}s {statistics.stdev(groq_times):>14.1f}s")
    print(f"  {'Avg tokens':<20} {statistics.mean(ollama_tokens):>14.0f} {statistics.mean(groq_tokens):>14.0f}")
    o_tps = [t/d for t, d in zip(ollama_tokens, ollama_times) if d > 0 and t > 0]
    g_tps = [t/d for t, d in zip(groq_tokens, groq_times) if d > 0 and t > 0]
    if o_tps and g_tps:
        print(f"  {'Throughput':<20} {statistics.mean(o_tps):>12.1f}t/s {statistics.mean(g_tps):>12.1f}t/s {statistics.mean(g_tps)/statistics.mean(o_tps):>10.1f}x")

    # Quality comparison
    print(f"\n{'─'*80}")
    print(f"  QUALITY SCORES (evaluated by DeepSeek R1 70B)")
    print(f"{'─'*80}")
    print(f"  {'Criterion':<25} {'Ollama':>8} {'Groq':>8} {'Diff':>8} {'Winner':>8}")
    print(f"  {'─'*60}")
    for c in criteria_ollama:
        o_avg = statistics.mean(criteria_ollama[c])
        g_avg = statistics.mean(criteria_groq[c])
        diff = g_avg - o_avg
        winner = "Groq" if diff > 0.1 else ("Ollama" if diff < -0.1 else "Tie")
        print(f"  {c:<25} {o_avg:>8.2f} {g_avg:>8.2f} {diff:>+8.2f} {winner:>8}")

    o_overall = statistics.mean(ollama_scores)
    g_overall = statistics.mean(groq_scores)
    diff = g_overall - o_overall
    winner = "Groq" if diff > 0.1 else ("Ollama" if diff < -0.1 else "Tie")
    print(f"  {'─'*60}")
    print(f"  {'OVERALL':<25} {o_overall:>8.2f} {g_overall:>8.2f} {diff:>+8.2f} {winner:>8}")

    # Per-patient breakdown
    print(f"\n{'─'*80}")
    print(f"  PER-PATIENT BREAKDOWN")
    print(f"{'─'*80}")
    print(f"  {'Patient':<22} {'Disease':<22} {'Ollama':>7} {'Groq':>7} {'Diff':>7} {'Gen-O':>7} {'Gen-G':>7}")
    print(f"  {'─'*75}")
    for r in results:
        name = r["patient"][:20]
        disease = r["disease"][:20]
        o_sc = r["ollama"]["eval"]["scores"]["overall"]
        g_sc = r["groq"]["eval"]["scores"]["overall"]
        o_t = r["ollama"]["gen"]["duration_s"]
        g_t = r["groq"]["gen"]["duration_s"]
        diff = g_sc - o_sc
        print(f"  {name:<22} {disease:<22} {o_sc:>7.1f} {g_sc:>7.1f} {diff:>+7.1f} {o_t:>6.1f}s {g_t:>6.1f}s")

    # Report length comparison
    print(f"\n{'─'*80}")
    print(f"  REPORT LENGTH (chars)")
    print(f"{'─'*80}")
    print(f"  Ollama: mean={statistics.mean(ollama_report_lens):.0f}  min={min(ollama_report_lens)}  max={max(ollama_report_lens)}")
    print(f"  Groq:   mean={statistics.mean(groq_report_lens):.0f}  min={min(groq_report_lens)}  max={max(groq_report_lens)}")

    # Conclusion
    print(f"\n{'═'*80}")
    print(f"  CONCLUSION")
    print(f"{'═'*80}")
    if abs(diff) <= 0.2:
        print(f"  Quality: EQUIVALENT — both produce similar quality reports")
    elif g_overall > o_overall:
        print(f"  Quality: Groq slightly better ({g_overall:.2f} vs {o_overall:.2f})")
    else:
        print(f"  Quality: Ollama slightly better ({o_overall:.2f} vs {g_overall:.2f})")
    print(f"  Speed:   Groq is {o_mean/g_mean:.1f}x faster ({g_mean:.1f}s vs {o_mean:.1f}s per report)")
    total_eval_o = sum(r["ollama"]["eval"]["eval_duration_s"] for r in results)
    total_eval_g = sum(r["groq"]["eval"]["eval_duration_s"] for r in results)
    total_gen_o = sum(r["ollama"]["gen"]["duration_s"] for r in results)
    total_gen_g = sum(r["groq"]["gen"]["duration_s"] for r in results)
    print(f"  Total generation: Ollama {total_gen_o:.0f}s | Groq {total_gen_g:.0f}s")
    print(f"  Total evaluation: {total_eval_o + total_eval_g:.0f}s (DeepSeek local)")


def main():
    parser = argparse.ArgumentParser(description="Compare GPT-oss 120B: Ollama vs Groq")
    parser.add_argument("--patients", type=int, default=10, help="Number of patients")
    args = parser.parse_args()

    if not GROQ_API_KEY:
        print("ERROR: GROQ_API_KEY not set. Export it first.")
        return

    print(f"{'═'*80}")
    print(f"GPT-oss 120B: LOCAL OLLAMA vs GROQ API — Head-to-Head Comparison")
    print(f"{'═'*80}")
    print(f"  Patients:   {args.patients}")
    print(f"  Generator:  gpt-oss:120b (Ollama) vs openai/gpt-oss-120b (Groq)")
    print(f"  Evaluator:  {EVALUATOR_MODEL} (Ollama — same for both)")
    print(f"  Started:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Collect cases (same for both)
    print(f"\n{'─'*80}")
    print(f"STEP 1: Collecting patient cases...")
    print(f"{'─'*80}")
    cases = query_imaging_cases(args.patients)
    if not cases:
        print("No imaging cases found.")
        return
    print(f"  Selected {len(cases)} patients")
    for c in cases:
        print(f"    - {c['patient_name']}: {c['modality'][:20]} — {c['ground_truth_disease'][:35]}")

    # 2. Warmup local Ollama models
    print(f"\n{'─'*80}")
    print(f"STEP 2: Warming up Ollama models...")
    print(f"{'─'*80}")
    for model in ["gpt-oss:120b", EVALUATOR_MODEL]:
        try:
            print(f"  Loading {model}...", end=" ", flush=True)
            _requests.post(
                f"{OLLAMA_BASE_URL}/api/generate",
                json={"model": model, "prompt": "Hi", "stream": False,
                      "keep_alive": "30m", "options": {"num_predict": 1}},
                timeout=300,
            )
            print("loaded")
        except Exception as e:
            print(f"FAILED: {e}")

    # 3. Generate + evaluate for each patient with BOTH providers
    results = []
    total = len(cases)

    print(f"\n{'─'*80}")
    print(f"STEP 3: Running {total} patients × 2 generators × 1 evaluator")
    print(f"{'─'*80}")

    for i, case in enumerate(cases):
        print(f"\n  Patient {i+1}/{total}: {case['patient_name']} — {case['ground_truth_disease'][:40]}")

        entry = {
            "patient": case["patient_name"],
            "patient_id": case["patient_id"],
            "disease": case["ground_truth_disease"],
            "modality": case["modality"],
        }

        # Generate with Ollama
        try:
            ollama_gen = generate_with_ollama(case, i, total)
        except Exception as e:
            print(f"  [OLLAMA GEN] ERROR: {e}")
            ollama_gen = {"report": "", "duration_s": 0, "tokens": 0, "provider": "ollama", "model": "gpt-oss:120b"}

        # Generate with Groq
        try:
            groq_gen = generate_with_groq(case, i, total)
        except Exception as e:
            print(f"  [GROQ  GEN] ERROR: {e}")
            groq_gen = {"report": "", "duration_s": 0, "tokens": 0, "provider": "groq", "model": "openai/gpt-oss-120b"}

        # Evaluate Ollama report
        try:
            ollama_eval = evaluate_report(ollama_gen["report"], case, "OLLAMA")
        except Exception as e:
            print(f"    [EVAL OLLAMA] ERROR: {e}")
            ollama_eval = {"scores": {"clinical_accuracy": 0, "no_diagnosis_leakage": 0, "completeness": 0,
                                       "internal_consistency": 0, "report_quality": 0, "overall": 0}, "eval_duration_s": 0}

        # Evaluate Groq report
        try:
            groq_eval = evaluate_report(groq_gen["report"], case, "GROQ")
        except Exception as e:
            print(f"    [EVAL GROQ] ERROR: {e}")
            groq_eval = {"scores": {"clinical_accuracy": 0, "no_diagnosis_leakage": 0, "completeness": 0,
                                     "internal_consistency": 0, "report_quality": 0, "overall": 0}, "eval_duration_s": 0}

        entry["ollama"] = {"gen": ollama_gen, "eval": ollama_eval}
        entry["groq"] = {"gen": groq_gen, "eval": groq_eval}
        results.append(entry)

    # 4. Save raw results
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / f"comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    output_file.write_text(json.dumps(results, indent=2, default=str))
    print(f"\n  Raw results saved to {output_file}")

    # 5. Print comparison
    print_comparison(results)


if __name__ == "__main__":
    main()
