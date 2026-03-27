# Synthetic Patient Data Generation

## Overview

Patient data for CMADS is generated using **Synthea** — an open-source, rule-based patient simulator that uses state transition machines and Monte Carlo simulation informed by CDC/NIH statistics. Synthea produces realistic synthetic patient records across 18 CSV tables covering demographics, conditions, encounters, medications, observations, procedures, imaging, and more.

## Generation Command

```bash
cd synthea/

java -jar build/libs/synthea-with-dependencies.jar \
  -p 50000 \
  -k ../config/keep_cmads_diseases.json \
  -c ../config/synthea.properties \
  --exporter.baseDirectory="../data/raw/batch_10k/" \
  -s 42 \
  Massachusetts
```

### Flags Explained

| Flag | Value | Purpose |
|------|-------|---------|
| `-p` | `50000` | Total patients to simulate. Not all are exported — the keep module filters output. |
| `-k` | `keep_cmads_diseases.json` | Keep module that filters patients. Only those with at least one target disease are exported. |
| `-c` | `synthea.properties` | Custom configuration file (CSV-only export, no FHIR, 10-year history window). |
| `--exporter.baseDirectory` | `data/raw/batch_10k/` | Output directory for generated CSV files. |
| `-s` | `42` | Random seed for reproducibility. Same seed produces the same patients. |
| `Massachusetts` | — | Geography. Synthea uses state-level demographics and provider data. |

## Keep Module — Disease Filtering

The `-k` flag is the key to generating a clinically relevant cohort. Synthea generates all 50,000 patients through its full simulation (birth to present day, applying all disease modules), but **only exports patients that match the keep module criteria**.

### How It Works

1. Synthea generates a patient and runs all disease modules (heart disease, diabetes, cancer, etc.)
2. At the end of simulation, the keep module checks: does this patient have an **Active Condition** matching any of the 11 target SNOMED codes?
3. If **yes** → patient is exported to CSV
4. If **no** → patient is silently discarded

This means the keep module does not change disease prevalence or patient characteristics — it simply filters output. The exported patients are the same as they would be in an unfiltered run.

### Target Diseases

These 11 diseases were selected because they produce rich observation data (labs, vitals, imaging) in Synthea output, enabling meaningful agent diagnosis.

| SNOMED Code | Disease | Exported Patients |
|-------------|---------|-------------------|
| 271737000 | Anemia | 10,763 |
| 237602007 | Metabolic syndrome X | 3,043 |
| 55822004 | Hyperlipidemia | 2,013 |
| 233604007 | Pneumonia | 1,865 |
| 44054006 | Diabetes mellitus type 2 | 1,741 |
| 46177005 | End-stage renal disease | 1,196 |
| 254837009 | Malignant neoplasm of breast | 879 |
| 88805009 | Chronic congestive heart failure | 535 |
| 401314000 | Acute non-ST segment elevation MI | 429 |
| 22298006 | Acute ST segment elevation MI | 366 |
| 424132000 | Non-small cell lung carcinoma (stage 1) | 137 |

Note: A single patient can have multiple target diseases (e.g., Diabetes + Anemia + Hyperlipidemia), so patient counts per disease sum to more than the total cohort.

## Configuration — `synthea.properties`

Key settings in `config/synthea.properties`:

| Setting | Value | Reason |
|---------|-------|--------|
| `exporter.csv.export` | `true` | CSV is the primary format for the Bronze layer |
| `exporter.fhir.export` | `false` | FHIR disabled — saves ~54 GB at this scale |
| `exporter.years_of_history` | `10` | Export 10 years of patient history |
| `generate.only_alive_patients` | `false` | Include deceased patients for complete cohort |
| `exporter.csv.excluded_files` | `patient_expenses.csv` | Exclude billing noise not used by CMADS |
| All other exporters | `false` | HTML, text, CCDA, CPCDS, symptoms — all disabled |

## Output — Generated Dataset

### Final Cohort

- **14,335 patients** exported (from 50,000 simulated)
- **~28.6% yield** — reflects natural prevalence of the 11 target diseases in a US population simulation
- **Seed 42** — fully reproducible; re-running with the same command produces identical patients

### CSV Files

| File | Rows | Size |
|------|------|------|
| observations.csv | 10,951,316 | 2.5 GB |
| claims_transactions.csv | 13,542,297 | 7.8 GB |
| imaging_studies.csv | 1,094,332 | 546 MB |
| claims.csv | 1,722,747 | 869 MB |
| encounters.csv | 963,992 | 423 MB |
| medications.csv | 764,666 | 264 MB |
| procedures.csv | 2,184,378 | 595 MB |
| conditions.csv | 442,280 | 82 MB |
| payer_transitions.csv | 401,696 | 88 MB |
| supplies.csv | 327,678 | 59 MB |
| immunizations.csv | 167,092 | 30 MB |
| devices.csv | 69,672 | 20 MB |
| careplans.csv | 41,554 | 11 MB |
| allergies.csv | 10,961 | 2.5 MB |
| patients.csv | 14,335 | 4.3 MB |
| **Total** | **~31M rows** | **~13 GB** |

### Output Location

```
data/raw/batch_10k/
└── csv/
    ├── patients.csv
    ├── conditions.csv
    ├── encounters.csv
    ├── observations.csv
    ├── medications.csv
    ├── imaging_studies.csv
    ├── procedures.csv
    ├── ... (15 CSV files total)
    └── supplies.csv
```

## Loading into DuckDB

After generation, load the CSVs into DuckDB for querying:

```bash
python pipeline/load_csv_to_duckdb.py batch_10k
```

This creates `data/clinical.duckdb` with one table per CSV file (1:1 mapping). Each subsequent run replaces existing tables.

## Synthea Data Model

All tables connect through the **ENCOUNTER** foreign key:

```
patients ──< encounters ──< conditions
                         ──< medications
                         ──< observations
                         ──< procedures
                         ──< imaging_studies
                         ──< devices
                         ──< careplans
                         ──< claims
```

Key relationships:
- Every condition, medication, observation, and imaging study belongs to an encounter
- `encounters.REASONCODE` links to the SNOMED code of the condition that prompted the visit — this is the **ground truth** used for radiology report generation and agent evaluation
- Medications link to diseases via `REASONCODE` (the condition being treated)
- Observations contain lab values and vitals measured during an encounter

## Reproducibility

To regenerate the exact same dataset:

1. Use the same Synthea version (built from the `synthea/` directory)
2. Use seed `-s 42`
3. Use the same `keep_cmads_diseases.json` and `synthea.properties`
4. Run against `Massachusetts`

The output will be byte-identical.
