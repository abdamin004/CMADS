"""Silver+ Layer — Derived features from Silver (OMOP CDM) tables.

Computes clinical features needed by the multi-agent pipeline:

  1. lab_trends         — Per-patient lab value statistics & trends
  2. critical_lab_flags — Labs outside normal ranges with severity
  3. comorbidity_matrix — Boolean disease flags + Charlson-like index
  4. risk_scores        — Composite clinical risk scores per patient
  5. medication_timeline— Active meds, polypharmacy, drug classes
  6. drug_condition_links— Which drugs treat which conditions

Runs on the 1K patient cohort (data/gold/cohort_1k_patient_ids.json).

Usage:
    python3 pipeline/silver_plus.py
    python3 pipeline/silver_plus.py --cohort data/gold/cohort_1k_patient_ids.json
    python3 pipeline/silver_plus.py --reload-duckdb
"""

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

DB_PATH = Path("data/clinical.duckdb")
SILVER_PLUS_DIR = Path("data/silver_plus")
COHORT_FILE = Path("data/gold/cohort_1k_patient_ids.json")


# ══════════════════════════════════════════════════════════════════════
# 1. LAB TRENDS — per-patient lab statistics over time
# ══════════════════════════════════════════════════════════════════════

LAB_TRENDS_SQL = """
CREATE OR REPLACE TABLE silver_plus_lab_trends AS
WITH lab_stats AS (
    SELECT
        m.person_id,
        m.measurement_source_value AS lab_name,
        m.unit_source_value AS units,
        COUNT(*) AS measurement_count,
        MIN(m.value_as_number) AS value_min,
        MAX(m.value_as_number) AS value_max,
        ROUND(AVG(m.value_as_number), 2) AS value_mean,
        ROUND(MEDIAN(m.value_as_number), 2) AS value_median,
        ROUND(STDDEV(m.value_as_number), 2) AS value_stddev,
        -- Latest value
        LAST(m.value_as_number ORDER BY m.measurement_date) AS value_latest,
        LAST(m.measurement_date ORDER BY m.measurement_date) AS latest_date,
        -- First value
        FIRST(m.value_as_number ORDER BY m.measurement_date) AS value_first,
        FIRST(m.measurement_date ORDER BY m.measurement_date) AS first_date,
        -- Recent mean (last 6 months of data per patient)
        AVG(CASE
            WHEN m.measurement_date >= (
                SELECT MAX(m2.measurement_date) - INTERVAL '180 days'
                FROM silver_measurement m2
                WHERE m2.person_id = m.person_id
                  AND m2.measurement_source_value = m.measurement_source_value
            ) THEN m.value_as_number
        END) AS value_mean_recent
    FROM silver_measurement m
    WHERE m.person_id IN (SELECT pid FROM _cohort_ids)
      AND m.value_as_number IS NOT NULL
      AND m.category = 'laboratory'
      AND m.measurement_source_value IN (
          'Glucose',
          'Glucose [Mass/volume] in Blood',
          'Creatinine',
          'Creatinine [Mass/volume] in Serum or Plasma',
          'Hemoglobin [Mass/volume] in Blood',
          'Hemoglobin A1c/Hemoglobin.total in Blood',
          'Potassium [Moles/volume] in Blood',
          'Sodium [Moles/volume] in Blood',
          'Calcium [Mass/volume] in Serum or Plasma',
          'Carbon dioxide  total [Moles/volume] in Blood',
          'Chloride [Moles/volume] in Blood',
          'Urea nitrogen [Mass/volume] in Blood',
          'Total Cholesterol',
          'Triglycerides',
          'Low Density Lipoprotein Cholesterol',
          'High Density Lipoprotein Cholesterol',
          'Glomerular filtration rate/1.73 sq M.predicted',
          'Albumin [Mass/volume] in Serum or Plasma',
          'Bilirubin.total [Mass/volume] in Serum or Plasma',
          'Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma',
          'Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma',
          'Leukocytes [#/volume] in Blood by Automated count',
          'Platelets [#/volume] in Blood by Automated count',
          'Erythrocytes [#/volume] in Blood by Automated count'
      )
    GROUP BY m.person_id, m.measurement_source_value, m.unit_source_value
)
SELECT
    person_id,
    lab_name,
    units,
    measurement_count,
    value_min,
    value_max,
    value_mean,
    value_median,
    value_stddev,
    value_latest,
    latest_date,
    value_first,
    first_date,
    ROUND(value_mean_recent, 2) AS value_mean_recent,
    -- Trend: compare recent mean to overall mean
    CASE
        WHEN value_mean_recent IS NULL OR value_mean IS NULL OR value_mean = 0 THEN 'insufficient_data'
        WHEN value_mean_recent > value_mean * 1.10 THEN 'increasing'
        WHEN value_mean_recent < value_mean * 0.90 THEN 'decreasing'
        ELSE 'stable'
    END AS trend,
    -- Delta: latest vs first
    CASE
        WHEN value_first IS NOT NULL AND value_first != 0
        THEN ROUND((value_latest - value_first) / value_first * 100, 1)
    END AS pct_change_first_to_latest,
    CURRENT_TIMESTAMP AS _computed_at
FROM lab_stats
ORDER BY person_id, lab_name
"""


# ══════════════════════════════════════════════════════════════════════
# 2. CRITICAL LAB FLAGS — labs outside normal ranges
# ══════════════════════════════════════════════════════════════════════

