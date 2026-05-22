"""Gold Layer — Point-in-Time Patient Cases for the Multi-Agent System.

Assembles per-patient diagnostic cases by:
  1. Selecting a target disease (the one agents must diagnose)
  2. Setting a cutoff date (when the disease was first diagnosed)
  3. Including ONLY data from BEFORE the cutoff
  4. HIDING the target disease from all outputs

Produces 3 files per patient:
  ehr_case.json    — demographics, pre-diagnosis conditions, visits, meds, imaging
  lab_case.json    — pre-diagnosis lab trends, critical flags, vitals
  ground_truth.json — the hidden answer (for evaluation only, never shown to agents)

Usage:
    python3 pipeline/gold.py
    python3 pipeline/gold.py --limit 5
    python3 pipeline/gold.py --cohort data/gold/cohort_1k_patient_ids.json
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import duckdb

DB_PATH = Path("data/clinical.duckdb")
COHORT_FILE = Path("data/gold/cohort_1k_patient_ids.json")
OUTPUT_DIR = Path("data/gold/patient_cases")

# Diseases the target encounter selector looks for (from cohort selection)
TARGET_DISEASES = [
    "Chronic congestive heart failure (disorder)",
    "Ischemic heart disease (disorder)",
    "Aortic valve regurgitation (disorder)",
    "Diabetes mellitus type 2 (disorder)",
    "Essential hypertension (disorder)",
    "Metabolic syndrome X (disorder)",
    "Chronic kidney disease stage 1 (disorder)",
    "Chronic kidney disease stage 2 (disorder)",
    "Chronic kidney disease stage 3 (disorder)",
    "End-stage renal disease (disorder)",
    "Cerebral palsy (disorder)",
    "Epilepsy (disorder)",
    # "Anemia (disorder)",  # Removed: labs are normal before diagnosis (Synthea assigns incidentally)
    "Malignant neoplasm of breast (disorder)",
    "Osteoporosis (disorder)",
    "Pneumonia (disorder)",
    "Osteoarthritis of knee (disorder)",
]

# Key labs to track for trends
KEY_LABS = [
    "Glucose", "Glucose [Mass/volume] in Blood",
    "Creatinine", "Creatinine [Mass/volume] in Serum or Plasma",
    "Hemoglobin [Mass/volume] in Blood",
    "Hemoglobin A1c/Hemoglobin.total in Blood",
    "Potassium [Moles/volume] in Blood",
    "Sodium [Moles/volume] in Blood",
    "Calcium [Mass/volume] in Serum or Plasma",
    "Carbon dioxide  total [Moles/volume] in Blood",
    "Chloride [Moles/volume] in Blood",
    "Urea nitrogen [Mass/volume] in Blood",
    "Total Cholesterol", "Triglycerides",
    "Low Density Lipoprotein Cholesterol",
    "High Density Lipoprotein Cholesterol",
    "Glomerular filtration rate/1.73 sq M.predicted",
    "Albumin [Mass/volume] in Serum or Plasma",
    "Bilirubin.total [Mass/volume] in Serum or Plasma",
    "Alanine aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
    "Aspartate aminotransferase [Enzymatic activity/volume] in Serum or Plasma",
    "Leukocytes [#/volume] in Blood by Automated count",
    "Platelets [#/volume] in Blood by Automated count",
    "Erythrocytes [#/volume] in Blood by Automated count",
]

# Minimum visits before cutoff to ensure enough data for diagnosis
MIN_PRE_DIAGNOSIS_VISITS = 3

# Minimum lab observations before cutoff to ensure MAS has diagnosable data
MIN_PRE_DIAGNOSIS_LABS = 5


def load_cohort(cohort_path, limit=None):
    ids = json.loads(cohort_path.read_text())
    return ids[:limit] if limit else ids


def get_person_id_map(con, uuids):
    con.execute("CREATE OR REPLACE TEMP TABLE _gold_uuids (uuid VARCHAR)")
    con.executemany("INSERT INTO _gold_uuids VALUES (?)", [(u,) for u in uuids])
    rows = con.execute("""
        SELECT person_source_value, person_id
        FROM silver_person
        WHERE person_source_value IN (SELECT uuid FROM _gold_uuids)
    """).fetchall()
    con.execute("DROP TABLE _gold_uuids")
    return {r[0]: r[1] for r in rows}


# ══════════════════════════════════════════════════════════════════════
# TARGET ENCOUNTER SELECTION
# ══════════════════════════════════════════════════════════════════════

def select_target_encounter(con, person_id):
    """Pick the target disease for this patient to diagnose.

    Strategy: pick the most clinically significant condition that has
    enough pre-diagnosis data (>= MIN_PRE_DIAGNOSIS_VISITS before cutoff).
    Prefer severe diseases, then pick the latest one for maximum history.
    """
    disease_list = ", ".join(f"'{d}'" for d in TARGET_DISEASES)

    rows = con.execute(f"""
        WITH candidates AS (
            SELECT
                c.person_id AS pid,
                c.condition_source_value AS target_disease,
                c.condition_source_code AS target_code,
                CAST(c.condition_start_date AS VARCHAR) AS diagnosis_date,
                c.condition_start_date AS dx_date,
                c.encounter_source_value AS encounter_id,
                -- Clinical priority (lower = more significant)
                CASE
                    WHEN c.condition_source_value LIKE '%heart failure%' THEN 1
                    WHEN c.condition_source_value LIKE '%neoplasm%' THEN 1
                    WHEN c.condition_source_value LIKE '%Ischemic heart%' THEN 1
                    WHEN c.condition_source_value LIKE '%End-stage renal%' THEN 1
                    WHEN c.condition_source_value LIKE '%Diabetes mellitus%' THEN 2
                    WHEN c.condition_source_value LIKE '%kidney disease stage 3%' THEN 2
                    WHEN c.condition_source_value LIKE '%Aortic valve%' THEN 2
                    WHEN c.condition_source_value LIKE '%Epilepsy%' THEN 3
                    WHEN c.condition_source_value LIKE '%kidney disease%' THEN 3
                    WHEN c.condition_source_value LIKE '%Anemia%' THEN 3
                    WHEN c.condition_source_value LIKE '%Osteoporosis%' THEN 3
                    ELSE 4
                END AS priority,
                -- Count visits before this diagnosis
                (SELECT COUNT(*) FROM silver_visit_occurrence v
                 WHERE v.person_id = c.person_id
                   AND v.visit_start_date < c.condition_start_date
                ) AS visits_before,
                -- Count lab observations before this diagnosis
                (SELECT COUNT(*) FROM silver_measurement m
                 WHERE m.person_id = c.person_id
                   AND m.measurement_date < c.condition_start_date
                ) AS labs_before
            FROM silver_condition_occurrence c
            WHERE c.person_id = ?
              AND c.condition_source_value IN ({disease_list})
        )
        SELECT target_disease, target_code, diagnosis_date, encounter_id,
               priority, visits_before, labs_before
        FROM candidates
        WHERE visits_before >= {MIN_PRE_DIAGNOSIS_VISITS}
          AND labs_before >= {MIN_PRE_DIAGNOSIS_LABS}
        ORDER BY priority ASC, dx_date DESC
        LIMIT 1
    """, [person_id]).fetchone()

    if not rows:
        # Fallback: any target disease, even with fewer visits
        rows = con.execute(f"""
            SELECT
                c.condition_source_value,
                c.condition_source_code,
                CAST(c.condition_start_date AS VARCHAR),
                c.encounter_source_value,
                1 AS priority, 0 AS visits_before
            FROM silver_condition_occurrence c
            WHERE c.person_id = ?
              AND c.condition_source_value IN ({disease_list})
            ORDER BY c.condition_start_date DESC
            LIMIT 1
        """, [person_id]).fetchone()

    if not rows:
        return None

    return {
        "target_disease": rows[0],
        "target_code": rows[1],
        "cutoff_date": rows[2],
        "encounter_id": rows[3],
        "priority": rows[4],
        "visits_before": rows[5],
    }


# ══════════════════════════════════════════════════════════════════════
# EHR CASE (point-in-time)
# ══════════════════════════════════════════════════════════════════════

def build_ehr_case(con, person_id, patient_uuid, cutoff_date, target_code):
    """Assemble ehr_case with only pre-diagnosis data, hiding target disease."""

    # Demographics (age at cutoff, not current)
    demo = con.execute("""
        SELECT person_id, person_source_value, gender_source_value,
               year_of_birth, month_of_birth, day_of_birth, birth_datetime,
               race_source_value, ethnicity_source_value, death_datetime,
               city, state, zip, county
        FROM silver_person WHERE person_id = ?
    """, [person_id]).fetchone()

    cutoff_dt = datetime.strptime(cutoff_date[:10], "%Y-%m-%d")
    age = cutoff_dt.year - demo[3] - (
        (cutoff_dt.month, cutoff_dt.day) < (demo[4] or 1, demo[5] or 1)
    )

    demographics = {
        "person_id": demo[0],
        "patient_uuid": demo[1],
        "gender": demo[2],
        "age": age,
        "date_of_birth": str(demo[6]),
        "race": demo[7],
        "ethnicity": demo[8],
        "deceased": demo[9] is not None and str(demo[9]) <= cutoff_date,
        "death_date": str(demo[9]) if demo[9] and str(demo[9]) <= cutoff_date else None,
        "location": {
            "city": demo[10], "state": demo[11],
            "zip": demo[12], "county": demo[13],
        },
    }

    # Conditions: before cutoff, EXCLUDING target disease
    conditions = con.execute("""
        SELECT condition_source_value, condition_source_code,
               CAST(condition_start_date AS VARCHAR),
               CAST(condition_end_date AS VARCHAR)
        FROM silver_condition_occurrence
        WHERE person_id = ?
          AND CAST(condition_start_date AS VARCHAR) < ?
          AND condition_source_code != ?
        ORDER BY condition_start_date DESC
    """, [person_id, cutoff_date, target_code]).fetchall()

    active_conditions = []
    resolved_conditions = []
    for c in conditions:
        entry = {"condition": c[0], "code": c[1], "start_date": c[2], "end_date": c[3]}
        # Active at cutoff: no end date OR end date >= cutoff
        if c[3] is None or c[3] >= cutoff_date:
            active_conditions.append(entry)
        else:
            resolved_conditions.append(entry)

    # Visits before cutoff
    visit_summary = con.execute("""
        SELECT
            COUNT(*),
            COUNT(CASE WHEN visit_source_value = 'emergency' THEN 1 END),
            COUNT(CASE WHEN visit_source_value = 'inpatient' THEN 1 END),
            COUNT(CASE WHEN visit_source_value = 'outpatient' THEN 1 END),
            COUNT(CASE WHEN visit_source_value = 'wellness' THEN 1 END),
            CAST(MIN(visit_start_date) AS VARCHAR),
            CAST(MAX(visit_start_date) AS VARCHAR)
        FROM silver_visit_occurrence
        WHERE person_id = ? AND CAST(visit_start_date AS VARCHAR) < ?
    """, [person_id, cutoff_date]).fetchone()

    visits = {
        "total": visit_summary[0], "emergency": visit_summary[1],
        "inpatient": visit_summary[2], "outpatient": visit_summary[3],
        "wellness": visit_summary[4],
        "first_visit": visit_summary[5], "last_visit": visit_summary[6],
    }

    # Recent visits (5 most recent before cutoff)
    recent_visits = con.execute("""
        SELECT visit_source_value, CAST(visit_start_date AS VARCHAR),
               CAST(visit_end_date AS VARCHAR), visit_description,
               reason_source_description
        FROM silver_visit_occurrence
        WHERE person_id = ? AND CAST(visit_start_date AS VARCHAR) < ?
        ORDER BY visit_start_date DESC LIMIT 5
    """, [person_id, cutoff_date]).fetchall()

    visits["recent"] = [
        {"type": v[0], "start_date": v[1], "end_date": v[2],
         "description": v[3], "reason": v[4]}
        for v in recent_visits
    ]

    # Comorbidity matrix (point-in-time, excluding target)
    comorbidity = _compute_comorbidity_pit(con, person_id, cutoff_date, target_code)

    # Risk scores (point-in-time)
    risk_scores = _compute_risk_scores_pit(con, person_id, cutoff_date, comorbidity)

    # Medications active at cutoff
    medications = _compute_medications_pit(con, person_id, patient_uuid, cutoff_date)

    # Drug-condition links (before cutoff, excluding target)
    drug_links = _compute_drug_links_pit(con, person_id, patient_uuid, cutoff_date, target_code)

    # Imaging before cutoff
    imaging = con.execute("""
        SELECT i.Id, CAST(i.DATE AS VARCHAR), i.MODALITY_CODE,
               i.MODALITY_DESCRIPTION, i.BODYSITE_DESCRIPTION,
               i.SOP_DESCRIPTION, e.REASONDESCRIPTION
        FROM imaging_studies i
        LEFT JOIN encounters e ON i.ENCOUNTER = e.Id
        WHERE i.PATIENT = ? AND CAST(i.DATE AS VARCHAR) < ?
        ORDER BY i.DATE DESC LIMIT 20
    """, [patient_uuid, cutoff_date]).fetchall()

    imaging_studies = [
        {"study_id": img[0], "date": img[1], "modality_code": img[2],
         "modality": img[3], "body_site": img[4], "sop": img[5], "reason": img[6]}
        for img in imaging
    ]

    return {
        "case_type": "ehr",
        "case_mode": "point_in_time",
        "cutoff_date": cutoff_date,
        "patient_uuid": patient_uuid,
        "person_id": person_id,
        "assembled_at": datetime.now().isoformat(),
        "demographics": demographics,
        "conditions": {
            "active": active_conditions, "active_count": len(active_conditions),
            "resolved": resolved_conditions, "resolved_count": len(resolved_conditions),
        },
        "visits": visits,
        "comorbidity": comorbidity,
        "risk_scores": risk_scores,
        "medications": medications,
        "drug_condition_links": drug_links,
        "imaging_studies": imaging_studies,
    }


# ══════════════════════════════════════════════════════════════════════
# LAB CASE (point-in-time)
# ══════════════════════════════════════════════════════════════════════

def build_lab_case(con, person_id, cutoff_date):
    """Assemble lab_case with only pre-diagnosis data."""

    lab_trends = _compute_lab_trends_pit(con, person_id, cutoff_date)
    critical_flags = _compute_critical_flags_pit(con, person_id, cutoff_date)

    flag_counts = {"critical": 0, "abnormal": 0, "borderline": 0}
    for f in critical_flags:
        if f["severity"] in flag_counts:
            flag_counts[f["severity"]] += 1

    # Vitals: most recent before cutoff
    vitals = con.execute("""
        SELECT measurement_source_value, value_as_number, unit_source_value,
               CAST(measurement_date AS VARCHAR)
        FROM silver_measurement
        WHERE person_id = ? AND category = 'vital-signs'
          AND value_as_number IS NOT NULL
          AND CAST(measurement_date AS VARCHAR) < ?
          AND measurement_date = (
              SELECT MAX(measurement_date) FROM silver_measurement
              WHERE person_id = ? AND category = 'vital-signs'
                AND CAST(measurement_date AS VARCHAR) < ?
          )
        ORDER BY measurement_source_value
    """, [person_id, cutoff_date, person_id, cutoff_date]).fetchall()

    recent_vitals = [
        {"vital": v[0], "value": v[1], "units": v[2], "date": v[3]}
        for v in vitals
    ]

    # Latest lab per test before cutoff
    recent_labs = con.execute("""
        SELECT measurement_source_value, value_as_number, unit_source_value,
               CAST(measurement_date AS VARCHAR)
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY measurement_source_value ORDER BY measurement_date DESC
            ) AS rn
            FROM silver_measurement
            WHERE person_id = ? AND category = 'laboratory'
              AND value_as_number IS NOT NULL
              AND CAST(measurement_date AS VARCHAR) < ?
        ) sub WHERE rn = 1
        ORDER BY measurement_source_value
    """, [person_id, cutoff_date]).fetchall()

    latest_labs = [
        {"lab_name": l[0], "value": l[1], "units": l[2], "date": l[3]}
        for l in recent_labs
    ]

    return {
        "case_type": "lab",
        "case_mode": "point_in_time",
        "cutoff_date": cutoff_date,
        "person_id": person_id,
        "assembled_at": datetime.now().isoformat(),
        "lab_trends": lab_trends,
        "critical_flags": {
            "flags": critical_flags,
            "summary": flag_counts,
            "total_abnormal": sum(flag_counts.values()),
        },
        "recent_vitals": recent_vitals,
        "latest_labs": latest_labs,
        "lab_count": len(latest_labs),
        "vital_count": len(recent_vitals),
    }


# ══════════════════════════════════════════════════════════════════════
# GROUND TRUTH (for evaluation only — never shown to agents)
# ══════════════════════════════════════════════════════════════════════

def build_ground_truth(con, person_id, patient_uuid, target_info, cutoff_date):
    """Build ground truth file for evaluating agent diagnostic accuracy."""

    # All conditions active at diagnosis
    conditions_at_dx = con.execute("""
        SELECT condition_source_value, condition_source_code,
               CAST(condition_start_date AS VARCHAR)
        FROM silver_condition_occurrence
        WHERE person_id = ?
          AND CAST(condition_start_date AS VARCHAR) <= ?
          AND (condition_end_date IS NULL OR CAST(condition_end_date AS VARCHAR) >= ?)
        ORDER BY condition_start_date
    """, [person_id, cutoff_date, cutoff_date]).fetchall()

    # Medications started AFTER diagnosis (treatment response)
    post_dx_meds = con.execute("""
        SELECT DISTINCT m.DESCRIPTION, m.REASONDESCRIPTION
        FROM medications m
        JOIN silver_person sp ON m.PATIENT = sp.person_source_value
        WHERE sp.person_id = ?
          AND CAST(m.START AS VARCHAR) >= ?
          AND m.REASONCODE = ?
        ORDER BY m.DESCRIPTION
    """, [person_id, cutoff_date, target_info["target_code"]]).fetchall()

    # Critical labs at cutoff that hint at diagnosis
    critical_at_cutoff = con.execute("""
        WITH pre_cutoff_latest AS (
            SELECT measurement_source_value, value_as_number, unit_source_value,
                   CAST(measurement_date AS VARCHAR) AS mdate,
                   ROW_NUMBER() OVER (
                       PARTITION BY measurement_source_value ORDER BY measurement_date DESC
                   ) AS rn
            FROM silver_measurement
            WHERE person_id = ? AND category = 'laboratory'
              AND value_as_number IS NOT NULL
              AND CAST(measurement_date AS VARCHAR) < ?
        )
        SELECT measurement_source_value, value_as_number, unit_source_value, mdate
        FROM pre_cutoff_latest WHERE rn = 1
        ORDER BY measurement_source_value
    """, [person_id, cutoff_date]).fetchall()

    return {
        "patient_uuid": patient_uuid,
        "person_id": person_id,
        "target_condition": {
            "name": target_info["target_disease"],
            "code": target_info["target_code"],
            "diagnosis_date": target_info["cutoff_date"],
            "encounter_id": target_info["encounter_id"],
        },
        "cutoff_date": cutoff_date,
        "visits_before_diagnosis": target_info["visits_before"],
        "all_conditions_at_diagnosis": [
            {"name": c[0], "code": c[1], "start_date": c[2]}
            for c in conditions_at_dx
        ],
        "post_diagnosis_medications": [
            {"medication": m[0], "prescribed_for": m[1]}
            for m in post_dx_meds
        ],
        "labs_at_cutoff": [
            {"lab": l[0], "value": l[1], "units": l[2], "date": l[3]}
            for l in critical_at_cutoff
        ],
    }


# ══════════════════════════════════════════════════════════════════════
# INLINE SILVER+ COMPUTATIONS (point-in-time)
# ══════════════════════════════════════════════════════════════════════

def _compute_lab_trends_pit(con, person_id, cutoff_date):
    """Lab trends using only measurements before cutoff."""
    lab_list = ", ".join(f"'{l}'" for l in KEY_LABS)

    rows = con.execute(f"""
        WITH lab_stats AS (
            SELECT
                m.measurement_source_value AS lab_name,
                m.unit_source_value AS units,
                COUNT(*) AS measurement_count,
                MIN(m.value_as_number) AS value_min,
                MAX(m.value_as_number) AS value_max,
                ROUND(AVG(m.value_as_number), 2) AS value_mean,
                ROUND(MEDIAN(m.value_as_number), 2) AS value_median,
                ROUND(STDDEV(m.value_as_number), 2) AS value_stddev,
                LAST(m.value_as_number ORDER BY m.measurement_date) AS value_latest,
                CAST(LAST(m.measurement_date ORDER BY m.measurement_date) AS VARCHAR) AS latest_date,
                FIRST(m.value_as_number ORDER BY m.measurement_date) AS value_first,
                CAST(FIRST(m.measurement_date ORDER BY m.measurement_date) AS VARCHAR) AS first_date,
                AVG(CASE
                    WHEN m.measurement_date >= (CAST(? AS DATE) - INTERVAL '180 days')
                    THEN m.value_as_number
                END) AS value_mean_recent
            FROM silver_measurement m
            WHERE m.person_id = ?
              AND CAST(m.measurement_date AS VARCHAR) < ?
              AND m.value_as_number IS NOT NULL
              AND m.category = 'laboratory'
              AND m.measurement_source_value IN ({lab_list})
            GROUP BY m.measurement_source_value, m.unit_source_value
        )
        SELECT lab_name, units, measurement_count,
               value_min, value_max, value_mean, value_median, value_stddev,
               value_latest, latest_date, value_first, first_date,
               ROUND(value_mean_recent, 2) AS value_mean_recent,
               CASE
                   WHEN value_mean_recent IS NULL OR value_mean IS NULL OR value_mean = 0
                   THEN 'insufficient_data'
                   WHEN value_mean_recent > value_mean * 1.10 THEN 'increasing'
                   WHEN value_mean_recent < value_mean * 0.90 THEN 'decreasing'
                   ELSE 'stable'
               END AS trend,
               CASE
                   WHEN value_first IS NOT NULL AND value_first != 0
                   THEN ROUND((value_latest - value_first) / value_first * 100, 1)
               END AS pct_change
        FROM lab_stats
        ORDER BY lab_name
    """, [cutoff_date, person_id, cutoff_date]).fetchall()

    return [
        {"lab_name": r[0], "units": r[1], "measurement_count": r[2],
         "value_min": r[3], "value_max": r[4], "value_mean": r[5],
         "value_median": r[6], "value_stddev": r[7], "value_latest": r[8],
         "latest_date": r[9], "value_first": r[10], "first_date": r[11],
         "value_mean_recent": r[12], "trend": r[13], "pct_change": r[14]}
        for r in rows
    ]


def _compute_critical_flags_pit(con, person_id, cutoff_date):
    """Critical lab flags using the latest value before cutoff."""
    rows = con.execute("""
        WITH latest_labs AS (
            SELECT
                m.measurement_source_value AS lab_name,
                m.unit_source_value AS units,
                LAST(m.value_as_number ORDER BY m.measurement_date) AS value_latest,
                CAST(LAST(m.measurement_date ORDER BY m.measurement_date) AS VARCHAR) AS latest_date
            FROM silver_measurement m
            WHERE m.person_id = ?
              AND CAST(m.measurement_date AS VARCHAR) < ?
              AND m.value_as_number IS NOT NULL
              AND m.category = 'laboratory'
            GROUP BY m.measurement_source_value, m.unit_source_value
        )
        SELECT lab_name, units, value_latest, latest_date,
            CASE
                WHEN lab_name LIKE '%Glucose%' AND units LIKE '%mg%' THEN
                    CASE WHEN value_latest < 50 THEN 'critical_low'
                         WHEN value_latest < 70 THEN 'low'
                         WHEN value_latest > 300 THEN 'critical_high'
                         WHEN value_latest > 200 THEN 'high'
                         WHEN value_latest > 126 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Creatinine%' AND units LIKE '%mg%' THEN
                    CASE WHEN value_latest > 4.0 THEN 'critical_high'
                         WHEN value_latest > 2.0 THEN 'high'
                         WHEN value_latest > 1.5 THEN 'mildly_elevated'
                         WHEN value_latest < 0.4 THEN 'low'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Hemoglobin%' AND lab_name NOT LIKE '%A1c%' AND units LIKE '%g/dL%' THEN
                    CASE WHEN value_latest < 7.0 THEN 'critical_low'
                         WHEN value_latest < 10.0 THEN 'low'
                         WHEN value_latest > 20.0 THEN 'critical_high'
                         WHEN value_latest > 17.5 THEN 'high'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%A1c%' AND units = '%' THEN
                    CASE WHEN value_latest >= 10.0 THEN 'critical_high'
                         WHEN value_latest >= 8.0 THEN 'high'
                         WHEN value_latest >= 6.5 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Potassium%' THEN
                    CASE WHEN value_latest < 2.5 THEN 'critical_low'
                         WHEN value_latest < 3.5 THEN 'low'
                         WHEN value_latest > 6.5 THEN 'critical_high'
                         WHEN value_latest > 5.0 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Sodium%' THEN
                    CASE WHEN value_latest < 120 THEN 'critical_low'
                         WHEN value_latest < 130 THEN 'low'
                         WHEN value_latest > 160 THEN 'critical_high'
                         WHEN value_latest > 145 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Glomerular%' THEN
                    CASE WHEN value_latest < 15 THEN 'critical_low'
                         WHEN value_latest < 30 THEN 'low'
                         WHEN value_latest < 60 THEN 'mildly_low'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Urea nitrogen%' THEN
                    CASE WHEN value_latest > 50 THEN 'critical_high'
                         WHEN value_latest > 30 THEN 'high'
                         WHEN value_latest > 20 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name = 'Total Cholesterol' THEN
                    CASE WHEN value_latest >= 300 THEN 'critical_high'
                         WHEN value_latest >= 240 THEN 'high'
                         WHEN value_latest >= 200 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Low Density%' THEN
                    CASE WHEN value_latest >= 190 THEN 'critical_high'
                         WHEN value_latest >= 160 THEN 'high'
                         WHEN value_latest >= 130 THEN 'mildly_elevated'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Platelet%' THEN
                    CASE WHEN value_latest < 50 THEN 'critical_low'
                         WHEN value_latest < 100 THEN 'low'
                         WHEN value_latest > 600 THEN 'critical_high'
                         WHEN value_latest > 400 THEN 'high'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Leukocyte%' THEN
                    CASE WHEN value_latest < 2.0 THEN 'critical_low'
                         WHEN value_latest < 4.0 THEN 'low'
                         WHEN value_latest > 20.0 THEN 'critical_high'
                         WHEN value_latest > 11.0 THEN 'high'
                         ELSE 'normal' END
                WHEN lab_name LIKE '%Calcium%' THEN
                    CASE WHEN value_latest < 7.0 THEN 'critical_low'
                         WHEN value_latest < 8.5 THEN 'low'
                         WHEN value_latest > 13.0 THEN 'critical_high'
                         WHEN value_latest > 10.5 THEN 'high'
                         ELSE 'normal' END
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
        WHERE flag NOT IN ('normal', 'not_evaluated')
    """, [person_id, cutoff_date]).fetchall()

    return [
        {"lab_name": r[0], "units": r[1], "value": r[2], "date": r[3],
         "flag": r[4], "normal_range": r[5],
         "severity": "critical" if "critical" in r[4]
                     else "abnormal" if r[4] in ("high", "low")
                     else "borderline"}
        for r in rows
    ]


def _compute_comorbidity_pit(con, person_id, cutoff_date, target_code):
    """Comorbidity flags using only conditions before cutoff, excluding target."""
    row = con.execute("""
        WITH ac AS (
            SELECT condition_source_value AS cn
            FROM silver_condition_occurrence
            WHERE person_id = ?
              AND CAST(condition_start_date AS VARCHAR) < ?
              AND condition_source_code != ?
        )
        SELECT
            MAX(CASE WHEN cn LIKE '%Chronic congestive heart failure%' THEN 1 ELSE 0 END) AS has_chf,
            MAX(CASE WHEN cn LIKE '%Ischemic heart disease%' THEN 1 ELSE 0 END) AS has_ihd,
            MAX(CASE WHEN cn LIKE '%Essential hypertension%' THEN 1 ELSE 0 END) AS has_hypertension,
            MAX(CASE WHEN cn LIKE '%Atrial fibrillation%' THEN 1 ELSE 0 END) AS has_afib,
            MAX(CASE WHEN cn LIKE '%Aortic valve%' THEN 1 ELSE 0 END) AS has_valvular_disease,
            MAX(CASE WHEN cn LIKE '%Diabetes mellitus type 2%' THEN 1 ELSE 0 END) AS has_diabetes_t2,
            MAX(CASE WHEN cn LIKE '%Metabolic syndrome%' THEN 1 ELSE 0 END) AS has_metabolic_syndrome,
            MAX(CASE WHEN cn LIKE '%Hyperlipidemia%' OR cn LIKE '%Hypertriglyceridemia%' THEN 1 ELSE 0 END) AS has_dyslipidemia,
            MAX(CASE WHEN cn LIKE '%Chronic kidney disease%' OR cn LIKE '%End-stage renal%' THEN 1 ELSE 0 END) AS has_ckd,
            MAX(CASE WHEN cn LIKE '%End-stage renal%' THEN 1 ELSE 0 END) AS has_esrd,
            MAX(CASE WHEN cn LIKE '%Cerebral palsy%' THEN 1 ELSE 0 END) AS has_cerebral_palsy,
            MAX(CASE WHEN cn LIKE '%Epilepsy%' THEN 1 ELSE 0 END) AS has_epilepsy,
            MAX(CASE WHEN cn LIKE '%Anemia%' THEN 1 ELSE 0 END) AS has_anemia,
            MAX(CASE WHEN cn LIKE '%Malignant neoplasm%' THEN 1 ELSE 0 END) AS has_cancer,
            MAX(CASE WHEN cn LIKE '%Osteoporosis%' THEN 1 ELSE 0 END) AS has_osteoporosis,
            MAX(CASE WHEN cn LIKE '%Osteoarthritis%' THEN 1 ELSE 0 END) AS has_osteoarthritis,
            MAX(CASE WHEN cn LIKE '%Pneumonia%' THEN 1 ELSE 0 END) AS has_pneumonia,
            MAX(CASE WHEN cn LIKE '%Chronic obstructive%' THEN 1 ELSE 0 END) AS has_copd,
            MAX(CASE WHEN cn LIKE '%Gastroesophageal reflux%' THEN 1 ELSE 0 END) AS has_gerd,
            COUNT(DISTINCT cn) AS total_condition_count,
            -- Charlson index
            (
                MAX(CASE WHEN cn LIKE '%Chronic congestive heart failure%' THEN 1 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Ischemic heart disease%' THEN 1 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Diabetes mellitus type 2%' THEN 2 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Chronic kidney disease%' OR cn LIKE '%End-stage renal%' THEN 2 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Cerebral palsy%' THEN 2 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Malignant neoplasm%' THEN 2 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Chronic obstructive%' THEN 1 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Anemia%' THEN 1 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Epilepsy%' THEN 1 ELSE 0 END) +
                MAX(CASE WHEN cn LIKE '%Osteoporosis%' THEN 1 ELSE 0 END)
            ) AS charlson_index
        FROM ac
    """, [person_id, cutoff_date, target_code]).fetchone()

    if not row or row[0] is None:
        return {"flags": {}, "total_condition_count": 0, "charlson_index": 0}

    flag_names = [
        "has_chf", "has_ihd", "has_hypertension", "has_afib", "has_valvular_disease",
        "has_diabetes_t2", "has_metabolic_syndrome", "has_dyslipidemia",
        "has_ckd", "has_esrd", "has_cerebral_palsy", "has_epilepsy",
        "has_anemia", "has_cancer", "has_osteoporosis", "has_osteoarthritis",
        "has_pneumonia", "has_copd", "has_gerd",
    ]
    flags = {name: bool(row[i]) for i, name in enumerate(flag_names) if row[i] == 1}

    return {
        "flags": flags,
        "total_condition_count": row[19],
        "charlson_index": row[20],
    }


def _compute_risk_scores_pit(con, person_id, cutoff_date, comorbidity):
    """Risk scores using vitals/labs before cutoff."""

    # Latest vitals before cutoff
    vitals = con.execute("""
        SELECT
            MAX(CASE WHEN measurement_source_value LIKE '%Systolic%' THEN value_as_number END),
            MAX(CASE WHEN measurement_source_value LIKE '%Diastolic%' THEN value_as_number END),
            MAX(CASE WHEN measurement_source_value LIKE '%Body Mass Index%' THEN value_as_number END),
            MAX(CASE WHEN measurement_source_value LIKE '%Heart rate%' THEN value_as_number END)
        FROM silver_measurement
        WHERE person_id = ? AND category = 'vital-signs'
          AND CAST(measurement_date AS VARCHAR) < ?
          AND measurement_date = (
              SELECT MAX(measurement_date) FROM silver_measurement
              WHERE person_id = ? AND category = 'vital-signs'
                AND CAST(measurement_date AS VARCHAR) < ?
          )
    """, [person_id, cutoff_date, person_id, cutoff_date]).fetchone()

    sbp = vitals[0] if vitals else None
    dbp = vitals[1] if vitals else None
    bmi = vitals[2] if vitals else None

    # Latest key labs before cutoff
    labs = con.execute("""
        SELECT measurement_source_value, value_as_number
        FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY measurement_source_value ORDER BY measurement_date DESC
            ) AS rn
            FROM silver_measurement
            WHERE person_id = ? AND category = 'laboratory'
              AND value_as_number IS NOT NULL
              AND CAST(measurement_date AS VARCHAR) < ?
        ) sub WHERE rn = 1
    """, [person_id, cutoff_date]).fetchall()

    lab_map = {r[0]: r[1] for r in labs}
    a1c = lab_map.get("Hemoglobin A1c/Hemoglobin.total in Blood")
    egfr = lab_map.get("Glomerular filtration rate/1.73 sq M.predicted")
    chol = lab_map.get("Total Cholesterol")
    ldl = lab_map.get("Low Density Lipoprotein Cholesterol")

    # Med count before cutoff
    med_count = con.execute("""
        SELECT COUNT(DISTINCT drug_source_value)
        FROM silver_drug_exposure
        WHERE person_id = ?
          AND CAST(drug_exposure_start_date AS VARCHAR) < ?
          AND (drug_exposure_end_date IS NULL OR CAST(drug_exposure_end_date AS VARCHAR) >= ?)
    """, [person_id, cutoff_date, cutoff_date]).fetchone()[0]

    charlson = comorbidity.get("charlson_index", 0)
    has_dm = comorbidity.get("flags", {}).get("has_diabetes_t2", False)
    has_chf = comorbidity.get("flags", {}).get("has_chf", False)
    has_ckd = comorbidity.get("flags", {}).get("has_ckd", False)

    # Compute scores
    ckd_stage = None
    if egfr is not None:
        if egfr >= 90: ckd_stage = 1
        elif egfr >= 60: ckd_stage = 2
        elif egfr >= 30: ckd_stage = 3
        elif egfr >= 15: ckd_stage = 4
        else: ckd_stage = 5

    bp_cat = "unknown"
    if sbp is not None:
        if sbp >= 180 or (dbp and dbp >= 120): bp_cat = "hypertensive_crisis"
        elif sbp >= 140 or (dbp and dbp >= 90): bp_cat = "stage2_hypertension"
        elif sbp >= 130 or (dbp and dbp >= 80): bp_cat = "stage1_hypertension"
        elif sbp >= 120: bp_cat = "elevated"
        else: bp_cat = "normal"

    glycemic = "unknown"
    if a1c is not None:
        if a1c >= 10: glycemic = "very_poor"
        elif a1c >= 8: glycemic = "poor"
        elif a1c >= 7: glycemic = "suboptimal"
        elif a1c >= 5.7: glycemic = "prediabetic"
        else: glycemic = "normal"

    polypharmacy = "low"
    if med_count >= 10: polypharmacy = "high"
    elif med_count >= 5: polypharmacy = "moderate"

    complexity = "low"
    if (charlson >= 5 or comorbidity.get("total_condition_count", 0) >= 10) and med_count >= 5:
        complexity = "high"
    elif charlson >= 3 or comorbidity.get("total_condition_count", 0) >= 5:
        complexity = "moderate"

    return {
        "sbp_latest": round(sbp) if sbp else None,
        "dbp_latest": round(dbp) if dbp else None,
        "bmi_latest": round(bmi, 1) if bmi else None,
        "hr_latest": round(vitals[3]) if vitals and vitals[3] else None,
        "a1c_latest": round(a1c, 1) if a1c else None,
        "egfr_latest": round(egfr, 1) if egfr else None,
        "total_cholesterol_latest": round(chol) if chol else None,
        "ldl_latest": round(ldl) if ldl else None,
        "ckd_stage": ckd_stage,
        "bp_category": bp_cat,
        "glycemic_control": glycemic,
        "active_med_count": med_count,
        "polypharmacy_risk": polypharmacy,
        "charlson_index": charlson,
        "clinical_complexity": complexity,
    }


def _compute_medications_pit(con, person_id, patient_uuid, cutoff_date):
    """Medications active at cutoff date."""
    rows = con.execute("""
        SELECT d.drug_source_value,
               CAST(d.drug_exposure_start_date AS VARCHAR),
               CAST(d.drug_exposure_end_date AS VARCHAR),
               CASE
                   WHEN d.drug_source_value LIKE '%lisinopril%' OR d.drug_source_value LIKE '%enalapril%'
                        OR d.drug_source_value LIKE '%ramipril%' THEN 'ACE_inhibitor'
                   WHEN d.drug_source_value LIKE '%losartan%' OR d.drug_source_value LIKE '%valsartan%' THEN 'ARB'
                   WHEN d.drug_source_value LIKE '%amlodipine%' THEN 'calcium_channel_blocker'
                   WHEN d.drug_source_value LIKE '%metoprolol%' OR d.drug_source_value LIKE '%atenolol%'
                        OR d.drug_source_value LIKE '%carvedilol%' THEN 'beta_blocker'
                   WHEN d.drug_source_value LIKE '%hydrochlorothiazide%' OR d.drug_source_value LIKE '%furosemide%'
                        OR d.drug_source_value LIKE '%spironolactone%' THEN 'diuretic'
                   WHEN d.drug_source_value LIKE '%metformin%' THEN 'biguanide'
                   WHEN d.drug_source_value LIKE '%insulin%' THEN 'insulin'
                   WHEN d.drug_source_value LIKE '%atorvastatin%' OR d.drug_source_value LIKE '%simvastatin%'
                        OR d.drug_source_value LIKE '%rosuvastatin%' THEN 'statin'
                   WHEN d.drug_source_value LIKE '%warfarin%' OR d.drug_source_value LIKE '%rivaroxaban%' THEN 'anticoagulant'
                   WHEN d.drug_source_value LIKE '%aspirin%' OR d.drug_source_value LIKE '%clopidogrel%' THEN 'antiplatelet'
                   WHEN d.drug_source_value LIKE '%levetiracetam%' OR d.drug_source_value LIKE '%valproic%'
                        OR d.drug_source_value LIKE '%carbamazepine%' THEN 'anticonvulsant'
                   WHEN d.drug_source_value LIKE '%omeprazole%' OR d.drug_source_value LIKE '%pantoprazole%' THEN 'PPI'
                   WHEN d.drug_source_value LIKE '%alendronate%' THEN 'bisphosphonate'
                   WHEN d.drug_source_value LIKE '%ibuprofen%' OR d.drug_source_value LIKE '%naproxen%' THEN 'NSAID'
                   ELSE 'other'
               END AS drug_class
        FROM silver_drug_exposure d
        WHERE d.person_id = ?
          AND CAST(d.drug_exposure_start_date AS VARCHAR) < ?
          AND (d.drug_exposure_end_date IS NULL OR CAST(d.drug_exposure_end_date AS VARCHAR) >= ?)
        ORDER BY d.drug_exposure_start_date DESC
    """, [person_id, cutoff_date, cutoff_date]).fetchall()

    meds = [
        {"medication": r[0], "start_date": r[1], "end_date": r[2], "drug_class": r[3]}
        for r in rows
    ]
    return {"active": meds, "active_count": len(meds)}


def _compute_drug_links_pit(con, person_id, patient_uuid, cutoff_date, target_code):
    """Drug-condition links before cutoff, excluding target disease."""
    rows = con.execute("""
        SELECT m.DESCRIPTION, m.REASONDESCRIPTION, m.REASONCODE, COUNT(*)
        FROM medications m
        JOIN silver_person sp ON m.PATIENT = sp.person_source_value
        WHERE sp.person_id = ?
          AND CAST(m.START AS VARCHAR) < ?
          AND m.REASONDESCRIPTION IS NOT NULL AND m.REASONDESCRIPTION != ''
          AND m.REASONCODE != ?
        GROUP BY m.DESCRIPTION, m.REASONDESCRIPTION, m.REASONCODE
        ORDER BY m.REASONDESCRIPTION
    """, [person_id, cutoff_date, target_code]).fetchall()

    return [
        {"medication": r[0], "condition_treated": r[1],
         "condition_code": r[2], "prescription_count": r[3]}
        for r in rows
    ]


# ══════════════════════════════════════════════════════════════════════
# MAIN PIPELINE
# ══════════════════════════════════════════════════════════════════════

def build_gold_layer(cohort_path, output_dir, limit=None):
    pipeline_start = time.time()

    print(f"{'═'*70}")
    print(f"GOLD LAYER — Point-in-Time Diagnostic Cases")
    print(f"{'═'*70}")
    print(f"  Mode:      Point-in-time (disease hidden from agents)")
    print(f"  Source:    Silver + Silver+ tables in {DB_PATH}")
    print(f"  Cohort:    {cohort_path}")
    print(f"  Output:    {output_dir}/")
    print(f"  Started:   {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    uuids = load_cohort(cohort_path, limit)
    print(f"  Patients:  {len(uuids)}\n")

    con = duckdb.connect(str(DB_PATH), read_only=True)
    id_map = get_person_id_map(con, uuids)
    print(f"  Mapped {len(id_map)}/{len(uuids)} UUIDs → person_ids\n")

    output_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    skipped = 0
    errors = 0
    disease_counts = {}

    for i, uuid in enumerate(uuids):
        person_id = id_map.get(uuid)
        if person_id is None:
            errors += 1
            continue

        try:
            # Step 1: Select target encounter
            target = select_target_encounter(con, person_id)
            if not target:
                skipped += 1
                continue

            cutoff_date = target["cutoff_date"]
            target_code = target["target_code"]

            # Step 2: Build case files (data before cutoff, disease hidden)
            ehr_case = build_ehr_case(con, person_id, uuid, cutoff_date, target_code)
            lab_case = build_lab_case(con, person_id, cutoff_date)
            ground_truth = build_ground_truth(con, person_id, uuid, target, cutoff_date)

            # Step 3: Save
            patient_dir = output_dir / uuid
            patient_dir.mkdir(parents=True, exist_ok=True)
            (patient_dir / "ehr_case.json").write_text(json.dumps(ehr_case, indent=2, default=str))
            (patient_dir / "lab_case.json").write_text(json.dumps(lab_case, indent=2, default=str))
            (patient_dir / "ground_truth.json").write_text(json.dumps(ground_truth, indent=2, default=str))

            # Mongo write path (additive — filesystem write above is unchanged)
            from src.config import cfg
            if cfg.USE_MONGO:
                import asyncio
                asyncio.run(write_patient_case_to_mongo({
                    "patient_uuid": uuid,
                    "person_id": person_id,
                    "cutoff_date": cutoff_date,
                    "case_type": "ehr+lab",
                    "demographics": ehr_case.get("demographics", {}),
                    "conditions": ehr_case.get("conditions", {}),
                    "medications": ehr_case.get("medications", {}),
                    "visits": ehr_case.get("visits", []),
                    "comorbidity": ehr_case.get("comorbidity", {}),
                    "risk_scores": ehr_case.get("risk_scores", {}),
                    "lab_case": lab_case,
                    "ground_truth": ground_truth,
                }))

            success += 1
            d = target["target_disease"]
            disease_counts[d] = disease_counts.get(d, 0) + 1

            if (i + 1) % 100 == 0 or (i + 1) == len(uuids):
                elapsed = time.time() - pipeline_start
                rate = (i + 1) / elapsed
                print(f"  [{i+1}/{len(uuids)}] {success} assembled, {skipped} skipped ({rate:.1f}/s)")

        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  [{i+1}] ERROR {uuid[:12]}...: {e}")

    con.close()

    # Compute sizes
    total_ehr = total_lab = total_gt = 0
    for uuid in uuids:
        for fname, acc in [("ehr_case.json", "ehr"), ("lab_case.json", "lab"), ("ground_truth.json", "gt")]:
            p = output_dir / uuid / fname
            if p.exists():
                s = p.stat().st_size
                if acc == "ehr": total_ehr += s
                elif acc == "lab": total_lab += s
                else: total_gt += s

    total_time = time.time() - pipeline_start

    print(f"\n{'═'*70}")
    print(f"GOLD LAYER SUMMARY — Point-in-Time")
    print(f"{'═'*70}")
    print(f"  Assembled:   {success} patients")
    print(f"  Skipped:     {skipped} (no target disease found)")
    print(f"  Errors:      {errors}")
    print(f"  Files:       {success * 3} ({success} ehr + {success} lab + {success} ground_truth)")
    print(f"  EHR size:    {total_ehr / 1024 / 1024:.1f} MB")
    print(f"  Lab size:    {total_lab / 1024 / 1024:.1f} MB")
    print(f"  GT size:     {total_gt / 1024 / 1024:.1f} MB")
    print(f"  Total:       {(total_ehr + total_lab + total_gt) / 1024 / 1024:.1f} MB")
    print(f"  Time:        {total_time:.1f}s ({total_time / max(success,1) * 1000:.0f}ms/patient)")

    # Disease distribution
    print(f"\n  Target diseases to diagnose:")
    for d, n in sorted(disease_counts.items(), key=lambda x: -x[1]):
        print(f"    {n:>4}x  {d}")

    # Sample patient
    if success > 0:
        sample_uuid = next(u for u in uuids if (output_dir / u / "ground_truth.json").exists())
        sample_ehr = json.loads((output_dir / sample_uuid / "ehr_case.json").read_text())
        sample_gt = json.loads((output_dir / sample_uuid / "ground_truth.json").read_text())

        print(f"\n{'─'*70}")
        print(f"SAMPLE CASE: {sample_uuid[:20]}...")
        print(f"{'─'*70}")
        d = sample_ehr["demographics"]
        print(f"  Patient:     {d['age']}yo {d['gender']} | {d['race']}")
        print(f"  Cutoff:      {sample_ehr['cutoff_date']}")
        print(f"  HIDDEN DX:   {sample_gt['target_condition']['name']}")
        print(f"  Conditions:  {sample_ehr['conditions']['active_count']} active (target excluded)")
        print(f"  Visits:      {sample_ehr['visits']['total']} before cutoff")
        print(f"  Active meds: {sample_ehr['medications']['active_count']}")

        # Verify no leakage
        target_name = sample_gt["target_condition"]["name"].lower()
        ehr_text = json.dumps(sample_ehr).lower()
        if target_name in ehr_text:
            print(f"  LEAKAGE:     WARNING — target disease found in ehr_case!")
        else:
            print(f"  Leakage:     NONE (verified)")

    print(f"\n  Output:      {output_dir}/")


def main():
    parser = argparse.ArgumentParser(description="Gold layer: point-in-time diagnostic cases")
    parser.add_argument("--cohort", default=str(COHORT_FILE), help="Cohort file")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output directory")
    parser.add_argument("--limit", type=int, help="Limit patients (for testing)")
    args = parser.parse_args()

    cohort_path = Path(args.cohort)
    if not cohort_path.exists():
        print(f"Cohort file not found: {cohort_path}")
        return

    build_gold_layer(cohort_path, Path(args.output), args.limit)


async def write_patient_case_to_mongo(payload: dict) -> None:
    """Write one Gold case to the PatientCase collection. Called from
    build_gold_layer() when USE_MONGO is set; the filesystem write path
    remains the default until the cutover."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import PatientCase

    await init_db()
    case_stats = {
        "activeConditions":  len((payload.get("conditions",  {}) or {}).get("active", []) or []),
        "activeMedications": len((payload.get("medications", {}) or {}).get("active", []) or []),
        "labTrends":         len((payload.get("lab_case", {}) or {}).get("latest_labs", []) or []),
        "criticalFlags":     len((payload.get("lab_case", {}) or {}).get("critical_flags", []) or []),
    }
    doc = PatientCase(
        id=str(payload["patient_uuid"]),
        person_id=int(payload.get("person_id", 0)),
        cutoff_date=datetime.fromisoformat(str(payload.get("cutoff_date", "1970-01-01"))[:10]),
        case_type=str(payload.get("case_type", "ehr+lab")),
        demographics=payload.get("demographics", {}),
        conditions=payload.get("conditions", {}),
        medications=payload.get("medications", {}),
        visits=payload.get("visits", []),
        comorbidity=payload.get("comorbidity", {}),
        risk_scores=payload.get("risk_scores", {}),
        labs=payload.get("lab_case", {}),
        ground_truth=payload.get("ground_truth", {}),
        case_stats=case_stats,
        assembled_at=datetime.utcnow(),
        pipeline_version="gold-3.4",
    )
    await PatientCase.find_one(PatientCase.id == doc.id).upsert(
        {"$set": doc.model_dump(by_alias=True, exclude={"_id"})},
        on_insert=doc,
    )


if __name__ == "__main__":
    main()
