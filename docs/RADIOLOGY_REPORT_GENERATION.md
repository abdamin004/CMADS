# Synthetic Radiology Report Generation — Implementation Document

> **Note:** This is a **separate data enrichment pipeline** that runs BEFORE the MAS agent pipeline. It is NOT a MAS agent stage. The radiology report generation pipeline produces synthetic reports from Synthea imaging metadata, which are then stored in `data/gold/radiology_reports/` and can be used by the EHR Analyst if imaging data is present for a patient.

## 1. Problem Statement

Synthea generates imaging study **metadata** (modality, body site, date, DICOM UIDs) but produces **no radiology report text** — no findings, measurements, or clinical impressions. The `imaging_studies` table contains only structural identifiers:

| Available in Synthea | NOT Available |
|---|---|
| Modality (CT, Ultrasound, X-ray) | Findings ("2.3 cm nodule") |
| Body site (Chest, Heart, Retina) | Measurements (tumor size, EF) |
| Date of scan | Radiologist impression |
| DICOM UIDs | Report narrative |
| Procedure code | Severity/urgency |

Without generated reports, agents can only see *that* a scan was performed, not *what was found*.

## 2. Implemented Solution

An LLM generates **synthetic radiology reports** as a data enrichment step. Synthea provides the **ground truth diagnosis** (via `conditions` and `encounters.REASONCODE`), which informs realistic report generation while being withheld from the downstream MAS agents.

### 2.1 Core Principle — Separation of Knowledge

```
REPORT GENERATION (knows the diagnosis):
  Synthea ground truth + imaging metadata → GPT-oss 120B → Synthetic report with findings

QUALITY EVALUATION (knows the diagnosis):
  Generated report + ground truth → Qwen3 32B → Quality scores (1-5)

MAS AGENT PIPELINE (does NOT know the diagnosis):
  EHR data (+ radiology findings if available) → 7 MAS agents → Differential diagnosis + treatment
```

The generated report describes **findings consistent with the disease** but never explicitly states the diagnosis. The MAS Diagnostic Reasoning agent uses these findings (via the EHR Analyst) alongside EHR and lab data to produce a **ranked differential diagnosis** with probabilities.

## 3. Architecture — 4-Agent Pipeline

**File:** `pipeline/radiology_agents.py`

```
Agent 1 — Data Collector    Query DuckDB for patient imaging cases (6-tier selection)
Agent 2 — Report Generator  Generate reports via GPT-oss 120B (Groq API — cloud)
Agent 3 — Quality Evaluator Score reports via Qwen3 32B (Groq API — cloud)
Agent 4 — Storage Manager   Save reports that pass quality threshold (≥4.0/5.0)
```

### 3.1 Parallel Pipeline Execution

Generator and evaluator run in **parallel threads** with a shared queue:

```
Generator thread (Groq):   GEN#1  GEN#2  GEN#3  GEN#4  ...
                                ↘      ↘      ↘      ↘
Evaluator thread (Groq):        EVAL#1 EVAL#2 EVAL#3 EVAL#4 ...
                                STORE  STORE  STORE  STORE
```

While the generator produces report N+1, the evaluator scores report N simultaneously. This overlap reduces total time from ~4s/case (sequential) to ~2-3s/case (pipelined).

### 3.2 Technology Stack

| Component | Technology | Details |
|-----------|-----------|---------|
| Generator model | `openai/gpt-oss-120b` | Via Groq API (cloud), ~2s/report |
| Evaluator model | `qwen/qwen3-32b` | Via Groq API (cloud), ~2s/eval |
| LLM adapter | `get_llm()` from `src.llm.adapter` | Provider-agnostic; supports Groq, OpenAI, Anthropic, Gemini, Ollama |
| Parallel execution | Python `threading` + `Queue` | Producer-consumer pattern |
| Data source | DuckDB | `data/clinical.duckdb` |
| Output | JSON files | Per-patient report + evaluation scores |

## 4. 6-Tier Imaging Selection

For each patient in the cohort, the pipeline selects **one imaging study** using a priority system. This maximizes coverage while respecting the point-in-time approach where possible.