CRITICAL_LAB_FLAGS_SQL = """
CREATE OR REPLACE TABLE silver_plus_critical_lab_flags AS
WITH latest_labs AS (
    SELECT
        m.person_id,
        m.measurement_source_value AS lab_name,
        m.unit_source_value AS units,
        LAST(m.value_as_number ORDER BY m.measurement_date) AS value_latest,
        LAST(m.measurement_date ORDER BY m.measurement_date) AS latest_date
    FROM silver_measurement m
    WHERE m.person_id IN (SELECT pid FROM _cohort_ids)
      AND m.value_as_number IS NOT NULL
      AND m.category = 'laboratory'
    GROUP BY m.person_id, m.measurement_source_value, m.unit_source_value
),
flagged AS (
    SELECT
        person_id,
        lab_name,
        units,
        value_latest,
        latest_date,
        CASE
            -- Glucose (mg/dL): normal 70-100, high >126, critical >300 or <50
            WHEN lab_name LIKE '%Glucose%' AND units LIKE '%mg%' THEN
                CASE
                    WHEN value_latest < 50 THEN 'critical_low'
                    WHEN value_latest < 70 THEN 'low'
                    WHEN value_latest > 300 THEN 'critical_high'
                    WHEN value_latest > 200 THEN 'high'
                    WHEN value_latest > 126 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- Creatinine (mg/dL): normal 0.6-1.2, high >1.5, critical >4.0
            WHEN lab_name LIKE '%Creatinine%' AND units LIKE '%mg%' THEN
                CASE
                    WHEN value_latest > 4.0 THEN 'critical_high'
                    WHEN value_latest > 2.0 THEN 'high'
                    WHEN value_latest > 1.5 THEN 'mildly_elevated'
                    WHEN value_latest < 0.4 THEN 'low'
                    ELSE 'normal'
                END

            -- Hemoglobin (g/dL): normal M 13.5-17.5, F 12-16
            WHEN lab_name LIKE '%Hemoglobin%' AND lab_name NOT LIKE '%A1c%' AND units LIKE '%g/dL%' THEN
                CASE
                    WHEN value_latest < 7.0 THEN 'critical_low'
                    WHEN value_latest < 10.0 THEN 'low'
                    WHEN value_latest > 20.0 THEN 'critical_high'
                    WHEN value_latest > 17.5 THEN 'high'
                    ELSE 'normal'
                END

            -- HbA1c (%): normal <5.7, prediabetic 5.7-6.4, diabetic >=6.5
            WHEN lab_name LIKE '%A1c%' AND units = '%' THEN
                CASE
                    WHEN value_latest >= 10.0 THEN 'critical_high'
                    WHEN value_latest >= 8.0 THEN 'high'
                    WHEN value_latest >= 6.5 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- Potassium (mEq/L): normal 3.5-5.0, critical <2.5 or >6.5
            WHEN lab_name LIKE '%Potassium%' THEN
                CASE
                    WHEN value_latest < 2.5 THEN 'critical_low'
                    WHEN value_latest < 3.5 THEN 'low'
                    WHEN value_latest > 6.5 THEN 'critical_high'
                    WHEN value_latest > 5.5 THEN 'high'
                    WHEN value_latest > 5.0 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- Sodium (mEq/L): normal 136-145, critical <120 or >160
            WHEN lab_name LIKE '%Sodium%' THEN
                CASE
                    WHEN value_latest < 120 THEN 'critical_low'
                    WHEN value_latest < 130 THEN 'low'
                    WHEN value_latest > 160 THEN 'critical_high'
                    WHEN value_latest > 150 THEN 'high'
                    WHEN value_latest > 145 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- eGFR (mL/min): <15 critical, <30 severe, <60 moderate
            WHEN lab_name LIKE '%Glomerular%' THEN
                CASE
                    WHEN value_latest < 15 THEN 'critical_low'
                    WHEN value_latest < 30 THEN 'low'
                    WHEN value_latest < 60 THEN 'mildly_low'
                    ELSE 'normal'
                END

            -- BUN (mg/dL): normal 7-20
            WHEN lab_name LIKE '%Urea nitrogen%' THEN
                CASE
                    WHEN value_latest > 50 THEN 'critical_high'
                    WHEN value_latest > 30 THEN 'high'
                    WHEN value_latest > 20 THEN 'mildly_elevated'
                    WHEN value_latest < 5 THEN 'low'
                    ELSE 'normal'
                END

            -- Total Cholesterol (mg/dL): <200 desirable, 200-239 borderline, >=240 high
            WHEN lab_name = 'Total Cholesterol' THEN
                CASE
                    WHEN value_latest >= 300 THEN 'critical_high'
                    WHEN value_latest >= 240 THEN 'high'
                    WHEN value_latest >= 200 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- LDL (mg/dL): <100 optimal, 100-129 near optimal, 130-159 borderline
            WHEN lab_name LIKE '%Low Density%' THEN
                CASE
                    WHEN value_latest >= 190 THEN 'critical_high'
                    WHEN value_latest >= 160 THEN 'high'
                    WHEN value_latest >= 130 THEN 'mildly_elevated'
                    ELSE 'normal'
                END

            -- Platelets (10*3/uL): normal 150-400
            WHEN lab_name LIKE '%Platelet%' THEN
                CASE
                    WHEN value_latest < 50 THEN 'critical_low'
                    WHEN value_latest < 100 THEN 'low'
                    WHEN value_latest > 600 THEN 'critical_high'
                    WHEN value_latest > 400 THEN 'high'
                    ELSE 'normal'
                END

            -- WBC (10*3/uL): normal 4.5-11.0
            WHEN lab_name LIKE '%Leukocyte%' THEN
                CASE
                    WHEN value_latest < 2.0 THEN 'critical_low'
                    WHEN value_latest < 4.0 THEN 'low'
                    WHEN value_latest > 20.0 THEN 'critical_high'
                    WHEN value_latest > 11.0 THEN 'high'
                    ELSE 'normal'
                END

            -- Calcium (mg/dL): normal 8.5-10.5
            WHEN lab_name LIKE '%Calcium%' THEN
                CASE
                    WHEN value_latest < 7.0 THEN 'critical_low'
                    WHEN value_latest < 8.5 THEN 'low'
                    WHEN value_latest > 13.0 THEN 'critical_high'
                    WHEN value_latest > 10.5 THEN 'high'
                    ELSE 'normal'
                END

            ELSE 'not_evaluated'
        END AS flag,
        CASE
            WHEN lab_name LIKE '%Glucose%' AND units LIKE '%mg%' THEN '70-100'
            WHEN lab_name LIKE '%Creatinine%' THEN '0.6-1.2'
            WHEN lab_name LIKE '%Hemoglobin%' AND lab_name NOT LIKE '%A1c%' THEN '12-17.5'
            WHEN lab_name LIKE '%A1c%' THEN '<5.7'
            WHEN lab_name LIKE '%Potassium%' THEN '3.5-5.0'
            WHEN lab_name LIKE '%Sodium%' THEN '136-145'
            WHEN lab_name LIKE '%Glomerular%' THEN '>60'
            WHEN lab_name LIKE '%Urea nitrogen%' THEN '7-20'
            WHEN lab_name = 'Total Cholesterol' THEN '<200'
            WHEN lab_name LIKE '%Low Density%' THEN '<100'
            WHEN lab_name LIKE '%Platelet%' THEN '150-400'
            WHEN lab_name LIKE '%Leukocyte%' THEN '4.5-11.0'
            WHEN lab_name LIKE '%Calcium%' THEN '8.5-10.5'
            ELSE NULL
        END AS normal_range
    FROM latest_labs
)
SELECT
    person_id,
    lab_name,
    units,
    value_latest,
    latest_date,
    flag,
    normal_range,
    CASE
        WHEN flag LIKE 'critical%' THEN 'critical'
        WHEN flag IN ('high', 'low') THEN 'abnormal'
        WHEN flag LIKE 'mildly%' THEN 'borderline'
        WHEN flag = 'normal' THEN 'normal'
        ELSE 'not_evaluated'
    END AS severity,
    CURRENT_TIMESTAMP AS _computed_at
FROM flagged
WHERE flag != 'not_evaluated'
ORDER BY person_id,
    CASE
        WHEN flag LIKE 'critical%' THEN 1
        WHEN flag IN ('high', 'low') THEN 2
        WHEN flag LIKE 'mildly%' THEN 3
        ELSE 4
    END,
    lab_name
"""


