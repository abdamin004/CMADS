"""Synthetic Radiology Report Generator

Reads Synthea imaging metadata + ground truth disease context,
sends to GPT-o3 120B via Ollama to generate realistic radiology
reports with findings (no explicit diagnosis).

Usage:
    python pipeline/generate_radiology_reports.py
    python pipeline/generate_radiology_reports.py --patient <PATIENT_ID>
    python pipeline/generate_radiology_reports.py --limit 5
"""

import argparse
import json
import time
from datetime import datetime
from pathlib import Path

import duckdb
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "gpt-oss:120b"
CSV_DIR = Path("data/raw/batch_test/csv")
OUTPUT_DIR = Path("data/gold/radiology_reports")

SYSTEM_PROMPT = """You are an experienced radiologist writing a structured radiology report.

RULES:
1. Describe imaging findings consistent with the patient's known condition
2. NEVER state the diagnosis or use the disease name in the report
3. Use standard radiology report structure: TECHNIQUE, FINDINGS, IMPRESSION
4. Use appropriate radiological terminology
5. Include measurements where clinically appropriate
6. Include incidental findings where relevant for the patient's age and history
7. End the impression with "Clinical correlation recommended."
8. If lab values are provided, reference relevant ones in your findings where appropriate
9. Keep the report concise and professional — similar in length to a real radiology report
10. Output ONLY the report text, no preamble or explanation"""


def get_db_connection():
    """Create in-memory DuckDB with Synthea CSVs loaded."""
    con = duckdb.connect(":memory:")
    tables = [
        "imaging_studies", "encounters", "conditions",
        "patients", "observations", "medications",
    ]
    for t in tables:
        csv_path = CSV_DIR / f"{t}.csv"
        if csv_path.exists():
            con.execute(
                f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{csv_path}', all_varchar=true)"
            )
    return con


def get_imaging_cases(con, patient_id=None, limit=None):
    """Get unique imaging cases with ground truth context.

    Returns one case per patient + disease + modality combination
    (uses the most recent scan for each combo).
    """
    where = ""
    if patient_id:
        where = f"AND i.PATIENT = '{patient_id}'"

    limit_clause = f"LIMIT {limit}" if limit else ""

    return con.execute(f"""
        WITH ranked AS (
            SELECT
                i.PATIENT,
                i.Id AS imaging_id,
                SUBSTRING(i.DATE, 1, 10) AS scan_date,
                i.MODALITY_CODE,
                i.MODALITY_DESCRIPTION,
                i.BODYSITE_DESCRIPTION,
                i.SOP_DESCRIPTION,
                i.ENCOUNTER,
                e.ENCOUNTERCLASS,
                e.REASONCODE AS ground_truth_code,
                e.REASONDESCRIPTION AS ground_truth_disease,
                p.FIRST || ' ' || p.LAST AS patient_name,
                p.BIRTHDATE,
                p.GENDER,
                p.DEATHDATE,
                ROW_NUMBER() OVER (
                    PARTITION BY i.PATIENT, e.REASONCODE, i.MODALITY_CODE
                    ORDER BY i.DATE DESC
                ) AS rn
            FROM imaging_studies i
            JOIN encounters e ON i.ENCOUNTER = e.Id
            JOIN patients p ON i.PATIENT = p.Id
            WHERE e.REASONDESCRIPTION IS NOT NULL
              AND e.REASONDESCRIPTION != ''
              {where}
        )
        SELECT *
        FROM ranked
        WHERE rn = 1
        ORDER BY patient_name, scan_date
        {limit_clause}
    """).fetchall()


def get_patient_conditions(con, patient_id, scan_date, exclude_code):
    """Get active conditions at time of scan, excluding ground truth."""
    rows = con.execute(f"""
        SELECT DESCRIPTION
        FROM conditions
        WHERE PATIENT = '{patient_id}'
          AND START <= '{scan_date}'
          AND (STOP IS NULL OR STOP = '' OR STOP >= '{scan_date}')
          AND CODE != '{exclude_code}'
          AND DESCRIPTION NOT LIKE '%finding%'
          AND DESCRIPTION NOT LIKE '%employment%'
          AND DESCRIPTION NOT LIKE '%education%'
          AND DESCRIPTION NOT LIKE '%housing%'
          AND DESCRIPTION NOT LIKE '%social%'
          AND DESCRIPTION NOT LIKE '%Body mass%'
          AND DESCRIPTION NOT LIKE '%military%'
          AND DESCRIPTION NOT LIKE '%Medication review%'
        ORDER BY START
    """).fetchall()
    return [r[0] for r in rows]


def get_encounter_observations(con, encounter_id):
    """Get observations from the imaging encounter."""
    rows = con.execute(f"""
        SELECT DESCRIPTION, VALUE, UNITS, CATEGORY
        FROM observations
        WHERE ENCOUNTER = '{encounter_id}'
          AND CATEGORY IN ('laboratory', 'vital-signs', 'exam')
        ORDER BY CATEGORY, DESCRIPTION
    """).fetchall()
    return [
        {"test": r[0], "value": r[1], "units": r[2] or "", "category": r[3]}
        for r in rows
    ]


