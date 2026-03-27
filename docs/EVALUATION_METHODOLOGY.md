# Evaluation Methodology

## CMADS — How MAS Diagnostic Output Is Evaluated

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Evaluation framework: LLM-as-Judge, matching criteria, accuracy metrics |

---

## 1. The Evaluation Challenge

The MAS produces a ranked differential diagnosis. The ground truth is a single target disease. Comparing them is not straightforward because:

1. **Naming variation** — The MAS might say "Stage 5 CKD" while the ground truth says "End-stage renal disease." Same disease, different names.
2. **Clinical equivalence** — "Ischemic cardiomyopathy" and "Ischemic heart disease" are clinically the same but string-different.
3. **Indirect matches** — "Diabetic nephropathy" is not ESRD itself, but it's the cause of ESRD. Is that a match?
4. **Partial credit** — Finding the target at rank #3 is better than not finding it at all.

---

## 2. Why Keyword Matching Failed

Initial evaluation used simple string matching:
```python
target_words = ["ischemic", "heart"]
found = any(word in diagnosis_name.lower() for word in target_words)
```

This failed in multiple cases:

| Target | MAS Diagnosis | Keyword Match | Clinically Correct? |
|--------|--------------|:---:|:---:|
| End-stage renal disease | Stage 5 CKD | NO | YES — same disease |
| End-stage renal disease | Diabetic nephropathy (stage 5) | NO | YES — cause + stage |
| CHF | Cardiogenic shock | NO | YES — acute CHF presentation |
| CHF | HFpEF | NO | YES — subtype of heart failure |
| IHD | Ischemic cardiomyopathy | YES | YES |
| IHD | Type-2 myocardial infarction | NO | YES — IHD event |

**Keyword matching reported 50-60% accuracy. Clinical accuracy was 70-80%.** The evaluation method was the bottleneck, not the MAS.

---

## 3. LLM-as-Judge Approach

### 3.1 Design

An LLM (Qwen3 32B) acts as a clinical evaluator. It receives:
- The ground truth disease name
- The MAS's ranked differential (top 5)

And classifies each diagnosis as:

| Classification | Meaning | Examples for ESRD target |
|---|---|---|
| **DIRECT** | Same disease, possibly different name | "Stage 5 CKD", "Kidney failure", "ESRD" |
| **INDIRECT** | Clinically related — cause, consequence, subtype, precursor | "Diabetic nephropathy", "CKD stage 4", "Uremic encephalopathy" |
| **UNRELATED** | Not connected to the target | "Metabolic syndrome", "Hypothyroidism" |

### 3.2 The Prompt

```
You are a clinical evaluator. A diagnostic system produced a ranked differential
diagnosis. The patient's ACTUAL disease was hidden from the system.

ACTUAL DISEASE (ground truth): {target}

SYSTEM'S DIFFERENTIAL:
#1 Diabetic nephropathy (P=0.35)
#2 Stage 5 CKD (P=0.21)
#3 Heart failure (P=0.15)
...

For each diagnosis, is it DIRECT, INDIRECT, or UNRELATED?

Respond with:
FOUND: YES or NO
MATCH_TYPE: DIRECT or INDIRECT or MISS
RANK: [1-5 or 0]
MATCHED_DIAGNOSIS: [name or NONE]
REASON: [one sentence]
```

### 3.3 Output Format

Per patient:
```
FOUND: YES
MATCH_TYPE: DIRECT
RANK: 2
MATCHED_DIAGNOSIS: Stage 5 CKD
REASON: Stage 5 CKD is the clinical definition of end-stage renal disease
```

Per cohort (formatted table):
```
Patient        Target                       Found  Type      Rank  Matched Diagnosis
──────────────────────────────────────────────────────────────────────────────────
1611d106...    Ischemic heart disease        YES    DIRECT    #1    Ischemic cardiomyopathy
e5373d98...    End-stage renal disease       YES    DIRECT    #2    Stage 5 CKD
48417e6d...    End-stage renal disease       YES    INDIRECT  #1    CKD stage 4
──────────────────────────────────────────────────────────────────────────────────
DIRECT:   X/N (X%)
INDIRECT: Y/N (Y%)
MISS:     Z/N (Z%)
TOTAL FOUND: (X+Y)/N
```