# ══════════════════════════════════════════════════════════════════════
# 3. COMORBIDITY MATRIX — boolean disease flags per patient
# ══════════════════════════════════════════════════════════════════════

COMORBIDITY_MATRIX_SQL = """
CREATE OR REPLACE TABLE silver_plus_comorbidity_matrix AS
WITH active_conditions AS (
    SELECT
        c.person_id,
        c.condition_source_value AS condition_name,
        c.condition_start_date,
        c.condition_end_date
    FROM silver_condition_occurrence c
    WHERE c.person_id IN (SELECT pid FROM _cohort_ids)
)
SELECT
    p.person_id,

    -- Cardiovascular
    MAX(CASE WHEN ac.condition_name LIKE '%Chronic congestive heart failure%' THEN 1 ELSE 0 END) AS has_chf,
    MAX(CASE WHEN ac.condition_name LIKE '%Ischemic heart disease%' THEN 1 ELSE 0 END) AS has_ihd,
    MAX(CASE WHEN ac.condition_name LIKE '%Essential hypertension%' OR ac.condition_name LIKE '%Hypertension%' THEN 1 ELSE 0 END) AS has_hypertension,
    MAX(CASE WHEN ac.condition_name LIKE '%Atrial fibrillation%' THEN 1 ELSE 0 END) AS has_afib,
    MAX(CASE WHEN ac.condition_name LIKE '%Aortic valve%' THEN 1 ELSE 0 END) AS has_valvular_disease,
    MAX(CASE WHEN ac.condition_name LIKE '%Coronary%' THEN 1 ELSE 0 END) AS has_cad,

    -- Metabolic
    MAX(CASE WHEN ac.condition_name LIKE '%Diabetes mellitus type 2%' THEN 1 ELSE 0 END) AS has_diabetes_t2,
    MAX(CASE WHEN ac.condition_name LIKE '%Diabetes mellitus type 1%' THEN 1 ELSE 0 END) AS has_diabetes_t1,
    MAX(CASE WHEN ac.condition_name LIKE '%Metabolic syndrome%' THEN 1 ELSE 0 END) AS has_metabolic_syndrome,
    MAX(CASE WHEN ac.condition_name LIKE '%Hyperlipidemia%' OR ac.condition_name LIKE '%Hypertriglyceridemia%' THEN 1 ELSE 0 END) AS has_dyslipidemia,
    MAX(CASE WHEN ac.condition_name LIKE '%Obesity%' OR ac.condition_name LIKE '%Body mass index 30%' THEN 1 ELSE 0 END) AS has_obesity,

    -- Renal
    MAX(CASE WHEN ac.condition_name LIKE '%Chronic kidney disease%' OR ac.condition_name LIKE '%End-stage renal%' THEN 1 ELSE 0 END) AS has_ckd,
    MAX(CASE WHEN ac.condition_name LIKE '%End-stage renal%' THEN 1 ELSE 0 END) AS has_esrd,
    MAX(CASE WHEN ac.condition_name LIKE '%kidney due to diabetes%' THEN 1 ELSE 0 END) AS has_diabetic_nephropathy,

    -- Neurological
    MAX(CASE WHEN ac.condition_name LIKE '%Cerebral palsy%' THEN 1 ELSE 0 END) AS has_cerebral_palsy,
    MAX(CASE WHEN ac.condition_name LIKE '%Epilepsy%' OR ac.condition_name LIKE '%Seizure%' THEN 1 ELSE 0 END) AS has_epilepsy,
    MAX(CASE WHEN ac.condition_name LIKE '%Alzheimer%' OR ac.condition_name LIKE '%Dementia%' THEN 1 ELSE 0 END) AS has_dementia,
    MAX(CASE WHEN ac.condition_name LIKE '%Stroke%' OR ac.condition_name LIKE '%cerebrovascular%' THEN 1 ELSE 0 END) AS has_stroke,

    -- Hematological
    MAX(CASE WHEN ac.condition_name LIKE '%Anemia%' THEN 1 ELSE 0 END) AS has_anemia,

    -- Pulmonary
    MAX(CASE WHEN ac.condition_name LIKE '%Chronic obstructive%' OR ac.condition_name = 'COPD' THEN 1 ELSE 0 END) AS has_copd,
    MAX(CASE WHEN ac.condition_name LIKE '%Asthma%' THEN 1 ELSE 0 END) AS has_asthma,
    MAX(CASE WHEN ac.condition_name LIKE '%Pneumonia%' THEN 1 ELSE 0 END) AS has_pneumonia,

    -- Cancer
    MAX(CASE WHEN ac.condition_name LIKE '%Malignant neoplasm%' OR ac.condition_name LIKE '%cancer%' THEN 1 ELSE 0 END) AS has_cancer,

    -- Musculoskeletal
    MAX(CASE WHEN ac.condition_name LIKE '%Osteoporosis%' THEN 1 ELSE 0 END) AS has_osteoporosis,
    MAX(CASE WHEN ac.condition_name LIKE '%Osteoarthritis%' THEN 1 ELSE 0 END) AS has_osteoarthritis,
    MAX(CASE WHEN ac.condition_name LIKE '%Fracture%' THEN 1 ELSE 0 END) AS has_fracture_history,

    -- GI
    MAX(CASE WHEN ac.condition_name LIKE '%Gastroesophageal reflux%' THEN 1 ELSE 0 END) AS has_gerd,

    -- Counts
    COUNT(DISTINCT ac.condition_name) AS total_condition_count,
    COUNT(DISTINCT CASE WHEN ac.condition_end_date IS NULL THEN ac.condition_name END) AS active_condition_count,

    -- Simplified Charlson-like comorbidity index
    (
        MAX(CASE WHEN ac.condition_name LIKE '%Chronic congestive heart failure%' THEN 1 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Ischemic heart disease%' THEN 1 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Diabetes mellitus type 2%' THEN 2 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Chronic kidney disease%' OR ac.condition_name LIKE '%End-stage renal%' THEN 2 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Cerebral palsy%' OR ac.condition_name LIKE '%Stroke%' THEN 2 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Malignant neoplasm%' THEN 2 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Chronic obstructive%' THEN 1 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Dementia%' OR ac.condition_name LIKE '%Alzheimer%' THEN 2 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Anemia%' THEN 1 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Epilepsy%' THEN 1 ELSE 0 END) +
        MAX(CASE WHEN ac.condition_name LIKE '%Osteoporosis%' THEN 1 ELSE 0 END)
    ) AS charlson_index,

    CURRENT_TIMESTAMP AS _computed_at
FROM silver_person p
LEFT JOIN active_conditions ac ON p.person_id = ac.person_id
WHERE p.person_id IN (SELECT pid FROM _cohort_ids)
GROUP BY p.person_id
ORDER BY charlson_index DESC, person_id
"""


