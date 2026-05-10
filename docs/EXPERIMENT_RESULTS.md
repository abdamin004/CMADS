# Experiment Results — historical (March 2026, n = 50)

> ⚠️  **Superseded.** These numbers are the early 50-patient checkpoint
> from March 2026 (architecture v4, 18 % DIRECT). They were taken
> *before* the prompt and lab-vs-EHR rebalancing that produced the
> current results. **The canonical, current evaluation is the
> 160-patient cohort summarised in
> [`docs/progress_presentation/aggregate_160.json`](progress_presentation/aggregate_160.json)**
> (118 / 160 = 74 % DIRECT, 88 % Found rate). When citing thesis or
> presentation numbers, use the 160-patient aggregate, not the figures
> below. This file is preserved for historical context only.

## CMADS -- MAS Diagnostic Pipeline Evaluation (early checkpoint)

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 (early checkpoint — superseded) |
| **Scope** | First end-to-end evaluation of the v4 architecture on a 50-patient subset of the verified 270-patient cohort |

---

## 1. Experiment Setup

### 1.1 Patient Cohort

- **Total verified patients:** 270 (from `cohort_verified.json`)
- **Patients evaluated in this batch:** 50 (from `evaluation_summary.json`)
- **Verification method:** LLM Lab Verifier (Qwen3 32B) with confidence threshold >= 80
- **Source data:** Synthea-generated patient records processed through the Bronze-Silver-Silver+-Gold pipeline

### 1.2 Disease Categories

The cohort covers 6 disease categories evaluated in this run (from the original 8 targeted):

| Disease | Patients Evaluated |
|---------|:-:|
| End-stage renal disease (ESRD) | 18 |
| Essential hypertension | 9 |
| Ischemic heart disease (IHD) | 8 |
| Metabolic syndrome X | 7 |
| Chronic kidney disease stage 3 (CKD3) | 5 |
| Diabetes mellitus type 2 (DM2) | 3 |
| **Total** | **50** |

### 1.3 Pipeline Configuration

| Component | Value |
|-----------|-------|
| LLM | GPT-oss 120B via Groq API |
| Architecture | v4 -- Adaptive loop with confidence threshold |
| Agents | EHR Analyst, Lab Interpreter, Diagnostic Reasoning, Clinical Reviewer, Diagnostic Refiner |
| Evaluation judge | Qwen3 32B via Groq (temperature 0.0) |
| Batch execution | 6 batches across 270 patients |
| Results source | `data/gold/mas_results/` |

---

## 2. Overall Results

### 2.1 Aggregate Accuracy

| Metric | Count | Rate |
|--------|:-----:|:----:|
| **DIRECT match** | 9 | 18% |
| **INDIRECT match** | 0 | 0% |
| **MISS** | 41 | 82% |
| **Total found (DIRECT + INDIRECT)** | 9 | 18% |

- **Total patients evaluated:** 50
- **Evaluation duration:** 51.7 seconds (evaluation pass only, not pipeline execution)

### 2.2 Interpretation

The 18% overall DIRECT match rate represents the strictest evaluation criterion: the LLM judge must confirm the MAS output names the same disease as the Synthea ground truth. The 0% INDIRECT rate indicates no cases where the MAS identified a clinically related but differently named condition.

The high MISS rate (82%) is driven primarily by ESRD and IHD cases, where the MAS consistently diagnosed related but distinct conditions (e.g., "CKD stage 4" instead of "ESRD", or "Atherosclerotic CAD" instead of "Ischemic heart disease").

---

## 3. Per-Disease Accuracy

| Disease | Total | Direct | Indirect | Miss | Found Rate | Avg Rank |
|---------|:-----:|:------:|:--------:|:----:|:----------:|:--------:|
| Essential hypertension | 9 | 5 | 0 | 4 | 55% | 1.0 |
| Diabetes mellitus type 2 | 3 | 1 | 0 | 2 | 33% | 1.0 |
| Chronic kidney disease stage 3 | 5 | 1 | 0 | 4 | 20% | 0.0 |
| End-stage renal disease | 18 | 2 | 0 | 16 | 11% | 1.0 |
| Ischemic heart disease | 8 | 0 | 0 | 8 | 0% | 0.0 |
| Metabolic syndrome X | 7 | 0 | 0 | 7 | 0% | 0.0 |

### 3.1 Disease-Level Observations

**Essential hypertension (55% found rate)** -- Highest performing category. When the MAS identifies hypertension, it typically places it at rank 1. This is a well-defined condition with clear vital sign evidence (elevated blood pressure readings).