### 4.1 Selection Priority

| Tier | Logic | When used |
|------|-------|-----------|
| **T1** | Pre-cutoff imaging for the target disease | Best case — imaging directly related to the disease, before diagnosis |
| **T2** | Pre-cutoff imaging on a clinically relevant body site | Related imaging (e.g., chest X-ray for a cardiac patient) |
| **T3** | Pre-cutoff any non-dental imaging | Unrelated imaging, but generator writes incidental findings for differential |
| **T4** | Pre-cutoff dental imaging (last pre-cutoff resort) | Generator notes findings relevant to target disease (e.g., bone density for CKD) |
| **T5** | Post-cutoff target disease imaging (fallback) | Only used when patient has zero pre-cutoff imaging |
| **T6** | Post-cutoff related body site imaging (fallback) | Only used when patient has zero pre-cutoff imaging |

### 4.2 Body Site Relevance Mapping

Each target disease maps to clinically relevant body sites:

| Disease | Relevant Body Sites |
|---------|-------------------|
| CHF, Ischemic HD, Aortic valve | Thoracic, Heart, Chest, Lung |
| Diabetes T2 | Retina, Eye, Foot, Kidney |
| CKD, ESRD | Kidney, Abdomen, Renal |
| Cerebral palsy, Epilepsy | Brain, Head, Spine, Cranial |
| Anemia | Thoracic, Abdomen, Bone, Spleen |
| Breast cancer | Breast, Thoracic, Chest |
| Pneumonia | Thoracic, Chest, Lung |
| Osteoporosis | Bone, Spine, Hip, Femur |
| Osteoarthritis of knee | Knee, Joint, Lower extremity |

Dental/oral imaging is excluded from T2/T3 as it is clinically irrelevant for non-dental diseases.

### 4.3 Coverage Results (1K Cohort)

| Tier | Patients | Cumulative |
|------|----------|------------|
| T1 — Target disease pre-cutoff | 5 | 5 |
| T2 — Related body site pre-cutoff | 18 | 23 |
| T3 — Any non-dental pre-cutoff | 152 | 175 |
| T4 — Dental pre-cutoff | 297 | 472 |
| T5 — Target disease post-cutoff | 26 | 498 |
| T6 — Related body site post-cutoff | 5 | 503 |
| **No imaging at all** | **497** | — |
| **Total covered** | **503 (50%)** | — |

497 patients have zero imaging studies in Synthea's data and therefore have no radiology reports available for the MAS pipeline.

## 5. Generation Prompt

### 5.1 System Prompt

```
You are an experienced radiologist writing a structured radiology report.

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
10. Output ONLY the report text, no preamble or explanation
```

### 5.2 User Prompt Template

```
Generate a radiology report for the following study:

Study: {modality} of {body_site}
Clinical setting: {encounter_class}
Patient: {age}-year-old {gender}

Active medical history (do NOT add these as diagnoses, use only for clinical context):
  - {condition_1}
  - {condition_2}
  ...

Relevant lab values and vitals from same visit:
  - {test}: {value} {units}
  ...

The patient has been diagnosed with: {ground_truth_disease}

Write a realistic radiology report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report.
```

### 5.3 Context Assembly

For each imaging study, the pipeline assembles:

| Data Source | Fields Used |
|-------------|------------|
| `imaging_studies` | Modality, body site, scan date |
| `encounters` (via ENCOUNTER FK) | Encounter class, reason code (ground truth) |
| `patients` | Name, birthdate, gender (→ age calculation) |
| `conditions` (via PATIENT, filtered) | Active conditions at scan time, excluding target disease |
| `observations` (via ENCOUNTER FK) | Labs and vitals from the same visit |

## 6. Quality Evaluation

### 6.1 Evaluation Criteria (scored 1-5 each)