# ══════════════════════════════════════════════════════════════════════
# 4. RISK SCORES — composite clinical risk per patient
# ══════════════════════════════════════════════════════════════════════

RISK_SCORES_SQL = """
CREATE OR REPLACE TABLE silver_plus_risk_scores AS
WITH
patient_age AS (
    SELECT
        person_id,
        EXTRACT(YEAR FROM AGE(COALESCE(death_datetime, CURRENT_DATE), birth_datetime)) AS age,
        gender_source_value AS gender,
        death_datetime
    FROM silver_person
    WHERE person_id IN (SELECT pid FROM _cohort_ids)
),
latest_vitals AS (
    SELECT
        m.person_id,
        MAX(CASE WHEN m.measurement_source_value LIKE '%Systolic%' THEN m.value_as_number END) AS sbp_latest,
        MAX(CASE WHEN m.measurement_source_value LIKE '%Diastolic%' THEN m.value_as_number END) AS dbp_latest,
        MAX(CASE WHEN m.measurement_source_value LIKE '%Body Mass Index%' THEN m.value_as_number END) AS bmi_latest,
        MAX(CASE WHEN m.measurement_source_value LIKE '%Heart rate%' THEN m.value_as_number END) AS hr_latest
    FROM silver_measurement m
    WHERE m.person_id IN (SELECT pid FROM _cohort_ids)
      AND m.category = 'vital-signs'
      AND m.measurement_date = (
          SELECT MAX(m2.measurement_date)
          FROM silver_measurement m2
          WHERE m2.person_id = m.person_id AND m2.category = 'vital-signs'
      )
    GROUP BY m.person_id
),
latest_labs AS (
    SELECT
        person_id,
        MAX(CASE WHEN measurement_source_value LIKE '%A1c%' THEN value_as_number END) AS a1c,
        MAX(CASE WHEN measurement_source_value LIKE '%Glomerular%' THEN value_as_number END) AS egfr,
        MAX(CASE WHEN measurement_source_value LIKE '%Creatinine%' THEN value_as_number END) AS creatinine,
        MAX(CASE WHEN measurement_source_value = 'Total Cholesterol' THEN value_as_number END) AS total_chol,
        MAX(CASE WHEN measurement_source_value LIKE '%Low Density%' THEN value_as_number END) AS ldl,
        MAX(CASE WHEN measurement_source_value LIKE '%Hemoglobin%' AND measurement_source_value NOT LIKE '%A1c%' THEN value_as_number END) AS hemoglobin
    FROM (
        SELECT person_id, measurement_source_value, value_as_number,
               ROW_NUMBER() OVER (PARTITION BY person_id, measurement_source_value ORDER BY measurement_date DESC) AS rn
        FROM silver_measurement
        WHERE person_id IN (SELECT pid FROM _cohort_ids)
          AND category = 'laboratory'
          AND value_as_number IS NOT NULL
    ) sub
    WHERE rn = 1
    GROUP BY person_id
),
visit_stats AS (
    SELECT
        person_id,
        COUNT(*) AS total_visits,
        COUNT(CASE WHEN visit_source_value = 'emergency' THEN 1 END) AS er_visits,
        COUNT(CASE WHEN visit_source_value = 'inpatient' THEN 1 END) AS inpatient_visits,
        MAX(visit_start_date) AS last_visit_date
    FROM silver_visit_occurrence
    WHERE person_id IN (SELECT pid FROM _cohort_ids)
    GROUP BY person_id
),
med_counts AS (
    SELECT
        person_id,
        COUNT(DISTINCT drug_source_value) AS total_unique_meds,
        COUNT(DISTINCT CASE
            WHEN drug_exposure_end_date IS NULL
              OR CAST(drug_exposure_end_date AS DATE) >= CURRENT_DATE
            THEN drug_source_value
        END) AS active_med_count
    FROM silver_drug_exposure
    WHERE person_id IN (SELECT pid FROM _cohort_ids)
    GROUP BY person_id
),
comorbidity AS (
    SELECT person_id, charlson_index, has_chf, has_diabetes_t2, has_hypertension,
           has_ckd, has_afib, active_condition_count
    FROM silver_plus_comorbidity_matrix
)
SELECT
    pa.person_id,
    pa.age,
    pa.gender,

    -- Vitals
    ROUND(lv.sbp_latest, 0) AS sbp_latest,
    ROUND(lv.dbp_latest, 0) AS dbp_latest,
    ROUND(lv.bmi_latest, 1) AS bmi_latest,
    ROUND(lv.hr_latest, 0) AS hr_latest,

    -- Key labs
    ROUND(ll.a1c, 1) AS a1c_latest,
    ROUND(ll.egfr, 1) AS egfr_latest,
    ROUND(ll.creatinine, 2) AS creatinine_latest,
    ROUND(ll.total_chol, 0) AS total_cholesterol_latest,
    ROUND(ll.ldl, 0) AS ldl_latest,
    ROUND(ll.hemoglobin, 1) AS hemoglobin_latest,

    -- CKD stage from eGFR
    CASE
        WHEN ll.egfr IS NULL THEN NULL
        WHEN ll.egfr >= 90 THEN 1
        WHEN ll.egfr >= 60 THEN 2
        WHEN ll.egfr >= 30 THEN 3
        WHEN ll.egfr >= 15 THEN 4
        ELSE 5
    END AS ckd_stage,

    -- BP category
    CASE
        WHEN lv.sbp_latest IS NULL THEN 'unknown'
        WHEN lv.sbp_latest >= 180 OR lv.dbp_latest >= 120 THEN 'hypertensive_crisis'
        WHEN lv.sbp_latest >= 140 OR lv.dbp_latest >= 90 THEN 'stage2_hypertension'
        WHEN lv.sbp_latest >= 130 OR lv.dbp_latest >= 80 THEN 'stage1_hypertension'
        WHEN lv.sbp_latest >= 120 THEN 'elevated'
        ELSE 'normal'
    END AS bp_category,

    -- Glycemic control
    CASE
        WHEN ll.a1c IS NULL THEN 'unknown'
        WHEN ll.a1c >= 10.0 THEN 'very_poor'
        WHEN ll.a1c >= 8.0 THEN 'poor'
        WHEN ll.a1c >= 7.0 THEN 'suboptimal'
        WHEN ll.a1c >= 5.7 THEN 'prediabetic'
        ELSE 'normal'
    END AS glycemic_control,

    -- Utilization
    COALESCE(vs.total_visits, 0) AS total_visits,
    COALESCE(vs.er_visits, 0) AS er_visits,
    COALESCE(vs.inpatient_visits, 0) AS inpatient_visits,
    vs.last_visit_date,

    -- Medication burden
    COALESCE(mc.total_unique_meds, 0) AS total_unique_meds,
    COALESCE(mc.active_med_count, 0) AS active_med_count,
    CASE
        WHEN COALESCE(mc.active_med_count, 0) >= 10 THEN 'high'
        WHEN COALESCE(mc.active_med_count, 0) >= 5 THEN 'moderate'
        ELSE 'low'
    END AS polypharmacy_risk,

    -- Comorbidity
    COALESCE(cb.charlson_index, 0) AS charlson_index,
    COALESCE(cb.active_condition_count, 0) AS active_condition_count,

    -- Composite cardiovascular risk (simplified Framingham-like)
    (
        CASE WHEN pa.age >= 65 THEN 3 WHEN pa.age >= 55 THEN 2 WHEN pa.age >= 45 THEN 1 ELSE 0 END +
        CASE WHEN pa.gender = 'M' THEN 1 ELSE 0 END +
        CASE WHEN lv.sbp_latest >= 140 THEN 2 WHEN lv.sbp_latest >= 130 THEN 1 ELSE 0 END +
        CASE WHEN ll.total_chol >= 240 THEN 2 WHEN ll.total_chol >= 200 THEN 1 ELSE 0 END +
        CASE WHEN ll.ldl >= 160 THEN 2 WHEN ll.ldl >= 130 THEN 1 ELSE 0 END +
        CASE WHEN COALESCE(cb.has_diabetes_t2, 0) = 1 THEN 2 ELSE 0 END +
        CASE WHEN COALESCE(cb.has_chf, 0) = 1 THEN 3 ELSE 0 END +
        CASE WHEN COALESCE(cb.has_ckd, 0) = 1 THEN 2 ELSE 0 END +
        CASE WHEN lv.bmi_latest >= 30 THEN 1 ELSE 0 END
    ) AS cv_risk_score,

    -- Overall clinical complexity
    CASE
        WHEN (COALESCE(cb.charlson_index, 0) >= 5 OR COALESCE(cb.active_condition_count, 0) >= 10)
             AND COALESCE(mc.active_med_count, 0) >= 5
        THEN 'high'
        WHEN COALESCE(cb.charlson_index, 0) >= 3 OR COALESCE(cb.active_condition_count, 0) >= 5
        THEN 'moderate'
        ELSE 'low'
    END AS clinical_complexity,

    CURRENT_TIMESTAMP AS _computed_at
FROM patient_age pa
LEFT JOIN latest_vitals lv ON pa.person_id = lv.person_id
LEFT JOIN latest_labs ll ON pa.person_id = ll.person_id
LEFT JOIN visit_stats vs ON pa.person_id = vs.person_id
LEFT JOIN med_counts mc ON pa.person_id = mc.person_id
LEFT JOIN comorbidity cb ON pa.person_id = cb.person_id
ORDER BY pa.person_id
"""


