"""Radiology Report Multi-Agent Pipeline — LangChain + LangGraph

4-agent system with parallel execution:

  Agent 1 — Data Collector:   Queries DuckDB for patient imaging cases
  Agent 2 — Report Generator: Generates reports via GPT-o3 120B (Groq API — cloud)
  Agent 3 — Quality Evaluator: Scores reports via DeepSeek R1 70B (Ollama — local)
  Agent 4 — Storage Manager:  Saves only reports that pass quality threshold

Pipeline graph (parallel generate+evaluate per case):
  collect_data → generate_report → evaluate_report → store_result → (next case)

Usage:
    python3 pipeline/radiology_agents.py --patients 10
    python3 pipeline/radiology_agents.py --patients 10 --threshold 4.0
    python3 pipeline/radiology_agents.py --patients 10 --diseases "Chronic congestive heart failure"
"""

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import os
import duckdb
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field
from src.llm.adapter import get_llm, get_evaluator_llm
from src.config import cfg

# ── Config (reads from .env via src.config) ─────────────────────────────

DB_PATH = Path(os.environ.get("DUCKDB_PATH", "data/clinical.duckdb"))
OUTPUT_DIR = Path("data/gold/radiology_reports")
EVAL_DIR = Path("data/gold/radiology_evaluations")
DEFAULT_QUALITY_THRESHOLD = 4.0
MAX_RETRIES = 3
FALLBACK_THRESHOLD = 3.5  # Accept best attempt if all retries fail but score ≥ this


# ── Pydantic Schemas ────────────────────────────────────────────────────

class CaseData(BaseModel):
    """Patient imaging case collected from DuckDB."""
    patient_id: str
    imaging_id: str
    scan_date: str
    modality_code: str
    modality: str
    body_site: str
    sop: str | None = None
    encounter_id: str
    encounter_class: str
    ground_truth_code: str
    ground_truth_disease: str
    patient_name: str
    birthdate: str
    gender: str
    deathdate: str | None = None
    active_conditions: list[str] = Field(default_factory=list)
    observations: list[dict] = Field(default_factory=list)


class EvaluationScores(BaseModel):
    """Scores from the quality evaluator."""
    clinical_accuracy: int = 0
    no_diagnosis_leakage: int = 0
    completeness: int = 0
    internal_consistency: int = 0
    report_quality: int = 0
    overall: float = 0.0


class PipelineState(BaseModel):
    """LangGraph state passed between agents."""
    # Input
    cases: list[dict] = Field(default_factory=list)
    current_index: int = 0
    threshold: float = DEFAULT_QUALITY_THRESHOLD

    # Per-case working state
    current_case: dict = Field(default_factory=dict)
    current_report: dict = Field(default_factory=dict)
    current_evaluation: dict = Field(default_factory=dict)
    current_scores: dict = Field(default_factory=dict)

    # Accumulated results
    accepted: list[dict] = Field(default_factory=list)
    rejected: list[dict] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)

    # Timing
    case_start_time: float = 0.0


# ── Agent 1: Data Collector ─────────────────────────────────────────────

def collect_data(state: dict) -> dict:
    """Agent 1: Query DuckDB for patient imaging cases with clinical context."""
    cases = state["cases"]
    idx = state["current_index"]

    if idx == 0:
        print(f"\n{'─'*60}")
        print(f"AGENT 1 — DATA COLLECTOR")
        print(f"{'─'*60}")
        diseases = {}
        for c in cases:
            d = c["ground_truth_disease"]
            diseases[d] = diseases.get(d, 0) + 1
        print(f"  {len(cases)} cases from {len(set(c['patient_id'] for c in cases))} patients")
        for d, n in sorted(diseases.items(), key=lambda x: -x[1]):
            print(f"    {n:>3}x  {d}")

    case = cases[idx]
    print(f"\n[{idx+1}/{len(cases)}] {case['patient_name']}: "
          f"{case['modality'][:20]} — {case['ground_truth_disease'][:40]}")

    return {
        **state,
        "current_case": case,
        "case_start_time": time.time(),
    }


# ── Agent 2: Report Generator ──────────────────────────────────────────

GENERATOR_SYSTEM = """You are an experienced radiologist writing a structured radiology report.

RULES:
1. Describe imaging findings consistent with the patient's known condition
2. NEVER state the diagnosis or use the disease name in the report
3. Use standard radiology report structure: TECHNIQUE, FINDINGS, IMPRESSION
4. Use appropriate radiological terminology
5. Include measurements where clinically appropriate
6. Include incidental findings where relevant for the patient's age and history
7. End the impression with "Clinical correlation recommended."
8. If lab values are provided, reference relevant ones in your findings
9. Keep the report concise and professional
10. Output ONLY the report text, no preamble or explanation"""


def _calc_age(birthdate, scan_date):
    try:
        birth = datetime.strptime(str(birthdate)[:10], "%Y-%m-%d")
        scan = datetime.strptime(str(scan_date)[:10], "%Y-%m-%d")
        return scan.year - birth.year - ((scan.month, scan.day) < (birth.month, birth.day))
    except (ValueError, TypeError):
        return "unknown"


