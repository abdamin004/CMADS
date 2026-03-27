# MAS Output Format & Storage

## CMADS — What the Pipeline Produces and Where It's Stored

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Documents the output structure of the MAS pipeline and the evaluation results |

---

## 1. Storage Structure

```
data/gold/mas_results/
├── {patient_uuid}/
│   ├── ehr_analyst.json             ← Stage 1: EHR clinical summary
│   ├── lab_interpreter.json         ← Stage 1: Lab findings
│   ├── diagnostic_reasoning.json    ← Stage 2: Initial differential
│   ├── clinical_reviewer.json       ← Stage 3: Verification
│   ├── final_diagnosis.json         ← Stage 4: Refined differential (Refiner Agent)
│   ├── evaluation.json              ← Stage 5: LLM judge result (DIRECT/INDIRECT/MISS)
│   ├── treatment_planning.json      ← Stage 6: NICE guideline treatment plan (DIRECT only)
│   └── execution_trace.json         ← Timing and status per agent
│
├── run_summary.json                 ← Cohort-level pipeline stats
└── evaluation_summary.json          ← All evaluations + accuracy rates
```

---

## 2. Per-Agent Output Schemas

### 2.1 ehr_analyst.json

```json
{
  "chief_complaint": "Progressive renal dysfunction with cardiac risk factors",
  "history_of_present_illness": "67-year-old male with...",
  "active_problems": [
    {
      "name": "Essential hypertension",
      "snomed_code": "59621000",
      "onset_date": "2010-03-15",
      "status": "active",
      "clinical_significance": "high"
    }
  ],
  "past_medical_history": "History of...",
  "active_medications": [
    {
      "name": "lisinopril 10 MG Oral Tablet",
      "purpose": "Hypertension",
      "relevance": "significant"
    }
  ],
  "allergies": [],
  "social_determinants": "",
  "risk_factor_summary": "Cardiovascular: HIGH risk due to...",
  "data_quality_flags": [
    {"field": "eGFR", "issue": "Missing latest eGFR value"}
  ],
  "clinical_impression": "Elderly male with multiple chronic conditions..."
}
```

### 2.2 lab_interpreter.json

```json
{
  "findings": [
    {
      "test_name": "Creatinine",
      "value": "6.8 mg/dL",
      "reference_range": "0.6-1.2 mg/dL",
      "classification": "abnormal",
      "trend": "increasing",
      "severity": 5,
      "clinical_note": "Severely elevated, indicates kidney failure",
      "panel_context": "Renal panel: elevated creatinine with low eGFR"
    }
  ],
  "critical_alerts": ["Creatinine critically elevated at 6.8 mg/dL"],
  "panel_patterns": [
    {
      "panel_name": "Renal Panel",
      "interpretation": "Severe renal dysfunction pattern",
      "contributing_tests": ["Creatinine", "eGFR", "BUN"]
    }
  ],
  "trending_concerns": ["Creatinine rising over 3 years"],
  "overall_assessment": "Dominant renal dysfunction with...",
  "data_gaps": ["Serum albumin missing", "Urine protein not available"]
}
```

### 2.3 diagnostic_reasoning.json

```json
{
  "differential": [
    {
      "rank": 1,
      "name": "End-stage renal disease",
      "icd10": "N18.6",
      "snomed": "46177005",
      "probability": 0.40,
      "confidence": "high",
      "supporting_evidence": [
        {"source": "lab_interpreter", "finding": "eGFR 12 mL/min", "strength": "strong"},
        {"source": "ehr_analyst", "finding": "CKD stage 4 in conditions", "strength": "strong"}
      ],
      "reasoning": "eGFR below 15 with years of progressive decline..."
    }
  ],
  "primary_diagnosis": "End-stage renal disease",
  "primary_probability": 0.40,
  "clinical_reasoning_summary": "The clinical picture is dominated by...",
  "unresolved_findings": ["Elevated platelets unexplained"],
  "recommended_workup": ["Renal ultrasound", "Nephrology referral"]
}
```

### 2.4 clinical_reviewer.json

```json
{
  "diagnosis_verifications": [
    {
      "diagnosis": "End-stage renal disease",
      "original_probability": 0.40,
      "verified_probability": 0.45,
      "confidence_score": 90,
      "evidence_strength": "strong",
      "supporting_evidence_verified": ["eGFR 12 confirmed", "Creatinine 6.8 confirmed"],
      "evidence_gaps": ["No renal biopsy data"],
      "concerns": [],
      "verdict": "supported"
    }
  ],
  "overall_confidence": 85,
  "consistency_checks": [
    {"area": "Lab-diagnosis alignment", "status": "consistent", "detail": "..."}
  ],
  "critical_findings_addressed": ["Creatinine 6.8 explained by ESRD"],
  "critical_findings_missed": [],
  "top_concerns": ["Missing nephrology referral documentation"],
  "recommended_primary": "End-stage renal disease",
  "recommended_primary_confidence": 90,
  "review_summary": "The differential is well-supported..."
}
```

