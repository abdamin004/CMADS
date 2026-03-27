# Data Pipeline Layers

## Bronze → Silver → Silver+ → Gold

| | |
|---|---|
| **Project** | Multi-Agent Systems for AI Clinical Decisioning via Automation Workflows |
| **Author** | Abdelrahman |
| **Date** | March 2026 |
| **Data Source** | Synthea (14,335 patients, seed 42) |
| **Database** | DuckDB (clinical.duckdb) |
| **Transform Engine** | dbt-core (SQL models) |

---

## 1. Overview

The CMADS data pipeline transforms raw Synthea-generated CSV files into structured, clinically enriched JSON case files consumed by the multi-agent pipeline. The pipeline follows a four-layer medallion architecture, with all data stored in a single DuckDB database file (`clinical.duckdb`).

Each layer has a specific tool, a specific purpose, and strict rules about what it can read and write:

| Layer | Tool | Tables | Purpose | Output |
|-------|------|--------|---------|--------|
| Bronze | Python → DuckDB | 15 | Raw CSV loaded as-is | DuckDB tables (1:1 with CSV) |
| Silver | dbt-core + DuckDB | 6 | OMOP CDM v5.4 mapping | Standardised clinical tables |
| Silver+ | dbt-core + DuckDB | 9 | Derived clinical features | Risk scores, trends, flags |
| Gold | Python assembler | 2 JSONs/pt | Case file assembly | ehr_case.json + lab_case.json |

### Execution sequence

```bash
# 1. Load CSVs into DuckDB (Bronze)
python pipeline/load_csv_to_duckdb.py batch_10k

# 2. Run Silver + Silver+ transforms
dbt run --select silver.* silver_plus.*

# 3. Run data quality tests
dbt test --select silver.* silver_plus.*

# 4. Assemble Gold case files
python pipeline/gold/assemble_cases.py
```

---

## 2. Bronze Layer

**Raw ingestion — Python + DuckDB**

### 2.1 What it does

The Bronze layer loads Synthea's 15 CSV files into DuckDB tables with zero transformations. Each CSV becomes one table with identical column names and types. This is a one-time bulk load operation.

### 2.2 How it works

```python
# pipeline/load_csv_to_duckdb.py
import duckdb

con = duckdb.connect('data/clinical.duckdb')

csv_files = [
    'patients', 'encounters', 'conditions', 'observations',
    'medications', 'procedures', 'imaging_studies', 'allergies',
    'devices', 'careplans', 'immunizations', 'claims',
    'claims_transactions', 'payer_transitions', 'supplies'
]

for name in csv_files:
    con.execute(f"""
        CREATE OR REPLACE TABLE {name} AS
        SELECT * FROM read_csv_auto('data/raw/batch_10k/csv/{name}.csv')
    """)
```

### 2.3 What's in it

| Table | Rows | Key Content |
|-------|------|-------------|
| patients | 14,335 | Demographics: name, DOB, gender, race, ethnicity, address |
| encounters | 963,992 | Every clinical visit: type, provider, reason code, dates, cost |
| conditions | 442,280 | Diagnoses (SNOMED-CT): onset date, resolution date, encounter FK |
| observations | 10,951,316 | All labs + vitals (LOINC): value, unit, date, reference ranges |
| medications | 764,666 | Prescriptions (RxNorm): drug name, dose, start/stop, reason code |
| procedures | 2,184,378 | Clinical procedures (SNOMED): date, cost, encounter FK |
| imaging_studies | 1,094,332 | Imaging metadata: modality, body site, DICOM UIDs (no report text) |
| allergies | 10,961 | Drug/food allergies: type, severity, onset |

### 2.4 Rules

- No transformations — data is loaded exactly as Synthea produced it
- No deduplication — if Synthea produces duplicates, they stay
- No type casting — DuckDB auto-detects types from CSV
- Idempotent — `CREATE OR REPLACE` means re-running replaces all tables

---

## 3. Silver Layer