def generate_report(state: dict) -> dict:
    """Agent 2: Generate a radiology report using GPT-o3 120B via ChatOllama."""
    case = state["current_case"]
    idx = state["current_index"]
    total = len(state["cases"])

    print(f"  [GEN] Calling {cfg.LLM_MODEL}...", end=" ", flush=True)

    # Build prompt
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

    user_prompt = f"""Generate a radiology report for the following study:

Study: {case['modality']} of {case['body_site']}
Clinical setting: {case['encounter_class']}
Patient: {age}-year-old {gender}

Active medical history (do NOT add these as diagnoses, use only for clinical context):
{cond_text}
{obs_text}
The patient has been diagnosed with: {case['ground_truth_disease']}

Write a realistic radiology report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report."""

    # Call LLM via Groq API (cloud)
    llm = get_llm(temperature=0.7, max_tokens=1024)

    start = time.time()
    try:
        response = llm.invoke([
            SystemMessage(content=GENERATOR_SYSTEM),
            HumanMessage(content=user_prompt),
        ])
        duration = time.time() - start
        report_text = response.content.strip()

        print(f"done ({duration:.1f}s)")

        report = {
            "patient_id": case["patient_id"],
            "patient_name": case["patient_name"],
            "imaging_study_id": case["imaging_id"],
            "scan_date": case["scan_date"],
            "modality_code": case["modality_code"],
            "modality": case["modality"],
            "body_site": case["body_site"],
            "encounter_class": case["encounter_class"],
            "report": report_text,
            "generation_metadata": {
                "model": cfg.LLM_MODEL,
                "temperature": 0.7,
                "ground_truth_disease": case["ground_truth_disease"],
                "ground_truth_code": case["ground_truth_code"],
                "active_conditions": conditions,
                "observations_used": len(observations),
                "duration_s": round(duration, 1),
                "tokens_generated": response.response_metadata.get("eval_count", 0),
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        return {**state, "current_report": report}

    except Exception as e:
        print(f"ERROR: {e}")
        return {
            **state,
            "current_report": {},
            "errors": state.get("errors", []) + [f"GEN {idx+1}: {e}"],
        }


# ── Agent 3: Quality Evaluator ─────────────────────────────────────────

EVAL_PROMPT_TEMPLATE = """You are a senior radiologist and clinical AI evaluator. Evaluate this synthetic radiology report.

The report was generated for a patient with a KNOWN disease (ground truth). It should describe findings CONSISTENT with the disease WITHOUT naming the diagnosis.

## Ground Truth
- **Disease**: {ground_truth_disease}
- **Modality**: {modality} of {body_site}
- **Active conditions**: {conditions}
- **Observations from encounter**: {observations_count} lab/vital values

## Report
```
{report_text}
```

## Score each criterion 1-5:

1. **Clinical Accuracy**: Are findings realistic and consistent with {ground_truth_disease}?
2. **No Diagnosis Leakage**: Does report avoid naming the diagnosis? (5=never mentioned, 1=explicitly stated)
3. **Completeness**: Are key expected findings present?
4. **Internal Consistency**: Are findings internally consistent? Measurements anatomically sensible?
5. **Report Quality**: Standard structure (Technique/Findings/Impression)? Appropriate terminology?

Return ONLY valid JSON:
{{
  "clinical_accuracy": {{"score": <1-5>, "justification": "<reason>"}},
  "no_diagnosis_leakage": {{"score": <1-5>, "justification": "<reason>", "leaked_terms": []}},
  "completeness": {{"score": <1-5>, "justification": "<reason>", "missing_findings": []}},
  "internal_consistency": {{"score": <1-5>, "justification": "<reason>"}},
  "report_quality": {{"score": <1-5>, "justification": "<reason>"}},
  "overall_score": <average of 5 scores, 1 decimal>,
  "summary": "<2-3 sentence assessment>",
  "could_agent_diagnose": "<yes/no/partially>"
}}"""


def _extract_json(text):
    """Extract JSON from LLM response, handling <think> tags and code blocks."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    match = re.search(r"\{[\s\S]*\}", text)
    if match:
        text = match.group(0)
    return json.loads(text)


def evaluate_report(state: dict) -> dict:
    """Agent 3: Evaluate report quality using DeepSeek R1 70B via ChatOllama."""
    report = state.get("current_report", {})
    idx = state["current_index"]

    if not report:
        return {**state, "current_evaluation": {}, "current_scores": {}}

    meta = report["generation_metadata"]
    conditions = meta.get("active_conditions", [])

    prompt = EVAL_PROMPT_TEMPLATE.format(
        ground_truth_disease=meta["ground_truth_disease"],
        modality=report["modality"],
        body_site=report["body_site"],
        conditions=", ".join(conditions) if conditions else "None",
        observations_count=meta.get("observations_used", 0),
        report_text=report["report"],
    )

    print(f"  [EVAL] Calling {cfg.LLM_EVALUATOR_MODEL}...", end=" ", flush=True)

    llm = get_evaluator_llm(temperature=0.3, max_tokens=4096)

    start = time.time()
    try:
        response = llm.invoke([HumanMessage(content=prompt)])
        duration = time.time() - start

        content = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
        evaluation = _extract_json(content)

        scores = {
            "clinical_accuracy": evaluation["clinical_accuracy"]["score"],
            "no_diagnosis_leakage": evaluation["no_diagnosis_leakage"]["score"],
            "completeness": evaluation["completeness"]["score"],
            "internal_consistency": evaluation["internal_consistency"]["score"],
            "report_quality": evaluation["report_quality"]["score"],
            "overall": evaluation["overall_score"],
        }

        eval_result = {
            "patient_id": report["patient_id"],
            "patient_name": report["patient_name"],
            "scan_date": report["scan_date"],
            "modality": report["modality"],
            "body_site": report["body_site"],
            "ground_truth": meta["ground_truth_disease"],
            "generation_model": meta["model"],
            "evaluation_model": cfg.LLM_EVALUATOR_MODEL,
            "scores": scores,
            "details": evaluation,
            "evaluated_at": datetime.now(timezone.utc).isoformat(),
        }

        print(f"Score: {scores['overall']}/5.0 | Leakage: {scores['no_diagnosis_leakage']}/5 | {duration:.0f}s")

        return {**state, "current_evaluation": eval_result, "current_scores": scores}

    except Exception as e:
        print(f"ERROR: {e}")
        return {
            **state,
            "current_evaluation": {},
            "current_scores": {},
            "errors": state.get("errors", []) + [f"EVAL {idx+1}: {e}"],
        }


# ── Agent 4: Storage Manager ───────────────────────────────────────────

def store_result(state: dict) -> dict:
    """Agent 4: Save or reject the report based on quality threshold."""
    report = state.get("current_report", {})
    evaluation = state.get("current_evaluation", {})
    scores = state.get("current_scores", {})
    threshold = state["threshold"]
    idx = state["current_index"]
    case_duration = time.time() - state.get("case_start_time", time.time())

    accepted = list(state.get("accepted", []))
    rejected = list(state.get("rejected", []))

    if not report or not scores:
        print(f"  [STORE] SKIP — no report or evaluation")
        rejected.append({"report": report, "reason": "generation/evaluation failed"})
        return {**state, "accepted": accepted, "rejected": rejected, "current_index": idx + 1}

    overall = scores.get("overall", 0)
    leakage = scores.get("no_diagnosis_leakage", 0)

    if overall < threshold:
        reason = f"score {overall} < {threshold}"
        print(f"  [STORE] REJECT — {reason}")
        rejected.append({"report": report, "evaluation": evaluation, "reason": reason})
    elif leakage < 3:
        reason = f"leakage {leakage}/5"
        print(f"  [STORE] REJECT — diagnosis leakage ({reason})")
        rejected.append({"report": report, "evaluation": evaluation, "reason": reason})
    else:
        # Save individual report
        output_dir = OUTPUT_DIR
        output_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{report['patient_id']}_{report['modality_code']}_{report['scan_date']}.json"
        (output_dir / filename).write_text(json.dumps(report, indent=2))

        print(f"  [STORE] ACCEPT — score {overall}/5.0 ({case_duration:.0f}s total)")
        accepted.append({"report": report, "evaluation": evaluation})

    return {**state, "accepted": accepted, "rejected": rejected, "current_index": idx + 1}


# ── LangGraph: Parallel Pipeline ────────────────────────────────────────
#
# Uses threading to overlap generation and evaluation:
#
#   Generator thread (GPT-o3):     GEN#1  GEN#2  GEN#3  ...
#   Evaluator thread (DeepSeek):          EVAL#1 EVAL#2 EVAL#3 ...
#   Storage (inline with eval):           STORE  STORE  STORE  ...
#
# LangGraph StateGraph manages the overall pipeline state,
# while threads handle the parallel execution.

import threading
from queue import Queue

import requests as _requests

_print_lock = threading.Lock()

def _tprint(*args, **kwargs):
    """Thread-safe print."""
    with _print_lock:
        print(*args, **kwargs, flush=True)


def warmup_models():
    """No warmup needed — both models run on Groq cloud."""
    print(f"\n  Both models on Groq API — no warmup needed.")
    print(f"    Generator: {cfg.LLM_MODEL}")
    print(f"    Evaluator: {cfg.LLM_EVALUATOR_MODEL}\n")


def _generator_thread(cases, report_queue):
    """Thread: generates reports using Groq API (cloud) and pushes to queue."""
    llm = get_llm(temperature=0.7, max_tokens=1024)

    for i, case in enumerate(cases):
        _tprint(f"  [GEN {i+1}/{len(cases)}] {case['patient_name']}: "
                f"{case['modality'][:15]} — {case['ground_truth_disease'][:35]}")

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

        user_prompt = f"""Generate a radiology report for the following study:

Study: {case['modality']} of {case['body_site']}
Clinical setting: {case['encounter_class']}
Patient: {age}-year-old {gender}

Active medical history (do NOT add these as diagnoses, use only for clinical context):
{cond_text}
{obs_text}
The patient has been diagnosed with: {case['ground_truth_disease']}

Write a realistic radiology report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report."""

        try:
            start = time.time()
            response = llm.invoke([
                SystemMessage(content=GENERATOR_SYSTEM),
                HumanMessage(content=user_prompt),
            ])
            duration = time.time() - start

            report = {
                "patient_id": case["patient_id"],
                "patient_name": case["patient_name"],
                "imaging_study_id": case["imaging_id"],
                "scan_date": case["scan_date"],
                "modality_code": case["modality_code"],
                "modality": case["modality"],
                "body_site": case["body_site"],
                "encounter_class": case["encounter_class"],
                "report": response.content.strip(),
                "generation_metadata": {
                    "model": cfg.LLM_MODEL,
                    "temperature": 0.7,
                    "ground_truth_disease": case["ground_truth_disease"],
                    "ground_truth_code": case["ground_truth_code"],
                    "active_conditions": conditions,
                    "observations_used": len(observations),
                    "duration_s": round(duration, 1),
                    "tokens_generated": response.response_metadata.get("token_usage", {}).get("completion_tokens", 0),
                    "provider": "groq",
                    "attempt": 1,
                    "total_attempts": 1,
                    "_birthdate": case.get("birthdate", ""),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
            }
            _tprint(f"  [GEN {i+1}/{len(cases)}] done ({duration:.1f}s)")
            report_queue.put(("report", report))

        except Exception as e:
            _tprint(f"  [GEN {i+1}/{len(cases)}] ERROR: {e}")
            report_queue.put(("error", str(e)))

    report_queue.put(("done", None))


def _evaluate_report(eval_llm, report, threshold):
    """Evaluate a single report. Returns (scores, eval_result, evaluation_details)."""
    meta = report["generation_metadata"]
    conditions = meta.get("active_conditions", [])

    prompt = EVAL_PROMPT_TEMPLATE.format(
        ground_truth_disease=meta["ground_truth_disease"],
        modality=report["modality"],
        body_site=report["body_site"],
        conditions=", ".join(conditions) if conditions else "None",
        observations_count=meta.get("observations_used", 0),
        report_text=report["report"],
    )

    start = time.time()
    response = eval_llm.invoke([HumanMessage(content=prompt)])
    duration = time.time() - start

    content = re.sub(r"<think>.*?</think>", "", response.content, flags=re.DOTALL).strip()
    evaluation = _extract_json(content)
    scores = {
        "clinical_accuracy": evaluation["clinical_accuracy"]["score"],
        "no_diagnosis_leakage": evaluation["no_diagnosis_leakage"]["score"],
        "completeness": evaluation["completeness"]["score"],
        "internal_consistency": evaluation["internal_consistency"]["score"],
        "report_quality": evaluation["report_quality"]["score"],
        "overall": evaluation["overall_score"],
    }

    eval_result = {
        "patient_id": report["patient_id"],
        "patient_name": report["patient_name"],
        "scan_date": report["scan_date"],
        "modality": report["modality"],
        "body_site": report["body_site"],
        "ground_truth": meta["ground_truth_disease"],
        "generation_model": meta["model"],
        "evaluation_model": cfg.LLM_EVALUATOR_MODEL,
        "scores": scores,
        "details": evaluation,
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    return scores, eval_result, evaluation, duration


def _build_feedback(evaluation):
    """Extract actionable feedback from evaluation for retry prompt."""
    parts = []
    for criterion in ["clinical_accuracy", "completeness", "internal_consistency"]:
        entry = evaluation.get(criterion, {})
        if isinstance(entry, dict) and entry.get("score", 5) < 4:
            parts.append(f"- {criterion}: {entry.get('justification', 'needs improvement')}")
    missing = evaluation.get("completeness", {}).get("missing_findings", [])
    if missing:
        parts.append(f"- Missing findings: {', '.join(missing)}")
    leaked = evaluation.get("no_diagnosis_leakage", {}).get("leaked_terms", [])
    if leaked:
        parts.append(f"- REMOVE these leaked diagnosis terms: {', '.join(leaked)}")
    summary = evaluation.get("summary", "")
    if summary:
        parts.append(f"- Evaluator summary: {summary}")
    return "\n".join(parts) if parts else "Improve overall quality and completeness."


def _regenerate_with_feedback(gen_llm, report, feedback, attempt):
    """Regenerate a report using evaluator feedback."""
    meta = report["generation_metadata"]
    age = _calc_age(meta.get("_birthdate", ""), report["scan_date"])
    conditions = meta.get("active_conditions", [])
    cond_text = "\n".join(f"  - {c}" for c in conditions) if conditions else "  None documented"

    retry_prompt = f"""Your previous radiology report was rejected. Here is the feedback:

{feedback}

Please generate an IMPROVED radiology report for the following study:

Study: {report['modality']} of {report['body_site']}
Clinical setting: {report['encounter_class']}
Patient: (same patient as before)

Active medical history:
{cond_text}

The patient has been diagnosed with: {meta['ground_truth_disease']}

Fix the issues above. Write a better report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report."""

    start = time.time()
    response = gen_llm.invoke([
        SystemMessage(content=GENERATOR_SYSTEM),
        HumanMessage(content=retry_prompt),
    ])
    duration = time.time() - start

    # Update the report with new text and metadata
    new_report = dict(report)
    new_report["report"] = response.content.strip()
    new_report["generation_metadata"] = dict(meta)
    new_report["generation_metadata"]["duration_s"] = round(duration, 1)
    new_report["generation_metadata"]["tokens_generated"] = (
        response.response_metadata.get("token_usage", {}).get("completion_tokens", 0)
    )
    new_report["generation_metadata"]["attempt"] = attempt
    new_report["generation_metadata"]["generated_at"] = datetime.now(timezone.utc).isoformat()

    return new_report, duration


def _evaluator_thread(report_queue, threshold, results):
    """Thread: evaluates reports, retries with feedback up to MAX_RETRIES times."""
    eval_llm = get_evaluator_llm(temperature=0.3, max_tokens=4096)
    gen_llm = get_llm(temperature=0.7, max_tokens=1024)

    eval_count = 0
    while True:
        msg_type, payload = report_queue.get()

        if msg_type == "done":
            break
        if msg_type == "error":
            continue

        report = payload
        eval_count += 1
        meta = report["generation_metadata"]

        _tprint(f"  [EVAL {eval_count}] {report['patient_name']}: "
                f"{report['modality'][:15]} — {meta['ground_truth_disease'][:35]}")

        # Track all attempts for this case
        best_report = report
        best_eval = None
        best_scores = None
        best_overall = 0.0
        accepted = False
        final_attempt = 1

        for attempt in range(1, MAX_RETRIES + 2):  # attempt 1 = original, 2-4 = retries
            current_report = report if attempt == 1 else best_report

            try:
                scores, eval_result, evaluation, dur = _evaluate_report(
                    eval_llm, current_report, threshold
                )
                overall = scores["overall"]
                leakage = scores["no_diagnosis_leakage"]

                # Track best attempt
                if overall > best_overall:
                    best_overall = overall
                    best_report = current_report
                    best_eval = eval_result
                    best_scores = scores

                is_accepted = overall >= threshold and leakage >= 3

                if is_accepted:
                    accepted = True
                    final_attempt = attempt
                    _tprint(f"  [EVAL {eval_count}] Score: {overall}/5.0 | "
                            f"Leakage: {leakage}/5 | {dur:.0f}s → ACCEPT"
                            f"{' (retry '+str(attempt-1)+')' if attempt > 1 else ''}")
                    break

                # Last retry — check fallback threshold
                if attempt == MAX_RETRIES + 1:
                    if best_overall >= FALLBACK_THRESHOLD:
                        accepted = True
                        final_attempt = attempt
                        _tprint(f"  [EVAL {eval_count}] Score: {best_overall}/5.0 | "
                                f"{dur:.0f}s → ACCEPT (fallback, best of {attempt} attempts)")
                    else:
                        _tprint(f"  [EVAL {eval_count}] Score: {best_overall}/5.0 | "
                                f"{dur:.0f}s → REJECT (all {attempt} attempts failed)")
                    break

                # Build feedback and retry
                feedback = _build_feedback(evaluation)
                _tprint(f"  [EVAL {eval_count}] Score: {overall}/5.0 | "
                        f"{dur:.0f}s → RETRY {attempt}/{MAX_RETRIES}")

                # Regenerate with feedback
                report_retry, gen_dur = _regenerate_with_feedback(
                    gen_llm, current_report, feedback, attempt + 1
                )
                best_report = report_retry if scores["overall"] <= best_overall else best_report
                # Use the new report for next evaluation
                report = report_retry

            except Exception as e:
                _tprint(f"  [EVAL {eval_count}] attempt {attempt} ERROR: {e}")
                if attempt == MAX_RETRIES + 1:
                    break
                continue

        # Storage decision
        if accepted and best_report and best_scores:
            OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            filename = f"{best_report['patient_id']}_{best_report['modality_code']}_{best_report['scan_date']}.json"
            # Add retry info to metadata
            best_report["generation_metadata"]["total_attempts"] = final_attempt
            (OUTPUT_DIR / filename).write_text(json.dumps(best_report, indent=2))
            reason = "accepted"
            if final_attempt > 1:
                reason = f"accepted (attempt {final_attempt})"
        else:
            reason = f"score {best_overall} < {FALLBACK_THRESHOLD} after {MAX_RETRIES + 1} attempts"

        results.append({
            "report": best_report,
            "evaluation": best_eval or {},
            "accepted": accepted,
            "reason": reason,
            "attempts": final_attempt,
        })


def build_and_run_parallel(cases, threshold):
    """Run generator and evaluator in parallel threads with a shared queue."""
    report_queue = Queue(maxsize=2)
    results = []

    gen_t = threading.Thread(
        target=_generator_thread, args=(cases, report_queue), name="Generator"
    )
    eval_t = threading.Thread(
        target=_evaluator_thread, args=(report_queue, threshold, results), name="Evaluator"
    )

    gen_t.start()
    eval_t.start()
    gen_t.join()
    eval_t.join()

    return results


# ── Data Collection: 6-Tier Imaging Selection ──────────────────────────
#
# For each patient in the Gold cohort, select the best imaging study:
#   T1: Pre-cutoff imaging for the target disease
#   T2: Pre-cutoff imaging on body site relevant to target disease
#   T3: Pre-cutoff any non-dental imaging
#   T4: Pre-cutoff dental imaging (last pre-cutoff resort)
#   T5: Post-cutoff target disease imaging (fallback)
#   T6: Post-cutoff related body site imaging (fallback)
#
# Picks 1 imaging study per patient (the most recent within the tier).
# Generator is told the target disease so it can write findings that
# contribute to the MAS differential diagnosis.

RELEVANT_BODY_SITES = {
    "88805009": ["Thoracic", "Heart", "Chest", "Lung"],         # CHF
    "53741008": ["Thoracic", "Heart", "Chest", "Coronary"],     # Ischemic HD
    "40095003": ["Thoracic", "Heart", "Chest"],                 # Aortic valve
    "44054006": ["Retina", "Eye", "Foot", "Kidney"],            # Diabetes T2
    "59621000": ["Thoracic", "Heart", "Kidney", "Brain"],       # Hypertension
    "237602007": ["Thoracic", "Heart"],                          # Metabolic syndrome
    "431855005": ["Kidney", "Abdomen", "Renal"],                # CKD 1
    "431856006": ["Kidney", "Abdomen", "Renal"],                # CKD 2
    "433144002": ["Kidney", "Abdomen", "Renal"],                # CKD 3
    "46177005":  ["Kidney", "Abdomen", "Renal"],                # ESRD
    "128613002": ["Brain", "Head", "Spine", "Cranial"],         # Cerebral palsy
    "84757009":  ["Brain", "Head", "Cranial"],                  # Epilepsy
    "271737000": ["Thoracic", "Abdomen", "Bone", "Spleen"],     # Anemia
    "254837009": ["Breast", "Thoracic", "Chest", "Axill"],      # Breast cancer
    "64859006":  ["Bone", "Spine", "Hip", "Lumbar", "Femur"],   # Osteoporosis
    "233604007": ["Thoracic", "Chest", "Lung"],                 # Pneumonia
    "239873007": ["Knee", "Joint", "Lower extremity"],          # OA knee
}

GOLD_DIR = Path("data/gold/patient_cases")
COHORT_FILE = Path("data/gold/cohort_1k_patient_ids.json")


def _pick_best_imaging(con, patient_uuid, target_code, cutoff_date):
    """6-tier selection: returns (imaging_row, tier) or (None, None)."""
    sites = RELEVANT_BODY_SITES.get(target_code, [])
    site_filter = ""
    if sites:
        site_filter = " AND (" + " OR ".join(
            f"i.BODYSITE_DESCRIPTION LIKE '%{s}%'" for s in sites
        ) + ")"

    tiers = [
        # T1: pre-cutoff target disease
        (1, f"""
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ? AND e.REASONCODE = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) < ?
            ORDER BY i.DATE DESC LIMIT 1
        """, [patient_uuid, target_code, cutoff_date]),

        # T2: pre-cutoff related body site (non-dental)
        (2, f"""
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) < ?
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%mouth%'
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%oral%'
              {site_filter}
            ORDER BY i.DATE DESC LIMIT 1
        """, [patient_uuid, cutoff_date]) if site_filter else None,

        # T3: pre-cutoff any non-dental
        (3, """
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) < ?
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%mouth%'
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%oral%'
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%dental%'
            ORDER BY i.DATE DESC LIMIT 1
        """, [patient_uuid, cutoff_date]),

        # T4: pre-cutoff dental (last pre-cutoff resort)
        (4, """
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) < ?
            ORDER BY i.DATE DESC LIMIT 1
        """, [patient_uuid, cutoff_date]),

        # T5: post-cutoff target disease
        (5, f"""
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ? AND e.REASONCODE = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) >= ?
            ORDER BY i.DATE ASC LIMIT 1
        """, [patient_uuid, target_code, cutoff_date]),

        # T6: post-cutoff related body site
        (6, f"""
            SELECT i.Id, i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                   i.SOP_DESCRIPTION, SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) AS scan_date,
                   i.ENCOUNTER, e.ENCOUNTERCLASS, e.REASONCODE, e.REASONDESCRIPTION
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            WHERE i.PATIENT = ?
              AND SUBSTRING(CAST(i.DATE AS VARCHAR),1,10) >= ?
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%mouth%'
              AND i.BODYSITE_DESCRIPTION NOT LIKE '%oral%'
              {site_filter}
            ORDER BY i.DATE ASC LIMIT 1
        """, [patient_uuid, cutoff_date]) if site_filter else None,
    ]

    for tier_entry in tiers:
        if tier_entry is None:
            continue
        tier_num, sql, params = tier_entry
        row = con.execute(sql, params).fetchone()
        if row:
            return row, tier_num

    return None, None


def query_cohort_imaging_cases(cohort_file=None):
    """Query imaging cases for a cohort using 6-tier selection.

    Reads each patient's ground_truth.json for target disease + cutoff,
    then picks the best imaging study per patient.

    Args:
        cohort_file: Path to JSON file with patient UUIDs.
                     Defaults to COHORT_FILE (1K cohort).
    """
    con = duckdb.connect(str(DB_PATH), read_only=True)

    src = Path(cohort_file) if cohort_file else COHORT_FILE
    with open(src) as f:
        cohort_uuids = json.load(f)

    results = []
    tier_counts = {1: 0, 2: 0, 3: 0, 4: 0, 5: 0, 6: 0}
    skipped = 0

    for uuid in cohort_uuids:
        gt_path = GOLD_DIR / uuid / "ground_truth.json"
        if not gt_path.exists():
            skipped += 1
            continue

        with open(gt_path) as f:
            gt = json.load(f)

        target_code = gt["target_condition"]["code"]
        target_name = gt["target_condition"]["name"]
        cutoff_date = gt["cutoff_date"]

        row, tier = _pick_best_imaging(con, uuid, target_code, cutoff_date)
        if row is None:
            skipped += 1
            continue

        tier_counts[tier] = tier_counts.get(tier, 0) + 1
        imaging_id, mod_code, modality, body_site, sop, scan_date, \
            encounter_id, enc_class, reason_code, reason_desc = row

        # Patient demographics
        pdata = con.execute("""
            SELECT FIRST || ' ' || LAST, CAST(BIRTHDATE AS VARCHAR),
                   GENDER, CAST(DEATHDATE AS VARCHAR)
            FROM patients WHERE Id = ?
        """, [uuid]).fetchone()

        # Active conditions at scan time (exclude target disease)
        conds = con.execute("""
            SELECT DESCRIPTION FROM conditions
            WHERE PATIENT = ?
              AND CAST(START AS VARCHAR) <= ?
              AND (STOP IS NULL OR CAST(STOP AS VARCHAR) = '' OR CAST(STOP AS VARCHAR) >= ?)
              AND CODE != ?
              AND DESCRIPTION NOT LIKE '%finding%'
              AND DESCRIPTION NOT LIKE '%employment%'
              AND DESCRIPTION NOT LIKE '%education%'
              AND DESCRIPTION NOT LIKE '%housing%'
              AND DESCRIPTION NOT LIKE '%social%'
              AND DESCRIPTION NOT LIKE '%Body mass%'
              AND DESCRIPTION NOT LIKE '%military%'
              AND DESCRIPTION NOT LIKE '%Medication review%'
            ORDER BY START
        """, [uuid, scan_date, scan_date, target_code]).fetchall()

        # Observations from same encounter
        obs = con.execute("""
            SELECT DESCRIPTION, VALUE, UNITS, CATEGORY FROM observations
            WHERE ENCOUNTER = ?
              AND CATEGORY IN ('laboratory', 'vital-signs', 'exam')
            ORDER BY CATEGORY, DESCRIPTION
        """, [encounter_id]).fetchall()

        results.append({
            "patient_id": uuid,
            "imaging_id": imaging_id,
            "scan_date": scan_date,
            "modality_code": mod_code,
            "modality": modality,
            "body_site": body_site,
            "sop": sop,
            "encounter_id": encounter_id,
            "encounter_class": enc_class,
            "ground_truth_code": target_code,
            "ground_truth_disease": target_name,
            "imaging_encounter_reason": reason_desc,
            "tier": tier,
            "patient_name": pdata[0] if pdata else "Unknown",
            "birthdate": pdata[1] if pdata else "",
            "gender": pdata[2] if pdata else "",
            "deathdate": pdata[3] if pdata else None,
            "active_conditions": [r[0] for r in conds],
            "observations": [
                {"test": r[0], "value": r[1], "units": r[2] or "", "category": r[3]}
                for r in obs
            ],
        })

    con.close()
    return results, tier_counts, skipped


def query_imaging_cases(n_patients, diseases=None):
    """Query random imaging cases (for quick tests, not cohort runs)."""
    con = duckdb.connect(str(DB_PATH), read_only=True)

    disease_filter = ""
    if diseases:
        disease_list = ", ".join(f"'{d}'" for d in diseases)
        disease_filter = f"AND e.REASONDESCRIPTION IN ({disease_list})"

    cases = con.execute(f"""
        WITH ranked AS (
            SELECT
                i.PATIENT, i.Id AS imaging_id,
                SUBSTRING(CAST(i.DATE AS VARCHAR), 1, 10) AS scan_date,
                i.MODALITY_CODE, i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
                i.SOP_DESCRIPTION, i.ENCOUNTER, e.ENCOUNTERCLASS,
                e.REASONCODE AS ground_truth_code,
                e.REASONDESCRIPTION AS ground_truth_disease,
                p.FIRST || ' ' || p.LAST AS patient_name,
                CAST(p.BIRTHDATE AS VARCHAR) AS birthdate,
                p.GENDER, CAST(p.DEATHDATE AS VARCHAR) AS deathdate,
                ROW_NUMBER() OVER (
                    PARTITION BY i.PATIENT, e.REASONCODE, i.MODALITY_CODE
                    ORDER BY i.DATE DESC
                ) AS rn
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            JOIN patients p ON i.PATIENT = p.Id
            WHERE e.REASONDESCRIPTION IS NOT NULL
              AND e.REASONDESCRIPTION != ''
              {disease_filter}
        )
        SELECT * FROM ranked WHERE rn = 1
        ORDER BY RANDOM() LIMIT {n_patients}
    """).fetchall()

    results = []
    for row in cases:
        patient_id, imaging_id, scan_date = row[0], row[1], row[2]
        gt_code, encounter_id = row[9], row[7]

        conds = con.execute(f"""
            SELECT DESCRIPTION FROM conditions
            WHERE PATIENT = '{patient_id}'
              AND CAST(START AS VARCHAR) <= '{scan_date}'
              AND (STOP IS NULL OR CAST(STOP AS VARCHAR) = '' OR CAST(STOP AS VARCHAR) >= '{scan_date}')
              AND CODE != '{gt_code}'
              AND DESCRIPTION NOT LIKE '%finding%' AND DESCRIPTION NOT LIKE '%employment%'
              AND DESCRIPTION NOT LIKE '%education%' AND DESCRIPTION NOT LIKE '%housing%'
              AND DESCRIPTION NOT LIKE '%social%' AND DESCRIPTION NOT LIKE '%Body mass%'
              AND DESCRIPTION NOT LIKE '%military%' AND DESCRIPTION NOT LIKE '%Medication review%'
            ORDER BY START
        """).fetchall()

        obs = con.execute(f"""
            SELECT DESCRIPTION, VALUE, UNITS, CATEGORY FROM observations
            WHERE ENCOUNTER = '{encounter_id}'
              AND CATEGORY IN ('laboratory', 'vital-signs', 'exam')
            ORDER BY CATEGORY, DESCRIPTION
        """).fetchall()

        results.append({
            "patient_id": patient_id, "imaging_id": imaging_id,
            "scan_date": scan_date, "modality_code": row[3], "modality": row[4],
            "body_site": row[5], "sop": row[6], "encounter_id": encounter_id,
            "encounter_class": row[8], "ground_truth_code": gt_code,
            "ground_truth_disease": row[10], "patient_name": row[11],
            "birthdate": row[12], "gender": row[13], "deathdate": row[14],
            "active_conditions": [r[0] for r in conds],
            "observations": [
                {"test": r[0], "value": r[1], "units": r[2] or "", "category": r[3]}
                for r in obs
            ],
        })

    con.close()
    return results


# ── Main ────────────────────────────────────────────────────────────────

def run_pipeline(n_patients=None, threshold=DEFAULT_QUALITY_THRESHOLD,
                 diseases=None, cohort=False, cohort_file=None):
    """Run the radiology report pipeline.

    Args:
        n_patients: Number of random patients (quick test mode).
        threshold: Minimum quality score to accept a report.
        diseases: Filter by specific diseases (quick test mode only).
        cohort: If True, run on the full 1K cohort using 6-tier selection.
    """
    pipeline_start = time.time()

    print(f"{'═'*60}")
    print(f"RADIOLOGY REPORT PIPELINE")
    print(f"{'═'*60}")
    print(f"  Generator:  {cfg.LLM_MODEL} (Groq API)")
    print(f"  Evaluator:  {cfg.LLM_EVALUATOR_MODEL} (Groq API)")
    print(f"  Threshold:  {threshold}/5.0")
    print(f"  Mode:       {'Cohort (6-tier)' if cohort else f'Random ({n_patients})'}")
    print(f"  Started:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Collect cases
    if cohort:
        cases, tier_counts, skipped = query_cohort_imaging_cases(cohort_file)
        if not cases:
            print("\nNo imaging cases found in cohort.")
            return

        print(f"\n{'─'*60}")
        print(f"AGENT 1 — DATA COLLECTOR (6-Tier Selection)")
        print(f"{'─'*60}")
        print(f"  Selected: {len(cases)} patients with imaging")
        print(f"  Skipped:  {skipped} patients (no imaging in Synthea)")
        print(f"\n  Tier breakdown:")
        tier_labels = {
            1: "T1 — Target disease pre-cutoff",
            2: "T2 — Related body site pre-cutoff",
            3: "T3 — Any non-dental pre-cutoff",
            4: "T4 — Dental pre-cutoff",
            5: "T5 — Target disease post-cutoff",
            6: "T6 — Related body site post-cutoff",
        }
        for t in range(1, 7):
            if tier_counts.get(t, 0) > 0:
                print(f"    {tier_labels[t]}: {tier_counts[t]}")
    else:
        cases = query_imaging_cases(n_patients or 10, diseases)
        if not cases:
            print("\nNo imaging cases found.")
            return

        print(f"\n{'─'*60}")
        print(f"AGENT 1 — DATA COLLECTOR")
        print(f"{'─'*60}")

    diseases_found = {}
    for c in cases:
        d = c["ground_truth_disease"]
        diseases_found[d] = diseases_found.get(d, 0) + 1
    print(f"\n  {len(cases)} cases across {len(diseases_found)} diseases:")
    for d, n in sorted(diseases_found.items(), key=lambda x: -x[1]):
        print(f"    {n:>3}x  {d}")

    print(f"\n{'─'*60}")
    print(f"PARALLEL EXECUTION — Generator + Evaluator")
    print(f"{'─'*60}")

    # Run generator and evaluator in parallel threads
    results = build_and_run_parallel(cases, threshold)

    # Split results
    accepted = [r for r in results if r["accepted"]]
    rejected = [r for r in results if not r["accepted"]]
    errors = [r["reason"] for r in results if "error" in r.get("reason", "")]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    EVAL_DIR.mkdir(parents=True, exist_ok=True)

    if accepted:
        all_reports = [a["report"] for a in accepted]
        (OUTPUT_DIR / "all_reports.json").write_text(json.dumps(all_reports, indent=2))

        all_evals = [a["evaluation"] for a in accepted]
        (EVAL_DIR / "evaluation_results.json").write_text(json.dumps(all_evals, indent=2))

    if rejected:
        rejected_data = []
        for r in rejected:
            entry = {
                "patient_name": r.get("report", {}).get("patient_name", "unknown"),
                "modality": r.get("report", {}).get("modality", "unknown"),
                "ground_truth": r.get("report", {}).get("generation_metadata", {}).get(
                    "ground_truth_disease", "unknown"),
                "reason": r.get("reason", "unknown"),
            }
            if "evaluation" in r:
                entry["scores"] = r["evaluation"].get("scores", {})
            rejected_data.append(entry)
        (EVAL_DIR / "rejected_reports.json").write_text(json.dumps(rejected_data, indent=2))

    # Summary
    total_time = time.time() - pipeline_start

    print(f"\n{'═'*60}")
    print(f"PIPELINE COMPLETE")
    print(f"{'═'*60}")
    # Retry stats
    first_try = sum(1 for r in accepted if r.get("attempts", 1) == 1)
    retried = sum(1 for r in accepted if r.get("attempts", 1) > 1)
    fallbacks = sum(1 for r in accepted if "fallback" in r.get("reason", ""))

    print(f"  Cases:      {len(cases)}")
    print(f"  Accepted:   {len(accepted)} (≥{threshold})")
    print(f"    1st try:  {first_try}")
    print(f"    Retried:  {retried}")
    print(f"    Fallback: {fallbacks} (≥{FALLBACK_THRESHOLD} after {MAX_RETRIES} retries)")
    print(f"  Rejected:   {len(rejected)}")
    print(f"  Errors:     {len(errors)}")

    if accepted:
        scores = [a["evaluation"]["scores"]["overall"] for a in accepted]
        print(f"  Avg score:  {sum(scores)/len(scores):.1f}/5.0")

        if len(accepted) <= 20:
            print(f"\n  {'Patient':<25} {'Modality':<15} {'Disease':<30} {'Score':>6}")
            print(f"  {'─'*80}")
            for a in accepted:
                r = a["report"]
                s = a["evaluation"]["scores"]["overall"]
                print(f"  {r['patient_name']:<25} {r['modality'][:13]:<15} "
                      f"{a['evaluation']['ground_truth'][:28]:<30} {s:>6.1f}")

    print(f"\n  Time:       {total_time/60:.1f} min ({total_time/max(len(cases),1):.0f}s/case)")
    print(f"  Reports:    {OUTPUT_DIR}/")
    print(f"  Evals:      {EVAL_DIR}/")


def main():
    parser = argparse.ArgumentParser(description="Radiology Report Pipeline")
    parser.add_argument("--patients", type=int, default=10,
                        help="Number of random patients (quick test mode)")
    parser.add_argument("--threshold", type=float, default=DEFAULT_QUALITY_THRESHOLD,
                        help="Minimum score to accept (default: 4.0)")
    parser.add_argument("--diseases", nargs="+", help="Filter by specific diseases")
    parser.add_argument("--cohort", action="store_true",
                        help="Run on cohort using 6-tier imaging selection")
    parser.add_argument("--cohort-file", type=str, default=None,
                        help="Path to cohort JSON file (default: 1K cohort)")
    args = parser.parse_args()

    run_pipeline(
        n_patients=args.patients,
        threshold=args.threshold,
        diseases=args.diseases,
        cohort=args.cohort,
        cohort_file=args.cohort_file,
    )


if __name__ == "__main__":
    main()
