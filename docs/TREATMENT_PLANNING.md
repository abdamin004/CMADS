# Treatment Planning Subsystem

## CMADS -- How Treatment Plans Are Generated from NICE Guidelines

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Scope** | Treatment Planning Agent, NICE guideline integration, Qdrant vector search, drug safety checking |

---

## 1. Overview

The Treatment Planning Agent is Stage 3 of the CMADS multi-agent pipeline. It takes the primary diagnosis produced by the Diagnostic Reasoning Agent (Stage 2), retrieves the matching NICE clinical guideline from a Qdrant vector database, and generates a patient-specific treatment plan.

The agent does not invent treatment protocols. Every medication, dose, and monitoring instruction traces back to a structured NICE guideline JSON stored in the system. The LLM's role is to adapt the guideline to the individual patient's circumstances -- their current medications, comorbidities, lab results, and clinical history.

```
Stage 2 output (primary diagnosis)
        |
        v
Qdrant vector search (BioLORD-2023 embeddings)
        |
        v
Top 3 NICE guideline matches
        |
        v
Treatment Planning Agent (2-call LLM approach)
        |
        v
TreatmentOutput (structured JSON)
```

**Key files:**

| File | Purpose |
|------|---------|
| `src/agents/treatment.py` | Agent implementation |
| `src/schemas/treatment.py` | Pydantic v2 output schema |
| `src/vectordb/query_guidelines.py` | Qdrant search client |
| `src/vectordb/setup_qdrant.py` | Qdrant collection setup and upload |
| `config/guidelines/guideline_index.json` | Disease-to-file mapping |
| `config/guidelines/*.json` | Individual NICE guideline JSONs |

---

## 2. NICE Guidelines

### 2.1 What Are NICE Guidelines?

NICE (National Institute for Health and Care Excellence) publishes evidence-based clinical guidelines for the NHS. Each guideline covers a specific disease and specifies:

- First-line, second-line, and additional treatment options
- Contraindicated drugs and why
- Monitoring requirements
- Non-pharmacological interventions
- Referral criteria

CMADS uses NICE guidelines as the authoritative treatment reference rather than allowing the LLM to generate treatment recommendations from its training data alone.

### 2.2 Diseases Covered

The system includes structured NICE guidelines for 8 target diseases (mapped via 9 entries in `guideline_index.json` because CKD stages 1-3 share one file):

| Disease (SNOMED term) | NICE Reference | NICE Title | Source |
|---|---|---|---|
| Chronic congestive heart failure (disorder) | NG106 | Chronic heart failure in adults: diagnosis and management | NICE NG106 (2018, updated 2023) |
| Essential hypertension (disorder) | NG136 | Hypertension in adults: diagnosis and management | NICE NG136 (2019, updated 2022) |
| Diabetes mellitus type 2 (disorder) | NG28 | Type 2 diabetes in adults: management | NICE NG28 (2015, updated 2022) |
| Ischemic heart disease (disorder) | CG126 / NG185 | Stable angina: management / Acute coronary syndromes | NICE CG126 (2011, updated 2016), NG185 (2020) |
| End-stage renal disease (disorder) | NG107 / NG203 | Renal replacement therapy and conservative management / CKD assessment and management | NICE NG107 (2018), NG203 (2021, updated 2023) |
| Chronic kidney disease stages 1-3 (disorder) | NG203 | Chronic kidney disease: assessment and management | NICE NG203 (2021, updated 2023) |
| Metabolic syndrome X (disorder) | CG181 / PH46 / NG28 | Cardiovascular disease risk assessment / BMI and waist circumference / Type 2 diabetes prevention | NICE CG181 (2014), PH46 (2013), NG28 (2015) |

The `guideline_index.json` maps SNOMED disease names to JSON filenames. CKD stages 1, 2, and 3 all point to the same `chronic_kidney_disease.json` file:

```json
{
  "mappings": {
    "Chronic congestive heart failure (disorder)": "chronic_congestive_heart_failure.json",
    "Essential hypertension (disorder)": "essential_hypertension.json",
    "Diabetes mellitus type 2 (disorder)": "diabetes_mellitus_type_2.json",
    "Ischemic heart disease (disorder)": "ischemic_heart_disease.json",
    "End-stage renal disease (disorder)": "end_stage_renal_disease.json",
    "Chronic kidney disease stage 1 (disorder)": "chronic_kidney_disease.json",
    "Chronic kidney disease stage 2 (disorder)": "chronic_kidney_disease.json",
    "Chronic kidney disease stage 3 (disorder)": "chronic_kidney_disease.json",
    "Metabolic syndrome X (disorder)": "metabolic_syndrome.json"
  }
}
```