### 2.5 final_diagnosis.json

Same schema as `diagnostic_reasoning.json` — produced by the **Refiner Agent** which merges the Diagnostic Agent's differential with the Clinical Reviewer's adjustments. This is the definitive diagnostic output used by downstream agents.

### 2.6 treatment_planning.json (DIRECT matches only)

Only generated when the LLM Evaluator classifies the diagnosis as a DIRECT match. Uses NICE clinical guidelines retrieved from Qdrant vector database.

```json
{
  "primary_diagnosis_treated": "Heart failure with reduced ejection fraction",
  "nice_guideline_used": "NG106",
  "medications": [
    {
      "medication": "Ramipril 2.5mg",
      "drug_class": "ACE inhibitor",
      "dose": "2.5mg once daily, titrate to 10mg over 4-6 weeks",
      "duration": "Lifelong — review annually",
      "purpose": "Reduce mortality and hospitalisation in HFrEF",
      "nice_justification": "NG106: First-line for all HFrEF patients",
      "line": "first_line"
    }
  ],
  "interactions_checked": [
    {
      "drug_pair": ["Ramipril", "Spironolactone"],
      "interaction": "Both raise potassium — risk of hyperkalaemia",
      "severity": "moderate",
      "action": "Monitor potassium within 1 week of starting"
    }
  ],
  "contraindications": [
    {
      "drug": "Verapamil",
      "reason": "Negative inotrope — contraindicated in HFrEF per NG106",
      "alternative": "Use bisoprolol (beta-blocker) instead"
    }
  ],
  "assumptions_warnings": [
    "eGFR unknown — assumed normal for ACE-I dosing; verify before prescribing",
    "LVEF not available — cannot confirm HFrEF vs HFpEF classification",
    "Allergy status unknown — cannot verify drug allergy safety"
  ],
  "treatment_summary": "NICE NG106-based quadruple therapy for HFrEF..."
}
```

### 2.7 execution_trace.json

```json
{
  "patient_uuid": "e5373d98-5dd...",
  "duration_s": 125.3,
  "agents": [
    {"agent_id": "ehr_analyst", "status": "success", "execution_ms": 18000, "error": null},
    {"agent_id": "lab_interpreter", "status": "success", "execution_ms": 22000, "error": null},
    {"agent_id": "diagnostic_reasoning", "status": "success", "execution_ms": 55000, "error": null},
    {"agent_id": "clinical_reviewer", "status": "success", "execution_ms": 20000, "error": null},
    {"agent_id": "final_diagnosis", "status": "success", "execution_ms": 8000, "error": null},
    {"agent_id": "evaluation", "status": "success", "execution_ms": 2000, "error": null},
    {"agent_id": "treatment_planning", "status": "success", "execution_ms": 21000, "error": null}
  ]
}
```

### 2.7 evaluation.json

```json
{
  "uuid": "e5373d98-5dd...",
  "target": "End-stage renal disease (disorder)",
  "found": "YES",
  "match_type": "DIRECT",
  "rank": 1,
  "matched_diagnosis": "End-stage renal disease",
  "reason": "Exact disease identified as primary diagnosis",
  "primary_diagnosis": "End-stage renal disease"
}
```

---

## 3. Cohort-Level Outputs

### 3.1 run_summary.json

```json
{
  "cohort_file": "data/gold/cohort_verified.json",
  "total_patients": 23,
  "succeeded": 22,
  "failed": 1,
  "total_time_s": 2875.5,
  "avg_time_per_patient_s": 125.0,
  "patients": [
    {"uuid": "...", "status": "success", "duration_s": 118.2, "error": null},
    {"uuid": "...", "status": "error", "duration_s": 5.1, "error": "LLM timeout"}
  ]
}
```

### 3.2 evaluation_summary.json

```json
{
  "summary": {
    "total": 23,
    "direct": 12,
    "indirect": 6,
    "miss": 5,
    "found_rate": "78%",
    "direct_rate": "52%",
    "duration_s": 46.2
  },
  "evaluations": [
    {"uuid": "...", "target": "ESRD", "found": "YES", "match_type": "DIRECT", "rank": 1, ...},
    {"uuid": "...", "target": "CHF", "found": "YES", "match_type": "INDIRECT", "rank": 3, ...}
  ]
}
```

---

## 4. How to Run

### Run MAS on a cohort
```bash
python3 -c "
from src.orchestrator.graph import run_cohort
results = run_cohort('data/gold/cohort_verified.json')
"
```

### Run MAS + evaluation
```bash
python3 -c "
from src.orchestrator.graph import run_cohort
from src.evaluation.llm_judge import evaluate_cohort
results = run_cohort('data/gold/cohort_verified.json')
evaluations, summary = evaluate_cohort(results)
"
```

### Results location
```
data/gold/mas_results/           ← all outputs
data/gold/mas_results/{uuid}/    ← per-patient
```

---

*— MAS Output Format v1.0 • March 2026 • CMADS*
