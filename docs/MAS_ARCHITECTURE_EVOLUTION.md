# MAS Architecture Evolution

## CMADS — From Single LLM Call to Adaptive Multi-Agent Pipeline

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Documents the iterative development of the diagnostic pipeline, from initial design through each improvement iteration |

---

## 1. Evolution Summary

The MAS diagnostic pipeline went through 4 major iterations, each addressing a specific limitation discovered through testing:

| Version | Architecture | Problem Solved |
|---------|-------------|----------------|
| v1 | Single LLM call per agent | Baseline — agents anchor on most obvious finding |
| v2 | Fixed 3-call per agent | Agents analyse before outputting — reduces anchoring |
| v3 | Fixed 5-call diagnostic + self-critique | Self-critique catches missed diagnoses |
| v4 | Adaptive loop with confidence threshold | Stops early for easy cases, refines for hard cases |

---

## 2. Version 1: Single LLM Call (Baseline)

### Architecture
```
EHR Analyst (1 call) ──→ Diagnostic Reasoning (1 call) ──→ END
Lab Interpreter (1 call) ↗
```

### How It Worked
Each agent received patient data and produced output in a single LLM call. The Diagnostic Agent received the EHR and Lab outputs and generated a differential diagnosis in one pass.

### Problem Discovered
The Diagnostic Agent **anchored on the most obvious finding** and missed the broader clinical picture. For a patient with IHD (ischemic heart disease), the agent focused entirely on CKD (the dominant lab finding) and never considered cardiovascular risk factors.

**Test result:** Target disease found in 0% of test cases for that patient.

### Lesson Learned
A single LLM call processes too much information at once. The model latches onto the most salient finding and builds the differential around it, ignoring other patterns.

---

## 3. Version 2: Fixed 3-Call Per Agent

### Architecture
```
EHR Analyst (3 calls) ──→ Diagnostic Reasoning (3 calls) ──→ END
Lab Interpreter (3 calls) ↗
```

### How It Worked
Each agent now makes 3 LLM calls:
1. **Analysis** — "Analyse the data thoroughly. Don't produce JSON yet."
2. **Structure** — "Convert your analysis into structured JSON."
3. **Review** — "Check your output — did you miss anything?"

### Why 3 Calls
- Call 1 forces the LLM to **organise evidence** before diagnosing
- Call 2 converts free-text analysis into structured output
- Call 3 catches obvious omissions through self-review

### Improvement
The separation of analysis from output prevented anchoring — the model explored all patterns in Call 1 before committing to a differential in Call 2.

---

## 4. Version 3: Fixed 5-Call Diagnostic with Self-Critique

### Architecture
```
EHR Analyst (3 calls) ──→ Diagnostic Reasoning (5 calls) ──→ END
Lab Interpreter (3 calls) ↗
```

### Diagnostic Agent's 5 Calls
1. **Evidence Synthesis** — organise findings into clinical patterns (cardiovascular, renal, metabolic, etc.)
2. **Hypothesis Generation** — generate 8-10 candidate diagnoses broadly
3. **Differential Ranking** — rank with probabilities and evidence mapping
4. **Self-Critique** — "Are you anchoring? Did you miss IHD, CHF, or diabetes given the risk factors?"
5. **Final Output** — produce structured JSON incorporating critique

### The Self-Critique Prompt
The self-critique call explicitly asks the model to check for common missed diagnoses:
```
"Did you miss ischemic heart disease, heart failure, peripheral vascular disease,
stroke, diabetes progression, or thyroid disorders given the risk factors?"
```

### Improvement
The self-critique step caught the IHD that Version 1 and 2 missed. The target disease moved from "not found" to #1 in the differential with P=0.29.

### Problem Discovered
The self-critique always ran — even when the first differential was already correct. Easy patients (ESRD with eGFR 12) wasted 2 extra calls on unnecessary critique.

---

## 5. Version 4: Adaptive Loop with Confidence Threshold (Current)

### Architecture
```
Stage 1 (parallel):
  EHR Analyst (3 calls) + Lab Interpreter (3 calls)
      ↓
Stage 2 (adaptive):
  Diagnostic Reasoning (3 fixed + 0-6 adaptive calls)
      ↓
Stage 3:
  Clinical Reviewer (3 calls)
      ↓
Stage 4:
  Diagnostic Refiner (1 call)
```

### Adaptive Loop Logic
```
Fixed calls (always):
  1. Evidence synthesis
  2. Hypothesis generation
  3. Initial ranking

Adaptive loop (repeat until confident):
  4. Self-critique → extract confidence (0-100)
     → If confidence ≥75: STOP
     → If confidence <75: continue
  5. Refine differential based on critique
     → Loop back to step 4
  Max 3 rounds (safety limit)

Final call (always):
  6. Produce structured JSON
```