# ══════════════════════════════════════════════════════════════════════
# 5. MEDICATION TIMELINE — active meds, classes, durations
# ══════════════════════════════════════════════════════════════════════

MEDICATION_TIMELINE_SQL = """
CREATE OR REPLACE TABLE silver_plus_medication_timeline AS
SELECT
    d.person_id,
    d.drug_source_value AS medication_name,
    d.drug_exposure_start_date AS start_date,
    d.drug_exposure_end_date AS end_date,
    d.quantity,

    -- Is it currently active?
    CASE
        WHEN d.drug_exposure_end_date IS NULL
          OR CAST(d.drug_exposure_end_date AS DATE) >= CURRENT_DATE
        THEN 1 ELSE 0
    END AS is_active,

    -- Duration in days
    CASE
        WHEN d.drug_exposure_end_date IS NOT NULL
        THEN DATEDIFF('day', d.drug_exposure_start_date, d.drug_exposure_end_date)
    END AS duration_days,

    -- Infer drug class from medication name
    CASE
        -- Antihypertensives
        WHEN d.drug_source_value LIKE '%lisinopril%' OR d.drug_source_value LIKE '%enalapril%'
             OR d.drug_source_value LIKE '%ramipril%' OR d.drug_source_value LIKE '%captopril%'
        THEN 'ACE_inhibitor'
        WHEN d.drug_source_value LIKE '%losartan%' OR d.drug_source_value LIKE '%valsartan%'
             OR d.drug_source_value LIKE '%irbesartan%'
        THEN 'ARB'
        WHEN d.drug_source_value LIKE '%amlodipine%' OR d.drug_source_value LIKE '%nifedipine%'
        THEN 'calcium_channel_blocker'
        WHEN d.drug_source_value LIKE '%metoprolol%' OR d.drug_source_value LIKE '%atenolol%'
             OR d.drug_source_value LIKE '%carvedilol%' OR d.drug_source_value LIKE '%propranolol%'
        THEN 'beta_blocker'
        WHEN d.drug_source_value LIKE '%hydrochlorothiazide%' OR d.drug_source_value LIKE '%furosemide%'
             OR d.drug_source_value LIKE '%spironolactone%' OR d.drug_source_value LIKE '%bumetanide%'
        THEN 'diuretic'

        -- Diabetes
        WHEN d.drug_source_value LIKE '%metformin%' THEN 'biguanide'
        WHEN d.drug_source_value LIKE '%insulin%' THEN 'insulin'
        WHEN d.drug_source_value LIKE '%glipizide%' OR d.drug_source_value LIKE '%glyburide%'
        THEN 'sulfonylurea'

        -- Lipid-lowering
        WHEN d.drug_source_value LIKE '%atorvastatin%' OR d.drug_source_value LIKE '%simvastatin%'
             OR d.drug_source_value LIKE '%rosuvastatin%' OR d.drug_source_value LIKE '%pravastatin%'
        THEN 'statin'
        WHEN d.drug_source_value LIKE '%gemfibrozil%' OR d.drug_source_value LIKE '%fenofibrate%'
        THEN 'fibrate'

        -- Anticoagulants / Antiplatelets
        WHEN d.drug_source_value LIKE '%warfarin%' OR d.drug_source_value LIKE '%rivaroxaban%'
             OR d.drug_source_value LIKE '%apixaban%'
        THEN 'anticoagulant'
        WHEN d.drug_source_value LIKE '%aspirin%' OR d.drug_source_value LIKE '%clopidogrel%'
        THEN 'antiplatelet'

        -- Anticonvulsants
        WHEN d.drug_source_value LIKE '%levetiracetam%' OR d.drug_source_value LIKE '%valproic%'
             OR d.drug_source_value LIKE '%carbamazepine%' OR d.drug_source_value LIKE '%phenytoin%'
             OR d.drug_source_value LIKE '%lamotrigine%' OR d.drug_source_value LIKE '%topiramate%'
        THEN 'anticonvulsant'

        -- Pain / Anti-inflammatory
        WHEN d.drug_source_value LIKE '%ibuprofen%' OR d.drug_source_value LIKE '%naproxen%'
             OR d.drug_source_value LIKE '%celecoxib%'
        THEN 'NSAID'
        WHEN d.drug_source_value LIKE '%acetaminophen%' THEN 'analgesic'
        WHEN d.drug_source_value LIKE '%oxycodone%' OR d.drug_source_value LIKE '%hydrocodone%'
             OR d.drug_source_value LIKE '%morphine%' OR d.drug_source_value LIKE '%fentanyl%'
        THEN 'opioid'

        -- Antibiotics
        WHEN d.drug_source_value LIKE '%amoxicillin%' OR d.drug_source_value LIKE '%azithromycin%'
             OR d.drug_source_value LIKE '%ciprofloxacin%' OR d.drug_source_value LIKE '%doxycycline%'
             OR d.drug_source_value LIKE '%penicillin%' OR d.drug_source_value LIKE '%cephalexin%'
        THEN 'antibiotic'

        -- GI
        WHEN d.drug_source_value LIKE '%omeprazole%' OR d.drug_source_value LIKE '%pantoprazole%'
             OR d.drug_source_value LIKE '%lansoprazole%'
        THEN 'PPI'

        -- Bone health
        WHEN d.drug_source_value LIKE '%alendronate%' OR d.drug_source_value LIKE '%risedronate%'
        THEN 'bisphosphonate'

        ELSE 'other'
    END AS drug_class,

    -- Reason for prescription
    d.drug_source_value AS drug_code,

    CURRENT_TIMESTAMP AS _computed_at
FROM silver_drug_exposure d
WHERE d.person_id IN (SELECT pid FROM _cohort_ids)
ORDER BY d.person_id, d.drug_exposure_start_date
"""


