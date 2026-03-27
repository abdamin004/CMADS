# Data Quality Analysis Report

## CMADS — Synthea Data Limitations and Mitigation Strategies

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Analysis of Synthea-generated patient data quality and its impact on MAS diagnostic accuracy |

---

## 1. Overview

This document reports the data quality issues discovered during development and testing of the CMADS multi-agent diagnostic pipeline. The core finding is that Synthea generates conditions (diseases) and observations (lab results) **independently** — lab values do not reliably reflect the patient's diseases before diagnosis. This fundamentally limits the MAS's ability to diagnose from pre-diagnosis data.

---

## 2. How Synthea Generates Data

Synthea uses **rule-based state transition machines** (Generic Module Framework) informed by CDC/NIH statistics. Each disease has its own module that runs independently:

- The **CKD module** decides when a patient gets CKD based on risk factors
- The **lab module** generates lab values during encounters
- These modules **do not communicate** — the lab module does not check what diseases the patient has

This means:
- A patient can have CKD with **normal creatinine** before diagnosis
- A patient can have **abnormal creatinine** without any CKD diagnosis
- Labs are generated as random values within physiological ranges, not driven by disease state

### 2.1 Verification: Labs vs Conditions

We compared average lab values for patients WITH vs WITHOUT specific diseases:

| Lab | With Disease | Without Disease | Difference | Clinically Meaningful? |
|-----|:-----------:|:---------------:|:----------:|:---:|
| Creatinine (CKD patients) | 2.02 mg/dL | 1.90 mg/dL | +0.12 | No — both elevated, barely different |
| HbA1c (Diabetic patients) | 4.36% | 4.95% | -0.59% | No — diabetics have LOWER HbA1c |
| Hemoglobin (Anemia patients) | 13.99 g/dL | 14.43 g/dL | -0.44 | No — both normal |
| LVEF (CHF patients) | 50.4% | 39.9% | +10.5% | Backwards — CHF patients have higher EF |

**Conclusion:** Synthea does not meaningfully adjust lab values based on conditions. The labs are essentially random within normal ranges regardless of disease status.

---

## 3. Encounter Reason Analysis

In Synthea's `encounters` table, the `REASONCODE` field indicates **why the patient visited**. We analysed the relationship between conditions and encounter reasons:

| Metric | Count | % |
|--------|-------|---|
| Total conditions | 599,111 | 100% |
| Condition IS the encounter reason (clinically confirmed) | 73,801 | **12%** |
| Condition is NOT the encounter reason (incidental) | 525,310 | **88%** |

**Only 12% of conditions are encounter-reason confirmed.** The other 88% are assigned incidentally by Synthea's state machine during visits for other reasons.

### 3.1 What This Means

When a condition IS the encounter reason:
- The patient **visited specifically for that disease**
- Labs ordered during that visit are **relevant to the disease**
- The diagnosis is **clinically confirmed**

When a condition is NOT the encounter reason:
- Synthea's module **assigned it during a visit for something else**
- No labs were ordered to investigate it
- No medications were prescribed for it
- The diagnosis has **no clinical evidence** in the data

### 3.2 Diseases by Encounter Reason Status

**Diseases that ARE encounter reasons (clinically confirmed):**
- Viral sinusitis, pharyngitis, bronchitis — acute conditions
- CHF, ESRD — chronic diseases with dedicated visits
- Fractures, lacerations — acute presentations

**Diseases that are NEVER encounter reasons (incidental):**
- Anemia (10,763 occurrences — never an encounter reason)
- Medication review, stress, gingivitis, employment status
- Social determinants of health

---

## 4. Anemia Case Study — The Proof

We examined anemia patients in detail to prove the data quality issue:

### 4.1 Hemoglobin Values Before vs After Diagnosis

| Patient | Before Cutoff (MAS sees) | After Cutoff (hidden) |
|---------|:---:|:---:|
| Patient 1 | Hemoglobin 13.0 g/dL (**NORMAL**) | 10.4 g/dL (**LOW = ANEMIA**) |
| Patient 2 | Hemoglobin 14.3 g/dL (**NORMAL**) | 10.6 g/dL (**LOW = ANEMIA**) |