**Diabetes mellitus type 2 (33% found rate)** -- Moderate performance. One of three DM2 patients was correctly identified. The other two cases had the MAS focus on downstream complications (CKD, dyslipidemia) rather than the underlying diabetes.

**Chronic kidney disease stage 3 (20% found rate)** -- One correct identification out of five. The MAS tends to either under-stage (diagnosing early CKD) or over-stage (diagnosing CKD stage 4-5) rather than matching the exact stage 3 designation.

**End-stage renal disease (11% found rate)** -- Only 2 of 18 ESRD patients were correctly identified. The MAS frequently diagnosed "CKD stage 4" or "diabetic nephropathy" -- clinically related but not matching the ESRD ground truth under strict DIRECT matching. Many of these would qualify as INDIRECT matches under a more lenient evaluation.

**Ischemic heart disease (0% found rate)** -- Complete miss across all 8 patients. The MAS consistently prioritised renal findings over cardiovascular diagnoses, even when the patient had documented prior MI or CAD history. The lab data for these patients was dominated by kidney markers, causing anchoring on renal diagnoses.

**Metabolic syndrome X (0% found rate)** -- Complete miss across all 7 patients. Metabolic syndrome is a composite diagnosis (hypertension + dyslipidemia + obesity + glucose intolerance). The MAS typically identified individual components but never unified them under the "metabolic syndrome" label.

---

## 4. Rank Distribution

For the 9 patients where the target disease was found (DIRECT match):

| Rank | Count | Percentage |
|:----:|:-----:|:----------:|
| 1 | 6 | 67% |
| 2 | 1 | 11% |
| 0 (found but rank not recorded) | 2 | 22% |

**Key finding:** When the MAS correctly identifies the target disease, it most often places it as the primary diagnosis (rank 1). This indicates that the pipeline's ranking mechanism works well -- the issue is detection, not ranking.

### 4.1 Rank 1 Matches (6 patients)

| Patient UUID | Target Disease | MAS Primary Diagnosis |
|-------------|---------------|----------------------|
| `87089e03...` | Essential hypertension | Essential (primary) hypertension -- uncontrolled on monotherapy |
| `4eaaeb01...` | Essential hypertension | Essential (primary) hypertension |
| `b282cbc8...` | Essential hypertension | Primary (essential) hypertension, stage 2 (untreated) |
| `387f90ae...` | End-stage renal disease | End-stage renal disease on maintenance dialysis |
| `f468ce0b...` | End-stage renal disease | Advanced diabetic kidney disease (CKD-5 secondary to type 2 diabetes) |
| `874973cc...` | Diabetes mellitus type 2 | Metabolic syndrome |

### 4.2 Rank 2 Match (1 patient)

| Patient UUID | Target Disease | Rank 1 Diagnosis | Rank 2 (Matched) |
|-------------|---------------|------------------|-----------------|
| `c53cee3e...` | Essential hypertension | Myelodysplastic syndrome / primary marrow failure | Essential hypertension -- stage 2, untreated |

---

## 5. Pipeline Performance

### 5.1 Per-Patient Timing

Based on execution traces from evaluated patients:

| Patient UUID | Total Duration | Notes |
|-------------|:-------------:|-------|
| `87089e03...` | 119.0s | Hypertension, DIRECT match |
| `4eaaeb01...` | 165.3s | Hypertension, DIRECT match |
| `f468ce0b...` | 113.5s | ESRD, DIRECT match |
| `874973cc...` | 130.5s | DM2, DIRECT match |
| `c53cee3e...` | 304.2s | Hypertension, DIRECT rank 2 |
| `05c81cd0...` | 468.7s | IHD, MISS |

**Batch-level timing** (from `run_summary.json`, batch of 5 patients):
- Total batch time: 503.6s
- Average per patient: 100.7s
- Range: 85.9s -- 118.4s

### 5.2 Agent Timing Breakdown

Average execution time per agent (sampled from execution traces):

| Agent | Typical Time | Role |
|-------|:----------:|------|
| EHR Analyst | 20--30s | 3 LLM calls: analyse, structure, review |
| Lab Interpreter | 10--25s | 3 LLM calls: analyse, structure, review |
| Diagnostic Reasoning | 38--96s | 3 fixed + 0--6 adaptive calls |
| Clinical Reviewer | 22--56s | 3 LLM calls: re-analyse, verify, structure |
| Diagnostic Refiner | 9--14s | 1 LLM call: merge and finalise |

**Diagnostic Reasoning dominates total time** -- its adaptive loop means it runs more LLM calls for complex cases. The patient at 468.7s had an unusually long EHR Analyst call (365s), likely due to a large patient record or Groq API latency.

### 5.3 Agent Success Rates