### 2.3 Guideline JSON Structure

Each guideline JSON follows a consistent structure. Example from `chronic_congestive_heart_failure.json`:

```json
{
  "disease": "Chronic congestive heart failure (disorder)",
  "snomed_code": "88805009",
  "nice_guideline": "NG106",
  "nice_title": "Chronic heart failure in adults: diagnosis and management",
  "source": "NICE NG106 (2018, updated 2023)",

  "first_line_treatment": [
    {
      "drug_class": "ACE inhibitor",
      "examples": ["Ramipril", "Lisinopril", "Enalapril"],
      "indication": "All patients with HFrEF (LVEF <=40%)",
      "notes": "Titrate to maximum tolerated dose..."
    }
  ],

  "second_line_treatment": [ ... ],
  "additional_options": [ ... ],

  "contraindicated_drugs": [
    {"drug": "Verapamil", "reason": "Negative inotrope -- worsens heart failure"},
    {"drug": "Diltiazem", "reason": "Negative inotrope -- worsens heart failure"},
    {"drug": "NSAIDs", "reason": "Fluid retention, worsen renal function"}
  ],

  "monitoring": [
    "Renal function and electrolytes: before starting ACE-I/ARB/MRA, 1-2 weeks after each dose change",
    "Weight: daily self-monitoring for fluid status"
  ],

  "non_pharmacological": [
    "Fluid restriction: 1.5-2L/day if hyponatraemia or fluid overload",
    "Exercise rehabilitation: supervised exercise programme"
  ],

  "referral_criteria": [
    "New diagnosis: refer to heart failure specialist within 2 weeks"
  ]
}
```

Each treatment entry contains `drug_class`, `examples` (specific drug names), `indication` (when to use), and `notes` (dosing/timing guidance). This structure lets the LLM select specific drugs from a defined set rather than hallucinating drug names.

---

## 3. Qdrant Vector Database

### 3.1 Why Vector Search?

The Diagnostic Agent produces a free-text disease name (e.g., "Atherosclerotic coronary artery disease" or "Stage 5 CKD"). This name does not necessarily match the exact SNOMED terms used in the guideline index. Vector search with biomedical embeddings handles this semantic gap -- "coronary artery disease" lands on the ischemic heart disease guideline, and "Stage 5 CKD" lands on the ESRD guideline.

### 3.2 Embedding Model

The system uses **BioLORD-2023** (`FremyCompany/BioLORD-2023`), a sentence-transformer model specifically trained on biomedical ontologies (SNOMED-CT, ICD-10, MeSH). This makes it superior to general-purpose embedding models for matching clinical disease names.

```python
from sentence_transformers import SentenceTransformer
model = SentenceTransformer("FremyCompany/BioLORD-2023")
```

The model is lazy-loaded as a singleton in `src/vectordb/query_guidelines.py` to avoid reloading on every query.

### 3.3 Collection Setup

The setup script (`src/vectordb/setup_qdrant.py`) creates a Qdrant collection called `nice_guidelines` using cosine similarity:

```python
client.create_collection(
    collection_name="nice_guidelines",
    vectors_config=VectorParams(size=embedding_dim, distance=Distance.COSINE),
)
```

Each guideline is embedded as a rich text string combining the disease name, NICE title, and first-line drug information:

```python
text_to_embed = (
    f"{disease_name}. "
    f"{guideline.get('nice_title', '')}. "
    f"{guideline.get('disease', '')}. "
    f"First-line treatment: {first_line_text}"
)
```

Including first-line treatment text in the embedding improves retrieval when the diagnostic agent uses treatment-related terminology in the disease name.

When the same guideline file is mapped to multiple disease names (e.g., CKD stages 1, 2, and 3 all use `chronic_kidney_disease.json`), each alias gets its own vector point with a separate embedding.

### 3.4 Stored Payload

Each Qdrant point stores the following payload alongside the embedding vector:

| Field | Type | Description |
|-------|------|-------------|
| `disease_name` | string | SNOMED disease name from `guideline_index.json` |
| `nice_guideline` | string | NICE reference (e.g., "NG106") |
| `nice_title` | string | Full guideline title |
| `source` | string | Source with year and update info |
| `filename` | string | JSON filename in `config/guidelines/` |
| `guideline_json` | string | Full guideline JSON serialized as string |