**OMOP CDM v5.4 — dbt-core + DuckDB**

### 3.1 What it does

The Silver layer transforms raw Synthea tables into the **OMOP Common Data Model v5.4** — a standardised healthcare data schema used across the industry. The core work is **vocabulary mapping**: converting Synthea's raw codes (SNOMED-CT, LOINC, RxNorm) into OMOP `concept_id` values using vocabulary lookup tables.

### 3.2 The 6 OMOP tables

| OMOP Table | dbt Model | Source Bronze Table | What the transform does |
|------------|-----------|---------------------|-------------------------|
| person | silver/person.sql | patients | Maps gender/race/ethnicity to concept_ids, extracts birth year/month |
| visit_occurrence | silver/visit_occurrence.sql | encounters | Maps encounter class to visit_concept_id, standardises dates |
| condition_occurrence | silver/condition_occurrence.sql | conditions | Maps SNOMED code → condition_concept_id via vocab lookup |
| measurement | silver/measurement.sql | observations | Maps LOINC code → measurement_concept_id, preserves value + range |
| drug_exposure | silver/drug_exposure.sql | medications | Maps RxNorm code → drug_concept_id, standardises dates + quantity |
| observation | silver/observation.sql | observations | Non-lab observations (social history, surveys) → concept_id |

### 3.3 Vocabulary mapping in detail

Each dbt model uses a macro to look up concept IDs. The vocabulary data comes from OHDSI Athena, seeded as CSV files in the dbt project:

```sql
-- Example: condition_occurrence.sql
SELECT
  c.PATIENT AS person_id,
  {{ snomed_to_concept('c.CODE') }} AS condition_concept_id,
  c.CODE AS condition_source_value,
  c.DESCRIPTION AS condition_source_name,
  CAST(c.START AS DATE) AS condition_start_date,
  CAST(c.STOP AS DATE) AS condition_end_date,
  e.ID AS visit_occurrence_id
FROM {{ ref('encounters') }} e
JOIN {{ ref('conditions') }} c ON c.ENCOUNTER = e.ID

-- The macro expands to:
-- COALESCE(v.concept_id, 0)  (0 = unmapped)
-- FROM concept_lookup v WHERE v.source_code = c.CODE
```

### 3.4 dbt tests

Every Silver table has dbt tests defined in `schema.yml`:

| Test | What it checks |
|------|----------------|
| unique | No duplicate primary keys (person_id, measurement_id, etc.) |
| not_null | Critical fields (concept_ids, dates) are never NULL |
| relationships | Every person_id in condition_occurrence exists in person |
| accepted_values | Concept IDs are valid OMOP values (not arbitrary numbers) |
| assert_concept_coverage | Less than 5% of records have unmapped concept_id = 0 |
| assert_no_patient_loss | COUNT(person) in Silver = COUNT(patients) in Bronze |

---

## 4. Silver+ Layer

**Derived clinical features — dbt-core + DuckDB**

### 4.1 What it does

The Silver+ layer computes **clinically meaningful derived features** from the Silver OMOP tables. These are not raw data — they are pre-computed clinical intelligence (trend analysis, risk scoring, comorbidity detection) that the agents would otherwise need to calculate themselves. Each table is a dbt SQL model running inside DuckDB.

### 4.2 All 9 derived tables

---

#### 4.2.1 lab_trends

**Purpose:** For each patient and each lab test (LOINC code), computes the slope of values over time using linear regression. Classifies the trend as rising, falling, or stable.

**Source:** `measurement` (Silver)

```sql
SELECT person_id, loinc_code,
  COUNT(*) AS measurement_count,
  REGR_SLOPE(value_as_number, EPOCH(measurement_date)) AS trend_slope,
  FIRST(value_as_number ORDER BY measurement_date) AS first_value,
  LAST(value_as_number ORDER BY measurement_date) AS last_value,
  CASE
    WHEN trend_slope > 0.01 THEN 'RISING'
    WHEN trend_slope < -0.01 THEN 'FALLING'
    ELSE 'STABLE'
  END AS trend_direction
FROM measurement GROUP BY person_id, loinc_code
```