def calculate_age(birthdate, scan_date):
    """Calculate age at time of scan."""
    birth = datetime.strptime(birthdate, "%Y-%m-%d")
    scan = datetime.strptime(scan_date, "%Y-%m-%d")
    return scan.year - birth.year - ((scan.month, scan.day) < (birth.month, birth.day))


def build_prompt(case, conditions, observations):
    """Build the generation prompt for one imaging case."""
    age = calculate_age(case["birthdate"], case["scan_date"])
    gender = "Male" if case["gender"] == "M" else "Female"

    conditions_text = "\n".join(f"  - {c}" for c in conditions) if conditions else "  None documented"

    obs_text = ""
    if observations:
        obs_text = "\nRelevant lab values and vitals from same visit:\n"
        for o in observations:
            obs_text += f"  - {o['test']}: {o['value']} {o['units']}\n"

    prompt = f"""Generate a radiology report for the following study:

Study: {case['modality']} of {case['body_site']}
Clinical setting: {case['encounter_class']}
Patient: {age}-year-old {gender}

Active medical history (do NOT add these as diagnoses, use only for clinical context):
{conditions_text}
{obs_text}
The patient has been diagnosed with: {case['ground_truth_disease']}

Write a realistic radiology report with findings consistent with this condition.
Do NOT name the diagnosis anywhere in the report."""

    return prompt


def call_ollama(prompt, system=SYSTEM_PROMPT):
    """Send prompt to Ollama and return generated text."""
    payload = {
        "model": MODEL,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 1024,
        },
    }

    resp = requests.post(OLLAMA_URL, json=payload, timeout=300)
    resp.raise_for_status()
    return resp.json()


def generate_report(con, case_row):
    """Generate a radiology report for one imaging case."""
    case = {
        "patient_id": case_row[0],
        "imaging_id": case_row[1],
        "scan_date": case_row[2],
        "modality_code": case_row[3],
        "modality": case_row[4],
        "body_site": case_row[5],
        "sop": case_row[6],
        "encounter_id": case_row[7],
        "encounter_class": case_row[8],
        "ground_truth_code": case_row[9],
        "ground_truth_disease": case_row[10],
        "patient_name": case_row[11],
        "birthdate": case_row[12],
        "gender": case_row[13],
        "deathdate": case_row[14],
    }

    conditions = get_patient_conditions(
        con, case["patient_id"], case["scan_date"], case["ground_truth_code"]
    )
    observations = get_encounter_observations(con, case["encounter_id"])
    prompt = build_prompt(case, conditions, observations)

    print(f"\n  Calling {MODEL}...", end=" ", flush=True)
    start = time.time()
    response = call_ollama(prompt)
    duration = time.time() - start

    report_text = response.get("response", "").strip()
    tokens = response.get("eval_count", 0)
    print(f"done ({duration:.1f}s, {tokens} tokens)")

    return {
        "patient_id": case["patient_id"],
        "patient_name": case["patient_name"],
        "imaging_study_id": case["imaging_id"],
        "scan_date": case["scan_date"],
        "modality_code": case["modality_code"],
        "modality": case["modality"],
        "body_site": case["body_site"],
        "encounter_class": case["encounter_class"],
        "report": report_text,
        "generation_metadata": {
            "model": MODEL,
            "temperature": 0.7,
            "ground_truth_disease": case["ground_truth_disease"],
            "ground_truth_code": case["ground_truth_code"],
            "active_conditions": conditions,
            "observations_used": len(observations),
            "duration_s": round(duration, 1),
            "tokens_generated": tokens,
            "generated_at": datetime.now().isoformat(),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic radiology reports")
    parser.add_argument("--patient", help="Generate for a specific patient ID")
    parser.add_argument("--limit", type=int, help="Max number of reports to generate")
    parser.add_argument("--output", default=str(OUTPUT_DIR), help="Output directory")
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Loading Synthea data...")
    con = get_db_connection()

    print("Finding imaging cases...")
    cases = get_imaging_cases(con, patient_id=args.patient, limit=args.limit)
    print(f"Found {len(cases)} unique imaging cases to process")

    reports = []
    for i, case_row in enumerate(cases):
        patient_name = case_row[11]
        modality = case_row[4]
        body_site = case_row[5]
        disease = case_row[10]
        print(f"\n[{i+1}/{len(cases)}] {patient_name}: {modality} of {body_site}")
        print(f"  Ground truth: {disease}")

        try:
            report = generate_report(con, case_row)
            reports.append(report)

            # Save individual report
            patient_id = case_row[0]
            modality_code = case_row[3]
            filename = f"{patient_id}_{modality_code}_{case_row[2]}.json"
            report_path = output_dir / filename
            report_path.write_text(json.dumps(report, indent=2))
            print(f"  Saved: {report_path}")

        except requests.exceptions.ConnectionError:
            print("  ERROR: Cannot connect to Ollama. Is it running? (ollama serve)")
            return
        except Exception as e:
            print(f"  ERROR: {e}")
            continue

    # Save all reports as a single file too
    if reports:
        all_path = output_dir / "all_reports.json"
        all_path.write_text(json.dumps(reports, indent=2))
        print(f"\n{'='*60}")
        print(f"Generated {len(reports)} reports")
        print(f"Individual reports: {output_dir}/")
        print(f"Combined file: {all_path}")

    con.close()


if __name__ == "__main__":
    main()