# ══════════════════════════════════════════════════════════════════════
# 6. DRUG-CONDITION LINKS — which drugs treat which conditions
# ══════════════════════════════════════════════════════════════════════

DRUG_CONDITION_LINKS_SQL = """
CREATE OR REPLACE TABLE silver_plus_drug_condition_links AS
WITH med_reasons AS (
    SELECT
        sp.person_id,
        m.DESCRIPTION AS medication_name,
        m.REASONDESCRIPTION AS condition_treated,
        m.REASONCODE AS condition_code,
        MIN(m.START) AS first_prescribed,
        MAX(COALESCE(m.STOP, CURRENT_TIMESTAMP)) AS last_prescribed,
        COUNT(*) AS prescription_count
    FROM medications m
    JOIN silver_person sp ON m.PATIENT = sp.person_source_value
    WHERE sp.person_id IN (SELECT pid FROM _cohort_ids)
      AND m.REASONDESCRIPTION IS NOT NULL
      AND m.REASONDESCRIPTION != ''
    GROUP BY sp.person_id, m.DESCRIPTION, m.REASONDESCRIPTION, m.REASONCODE
)
SELECT
    person_id,
    medication_name,
    condition_treated,
    condition_code,
    first_prescribed,
    last_prescribed,
    prescription_count,
    DATEDIFF('day', first_prescribed, last_prescribed) AS treatment_duration_days,
    CURRENT_TIMESTAMP AS _computed_at
FROM med_reasons
ORDER BY person_id, condition_treated, medication_name
"""