**Example:** Patient's creatinine readings: 1.0 → 1.2 → 1.5 → 1.8 over 2 years. Slope is positive → trend_direction = 'RISING'. The Lab Interpreter Agent sees this and reports: "creatinine has been rising, suggesting declining renal function."

**Consumed by:** Lab Interpreter Agent, Gold layer (lab_case.json)

---

#### 4.2.2 critical_lab_flags

**Purpose:** Flags lab values that are dangerously abnormal, scored on a severity scale of 1–5. Uses a threshold reference table seeded as CSV.

**Source:** `measurement` (Silver) + `critical_thresholds.csv` (dbt seed)

```sql
SELECT m.person_id, m.loinc_code, m.value_as_number,
  CASE
    WHEN m.value_as_number > t.critical_high * 1.5 THEN 5  -- life-threatening
    WHEN m.value_as_number > t.critical_high THEN 3        -- urgent
    WHEN m.value_as_number < t.critical_low * 0.5 THEN 5
    WHEN m.value_as_number < t.critical_low THEN 3
    WHEN m.value_as_number > t.ref_high THEN 2             -- abnormal
    WHEN m.value_as_number < t.ref_low THEN 2
    ELSE 1                                                 -- normal
  END AS severity
FROM measurement m JOIN critical_thresholds t ON m.loinc_code = t.loinc
```

**Example:** Potassium = 6.8 mEq/L (critical threshold = 6.5) → severity 5. Hemoglobin = 6.2 g/dL (critical low = 7.0) → severity 5.

**Consumed by:** Lab Interpreter Agent (prioritises findings), Clinical Reviewer Agent (verifies severity ≥3 findings are addressed)

---

#### 4.2.3 patient_risk_scores

**Purpose:** Computes standardised clinical risk scores per patient from their labs and conditions.

**Source:** `measurement` + `condition_occurrence` + `drug_exposure` (Silver)

| Score | Computation | Clinical meaning |
|-------|-------------|------------------|
| CKD stage (1–5) | Based on latest eGFR value | Stage of chronic kidney disease |
| HbA1c band | Latest HbA1c: normal / prediabetic / diabetic | Diabetes control status |
| Framingham risk | Age + cholesterol + BP + smoking + diabetes | 10-year cardiovascular event risk (%) |
| SOFA score | Organ dysfunction scoring from labs + vitals | ICU severity indicator |
| Polypharmacy index | COUNT of concurrent active medications | Drug interaction risk indicator |

```sql
CASE
  WHEN egfr >= 90 THEN 'Stage 1'
  WHEN egfr >= 60 THEN 'Stage 2'
  WHEN egfr >= 30 THEN 'Stage 3'
  WHEN egfr >= 15 THEN 'Stage 4'
  ELSE 'Stage 5'
END AS ckd_stage
```

**Consumed by:** Diagnostic Reasoning Agent (considers CKD stage and Framingham when ranking differential diagnoses)

---

#### 4.2.4 comorbidity_matrix

**Purpose:** Binary flag matrix — one row per patient, one boolean column per target condition (has_diabetes, has_ckd, has_chf, etc.). Plus a complexity_score = count of active conditions.

**Source:** `condition_occurrence` (Silver)

```sql
SELECT person_id,
  MAX(CASE WHEN condition_concept_id = 201826 THEN 1 ELSE 0 END) AS has_diabetes,
  MAX(CASE WHEN condition_concept_id = 192671 THEN 1 ELSE 0 END) AS has_ckd,
  MAX(CASE WHEN condition_concept_id = 316139 THEN 1 ELSE 0 END) AS has_chf,
  ... -- one column per target condition
  SUM(CASE WHEN condition_end_date IS NULL THEN 1 END) AS complexity_score
FROM condition_occurrence GROUP BY person_id
```

