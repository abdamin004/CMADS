"""LLM Evaluator Agent — Compares MAS diagnosis against ground truth.

Reads: agent_outputs.final_diagnosis, patient_context (for ground truth lookup)
Writes: agent_outputs.evaluation

Runs as a LangGraph node inside the pipeline, not as a separate post-step.
Uses a configurable evaluator model (default: qwen/qwen3-32b via LLM_EVALUATOR_MODEL env var).
"""

import json
import time
import structlog
from langchain_core.messages import HumanMessage

from src.config import cfg
from src.llm.adapter import get_evaluator_llm
from src.evaluation.judge_common import (
    JUDGE_PROMPT, format_differential, strip_think_tags, parse_judge_response,
)

logger = structlog.get_logger()


def evaluate_node(state: dict) -> dict:
    """LangGraph node function — evaluates the final diagnosis against ground truth."""
    agent_outputs = state.get("agent_outputs", {})
    ctx = state.get("patient_context", {})
    ehr_case = ctx.get("ehr_case", {})
    patient_uuid = ehr_case.get("patient_uuid", "")

    # --- Early skip for test runs (no ground truth) ---
    # Tester-journey patients have no ground truth file and no target condition
    # in patient_context. Skip the evaluator entirely so no LLM cost is
    # incurred and the trace shows status=skipped rather than error.
    # Treatment Planning also gracefully skips on non-DIRECT, so this is safe.
    gt_in_ctx = (ctx.get("ground_truth") or {})
    target_from_ctx = (gt_in_ctx.get("target_condition") or {}).get("name")

    gt_path = cfg.GOLD_DIR / patient_uuid / "ground_truth.json"

    if not target_from_ctx and not gt_path.exists():
        logger.info("evaluator_skipped_no_gt", patient=patient_uuid[:12])
        return {
            "agent_outputs": {"evaluation": {
                "found": "NO", "match_type": "SKIPPED", "rank": 0,
                "matched_diagnosis": "NONE",
                "reason": "No ground truth — evaluator skipped (test run)",
            }},
            "execution_trace": [{"agent_id": "evaluation", "status": "skipped",
                                  "execution_ms": 0, "error": None}],
        }

    # Load ground truth from file (Gold-layer / known-patient runs)
    if not gt_path.exists():
        logger.warning("evaluator_no_gt", patient=patient_uuid[:12])
        return {
            "agent_outputs": {"evaluation": {
                "found": "NO", "match_type": "MISS", "rank": 0,
                "matched_diagnosis": "NONE", "reason": "No ground truth file",
            }},
            "execution_trace": [{"agent_id": "evaluation", "status": "error",
                                  "execution_ms": 0, "error": "No ground truth"}],
        }

    gt = json.loads(gt_path.read_text())
    target = gt["target_condition"]["name"]

    final = agent_outputs.get("final_diagnosis") or agent_outputs.get("diagnostic_reasoning") or {}
    differential = final.get("differential", [])

    if not differential:
        return {
            "agent_outputs": {"evaluation": {
                "uuid": patient_uuid, "target": target,
                "found": "NO", "match_type": "MISS", "rank": 0,
                "matched_diagnosis": "NONE", "reason": "No differential produced",
            }},
            "execution_trace": [{"agent_id": "evaluation", "status": "success",
                                  "execution_ms": 0, "error": None}],
        }

    diff_text = format_differential(differential)
    prompt = JUDGE_PROMPT.format(target_disease=target, differential=diff_text)

    start = time.time()
    llm = get_evaluator_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    text = strip_think_tags(response.content)
    result = parse_judge_response(text)
    duration_ms = int((time.time() - start) * 1000)

    eval_result = {
        "uuid": patient_uuid,
        "target": target,
        **result,
        "primary_diagnosis": final.get("primary_diagnosis", "?"),
    }

    logger.info("evaluation_complete", patient=patient_uuid[:12],
                match_type=result["match_type"], rank=result["rank"])

    return {
        "agent_outputs": {"evaluation": eval_result},
        "execution_trace": [{"agent_id": "evaluation", "status": "success",
                              "execution_ms": duration_ms, "error": None}],
    }
