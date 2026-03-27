"""Silver Layer — Bronze Synthea → OMOP CDM v5.4 tables in DuckDB.

Transforms Bronze-layer Synthea tables into 6 standardized OMOP CDM tables:
  person, visit_occurrence, condition_occurrence,
  measurement, drug_exposure, observation

Reads from data/bronze/ Parquet, writes to data/silver/ Parquet,
and loads into clinical.duckdb.

Usage:
    python3 pipeline/silver.py
    python3 pipeline/silver.py --validate-only
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import duckdb

BRONZE_DIR = Path("data/bronze")
SILVER_DIR = Path("data/silver")
DB_PATH = Path("data/clinical.duckdb")

# ── OMOP Concept ID Mappings ────────────────────────────────────────────
# Synthea uses standard vocabularies (SNOMED, LOINC, RxNorm).
# These static mappings cover the categorical fields that need concept_ids.

GENDER_CONCEPTS = {
    "M": 8507,
    "F": 8532,
}

RACE_CONCEPTS = {
    "white": 8527,
    "black": 8516,
    "asian": 8515,
    "native": 8657,
    "hawaiian": 8557,
    "other": 8522,
}

ETHNICITY_CONCEPTS = {
    "hispanic": 38003563,
    "nonhispanic": 38003564,
}

VISIT_CONCEPTS = {
    "ambulatory": 9202,
    "outpatient": 9202,
    "wellness": 9202,
    "inpatient": 9201,
    "emergency": 9203,
    "urgentcare": 9203,
    "virtual": 581399,
    "snf": 8717,
    "hospice": 8546,
    "home": 581476,
}

# OMOP condition type: EHR diagnosis
CONDITION_TYPE_CONCEPT = 32817
# OMOP measurement type: from EHR
MEASUREMENT_TYPE_CONCEPT = 32817
# OMOP drug type: prescription written
DRUG_TYPE_CONCEPT = 32838
# OMOP observation type: from EHR
OBSERVATION_TYPE_CONCEPT = 32817


# ── SQL Transformations ─────────────────────────────────────────────────

PERSON_SQL = """
CREATE TABLE silver_person AS
SELECT
    ROW_NUMBER() OVER (ORDER BY Id) AS person_id,
    Id AS person_source_value,
    CASE GENDER
        WHEN 'M' THEN 8507
        WHEN 'F' THEN 8532
        ELSE 0
    END AS gender_concept_id,
    GENDER AS gender_source_value,
    YEAR(BIRTHDATE) AS year_of_birth,
    MONTH(BIRTHDATE) AS month_of_birth,
    DAY(BIRTHDATE) AS day_of_birth,
    BIRTHDATE AS birth_datetime,
    CASE LOWER(RACE)
        WHEN 'white' THEN 8527
        WHEN 'black' THEN 8516
        WHEN 'asian' THEN 8515
        WHEN 'native' THEN 8657
        WHEN 'hawaiian' THEN 8557
        ELSE 8522
    END AS race_concept_id,
    RACE AS race_source_value,
    CASE LOWER(ETHNICITY)
        WHEN 'hispanic' THEN 38003563
        WHEN 'nonhispanic' THEN 38003564
        ELSE 0
    END AS ethnicity_concept_id,
    ETHNICITY AS ethnicity_source_value,
    DEATHDATE AS death_datetime,
    CITY AS city,
    STATE AS state,
    ZIP AS zip,
    COUNTY AS county
FROM read_parquet('{bronze_dir}/patients/*.parquet')
"""

VISIT_OCCURRENCE_SQL = """
CREATE TABLE silver_visit_occurrence AS
SELECT
    ROW_NUMBER() OVER (ORDER BY Id) AS visit_occurrence_id,
    p.person_id,
    CASE LOWER(e.ENCOUNTERCLASS)
        WHEN 'ambulatory' THEN 9202
        WHEN 'outpatient' THEN 9202
        WHEN 'wellness' THEN 9202
        WHEN 'inpatient' THEN 9201
        WHEN 'emergency' THEN 9203
        WHEN 'urgentcare' THEN 9203
        WHEN 'virtual' THEN 581399
        WHEN 'snf' THEN 8717
        WHEN 'hospice' THEN 8546
        WHEN 'home' THEN 581476
        ELSE 0
    END AS visit_concept_id,
    e.ENCOUNTERCLASS AS visit_source_value,
    CAST(e.START AS DATE) AS visit_start_date,
    e.START AS visit_start_datetime,
    CAST(e.STOP AS DATE) AS visit_end_date,
    e.STOP AS visit_end_datetime,
    32817 AS visit_type_concept_id,
    e.Id AS visit_source_id,
    e.ORGANIZATION AS care_site_source_value,
    e.PROVIDER AS provider_source_value,
    e.CODE AS visit_source_code,
    e.DESCRIPTION AS visit_description,
    e.BASE_ENCOUNTER_COST AS cost,
    e.TOTAL_CLAIM_COST AS total_cost,
    e.PAYER_COVERAGE AS payer_coverage,
    e.REASONCODE AS reason_source_code,
    e.REASONDESCRIPTION AS reason_source_description