# ══════════════════════════════════════════════════════════════════════
# Pipeline execution
# ══════════════════════════════════════════════════════════════════════

TABLES = [
    ("lab_trends", LAB_TRENDS_SQL),
    ("critical_lab_flags", CRITICAL_LAB_FLAGS_SQL),
    ("comorbidity_matrix", COMORBIDITY_MATRIX_SQL),
    ("risk_scores", RISK_SCORES_SQL),
    ("medication_timeline", MEDICATION_TIMELINE_SQL),
    ("drug_condition_links", DRUG_CONDITION_LINKS_SQL),
]


def load_cohort(cohort_path):
    """Load patient IDs from the cohort JSON file."""
    data = json.loads(cohort_path.read_text())
    return data


def build_silver_plus(cohort_path, output_dir, reload_db=False):
    """Build all Silver+ tables."""
    pipeline_start = time.time()

    print(f"{'═'*70}")
    print(f"SILVER+ LAYER — Derived Clinical Features")
    print(f"{'═'*70}")
    print(f"  Source:     Silver OMOP CDM tables in {DB_PATH}")
    print(f"  Cohort:     {cohort_path}")
    print(f"  Output:     {output_dir}/")
    print(f"  Started:    {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # Load cohort
    patient_ids = load_cohort(cohort_path)
    print(f"  Cohort size: {len(patient_ids):,} patients\n")

    # Connect to DuckDB
    con = duckdb.connect(str(DB_PATH))

    # Create temporary cohort table with BIGINT person_ids
    # Silver OMOP tables use BIGINT person_id, cohort file has VARCHAR Synthea UUIDs
    # Map through silver_person.person_source_value
    con.execute("CREATE OR REPLACE TEMP TABLE _cohort_uuids (uuid VARCHAR)")
    con.executemany("INSERT INTO _cohort_uuids VALUES (?)", [(pid,) for pid in patient_ids])
    con.execute("""
        CREATE OR REPLACE TEMP TABLE _cohort_ids AS
        SELECT p.person_id AS pid
        FROM silver_person p
        WHERE p.person_source_value IN (SELECT uuid FROM _cohort_uuids)
    """)
    matched = con.execute("SELECT COUNT(*) FROM _cohort_ids").fetchone()[0]
    con.execute("DROP TABLE _cohort_uuids")
    print(f"  Loaded {len(patient_ids):,} patient UUIDs → {matched:,} OMOP person_ids\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    results = []

    for table_name, sql in TABLES:
        full_name = f"silver_plus_{table_name}"
        print(f"  {full_name:<45}", end="", flush=True)
        start = time.time()

        try:
            con.execute(sql)
            row_count = con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
            duration = time.time() - start

            # Export to Parquet
            table_dir = output_dir / table_name
            table_dir.mkdir(parents=True, exist_ok=True)
            out_path = table_dir / "data.parquet"
            con.execute(f"""
                COPY (SELECT * FROM {full_name})
                TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3)
            """)
            size_mb = out_path.stat().st_size / 1024 / 1024

            print(f"  {row_count:>10,} rows  {size_mb:>7.1f} MB  ({duration:.1f}s)")
            results.append({
                "table": full_name,
                "rows": row_count,
                "size_mb": size_mb,
                "duration_s": round(duration, 1),
            })

        except Exception as e:
            duration = time.time() - start
            print(f"  [ERROR] {e}")
            results.append({
                "table": full_name,
                "rows": 0,
                "size_mb": 0,
                "error": str(e),
                "duration_s": round(duration, 1),
            })

    # Cleanup temp table
    con.execute("DROP TABLE IF EXISTS _cohort_ids")

    # Print summary
    total_time = time.time() - pipeline_start
    total_rows = sum(r["rows"] for r in results)
    total_size = sum(r["size_mb"] for r in results)
    errors = [r for r in results if "error" in r]

    print(f"\n{'═'*70}")
    print(f"SILVER+ SUMMARY")
    print(f"{'═'*70}")
    print(f"  Tables:     {len(results) - len(errors)}/{len(results)} successful")
    print(f"  Total rows: {total_rows:,}")
    print(f"  Total size: {total_size:.1f} MB")
    print(f"  Time:       {total_time:.1f}s")
    print(f"  Output:     {output_dir}/")

    if errors:
        print(f"\n  ERRORS:")
        for e in errors:
            print(f"    {e['table']}: {e['error']}")

    # Quick validation stats
    print(f"\n{'─'*70}")
    print(f"VALIDATION")
    print(f"{'─'*70}")

    # Comorbidity distribution
    try:
        dist = con.execute("""
            SELECT charlson_index, COUNT(*) as n
            FROM silver_plus_comorbidity_matrix
            GROUP BY charlson_index ORDER BY charlson_index
        """).fetchall()
        print(f"\n  Charlson Index distribution:")
        for idx, n in dist:
            bar = '█' * (n // 10)
            print(f"    {idx:>2}: {n:>5} {bar}")
    except Exception:
        pass

    # Clinical complexity
    try:
        complexity = con.execute("""
            SELECT clinical_complexity, COUNT(*) as n
            FROM silver_plus_risk_scores
            GROUP BY clinical_complexity ORDER BY n DESC
        """).fetchall()
        print(f"\n  Clinical complexity:")
        for level, n in complexity:
            print(f"    {level:<12}: {n:>5}")
    except Exception:
        pass

    # Critical lab flags
    try:
        flags = con.execute("""
            SELECT severity, COUNT(*) as n, COUNT(DISTINCT person_id) as patients
            FROM silver_plus_critical_lab_flags
            GROUP BY severity ORDER BY
                CASE severity WHEN 'critical' THEN 1 WHEN 'abnormal' THEN 2
                     WHEN 'borderline' THEN 3 ELSE 4 END
        """).fetchall()
        print(f"\n  Lab flag severity:")
        for sev, n, pts in flags:
            print(f"    {sev:<12}: {n:>6} flags across {pts:>4} patients")
    except Exception:
        pass

    # Drug classes
    try:
        classes = con.execute("""
            SELECT drug_class, COUNT(*) as n, COUNT(DISTINCT person_id) as patients
            FROM silver_plus_medication_timeline
            WHERE drug_class != 'other' AND is_active = 1
            GROUP BY drug_class ORDER BY n DESC LIMIT 10
        """).fetchall()
        print(f"\n  Top active drug classes:")
        for cls, n, pts in classes:
            print(f"    {cls:<25}: {n:>6} prescriptions ({pts:>4} patients)")
    except Exception:
        pass

    con.close()
    print(f"\n  Database: {DB_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Silver+ layer: derived clinical features")
    parser.add_argument("--cohort", default=str(COHORT_FILE), help="Path to cohort patient IDs JSON")
    parser.add_argument("--output", default=str(SILVER_PLUS_DIR), help="Output directory")
    parser.add_argument("--reload-duckdb", action="store_true", help="Also reload DuckDB tables")
    args = parser.parse_args()

    cohort_path = Path(args.cohort)
    if not cohort_path.exists():
        print(f"Cohort file not found: {cohort_path}")
        print("Run the cohort selection first.")
        return

    build_silver_plus(cohort_path, Path(args.output))


if __name__ == "__main__":
    main()