### 3.5 Query Flow

At runtime, the Treatment Agent calls `search_guidelines(disease_name, top_k=3)`:

1. Encode the diagnosed disease name using BioLORD-2023
2. Query Qdrant for the top 3 nearest vectors by cosine similarity
3. Parse the stored `guideline_json` back into a dict
4. Return a list of results, each containing `disease_name`, `nice_guideline`, `nice_title`, `score`, `source`, and `guideline`

```python
from src.vectordb.query_guidelines import search_guidelines
results = search_guidelines("heart failure with reduced ejection fraction", top_k=3)
# Returns: [
#   {"disease_name": "Chronic congestive heart failure (disorder)",
#    "nice_guideline": "NG106", "score": 0.912, "guideline": {...}},
#   ...
# ]
```

The top match is used as the primary guideline. All 3 matches are included in the prompt so the LLM can cross-reference related guidelines (e.g., a patient with both heart failure and CKD).

### 3.6 Environment Variables

Qdrant connection requires two environment variables:

| Variable | Purpose |
|----------|---------|
| `QDRANT_URL` | Qdrant cloud instance URL |
| `QDRANT_API_KEY` | Authentication API key |

---

## 4. Agent Architecture -- 2-Call Approach

The Treatment Planning Agent uses a two-call LLM strategy, consistent with the pattern used by other CMADS agents. This separates clinical reasoning from structured output generation.

### 4.1 Call 1 -- Clinical Analysis (Free Text)

The first call uses a clinical pharmacist persona. The LLM receives the full patient context and NICE guideline, then produces an unstructured analysis covering:

1. Which first-line medications should be prescribed (specific drugs and doses)
2. Which guideline-recommended drugs the patient already takes
3. Drug interactions between proposed and current medications
4. Contraindication checks against the NICE contraindicated drugs list
5. Assumptions and warnings for missing patient data

The system message explicitly instructs "Do NOT produce JSON yet" -- this lets the LLM reason freely before being constrained by schema.

```
System: "You are a clinical pharmacist reviewing a patient case against NICE guidelines.
         Analyse the patient's situation and plan the treatment. Do NOT produce JSON yet."
```

The contraindicated drugs from all matched guidelines are extracted and appended to the prompt as a separate section:

```
CONTRAINDICATED DRUGS FROM NICE GUIDELINES (MUST CHECK):
  - Verapamil: Negative inotrope -- worsens heart failure
  - Diltiazem: Negative inotrope -- worsens heart failure
  - NSAIDs: Fluid retention, worsen renal function
```

### 4.2 Call 2 -- Structured Output (JSON)

The second call receives the analysis from Call 1 plus the original patient data, and is instructed to convert the analysis into the `TreatmentOutput` JSON schema. The full Pydantic schema is included in the prompt via `TreatmentOutput.model_json_schema()`.

```
System: Treatment Planning Agent system prompt (rules + output format)
User:   "# Your Analysis\n{analysis}\n\n# Patient Data and Guideline\n{prompt_data}\n\n
         Convert your analysis into the required JSON format."
```

The output is parsed using the base agent's `_parse_output` method, which handles JSON extraction, repair, and Pydantic validation.

### 4.3 Inputs from Upstream Agents

The Treatment Agent reads from multiple upstream agent outputs:

| Source | Data Used | Purpose |
|--------|-----------|---------|
| `agent_outputs.final_diagnosis` or `agent_outputs.diagnostic_reasoning` | `primary_diagnosis`, `differential` | Determines which disease to treat |
| `agent_outputs.ehr_analyst` | `active_medications`, `active_problems`, `clinical_impression`, `risk_factor_summary` | Current drugs (interaction checking), conditions (contraindication checking), clinical context |
| `agent_outputs.lab_interpreter` | `findings` (severity >= 3), `overall_assessment`, `critical_alerts` | Lab values for dosing decisions (eGFR, potassium, HbA1c) |
| `patient_context.ehr_case` | `patient_uuid` | Locates the evaluation.json for gate logic |

---

## 5. Gate Logic -- DIRECT Matches Only

The Treatment Agent does not run for every patient. It checks the evaluation result before proceeding.

### 5.1 How It Works

Before building the treatment prompt, the agent reads:

```
data/gold/mas_results/{patient_uuid}/evaluation.json
```

This file is produced by the evaluation framework (LLM-as-Judge) and contains the `match_type` field -- one of `DIRECT`, `INDIRECT`, or `MISS`.

