"""LLM Evaluator Agent — Compares MAS diagnosis against ground truth.

Reads: agent_outputs.final_diagnosis, patient_context (for ground truth lookup)
Writes: agent_outputs.evaluation

Runs as a LangGraph node inside the pipeline, not as a separate post-step.
Uses a configurable evaluator model (default: qwen/qwen3-32b via LLM_EVALUATOR_MODEL env var).
"""

import json
import re
import time
import structlog
from pathlib import Path
from langchain_core.messages import HumanMessage

from src.llm.adapter import get_evaluator_llm

logger = structlog.get_logger()

from src.config import cfg

GOLD_DIR = cfg.GOLD_DIR

JUDGE_PROMPT = """You are a clinical evaluator. Compare the system's diagnoses against the actual disease.

ACTUAL DISEASE: {target_disease}

SYSTEM'S TOP 5:
{differential}

Step 1: Check each diagnosis. Is it DIRECT, INDIRECT, or UNRELATED?

DIRECT = same disease, different name:
  "Coronary artery disease" = "Ischemic heart disease"
  "ESRD on dialysis" = "End-stage renal disease"
  "Essential hypertension uncontrolled" = "Essential hypertension"
  "Metabolic syndrome with dyslipidemia" = "Metabolic syndrome X"
  "HFrEF" or "HFpEF" = "Congestive heart failure"
  "Diabetic nephropathy stage 5 CKD" = "End-stage renal disease"
  "Atherosclerotic CVD" = "Ischemic heart disease"
  "CKD stage 3 from diabetes" = "Chronic kidney disease stage 3"

INDIRECT = cause, consequence, precursor, or subtype:
  "CKD stage 4" for ESRD = INDIRECT (precursor)
  "Diabetic nephropathy" for ESRD = INDIRECT (cause)
  "Focal segmental glomerulosclerosis" for ESRD = INDIRECT (cause)
  "Myocardial infarction" for IHD = INDIRECT (acute event)
  "Prediabetes" for diabetes T2 = INDIRECT (precursor)
  "Hypertensive CKD" for hypertension = INDIRECT (consequence)

UNRELATED = no clinical connection.

Step 2: Pick the BEST match (DIRECT > INDIRECT). Report its rank.

Respond with EXACTLY these 5 lines:
FOUND: YES or NO
MATCH_TYPE: DIRECT or INDIRECT or MISS
RANK: [1-5 or 0]
MATCHED_DIAGNOSIS: [name from list or NONE]
REASON: [one sentence]"""


def evaluate_node(state: dict) -> dict:
    """LangGraph node function — evaluates the final diagnosis against ground truth."""
    agent_outputs = state.get("agent_outputs", {})
    ctx = state.get("patient_context", {})
    ehr_case = ctx.get("ehr_case", {})
    patient_uuid = ehr_case.get("patient_uuid", "")

    final = agent_outputs.get("final_diagnosis", {}) or agent_outputs.get("diagnostic_reasoning", {})
    differential = final.get("differential", [])

    # Load ground truth
    gt_path = GOLD_DIR / patient_uuid / "ground_truth.json"
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

    # Format differential
    diff_text = ""
    for d in differential[:5]:
        if isinstance(d, dict):
            diff_text += f"#{d.get('rank', '?')} {d.get('name', '?')} (P={d.get('probability', '?')})\n"

    prompt = JUDGE_PROMPT.format(target_disease=target, differential=diff_text)

    start = time.time()

    llm = get_evaluator_llm()
    response = llm.invoke([HumanMessage(content=prompt)])
    text = response.content
    # Strip think tags — handle both closed and unclosed
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    text = text.strip()

    # Parse structured response
    found = "NO"
    match_type = "MISS"
    rank = 0
    matched = "NONE"
    reason = ""

    for line in text.split("\n"):
        line = line.strip()
        if line.upper().startswith("FOUND:"):
            found = "YES" if "YES" in line.upper() else "NO"
        elif line.upper().startswith("MATCH_TYPE:"):
            val = line.split(":", 1)[1].strip().upper()
            if "DIRECT" in val:
                match_type = "DIRECT"
            elif "INDIRECT" in val:
                match_type = "INDIRECT"
            else:
                match_type = "MISS"
        elif line.upper().startswith("RANK:"):
            try:
                rank = int(re.search(r"\d+", line.split(":", 1)[1]).group())
            except (AttributeError, ValueError):
                rank = 0
        elif line.upper().startswith("MATCHED_DIAGNOSIS:"):
            matched = line.split(":", 1)[1].strip()
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    # Fix: if match_type is DIRECT or INDIRECT, found should be YES
    if match_type in ("DIRECT", "INDIRECT") and found == "NO":
        found = "YES"

    duration_ms = int((time.time() - start) * 1000)

    eval_result = {
        "uuid": patient_uuid,
        "target": target,
        "found": found,
        "match_type": match_type,
        "rank": rank,
        "matched_diagnosis": matched,
        "reason": reason,
        "primary_diagnosis": final.get("primary_diagnosis", "?"),
    }

    # Save to disk
    eval_dir = cfg.MAS_RESULTS_DIR / patient_uuid
    eval_dir.mkdir(parents=True, exist_ok=True)
    (eval_dir / "evaluation.json").write_text(json.dumps(eval_result, indent=2))

    logger.info("evaluation_complete", patient=patient_uuid[:12],
                match_type=match_type, rank=rank)

    return {
        "agent_outputs": {"evaluation": eval_result},
        "execution_trace": [{"agent_id": "evaluation", "status": "success",
                              "execution_ms": duration_ms, "error": None}],
    }