| Criterion | What It Measures |
|-----------|-----------------|
| **Clinical Accuracy** | Are findings realistic and consistent with the ground truth disease? |
| **No Diagnosis Leakage** | Does the report avoid naming the disease? (5=never mentioned, 1=explicitly stated) |
| **Completeness** | Are key expected findings for this disease present? |
| **Internal Consistency** | Are findings internally consistent? Measurements anatomically sensible? |
| **Report Quality** | Standard structure (Technique/Findings/Impression)? Appropriate terminology? |
| **Overall** | Average of 5 criteria (1 decimal) |

### 6.2 Acceptance Criteria

- Overall score ≥ 4.0/5.0
- Diagnosis leakage score ≥ 3/5
- Reports failing either criterion are **rejected** and not stored

### 6.3 Evaluator Output

The evaluator also produces:
- `summary` — 2-3 sentence assessment
- `could_agent_diagnose` — "yes", "no", or "partially" — whether the report contains enough findings for an agent to reach the correct diagnosis
- `missing_findings` — list of expected findings that were absent
- `leaked_terms` — any disease terms found in the report

## 7. Output Storage

### 7.1 File Structure

```
data/gold/radiology_reports/
├── {patient_id}_{modality_code}_{scan_date}.json   # Individual accepted reports
└── all_reports.json                                  # All accepted reports combined

data/gold/radiology_evaluations/
├── evaluation_results.json                           # Scores for accepted reports
└── rejected_reports.json                             # Reports that failed quality check
```

### 7.2 Report JSON Schema

```json
{
  "patient_id": "000cb105-0f6a-e089-2701-7fa5fdf7ec03",
  "patient_name": "Idalia306 Kuhlman484",
  "imaging_study_id": "000cb105-0f6a-e089-fe1d-7489fcf263fe",
  "scan_date": "2023-11-12",
  "modality_code": "CR",
  "modality": "Computed Radiography",
  "body_site": "Thoracic structure (body structure)",
  "encounter_class": "inpatient",
  "report": "**TECHNIQUE:**\nPA and lateral chest radiographs...\n\n**FINDINGS:**\n...\n\n**IMPRESSION:**\n...\nClinical correlation recommended.",
  "generation_metadata": {
    "model": "openai/gpt-oss-120b",
    "temperature": 0.7,
    "ground_truth_disease": "Chronic congestive heart failure (disorder)",
    "ground_truth_code": "88805009",
    "active_conditions": ["Essential hypertension", "Hyperlipidemia"],
    "observations_used": 12,
    "duration_s": 2.1,
    "tokens_generated": 650,
    "provider": "groq",
    "generated_at": "2026-03-25T01:55:20.123456+00:00"
  }
}
```

The `generation_metadata.ground_truth_disease` is stored for **evaluation purposes only** and is never included in the MAS agent input.

## 8. Pipeline Integration

### 8.1 Where It Fits

This is a **data enrichment pipeline** that runs between Gold assembly and the MAS agent pipeline. It is not a MAS agent stage.

```
Bronze (raw Synthea CSV -> DuckDB)
    |
Silver (OMOP CDM transformation)
    |
Silver+ (derived features: trends, risk scores, comorbidity)
    |
Gold (per-patient JSON case files: ehr_case, lab_case, ground_truth)
    |
Radiology Reports (LLM-generated from imaging metadata + ground truth)  <-- THIS STEP (separate pipeline)
    |
MAS Agent Pipeline (7 agents: EHR, Lab, Diagnostic, Reviewer, Refiner, Evaluator, Treatment)
```

### 8.2 Information Boundary

| Data Element | EHR Analyst | Lab Interpreter | Hidden From All |
|---|---|---|---|
| Demographics, conditions, visits | Yes | — | — |
| Lab values, vitals, trends | — | Yes | — |
| Radiology report (findings only, if present) | Yes | — | — |
| Ground truth diagnosis | — | — | **Yes** |
| encounter.REASONCODE | — | — | **Yes** |
| generation_metadata | — | — | **Yes** |

### 8.3 How the MAS Uses Radiology Reports

The radiology reports are stored in `data/gold/radiology_reports/` and can be used by the EHR Analyst if imaging data is present for a patient. The MAS outputs a **ranked differential diagnosis** with probabilities. Radiology findings contribute signals:

- **T1/T2 patients** (23): Direct disease-related imaging -- strong diagnostic signal
- **T3 patients** (152): Unrelated imaging with incidental findings -- supporting signal for differential
- **T4 patients** (297): Dental imaging with subtle findings -- weak signal (bone density, calcifications)
- **T5/T6 patients** (31): Post-cutoff disease imaging -- direct signal but breaks strict point-in-time
- **No imaging** (497): No radiology report available -- MAS diagnoses from EHR + labs only

## 9. Running the Pipeline

### 9.1 Commands

```bash
# Quick test — random patients
python3 pipeline/radiology_agents.py --patients 4

# Full 1K cohort with 6-tier selection
python3 pipeline/radiology_agents.py --cohort

# Test cohort (100 patients)
python3 pipeline/radiology_agents.py --cohort --cohort-file data/gold/cohort_100_test_ids.json

# Custom threshold
python3 pipeline/radiology_agents.py --cohort --threshold 3.5
```

### 9.2 Environment Requirements

```bash
# API key for configured provider (default: Groq)
export GROQ_API_KEY="gsk_..."

# Required packages (LLM access goes through get_llm() adapter in src.llm.adapter)
pip install langchain-groq langchain-ollama langchain-core duckdb pydantic
```

### 9.3 Performance

| Configuration | Gen Time | Eval Time | Total/Case | 100 Patients |
|--------------|----------|-----------|------------|-------------|
| Both on Groq (current) | ~2s | ~2s | ~2-3s | ~4 min |
| Groq gen + DeepSeek local eval | ~2s | ~75s | ~77s | ~2 hours |
| Groq gen + Qwen3 local eval | ~2s | ~31s | ~33s | ~55 min |
| Both local Ollama | ~18s | ~75s | ~93s | ~2.5 hours |

## 10. Test Results (100-Patient Run)

| Metric | Result |
|--------|--------|
| Cases | 100 |
| Accepted (≥4.0) | 72 |
| Rejected (<4.0) | 28 |
| Errors | 0 |
| Avg score | 4.5/5.0 |
| Diagnosis leakage | 5/5 on all (perfect) |
| Total time | 3.8 min (2s/case) |

### 10.1 Tier Distribution (100-Patient Test)

| Tier | Count |
|------|-------|
| T1 — Target disease pre-cutoff | 1 |
| T2 — Related body site pre-cutoff | 2 |
| T3 — Any non-dental pre-cutoff | 24 |
| T4 — Dental pre-cutoff | 67 |
| T5 — Target disease post-cutoff | 6 |

### 10.2 Disease Coverage (100-Patient Test)

16 diseases covered across 100 patients, including ischemic HD (21), CHF (16), ESRD (9), diabetes T2 (9), anemia (8), CKD stages 1-3 (13), breast cancer (6), and others.

## 11. Limitations and Considerations

### 11.1 Limitations

- **50% coverage**: Only 503/1000 patients have imaging in Synthea — the other 497 get no radiology input
- **Synthea imaging bias**: Only 3 disease modules (cardiac, diabetic retinal, aortic valve) generate targeted imaging; other diseases rely on unrelated imaging with incidental findings
- **T4 dental imaging**: 297 patients have only dental X-rays — the generator produces incidental findings (bone density, calcifications) that may not be clinically realistic
- **T5/T6 post-cutoff**: 31 patients use post-diagnosis imaging, breaking strict point-in-time for maximum coverage
- **LLM-generated**: Reports are synthetic — they may not capture the full variability of real radiology language

### 11.2 Mitigations

- Quality evaluation catches poor reports (28% rejection rate ensures only good reports reach agents)
- Perfect diagnosis leakage scores (5/5 on all accepted reports)
- Tier metadata is stored -- evaluation can be stratified by tier to measure signal quality
- When no imaging is available for a patient, the MAS pipeline proceeds without radiology input

---

*-- Radiology Report Generation v3.0 -- March 2026 -- CMADS -- Updated: clarified as separate data enrichment pipeline (not a MAS agent), uses get_llm() adapter, removed Synthesis Agent references*