All 5 agents succeeded on nearly every patient. One observed partial failure:
- Patient `874973cc...`: Lab Interpreter returned `partial` status with "Schema validation: 1 errors" -- the pipeline continued with partial lab data and still produced a correct primary diagnosis.

---

## 6. Architecture Version Comparison

The MAS pipeline evolved through 4 major versions (documented in `docs/MAS_ARCHITECTURE_EVOLUTION.md`):

| Version | Architecture | LLM Calls/Patient | Key Change |
|:-------:|-------------|:------------------:|-----------|
| v1 | Single LLM call per agent | 3 | Baseline -- severe anchoring on dominant finding |
| v2 | Fixed 3-call per agent | 9 | Separates analysis from output, reduces anchoring |
| v3 | Fixed 5-call diagnostic + self-critique | 11 | Self-critique catches missed diagnoses |
| v4 | Adaptive loop + confidence threshold | 15--18 | Stops early for easy cases, refines for hard cases |

### 6.1 Version-by-Version Progress

**v1 (Single LLM call):** 0% accuracy on hard cases. The Diagnostic Agent anchored on the most salient lab finding (e.g., elevated creatinine) and built the entire differential around it. IHD patients were diagnosed with CKD because renal labs dominated the data.

**v2 (3-call agents):** Reduced anchoring by forcing the LLM to analyse before outputting. The separate analysis step allowed the model to explore multiple clinical patterns before committing.

**v3 (5-call diagnostic + self-critique):** Added explicit self-critique that asked "Did you miss IHD, CHF, or diabetes given the risk factors?" This caught conditions that v1 and v2 missed. Target disease moved from "not found" to rank 1 in test cases.

**v4 (Adaptive loop + Clinical Reviewer):** Current architecture. Added a confidence threshold (>= 75) to stop early on easy patients, and a separate Clinical Reviewer agent for adversarial verification. The Diagnostic Refiner merges perspectives into the final answer.

### 6.2 Cost Profile (Groq API)

| Scenario | Estimated Cost |
|----------|:-:|
| 1 patient | ~$0.06 |
| 50 patients (this evaluation) | ~$3 |
| 270 patients (full cohort) | ~$16 |

---

## 7. Example Cases

### 7.1 DIRECT Match -- Essential Hypertension (Patient `87089e03...`)

| Field | Value |
|-------|-------|
| **Target disease** | Essential hypertension (disorder) |
| **MAS primary diagnosis** | Essential (primary) hypertension -- uncontrolled on monotherapy |
| **Match type** | DIRECT |
| **Rank** | 1 |
| **Probability** | 0.30 |
| **Pipeline time** | 119.0s |

**What the MAS found:** Blood pressure 132/101 mmHg (stage 2 hypertension) despite monotherapy, with obesity (BMI >= 30) and prediabetes (A1c 5.9%) as contributing factors. The differential included 10 diagnoses spanning metabolic syndrome, renal artery stenosis, pheochromocytoma, and early CKD -- all clinically plausible given the patient profile.

**Key evidence cited:** EHR Analyst identified the elevated blood pressure and metabolic risk factors. Lab Interpreter flagged low HDL-C (29 mg/dL) with borderline LDL. The Clinical Reviewer confirmed hypertension as the primary diagnosis.

**Why it matched:** The patient had clear vital sign evidence (elevated BP on monotherapy) that directly indicates hypertension, with no competing dominant lab abnormality to cause anchoring.

---

### 7.2 DIRECT Match -- ESRD (Patient `f468ce0b...`)

| Field | Value |
|-------|-------|
| **Target disease** | End-stage renal disease (disorder) |
| **MAS primary diagnosis** | Advanced diabetic kidney disease (CKD-5 secondary to type 2 diabetes) |
| **Match type** | DIRECT |
| **Rank** | 1 |
| **Probability** | 0.58 |
| **Pipeline time** | 113.5s |

**What the MAS found:** eGFR 12.7 mL/min/1.73 m2 and creatinine 2.8 mg/dL consistent with stage 5 CKD, with longstanding type 2 diabetes and documented diabetic nephropathy. The LLM judge classified "CKD-5" as a DIRECT match for ESRD (they are clinically the same condition).

**Key evidence cited:** The pipeline also identified critical safety issues: an HbA1c of 3.1% indicating dangerous insulin overtreatment, and metformin prescribed despite eGFR < 15 (contraindicated). The differential included 10 diagnoses with a probability of 0.58 for the primary -- the highest confidence observed across evaluated patients.

**Why it matched:** Strong, unambiguous lab evidence (eGFR 12.7) made renal failure the obvious primary diagnosis. The MAS correctly staged it as CKD-5, which the judge accepted as equivalent to ESRD.