**Consumed by:** Diagnostic Reasoning Agent ("diabetes + CKD + hypertension" pattern guides differential ranking)

---

#### 4.2.5 medication_timeline

**Purpose:** Resolves overlapping drug_exposure records into continuous therapy episodes. Detects gaps (>30 days = new episode). Counts concurrent medications at any point.

**Source:** `drug_exposure` (Silver)

**Key computation:** Uses window functions (`LAG`) to detect therapy gaps and group into episodes. Computes concurrent med count at each date.

```sql
CASE
  WHEN drug_start - LAG(drug_end) OVER (
    PARTITION BY person_id, drug_concept_id ORDER BY drug_start
  ) > 30 THEN 'NEW_EPISODE'
END
```

**Consumed by:** Treatment Planning Agent (checks what the patient is already taking before proposing new drugs)

---

#### 4.2.6 encounter_summary

**Purpose:** Per-patient visit statistics — counts by visit type (ED, inpatient, ambulatory), visit frequency, and 30-day readmission rate.

**Source:** `visit_occurrence` (Silver)

**Key computation:** Uses `LEAD` window function to find next admission within 30 days of discharge for readmission rate.

```sql
COUNT(CASE WHEN visit_concept_id = 9201 THEN 1 END) AS inpatient_count,
COUNT(CASE WHEN visit_concept_id = 9203 THEN 1 END) AS ed_count,
-- 30-day readmission via LEAD window function
CASE WHEN LEAD(visit_start_date) OVER (...) - visit_end_date <= 30 THEN 1 END
```

**Consumed by:** EHR Analyst Agent ("3 ED visits in 6 months suggests poorly controlled condition")

---

#### 4.2.7 drug_condition_links

**Purpose:** Maps which drug treats which condition (drug → indication pairs) by joining `drug_exposure.REASONCODE` to conditions. Also flags known contraindications.

**Source:** `drug_exposure` + `condition_occurrence` (Silver)

```sql
SELECT d.drug_concept_id, c.condition_concept_id,
  'INDICATION' AS link_type
FROM drug_exposure d
JOIN condition_occurrence c ON d.reason_code = c.condition_source_value

UNION ALL

-- Cross-reference with contraindication seed table
SELECT ci.drug_concept_id, ci.condition_concept_id,
  'CONTRAINDICATION' AS link_type
FROM contraindications_seed ci
```

**Consumed by:** Treatment Planning Agent (checks proposed medications against existing conditions for interactions and contraindications)

---

#### 4.2.8 lab_panel_summary

**Purpose:** Groups individual lab results into clinical panels (CMP, CBC, lipid panel, etc.) per encounter. Counts total tests, abnormal count, and completeness percentage.

**Source:** `measurement` (Silver) + `loinc_panel_groups.csv` (dbt seed)

```sql
SELECT m.visit_occurrence_id, p.panel_name,
  COUNT(*) AS total_tests,
  SUM(CASE WHEN m.value_as_number > m.range_high
           OR m.value_as_number < m.range_low THEN 1 ELSE 0 END) AS abnormal_count,
  ROUND(COUNT(*) * 100.0 / p.expected_tests) AS completeness_pct
FROM measurement m
JOIN loinc_panel_groups p ON m.measurement_source_value = p.loinc_code
GROUP BY 1, 2
```

**Consumed by:** Lab Interpreter Agent (correlates across panels: "CMP shows elevated BUN + creatinine together, suggesting renal pattern")

---

#### 4.2.9 data_quality_report

**Purpose:** Data quality checks across all Silver/Silver+ tables — null rates, orphan records, concept mapping coverage. Produces an HTML report per pipeline run.

**Source:** All Silver and Silver+ tables

**Mechanism:** Combination of dbt tests (`schema.yml`) and Great Expectations statistical profile checks.

**Consumed by:** EHR Analyst Agent (data_quality_flags field in ehr_case.json warns about incomplete data)

---

## 5. Gold Layer