FROM read_parquet('{bronze_dir}/encounters/*.parquet') e
JOIN silver_person p ON e.PATIENT = p.person_source_value
"""

CONDITION_OCCURRENCE_SQL = """
CREATE TABLE silver_condition_occurrence AS
SELECT
    ROW_NUMBER() OVER (ORDER BY c.PATIENT, c.START) AS condition_occurrence_id,
    p.person_id,
    TRY_CAST(c.CODE AS BIGINT) AS condition_concept_id,
    c.START AS condition_start_date,
    c.START AS condition_start_datetime,
    c.STOP AS condition_end_date,
    c.STOP AS condition_end_datetime,
    {condition_type} AS condition_type_concept_id,
    c.DESCRIPTION AS condition_source_value,
    c.CODE AS condition_source_code,
    c.SYSTEM AS vocabulary_id,
    v.visit_occurrence_id,
    v.visit_source_id AS encounter_source_value
FROM read_parquet('{bronze_dir}/conditions/*.parquet') c
JOIN silver_person p ON c.PATIENT = p.person_source_value
LEFT JOIN silver_visit_occurrence v ON c.ENCOUNTER = v.visit_source_id
"""

MEASUREMENT_SQL = """
CREATE TABLE silver_measurement AS
SELECT
    ROW_NUMBER() OVER (ORDER BY o.PATIENT, o.DATE) AS measurement_id,
    p.person_id,
    TRY_CAST(o.CODE AS BIGINT) AS measurement_concept_id,
    CAST(o.DATE AS DATE) AS measurement_date,
    o.DATE AS measurement_datetime,
    {measurement_type} AS measurement_type_concept_id,
    TRY_CAST(o.VALUE AS DOUBLE) AS value_as_number,
    CASE WHEN TRY_CAST(o.VALUE AS DOUBLE) IS NULL
         THEN o.VALUE
         ELSE NULL
    END AS value_as_string,
    o.UNITS AS unit_source_value,
    o.CODE AS measurement_source_code,
    o.DESCRIPTION AS measurement_source_value,
    o.CATEGORY AS category,
    v.visit_occurrence_id,
    v.visit_source_id AS encounter_source_value
FROM read_parquet('{bronze_dir}/observations/*.parquet') o
JOIN silver_person p ON o.PATIENT = p.person_source_value
LEFT JOIN silver_visit_occurrence v ON o.ENCOUNTER = v.visit_source_id
WHERE o.CATEGORY IN ('laboratory', 'vital-signs')
"""

DRUG_EXPOSURE_SQL = """
CREATE TABLE silver_drug_exposure AS
SELECT
    ROW_NUMBER() OVER (ORDER BY m.PATIENT, m.START) AS drug_exposure_id,
    p.person_id,
    TRY_CAST(m.CODE AS BIGINT) AS drug_concept_id,
    CAST(m.START AS DATE) AS drug_exposure_start_date,
    m.START AS drug_exposure_start_datetime,
    CAST(m.STOP AS DATE) AS drug_exposure_end_date,
    m.STOP AS drug_exposure_end_datetime,
    {drug_type} AS drug_type_concept_id,
    m.DESCRIPTION AS drug_source_value,
    m.CODE AS drug_source_code,
    m.DISPENSES AS quantity,
    m.BASE_COST AS cost,
    m.TOTALCOST AS total_cost,
    m.REASONCODE AS reason_source_code,
    m.REASONDESCRIPTION AS reason_source_value,
    v.visit_occurrence_id,
    v.visit_source_id AS encounter_source_value
FROM read_parquet('{bronze_dir}/medications/*.parquet') m
JOIN silver_person p ON m.PATIENT = p.person_source_value
LEFT JOIN silver_visit_occurrence v ON m.ENCOUNTER = v.visit_source_id
"""

OBSERVATION_SQL = """
CREATE TABLE silver_observation AS
SELECT
    ROW_NUMBER() OVER (ORDER BY o.PATIENT, o.DATE) AS observation_id,
    p.person_id,
    TRY_CAST(o.CODE AS BIGINT) AS observation_concept_id,
    CAST(o.DATE AS DATE) AS observation_date,
    o.DATE AS observation_datetime,
    {observation_type} AS observation_type_concept_id,
    TRY_CAST(o.VALUE AS DOUBLE) AS value_as_number,
    CASE WHEN TRY_CAST(o.VALUE AS DOUBLE) IS NULL
         THEN o.VALUE
         ELSE NULL
    END AS value_as_string,
    o.UNITS AS unit_source_value,
    o.CODE AS observation_source_code,
    o.DESCRIPTION AS observation_source_value,
    o.CATEGORY AS category,
    v.visit_occurrence_id,
    v.visit_source_id AS encounter_source_value