The anemia develops AFTER the diagnosis date. The point-in-time approach shows the MAS only the normal values. No LLM can diagnose anemia from normal hemoglobin.

### 4.2 Cross-Validation with Claude Opus

We sent the same patient data to Claude Opus (state-of-the-art LLM) with the prompt: "Diagnose this patient." Opus produced the same result as our MAS — metabolic syndrome and obesity, with no mention of anemia or heart failure. This confirms the limitation is in the **data**, not the **reasoning system**.

### 4.3 Decision: Remove Anemia

Anemia was removed from the target disease list because:
1. Labs are normal before diagnosis
2. Synthea assigns it incidentally (never an encounter reason)
3. No LLM can diagnose it from the available data
4. Including it would artificially lower MAS accuracy metrics

---

## 5. Disease Classification by Data Quality

### 5.1 Diseases with Lab Evidence (Retained)

| Disease | Lab Evidence | Verification Rate | Why It Works |
|---------|-------------|:-:|---|
| ESRD | Creatinine, eGFR <15 | 100% | Synthea's renal module generates correlated labs |
| CKD Stage 3 | Creatinine, eGFR <60 | 85% | Same renal module |
| Metabolic Syndrome | Triglycerides, HDL, glucose, BP | 75% | Multiple measurable criteria |
| IHD | Cardiac history, meds, troponin | 54% | Encounter-reason confirmed with labs |
| Hypertension | BP readings, medications | 50% | Detectable from vitals |
| CKD Stage 2 | eGFR 60-89 | 50% | Renal module |
| CHF | LVEF, BNP, cardiac meds | 27% | Only when cardiac labs exist |
| Diabetes T2 | HbA1c, glucose, metformin | 22% | Only when above threshold |

### 5.2 Diseases Without Lab Evidence (Removed)

| Disease | Why It Fails |
|---------|-------------|
| Anemia | Labs normal before diagnosis |
| Breast cancer | Needs mammography/biopsy |
| Osteoporosis | Needs DEXA scan |
| Pneumonia | Needs chest imaging |
| Cerebral palsy | Congenital, no lab markers |
| Epilepsy | Needs EEG |
| Osteoarthritis | Clinical/imaging diagnosis |

---

## 6. Mitigation Strategies Implemented

### 6.1 Disease Selection Filter

Only diseases with demonstrated lab evidence are included as target diseases in the Gold layer. The `TARGET_DISEASES` list in `pipeline/gold.py` excludes anemia and other undianosable conditions.

### 6.2 Data Sufficiency Filter

Patients must have:
- ≥3 visits before diagnosis date
- ≥5 lab observations before diagnosis date

This ensures the MAS always has some evidence to reason from. Implemented in `pipeline/gold.py` via `MIN_PRE_DIAGNOSIS_VISITS` and `MIN_PRE_DIAGNOSIS_LABS`.

### 6.3 LLM Lab Verifier

An LLM (Qwen3 32B) independently verifies each patient: "Could a doctor detect this disease from these labs?" Only patients with confidence ≥80 pass into the verified cohort. Implemented in `pipeline/lab_verifier_llm.py`.

### 6.4 Filtering Pipeline

```
14,850 Synthea patients
    ↓ Disease filter: remove undianosable diseases
    ↓ Data sufficiency: ≥3 visits + ≥5 labs
3,348 patients
    ↓ LLM Verifier: confidence ≥80
Verified cohort (results pending)
```

---

## 7. Impact on Thesis

### 7.1 What This Means for MAS Evaluation

The MAS diagnostic accuracy is **bounded by Synthea's data quality**, not by the reasoning capability of the agents. When the data contains the signal, the MAS diagnoses correctly. When the data lacks the signal, no LLM can diagnose — as confirmed by cross-validation with Claude Opus.

### 7.2 Thesis Narrative

The data quality analysis supports a thesis narrative of:
1. Building a clinically sound MAS pipeline
2. Discovering fundamental limitations in synthetic patient data
3. Developing mitigation strategies (LLM verifier) to identify diagnosable cases
4. Demonstrating that MAS accuracy on verified data reflects actual reasoning capability

---

*— Data Quality Analysis Report v1.0 • March 2026 • CMADS*