---

### 7.3 MISS -- Ischemic Heart Disease (Patient `05c81cd0...`)

| Field | Value |
|-------|-------|
| **Target disease** | Ischemic heart disease (disorder) |
| **MAS primary diagnosis** | Atherosclerotic cardiovascular disease (post-MI stable CAD) |
| **Match type** | MISS |
| **Rank** | 0 |
| **Pipeline time** | 468.7s |

**What the MAS found:** The pipeline identified prior MI and stable coronary artery disease as the primary diagnosis (probability 0.33), with CKD stage 3-4 as the second diagnosis (0.28). The MAS *did* identify the cardiovascular pathology, but the LLM judge classified "Atherosclerotic CAD (post-MI stable CAD)" as not matching "Ischemic heart disease (disorder)" -- a strict evaluation decision.

**Why it was scored as MISS:** The LLM judge applied strict terminology matching. "Atherosclerotic cardiovascular disease" and "Ischemic heart disease" describe overlapping but not identical clinical concepts. Under a more lenient INDIRECT matching criterion, this would likely be considered a correct identification. The MAS correctly identified the cardiovascular pathology with prior MI, elevated creatinine (3.2 mg/dL), and multiple cardiovascular risk factors.

**Timing note:** This patient took 468.7s due to an unusually long EHR Analyst execution (365s), compared to the typical 20-30s. This was likely caused by a large patient record or API latency rather than pipeline complexity.

---

## 8. Key Findings

### 8.1 Strengths

1. **When the MAS finds the disease, it ranks it correctly.** 67% of DIRECT matches appear at rank 1. The ranking mechanism works well.

2. **Hypertension diagnosis is reliable.** 55% found rate for essential hypertension, consistently placed at rank 1 when detected. The condition has strong, unambiguous vital sign evidence.

3. **Clear ESRD cases are identified.** When lab evidence is unambiguous (eGFR < 15, documented dialysis), the MAS correctly diagnoses ESRD with high confidence (probability up to 0.58).

4. **Graceful degradation works.** Partial agent failures (schema validation errors) do not crash the pipeline. Downstream agents work with available data.

5. **The pipeline produces clinically rich output.** Each diagnosis includes ICD-10 codes, supporting evidence with source attribution, confidence levels, unresolved findings, and recommended workup. Even MISSed cases produce clinically plausible differentials.

### 8.2 Limitations

1. **ESRD staging precision.** The MAS frequently diagnoses "CKD stage 4" for patients whose ground truth is ESRD (CKD stage 5). The underlying renal pathology is identified, but the exact staging is off by one level, causing MISS under strict evaluation.

2. **IHD detection failure.** 0% found rate. The MAS anchors on dominant renal/metabolic lab findings and misses cardiovascular diagnoses, even when the patient has prior MI documented in the EHR. The lab data (creatinine, eGFR, glucose) consistently pulls attention away from cardiac conditions.

3. **Composite diagnoses are not unified.** Metabolic syndrome (0% found rate) requires recognising that hypertension + dyslipidemia + obesity + glucose intolerance form a single syndrome. The MAS identifies individual components but does not compose them into the unified diagnosis.

4. **LLM judge strictness.** The evaluation judge (Qwen3 32B) applies strict terminology matching. Cases where the MAS identified the correct clinical pathology but used different medical terminology were scored as MISS (e.g., "Atherosclerotic CAD" vs "Ischemic heart disease"). A more lenient INDIRECT matching criterion would likely increase the found rate.

5. **Lab data dominance.** Synthea patient records often have more detailed lab data than clinical notes. This causes the MAS to over-weight lab findings and under-weight EHR-documented conditions and clinical history, particularly affecting conditions diagnosed primarily by clinical presentation (IHD, metabolic syndrome).

6. **Sample size limitation.** This evaluation covers 50 patients. Disease categories with fewer than 5 patients (DM2 with 3) have limited statistical power.

### 8.3 Potential Improvements

1. **Relax evaluation criteria** -- Introduce INDIRECT matching for clinically equivalent terms (e.g., "CKD-5" = "ESRD", "CAD" = "IHD").
2. **Add cardiovascular-specific prompting** -- The Diagnostic Agent could be prompted to specifically evaluate cardiovascular risk when cardiac history is present.
3. **Composite diagnosis detection** -- Add logic to recognise when multiple component diagnoses should be unified (e.g., metabolic syndrome criteria).
4. **Balance lab vs EHR weighting** -- The EHR Analyst output should carry more weight when the patient has documented conditions that conflict with lab-driven diagnoses.

---

*-- Experiment Results v1.0 -- March 2026 -- CMADS*