### Confidence Extraction
The self-critique prompt asks the LLM to rate its own confidence:
```
"CONFIDENCE: On a scale of 0-100, how confident are you in this differential?"
```

The code extracts this number using regex patterns that handle multiple formats: "confidence: 85", "85%", "85/100", "confidence score of 85".

### Stopping Conditions
The loop stops when:
- Confidence ≥75, OR
- The LLM says "differential is adequate" (or similar phrases), OR
- Max 3 rounds reached

### Configuration
```python
MAX_REASONING_ROUNDS = 3      # Safety limit
CONFIDENCE_THRESHOLD = 75     # Stop when confident enough
```

### Behaviour Observed
- Easy patients (ESRD): confidence 85 on round 1 → 5 total calls
- Hard patients (IHD): confidence 68→78 over 2 rounds → 8 total calls
- Very hard patients: hit max 3 rounds → 11 total calls

---

## 6. Clinical Reviewer and Refiner (Added in v4)

### Clinical Reviewer Agent
An adversarial agent that independently re-analyses the raw evidence and verifies each diagnosis:

**3 LLM calls:**
1. **Independent re-analysis** — "Ignore the diagnostic conclusions. Look at the raw data with fresh eyes."
2. **Per-diagnosis verification** — "Does the evidence actually support each diagnosis? Adjust probabilities."
3. **Structured output** — JSON with per-diagnosis confidence, evidence strength, concerns

**Why it was added:** The Diagnostic Agent can produce confident but wrong differentials. The Reviewer catches:
- Diagnoses with no real evidence (inflated probabilities)
- Missing common conditions given the risk factors
- Critical lab findings not addressed by any diagnosis

### Diagnostic Refiner Agent
Merges the Diagnostic Agent's and Reviewer's outputs into a final differential:

**1 LLM call:**
- Takes both perspectives
- Removes unsupported diagnoses
- Promotes what the Reviewer recommended
- Produces the final answer

---

## 7. JSON Parsing Challenges

### Problem: Invalid JSON from LLM
The local Ollama model (gpt-oss:120b) frequently produced invalid JSON:
- Single quotes instead of double quotes (`'key': 'value'`)
- Trailing commas before closing braces
- Unescaped newlines in string values

### Solutions Implemented

1. **JSON repair function** — Fixes common formatting errors:
   - Trailing comma removal
   - Single-to-double quote conversion
   - Missing comma insertion
   - Unescaped newline fix

2. **Parse retry** — When JSON parsing fails, the agent asks the LLM to fix its own output:
   ```
   "Your previous response had invalid JSON. Error: [error].
   Please output ONLY valid JSON."
   ```

3. **Groq json_mode** — When using Groq API, structured output calls use `response_format: {"type": "json_object"}` which forces valid JSON. Free-text analysis calls use normal mode.

4. **Fallback** — If json_mode fails 3 times (Groq returns "Failed to validate JSON"), the system falls back to non-json_mode and lets the repair function handle parsing.

### Dual LLM Approach
Each agent creates two LLM instances:
- `llm` — normal mode for free-text analysis calls
- `json_llm` — json_mode enabled for structured output calls

---

## 8. Pydantic Schema Evolution

### Initial: Strict Required Fields
All fields were required — if the LLM omitted any field, the entire output failed validation.

### Current: Defaults for Robustness
Fields that the LLM sometimes omits have defaults:
```python
class DiagnosticOutput(BaseModel):
    differential: list[Diagnosis] = Field(default_factory=list)  # was required
    primary_diagnosis: str = Field(default="")                    # was required
    primary_probability: float = Field(default=0.0)               # was required
    clinical_reasoning_summary: str = Field(default="")           # was required
```

This allows partial results to pass validation — a differential with 4 diagnoses instead of 5 is still useful.

### Auto-Fill Logic
If the LLM produces a differential but forgets `primary_diagnosis`, the Refiner auto-fills it from the first diagnosis:
```python
if not result.get("primary_diagnosis") and result.get("differential"):
    result["primary_diagnosis"] = result["differential"][0]["name"]
    result["primary_probability"] = result["differential"][0]["probability"]
```

---

## 9. Performance Comparison

### LLM Calls Per Patient