FROM read_parquet('{bronze_dir}/observations/*.parquet') o
JOIN silver_person p ON o.PATIENT = p.person_source_value
LEFT JOIN silver_visit_occurrence v ON o.ENCOUNTER = v.visit_source_id
WHERE o.CATEGORY NOT IN ('laboratory', 'vital-signs')
"""

# Order matters — person and visit must be created before tables that reference them
SILVER_TABLES = [
    ("person", PERSON_SQL),
    ("visit_occurrence", VISIT_OCCURRENCE_SQL),
    ("condition_occurrence", CONDITION_OCCURRENCE_SQL),
    ("measurement", MEASUREMENT_SQL),
    ("drug_exposure", DRUG_EXPOSURE_SQL),
    ("observation", OBSERVATION_SQL),
]


def run_validations(con):
    """Run data quality checks on Silver tables."""
    print(f"\n{'─' * 60}")
    print("DATA QUALITY CHECKS")
    print(f"{'─' * 60}")
    issues = []

    # 1. No patient loss: Bronze patients = Silver persons
    bronze_count = con.execute(
        f"SELECT COUNT(*) FROM read_parquet('{BRONZE_DIR}/patients/*.parquet')"
    ).fetchone()[0]
    silver_count = con.execute("SELECT COUNT(*) FROM silver_person").fetchone()[0]
    status = "PASS" if bronze_count == silver_count else "FAIL"
    print(f"  [{status}] Patient count: Bronze={bronze_count:,} Silver={silver_count:,}")
    if status == "FAIL":
        issues.append(f"Patient loss: {bronze_count - silver_count:,} patients missing")

    # 2. No unmapped gender
    unmapped = con.execute(
        "SELECT COUNT(*) FROM silver_person WHERE gender_concept_id = 0"
    ).fetchone()[0]
    status = "PASS" if unmapped == 0 else "WARN"
    print(f"  [{status}] Unmapped gender: {unmapped:,}")

    # 3. No unmapped visit types
    unmapped = con.execute(
        "SELECT COUNT(*) FROM silver_visit_occurrence WHERE visit_concept_id = 0"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM silver_visit_occurrence").fetchone()[0]
    pct = (unmapped / total * 100) if total > 0 else 0
    status = "PASS" if pct < 5 else "WARN"
    print(f"  [{status}] Unmapped visit types: {unmapped:,} ({pct:.1f}%)")

    # 4. Condition concept_id parse rate
    null_concepts = con.execute(
        "SELECT COUNT(*) FROM silver_condition_occurrence WHERE condition_concept_id IS NULL"
    ).fetchone()[0]
    total = con.execute("SELECT COUNT(*) FROM silver_condition_occurrence").fetchone()[0]
    pct = (null_concepts / total * 100) if total > 0 else 0
    status = "PASS" if pct < 5 else "WARN"
    print(f"  [{status}] Conditions with NULL concept_id: {null_concepts:,} ({pct:.1f}%)")

    # 5. Measurement numeric parse rate
    total_meas = con.execute("SELECT COUNT(*) FROM silver_measurement").fetchone()[0]
    numeric = con.execute(
        "SELECT COUNT(*) FROM silver_measurement WHERE value_as_number IS NOT NULL"
    ).fetchone()[0]
    pct = (numeric / total_meas * 100) if total_meas > 0 else 0
    print(f"  [INFO] Measurements with numeric value: {numeric:,}/{total_meas:,} ({pct:.1f}%)")

    # 6. Referential integrity: conditions → person
    orphans = con.execute("""
        SELECT COUNT(*) FROM silver_condition_occurrence c
        WHERE c.person_id NOT IN (SELECT person_id FROM silver_person)
    """).fetchone()[0]
    status = "PASS" if orphans == 0 else "FAIL"
    print(f"  [{status}] Orphan conditions (no matching person): {orphans:,}")

    # 7. Referential integrity: measurements → person
    orphans = con.execute("""
        SELECT COUNT(*) FROM silver_measurement m
        WHERE m.person_id NOT IN (SELECT person_id FROM silver_person)
    """).fetchone()[0]
    status = "PASS" if orphans == 0 else "FAIL"
    print(f"  [{status}] Orphan measurements (no matching person): {orphans:,}")

    return issues


def export_to_parquet(con, table_name, silver_dir):
    """Export a Silver table to Parquet."""
    out_dir = silver_dir / table_name
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "data.parquet"

    con.execute(f"""
        COPY (SELECT * FROM silver_{table_name})
        TO '{out_path}' (FORMAT PARQUET, COMPRESSION ZSTD, COMPRESSION_LEVEL 3)
    """)

    size_mb = out_path.stat().st_size / 1024 / 1024
    return size_mb


def save_to_duckdb(con):
    """Copy Silver tables from in-memory to persistent DuckDB."""
    print(f"\nSaving Silver → DuckDB ({DB_PATH})...")
    db_con = duckdb.connect(str(DB_PATH))

    for table_name, _ in SILVER_TABLES:
        full_name = f"silver_{table_name}"

        # Export to parquet as intermediate, then load
        tmp_path = SILVER_DIR / table_name / "data.parquet"
        if tmp_path.exists():
            db_con.execute(f"DROP TABLE IF EXISTS {full_name}")
            db_con.execute(
                f"CREATE TABLE {full_name} AS SELECT * FROM read_parquet('{tmp_path}')"
            )
            count = db_con.execute(f"SELECT COUNT(*) FROM {full_name}").fetchone()[0]
            print(f"  {full_name:<35} {count:>12,} rows")

    db_con.close()
    print(f"Database saved to: {DB_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Silver layer: Bronze → OMOP CDM v5.4")
    parser.add_argument("--validate-only", action="store_true", help="Run validations only")
    parser.add_argument("--bronze-dir", default=str(BRONZE_DIR), help="Bronze input directory")
    parser.add_argument("--silver-dir", default=str(SILVER_DIR), help="Silver output directory")
    args = parser.parse_args()

    bronze_dir = Path(args.bronze_dir)
    silver_dir = Path(args.silver_dir)

    if not bronze_dir.exists():
        print(f"Bronze directory not found: {bronze_dir}")
        print("Run: python3 pipeline/bronze.py batch_10k")
        sys.exit(1)

    silver_dir.mkdir(parents=True, exist_ok=True)

    print(f"Silver layer: OMOP CDM v5.4")
    print(f"Bronze source: {bronze_dir}")
    print(f"Silver output: {silver_dir}\n")

    con = duckdb.connect(":memory:")

    # ── Build Silver tables ──
    results = []
    for table_name, sql_template in SILVER_TABLES:
        print(f"  {table_name:<30}", end="", flush=True)

        sql = sql_template.format(
            bronze_dir=bronze_dir,
            condition_type=CONDITION_TYPE_CONCEPT,
            measurement_type=MEASUREMENT_TYPE_CONCEPT,
            drug_type=DRUG_TYPE_CONCEPT,
            observation_type=OBSERVATION_TYPE_CONCEPT,
        )

        try:
            con.execute(f"DROP TABLE IF EXISTS silver_{table_name}")
            con.execute(sql)
            row_count = con.execute(
                f"SELECT COUNT(*) FROM silver_{table_name}"
            ).fetchone()[0]

            if not args.validate_only:
                size_mb = export_to_parquet(con, table_name, silver_dir)
                print(f"[ok] {row_count:>12,} rows  → {size_mb:>7.1f} MB")
                results.append({"table": table_name, "rows": row_count, "size_mb": size_mb})
            else:
                print(f"[ok] {row_count:>12,} rows")
                results.append({"table": table_name, "rows": row_count, "size_mb": 0})

        except Exception as e:
            print(f"[ERROR] {e}")
            results.append({"table": table_name, "rows": 0, "size_mb": 0})

    # ── Summary ──
    print(f"\n{'=' * 60}")
    print(f"SILVER LAYER SUMMARY — OMOP CDM v5.4")
    print(f"{'=' * 60}")

    total_rows = sum(r["rows"] for r in results)
    total_size = sum(r["size_mb"] for r in results)

    print(f"\n  {'OMOP Table':<30} {'Rows':>12} {'Size':>10}")
    print(f"  {'─' * 55}")
    for r in results:
        size_str = f"{r['size_mb']:.1f} MB" if r['size_mb'] > 0 else "—"
        print(f"  {r['table']:<30} {r['rows']:>12,} {size_str:>10}")
    print(f"  {'─' * 55}")
    print(f"  {'TOTAL':<30} {total_rows:>12,} {total_size:>9.1f} MB")

    # ── Validations ──
    validation_issues = run_validations(con)

    con.close()

    # ── Save to DuckDB ──
    if not args.validate_only:
        save_to_duckdb(con=None)

    print(f"\n  Output: {silver_dir}/")


if __name__ == "__main__":
    main()