**Agent input JSONs — Python assembler**

### 5.1 What it does

The Gold layer is a Python script (not dbt) that queries DuckDB to pull data from both Silver and Silver+ tables, then assembles everything into **two self-contained JSON files per patient**. These are the sole input to the multi-agent pipeline. Agents never touch DuckDB directly.

### 5.2 ehr_case.json

One file per patient. Contains everything the EHR Analyst Agent needs:

| Field | Source Table | Content |
|-------|-------------|---------|
| demographics | person | Age, gender, race, ethnicity |
| conditions | condition_occurrence | All diagnoses with SNOMED code, onset/end dates |
| medications | drug_exposure | Active + historical meds with RxNorm, dose, dates |
| allergies | Bronze allergies table | Drug/food allergies with severity |
| observations | observation | Non-lab observations (social history, surveys) |
| risk_scores | patient_risk_scores (Silver+) | CKD stage, HbA1c band, Framingham, SOFA, polypharmacy |
| comorbidity_matrix | comorbidity_matrix (Silver+) | Binary condition flags + complexity score |
| encounter_summary | encounter_summary (Silver+) | Visit counts, frequency, readmission rate |
| drug_condition_links | drug_condition_links (Silver+) | Drug → indication/contraindication pairs |

### 5.3 lab_case.json

One file per patient. Contains everything the Lab Interpreter Agent needs:

| Field | Source Table | Content |
|-------|-------------|---------|
| measurements | measurement | Raw lab values with LOINC code, value, unit, date |
| reference_ranges | measurement | Per-LOINC normal ranges (range_low, range_high) |
| lab_trends | lab_trends (Silver+) | Regression slopes, trend direction per LOINC |
| critical_lab_flags | critical_lab_flags (Silver+) | Severity 1–5 flags for abnormal values |
| lab_panel_summary | lab_panel_summary (Silver+) | Panel groupings, abnormal counts, completeness |
| risk_scores (lab fields) | patient_risk_scores (Silver+) | CKD stage, HbA1c band (lab-derived scores) |

### 5.4 Assembly process

```python
# pipeline/gold/assemble_cases.py
import duckdb, json, os

con = duckdb.connect('data/clinical.duckdb', read_only=True)

# Get all patient IDs
patients = con.execute('SELECT person_id FROM person').fetchall()

for (pid,) in patients:
    # Query Silver + Silver+ tables for this patient
    demographics = con.execute('SELECT * FROM person WHERE person_id = ?', [pid]).fetchdf()
    conditions = con.execute('SELECT * FROM condition_occurrence WHERE person_id = ?', [pid]).fetchdf()
    risk_scores = con.execute('SELECT * FROM patient_risk_scores WHERE person_id = ?', [pid]).fetchdf()
    # ... (all fields)

    ehr_case = {
        'patient_id': pid,
        'demographics': demographics.to_dict('records')[0],
        'conditions': conditions.to_dict('records'),
        'risk_scores': risk_scores.to_dict('records')[0],
        # ... (all fields assembled into one JSON)
    }

    with open(f'data/gold/{pid}/ehr_case.json', 'w') as f:
        json.dump(ehr_case, f, indent=2, default=str)
```

### 5.5 Key design principles

- **Self-contained:** Each JSON file includes ALL data the consuming agent needs. No additional lookups required.
- **Agent-specific:** ehr_case.json is shaped for the EHR Analyst; lab_case.json for the Lab Interpreter. Different agents get different slices.
- **No ground truth leakage:** The `encounters.REASONCODE` (which contains the true diagnosis) is excluded from Gold files. Agents must infer diagnoses from evidence.
- **Reproducible:** Same DuckDB + same assembler = identical Gold output.
- **Agents never touch DuckDB:** The Gold JSONs are loaded into LangGraph shared memory. The database is only used by the data pipeline and the Streamlit portal.

---

*— End of Document — Data Pipeline Layers v1.0 • March 2026 • CMADS*