```python
eval_path = Path("data/gold/mas_results") / patient_uuid / "evaluation.json"
if eval_path.exists():
    ev = json.loads(eval_path.read_text())
    if ev.get("match_type") != "DIRECT":
        return {
            "primary_diagnosis_treated": "SKIPPED -- not a DIRECT match",
            "treatment_summary": f"Treatment not generated. Evaluation result: {ev.get('match_type')} ...",
        }
```

### 5.2 Why Only DIRECT?

| Match Type | Treatment Generated? | Rationale |
|---|:---:|---|
| **DIRECT** | YES | The MAS correctly identified the disease. A treatment plan against the right diagnosis is meaningful. |
| **INDIRECT** | NO | The MAS found a related condition (e.g., "Diabetic nephropathy" for ESRD target). Treating the wrong-but-related disease would produce a misleading plan. |
| **MISS** | NO | The MAS did not find the target disease at all. No basis for treatment. |

### 5.3 Fallback When No Evaluation Exists

If `evaluation.json` does not exist (e.g., during development or testing), the agent falls back to using the primary diagnosis from the diagnostic agent's output directly, without gating:

```python
else:
    final = agent_outputs.get("final_diagnosis", {}) or agent_outputs.get("diagnostic_reasoning", {})
    primary = final.get("primary_diagnosis", "Unknown")
```

---

## 6. Drug Interaction and Contraindication Checking

Drug safety checking happens at two levels.

### 6.1 NICE Guideline Contraindications (Rule-Based)

Each guideline JSON contains a `contraindicated_drugs` array. The agent extracts these from all matched guidelines and presents them explicitly in the Call 1 prompt. The LLM is instructed to check each contraindicated drug against three conditions:

1. **Is the patient currently taking it?** If yes, flag it.
2. **Does the patient have a condition that makes it contraindicated?** If yes, flag it.
3. **Were you about to propose it?** If yes, do NOT prescribe it and suggest an alternative.

Example contraindicated drugs for heart failure (NG106):

| Drug | Reason |
|------|--------|
| Verapamil | Negative inotrope -- worsens heart failure |
| Diltiazem | Negative inotrope -- worsens heart failure |
| NSAIDs | Fluid retention, worsen renal function |
| Thiazolidinediones (Pioglitazone) | Fluid retention |
| Class I antiarrhythmics (Flecainide) | Pro-arrhythmic in HF |

### 6.2 System Prompt Safety Rules (LLM-Driven)

The system prompt includes hard-coded safety rules that apply across all guidelines:

| Rule | Trigger | Action |
|------|---------|--------|
| eGFR < 30 | Renal impairment | Flag metformin, NSAIDs, and dose-adjusted drugs |
| Heart failure present | Comorbidity | Avoid verapamil, diltiazem, pioglitazone, NSAIDs |
| Patient on ACE-I | Current medication | Do NOT add ARB (no dual RAAS blockade) |
| Elderly/frail patient | Age/status | Consider lower starting doses |

### 6.3 Output Schema for Safety Checks

Interactions and contraindications are captured as structured lists in the output:

```json
{
  "interactions_checked": [
    {
      "drug_pair": ["Ramipril", "Spironolactone"],
      "interaction": "Both increase potassium -- risk of hyperkalaemia",
      "severity": "moderate",
      "action": "Monitor potassium within 1 week of starting, then monthly"
    }
  ],
  "contraindications": [
    {
      "drug": "Metformin",
      "reason": "eGFR 22 mL/min -- contraindicated below 30",
      "alternative": "Consider insulin or SGLT2i with renal dosing"
    }
  ]
}
```

---

## 7. Assumptions and Warnings

A critical design feature of the Treatment Agent is explicit declaration of assumptions made due to missing patient data.

### 7.1 The Problem

NICE guidelines often require clinical data that Synthea does not generate or that may not be present in every patient record. For example:

- NG106 (heart failure) requires LVEF to distinguish HFrEF from HFpEF -- Synthea does not produce echocardiography values
- NG136 (hypertension) requires QRISK assessment -- not calculated in the data pipeline
- NG28 (diabetes) requires HbA1c for glycemic targets -- may or may not be in the lab data

### 7.2 How It Works

The Call 1 prompt instructs the LLM to identify every assumption:

```
ASSUMPTIONS & WARNINGS -- check what the NICE guideline REQUIRES but the patient
data does NOT have. For example:
  - eGFR unknown -> 'Cannot verify renal safety of ACE-I dosing'
  - Allergy data missing -> 'Cannot verify drug allergy safety'
  - QRISK not calculated -> 'NICE requires QRISK for statin decision'
  - LVEF unknown -> 'Cannot confirm HFrEF vs HFpEF for drug selection'
  - HbA1c unknown -> 'Cannot verify glycemic target for insulin dosing'
  - Potassium unknown -> 'Cannot verify MRA/spironolactone safety'
```

### 7.3 Output

Assumptions are stored as a list of strings in `assumptions_warnings`:

```json
{
  "assumptions_warnings": [
    "NICE NG106 requires LVEF to confirm HFrEF -- not available in patient data. Treatment assumes HFrEF based on diagnostic impression.",
    "Potassium level unknown -- cannot verify safety of spironolactone. Monitor within 1 week of starting.",
    "Allergy status not documented -- cannot verify drug allergy safety for any proposed medication."
  ]
}
```

This ensures that downstream agents (Clinical Reviewer, Synthesis) and human readers understand the limitations of the treatment plan.

---

## 8. Output Schema

The Treatment Agent produces a `TreatmentOutput` object defined in `src/schemas/treatment.py`. All fields use Pydantic v2.

### 8.1 Top-Level Schema

| Field | Type | Description |
|-------|------|-------------|
| `primary_diagnosis_treated` | `str` | The disease this treatment plan addresses |
| `nice_guideline_used` | `str` | NICE reference (e.g., "NG106", "NG136") |
| `medications` | `list[PrescribedMedication]` | Prescribed medications with dose, duration, and justification |
| `interactions_checked` | `list[InteractionCheck]` | Drug interactions between proposed and current medications |
| `contraindications` | `list[ContraindicationCheck]` | Drugs contraindicated for this patient |
| `assumptions_warnings` | `list[str]` | Warnings where NICE guideline requires data the patient record does not have |
| `treatment_summary` | `str` | Brief summary of the treatment plan and rationale |

### 8.2 PrescribedMedication

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `medication` | `str` | *(required)* | Drug name and dose |
| `drug_class` | `str` | `""` | Drug class (e.g., "ACE inhibitor", "Beta-blocker") |
| `dose` | `str` | `""` | Dosing regimen (e.g., "5mg once daily") |
| `duration` | `str` | `""` | Duration -- see Section 9 for rules |
| `purpose` | `str` | `""` | Why this drug is prescribed for this patient |
| `nice_justification` | `str` | `""` | NICE guideline reference supporting this choice |
| `line` | `str` | `"first_line"` | `first_line`, `second_line`, or `additional` |

### 8.3 InteractionCheck

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `drug_pair` | `list[str]` | *(required)* | The two drugs that interact |
| `interaction` | `str` | *(required)* | Description of the interaction |
| `severity` | `str` | `"moderate"` | `mild`, `moderate`, or `severe` |
| `action` | `str` | `""` | Recommended action |

### 8.4 ContraindicationCheck

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `drug` | `str` | *(required)* | Drug that is contraindicated |
| `reason` | `str` | *(required)* | Why it is contraindicated for this patient |
| `alternative` | `str` | `""` | What to use instead |

### 8.5 MonitoringPlan

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `test` | `str` | *(required)* | What to monitor |
| `frequency` | `str` | *(required)* | How often |
| `reason` | `str` | `""` | Why this monitoring is needed |

Note: `MonitoringPlan` is defined in the schema but monitoring data in the current implementation is conveyed through the guideline's `monitoring` array and the treatment summary rather than as a separate structured list in the output.

### 8.6 Full Output Example