### 3.4 Why Qwen3 32B for Judging

- Classification task (not complex reasoning) — small model is sufficient
- Medical knowledge to understand clinical equivalence
- Fast (~2s per evaluation on Groq)
- Free tier on Groq — no cost for evaluation
- Temperature 0.0 for deterministic results

---

## 4. Metrics

### 4.1 Primary Metrics

| Metric | Definition |
|--------|-----------|
| **Direct Match Rate** | % of patients where the exact target disease appears in the differential |
| **Indirect Match Rate** | % where a clinically related disease appears |
| **Total Found Rate** | Direct + Indirect (the primary accuracy metric) |
| **Miss Rate** | % where no related disease appears |
| **Average Rank** | Mean position of the best match (lower = better, 1 = top diagnosis) |

### 4.2 Per-Disease Metrics

Accuracy is reported per disease to identify which conditions the MAS handles well vs poorly:
- ESRD: expected high accuracy (strong lab signals)
- CHF: expected moderate accuracy (depends on cardiac labs)
- Diabetes T2: expected lower accuracy (borderline HbA1c values)

---

## 5. Cross-Validation with External LLMs

To distinguish MAS limitations from data limitations, the same patient data was sent to Claude Opus and ChatGPT with the prompt:
```
"You are a senior diagnostic physician. Based ONLY on the following
patient data, produce a ranked differential diagnosis."
```

If the external LLM also cannot find the target disease, the problem is **data quality** (insufficient evidence), not MAS reasoning.

This cross-validation was performed on:
- CHF patient with no cardiac labs → Opus also missed CHF (confirmed: data issue)
- Diabetes patient with HbA1c 6.4% → Opus identified "progression to diabetes" but not current DM2 (confirmed: borderline data)

---

## 6. LLM Lab Verifier — Pre-Evaluation Data Quality Gate

### 6.1 Purpose

Before running the MAS, each patient is verified by an LLM (Qwen3 32B):
> "Could a doctor detect this disease from these labs?"

Only patients with confidence ≥80 enter the evaluation cohort. This ensures accuracy metrics reflect MAS reasoning capability, not Synthea data quality.

### 6.2 Verification Prompt

```
You are a senior clinical pathologist.
TARGET DISEASE: {disease}
PATIENT DATA: {labs, meds, conditions, vitals}

Answer:
1. Are labs abnormal in a way consistent with this disease?
2. Are medications suggesting this disease?
3. Are conditions/risk factors pointing to it?
4. Could a doctor suspect this disease from this data?

VERDICT: YES or NO
CONFIDENCE: 0-100
EVIDENCE: [findings]
REASONING: [one sentence]
```

### 6.3 Confidence Threshold

Threshold set at 80 based on testing:
- Confidence 70: let through borderline cases (DM2 with HbA1c 6.4%) → MAS couldn't diagnose
- Confidence 80: filters borderline cases → only patients with clear evidence pass
- Confidence 90: too strict — filters valid patients

---

## 7. Evaluation Storage

All evaluation results are saved alongside MAS outputs:

```
data/gold/mas_results/
├── {patient_uuid}/
│   ├── final_diagnosis.json     ← MAS output
│   ├── evaluation.json          ← LLM judge result
│   └── execution_trace.json     ← Timing data
├── evaluation_summary.json      ← Cohort-level results
└── run_summary.json             ← Pipeline statistics
```

---

## 8. Limitations of the Evaluation

1. **LLM-as-Judge is not perfect** — The judge LLM may occasionally misclassify a diagnosis. Using temperature 0.0 and a focused prompt minimises this.

2. **Binary target** — Each patient has one target disease, but patients often have multiple conditions. The MAS may correctly identify comorbidities that aren't the "target" — these are not counted as matches.

3. **Indirect match subjectivity** — Whether "diabetic nephropathy" counts as matching "ESRD" depends on clinical judgement. The LLM judge applies reasonable clinical standards but edge cases exist.

4. **Verified cohort bias** — By filtering to only diagnosable patients, the accuracy metric applies to "diagnosable cases" not "all cases." This is stated explicitly in results.

---

*— Evaluation Methodology v1.0 • March 2026 • CMADS*