| Version | EHR | Lab | Diagnostic | Reviewer | Refiner | Total |
|---------|:---:|:---:|:----------:|:--------:|:-------:|:-----:|
| v1 | 1 | 1 | 1 | — | — | 3 |
| v2 | 3 | 3 | 3 | — | — | 9 |
| v3 | 3 | 3 | 5 | — | — | 11 |
| v4 (easy) | 3 | 3 | 5 | 3 | 1 | 15 |
| v4 (hard) | 3 | 3 | 8 | 3 | 1 | 18 |

### Timing (Groq API)

| Component | Time |
|-----------|------|
| Per LLM call | ~2-8s |
| Per patient (easy) | ~90s |
| Per patient (hard) | ~150s |
| Stage 1 (parallel) | ~15s |
| Stage 2 (adaptive) | ~40-90s |
| Stage 3 (reviewer) | ~25s |
| Stage 4 (refiner) | ~10s |

### Cost (Groq API, gpt-oss-120b at $0.90/M tokens)

| Scenario | Est. Cost |
|----------|----------|
| 1 patient | ~$0.06 |
| 100 patients | ~$6 |
| 1,000 patients | ~$60 |

---

## 10. Key Design Decisions

### Why Multi-Agent, Not Single LLM Call?
A single call with "diagnose this patient" anchors on the most obvious finding. The multi-agent approach forces structured reasoning: evidence organisation → hypothesis generation → ranking → critique → verification.

### Why Adaptive Rounds, Not Fixed?
Fixed rounds waste calls on easy patients and under-serve hard patients. The adaptive approach uses clinical reasoning — a doctor doesn't spend the same time on every patient.

### Why a Separate Reviewer?
The Diagnostic Agent can be confidently wrong. The Reviewer goes back to raw data independently and catches what the Diagnostic Agent missed. It also provides per-diagnosis confidence scores.

### Why a Refiner?
The Diagnostic Agent and Reviewer may disagree. The Refiner merges perspectives into one final answer — it doesn't re-diagnose, it resolves.

### Why Groq Over Local Ollama?
Same model (gpt-oss-120b), 10x faster, $0.06/patient. Local Ollama: ~16 min/patient. Groq: ~2 min/patient. The quality is identical — confirmed by head-to-head comparison.

---

## 11. Version 5: Bias Removal + Treatment Planning

### Problem Discovered
Agent prompts explicitly mentioned the 8 target diseases (IHD, CHF, CKD, diabetes, etc.). This meant the LLM was biased toward diagnosing those specific diseases rather than reasoning from evidence. This was detected when reviewing batch 1 results — the agents correctly diagnosed target diseases but the reasoning felt "guided" rather than genuine.

### Changes Made

**Prompt Debiasing:**
- Removed all disease-specific mentions from EHR Analyst, Lab Interpreter, and Diagnostic prompts
- Replaced disease-specific instructions with organ-system reasoning (e.g., "consider cardiovascular risk factors" instead of "check for IHD")
- Lab Interpreter reference ranges use "borderline" instead of "prediabetes"
- Diagnostic Agent uses "root cause vs consequence" ranking rule without naming specific diseases

**Treatment Planning Agent Added (Stage 6):**
- Only runs on DIRECT matches (reads evaluation.json)
- Searches Qdrant vector database for top 3 NICE guidelines matching the diagnosed disease
- Uses BioLORD-2023 medical embeddings (768-dim) for semantic search
- 2-call architecture: pharmacist analysis → structured JSON output
- Checks drug interactions against current medications
- Checks contraindications against patient conditions
- Generates assumptions_warnings for missing data the NICE guideline requires

**LLM Evaluator Added (Stage 5):**
- Uses Qwen3 32B (separate from reasoning model for independence)
- Compares final differential against Synthea ground truth
- Outputs DIRECT / INDIRECT / MISS classification
- Runs inside the LangGraph pipeline, not as a separate post-step

### Architecture (Final)
```
Stage 1 (parallel): EHR Analyst + Lab Interpreter
    ↓
Stage 2: Diagnostic Reasoning (adaptive, max 3 rounds)
    ↓
Stage 3: Clinical Reviewer (adversarial)
    ↓
Stage 4: Diagnostic Refiner (merge)
    ↓
Stage 5: LLM Evaluator (ground truth comparison)
    ↓
Stage 6: Treatment Planning (DIRECT matches only, NICE guidelines via Qdrant)
```

### Impact
- Batch 1 (biased prompts): 86% DIRECT
- Batch 2 (partially biased): 94% DIRECT
- Batch 3+ (fully unbiased): 100% DIRECT on test set of 5 patients
- Treatment plans generated for all DIRECT matches with NICE guideline citations

---

*— MAS Architecture Evolution v2.0 • March 2026 • CMADS*