```json
{
  "primary_diagnosis_treated": "Chronic congestive heart failure (disorder)",
  "nice_guideline_used": "NG106",
  "medications": [
    {
      "medication": "Ramipril 2.5mg",
      "drug_class": "ACE inhibitor",
      "dose": "2.5mg once daily, titrate to 10mg over 4-6 weeks",
      "duration": "Lifelong -- review annually",
      "purpose": "First-line HFrEF treatment to reduce mortality and hospitalisation",
      "nice_justification": "NICE NG106: ACE-I recommended for all patients with HFrEF, titrate to max tolerated dose",
      "line": "first_line"
    },
    {
      "medication": "Bisoprolol 1.25mg",
      "drug_class": "Beta-blocker (licensed for heart failure)",
      "dose": "1.25mg once daily, titrate to 10mg over 8-12 weeks",
      "duration": "Lifelong -- review annually",
      "purpose": "Reduces heart rate, improves LVEF, reduces mortality in stable HFrEF",
      "nice_justification": "NICE NG106: Beta-blocker licensed for HF recommended for all stable HFrEF patients",
      "line": "first_line"
    },
    {
      "medication": "Dapagliflozin 10mg",
      "drug_class": "SGLT2 inhibitor",
      "dose": "10mg once daily",
      "duration": "Lifelong -- review annually",
      "purpose": "Reduces HF hospitalisation and CV death regardless of diabetes status",
      "nice_justification": "NICE NG106 (TA902): SGLT2i now first-line for HFrEF per 2023 update",
      "line": "first_line"
    },
    {
      "medication": "Furosemide 40mg",
      "drug_class": "Loop diuretic",
      "dose": "40mg once daily, titrate to symptoms",
      "duration": "As needed for congestion -- reassess at each visit",
      "purpose": "Symptomatic relief of fluid overload (oedema, breathlessness)",
      "nice_justification": "NICE NG106: Loop diuretic for fluid overload symptoms, not disease-modifying",
      "line": "first_line"
    }
  ],
  "interactions_checked": [
    {
      "drug_pair": ["Ramipril", "Spironolactone"],
      "interaction": "Both increase potassium -- risk of hyperkalaemia",
      "severity": "moderate",
      "action": "Monitor potassium and renal function within 1 week, then monthly for 3 months"
    }
  ],
  "contraindications": [
    {
      "drug": "Verapamil",
      "reason": "Patient has heart failure -- verapamil is a negative inotrope that worsens HF (NICE NG106)",
      "alternative": "Use bisoprolol for rate control if needed"
    }
  ],
  "assumptions_warnings": [
    "LVEF not available -- treatment assumes HFrEF based on diagnostic impression. NICE NG106 drug selection depends on LVEF <= 40%.",
    "Potassium level unknown -- cannot verify safety of spironolactone/MRA initiation. Must check before starting.",
    "NT-proBNP not available -- cannot use for baseline treatment response tracking."
  ],
  "treatment_summary": "Four-pillar HFrEF therapy initiated per NICE NG106 (2023): ACE-I (Ramipril), beta-blocker (Bisoprolol), SGLT2i (Dapagliflozin), and loop diuretic (Furosemide) for symptom relief. MRA deferred pending potassium confirmation. No contraindicated drugs identified in current medication list. Key monitoring: renal function and electrolytes before and after ACE-I titration, daily weight, echocardiogram at 6-12 months."
}
```

---

## 9. Duration Rules

The system prompt enforces specific duration rules to prevent the LLM from defaulting every medication to "Ongoing."

| Medication Category | Required Duration Format | Example |
|---|---|---|
| Chronic/lifelong drugs | "Lifelong -- review annually" | ACE-I for HFrEF |
| Titration drugs | Specify the titration period, then maintenance | "Start 2.5mg, titrate to 10mg over 4-6 weeks, then lifelong" |
| Acute drugs | Exact duration | "Antibiotics: 7 days" |
| Time-limited post-event drugs | NICE-specified duration | "Clopidogrel: 12 months post-ACS" |
| Goal-directed drugs | Specify the target | "Until ferritin > 200, then review" |
| Monitoring-dependent drugs | Specify review points | "6 months, reassess based on LVEF response" |

The key instruction from the system prompt:

```
## Duration Rules -- DO NOT default to "Ongoing"
- Use the NICE guideline duration if specified
- For titration drugs: specify the titration period
- For acute drugs: specify exact duration
- For chronic drugs: say "Lifelong -- review annually" not just "Ongoing"
- For goal-directed drugs: specify the target
- For monitoring-dependent drugs: specify review points
```

This produces clinically meaningful duration fields that distinguish between a drug prescribed for life and one prescribed for a defined period, which is critical for the Clinical Reviewer and Synthesis agents downstream.

---

## 10. Agent Configuration

The Treatment Planning Agent uses the following configuration constants:

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| `agent_id` | `"treatment_planning"` | Identifier in shared memory (`agent_outputs.treatment_planning`) |
| `temperature` | `0.2` | Low temperature for deterministic, guideline-adherent output |
| `max_tokens` | `8192` | Treatment plans with multiple medications and safety checks can be lengthy |
| `output_schema` | `TreatmentOutput` | Pydantic v2 model for structured parsing |

The agent extends `BaseAgent`, inheriting the 5-component blueprint: Input Gate, Prompt Assembler, LLM call, Output Parser, and Output Gate.
