"""Shared evaluation logic — used by both the in-pipeline evaluator and the standalone batch judge.

Eliminates duplication between src/agents/evaluator.py and src/evaluation/llm_judge.py.
"""

import re

JUDGE_PROMPT = """You are a clinical evaluator. Compare the system's diagnoses against the actual disease.

ACTUAL DISEASE: {target_disease}

SYSTEM'S TOP 5:
{differential}

Step 1: Check each diagnosis. Is it DIRECT, INDIRECT, or MISS?

DIRECT = the system names the target disease (with or without an
etiology / cause qualifier). If the system's diagnosis explicitly
includes the target disease, it is DIRECT even when the diagnosis
also names the underlying cause. Synonyms and commitments to the
target stage also count as DIRECT.
  "Coronary artery disease" = "Ischemic heart disease"
  "ESRD on dialysis" = "End-stage renal disease"
  "Essential hypertension uncontrolled" = "Essential hypertension"
  "Metabolic syndrome with dyslipidemia" = "Metabolic syndrome X"
  "HFrEF" or "HFpEF" = "Congestive heart failure"
  "Diabetic nephropathy stage 5 CKD" = "End-stage renal disease"
  "Atherosclerotic CVD" = "Ischemic heart disease"
  "CKD stage 3 from diabetes" = "Chronic kidney disease stage 3"
  "Diabetic nephropathy leading to ESRD" = "End-stage renal disease" (DIRECT — names target)
  "Hypertensive nephrosclerosis culminating in ESRD" = "End-stage renal disease" (DIRECT — names target)
  "Combined diabetic-hypertensive nephropathy leading to end-stage renal disease" = "End-stage renal disease" (DIRECT — names target)
  "Atherosclerotic CAD with prior MI" = "Ischemic heart disease" (DIRECT — CAD = IHD)

INDIRECT = the target disease is NOT explicitly named by the system,
but the system named a cause, consequence, precursor, or subtype:
  "CKD stage 4" for ESRD = INDIRECT (target stage 5 not committed to)
  "CKD stage 3" for ESRD = INDIRECT (precursor only)
  "Diabetic nephropathy" alone for ESRD = INDIRECT (cause only, target not named)
  "Focal segmental glomerulosclerosis" alone for ESRD = INDIRECT (cause only)
  "Hypertensive nephrosclerosis" alone for ESRD = INDIRECT (cause only)
  "Myocardial infarction" for IHD = INDIRECT (acute event, IHD not named)
  "Cardiorenal syndrome" for heart failure = INDIRECT (consequence)
  "Prediabetes" for diabetes T2 = INDIRECT (precursor)
  "Dyslipidemia" for metabolic syndrome = INDIRECT (component, target not named)
  "Hypertensive CKD" for hypertension = INDIRECT (consequence)

MISS = no clinical connection.

Step 2: Pick the BEST match (DIRECT > INDIRECT). Report its rank.

Respond with EXACTLY these 5 lines:
FOUND: YES or NO
MATCH_TYPE: DIRECT or INDIRECT or MISS
RANK: [1-5 or 0]
MATCHED_DIAGNOSIS: [name from list or NONE]
REASON: [one sentence]"""


def format_differential(differential: list) -> str:
    """Format a differential diagnosis list into text for the judge prompt."""
    text = ""
    for d in differential[:5]:
        if isinstance(d, dict):
            text += f"#{d.get('rank', '?')} {d.get('name', '?')} (P={d.get('probability', '?')})\n"
    return text


def strip_think_tags(text: str) -> str:
    """Remove <think>...</think> tags (closed and unclosed) from LLM output."""
    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
    text = re.sub(r"<think>.*", "", text, flags=re.DOTALL)
    return text.strip()


def parse_judge_response(text: str) -> dict:
    """Parse the 5-line structured response from the judge LLM.

    Returns dict with: found, match_type, rank, matched_diagnosis, reason.
    """
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
            if "INDIRECT" in val:
                match_type = "INDIRECT"
            elif "DIRECT" in val:
                match_type = "DIRECT"
            else:
                match_type = "MISS"
        elif line.upper().startswith("RANK:"):
            try:
                rank = int(re.search(r"\d+", line.split(":", 1)[1]).group())
            except (AttributeError, ValueError, IndexError):
                rank = 0
        elif line.upper().startswith("MATCHED_DIAGNOSIS:"):
            matched = line.split(":", 1)[1].strip()
            if matched.upper() == "NONE":
                matched = "NONE"
        elif line.upper().startswith("REASON:"):
            reason = line.split(":", 1)[1].strip()

    # Fix inconsistency: if match_type is DIRECT or INDIRECT, found must be YES
    if match_type in ("DIRECT", "INDIRECT") and found == "NO":
        found = "YES"

    return {
        "found": found,
        "match_type": match_type,
        "rank": rank,
        "matched_diagnosis": matched,
        "reason": reason,
    }
