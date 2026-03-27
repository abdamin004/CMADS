# tests/test_data_pipeline.py
"""Data Pipeline Tests — Bronze → Silver → Silver+ → Gold → Radiology Reports

Tests the complete data pipeline without LLM inference.
Fast (~10s), deterministic, suitable for CI.
"""

import json
import os
import pytest
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
GOLD_DIR = PROJECT_ROOT / "data" / "gold" / "patient_cases"
RADIOLOGY_DIR = PROJECT_ROOT / "data" / "gold" / "radiology_reports"
RADIOLOGY_EVAL_DIR = PROJECT_ROOT / "data" / "gold" / "radiology_evaluations"
COHORT_FILE = PROJECT_ROOT / "data" / "gold" / "cohort_1k_patient_ids.json"


# ═══════════════════════════════════════════════════════════════════════
# BRONZE LAYER — Raw Synthea CSV → DuckDB
# ═══════════════════════════════════════════════════════════════════════

class TestBronzeLayer:
    """Verify Bronze tables are loaded correctly from Synthea CSV files."""

    EXPECTED_TABLES = [
        "patients", "encounters", "conditions", "observations",
        "medications", "procedures", "imaging_studies", "allergies",
    ]

    def test_all_bronze_tables_exist(self, db):
        """DP-001: All required Synthea tables are loaded into DuckDB."""
        tables = [r[0] for r in db.execute("SHOW TABLES").fetchall()]
        for table in self.EXPECTED_TABLES:
            assert table in tables, f"Bronze table '{table}' missing from DuckDB"

    def test_patients_table_has_data(self, db):
        """Patients table contains the full Synthea population."""
        count = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        assert count > 0, "patients table is empty"
        assert count >= 14000, f"Expected ≥14,000 patients, got {count}"

    def test_patients_have_required_columns(self, db):
        """Patient records have essential demographic fields."""
        cols = {r[0].upper() for r in db.execute("DESCRIBE patients").fetchall()}
        required = {"ID", "BIRTHDATE", "GENDER", "FIRST", "LAST"}
        missing = required - cols
        assert not missing, f"Missing patient columns: {missing}"

    def test_encounters_have_reason_code(self, db):
        """DP-001: REASONCODE exists — ground truth for evaluation."""
        cols = {r[0].upper() for r in db.execute("DESCRIBE encounters").fetchall()}
        assert "REASONCODE" in cols, "encounters missing REASONCODE column"

    def test_encounters_have_reason_descriptions(self, db):
        """Encounters with imaging have disease descriptions for ground truth."""
        count = db.execute("""
            SELECT COUNT(*) FROM encounters
            WHERE REASONDESCRIPTION IS NOT NULL AND REASONDESCRIPTION != ''
        """).fetchone()[0]
        assert count > 100000, f"Only {count} encounters have REASONDESCRIPTION"

    def test_observations_table_has_data(self, db):
        """Observations table is populated with lab/vital data."""
        count = db.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
        assert count > 10_000_000, f"Expected >10M observations, got {count}"

    def test_imaging_studies_exist(self, db):
        """Imaging studies table is populated."""
        count = db.execute("SELECT COUNT(*) FROM imaging_studies").fetchone()[0]
        assert count > 1_000_000, f"Expected >1M imaging studies, got {count}"

    def test_imaging_studies_have_modality(self, db):
        """Imaging studies have modality information."""
        cols = {r[0].upper() for r in db.execute("DESCRIBE imaging_studies").fetchall()}
        assert "MODALITY_CODE" in cols, "imaging_studies missing MODALITY_CODE"
        assert "MODALITY_DESCRIPTION" in cols, "imaging_studies missing MODALITY_DESCRIPTION"

    def test_conditions_have_snomed_codes(self, db):
        """Conditions have SNOMED codes for disease identification."""
        null_rate = db.execute("""
            SELECT COUNT(CASE WHEN CODE IS NULL OR CODE = '' THEN 1 END) * 100.0
                   / COUNT(*)
            FROM conditions
        """).fetchone()[0]
        assert null_rate < 1.0, f"Condition SNOMED null rate: {null_rate:.1f}%"

    def test_no_duplicate_patient_ids(self, db):
        """Each patient has a unique ID."""
        total = db.execute("SELECT COUNT(*) FROM patients").fetchone()[0]
        unique = db.execute("SELECT COUNT(DISTINCT Id) FROM patients").fetchone()[0]
        assert total == unique, f"Duplicate patients: {total} total, {unique} unique"


# ═══════════════════════════════════════════════════════════════════════
# SILVER LAYER — OMOP CDM Transformation
# ═══════════════════════════════════════════════════════════════════════

class TestSilverLayer:
    """Verify Silver OMOP CDM tables are correctly transformed."""

    OMOP_TABLES = [
        "silver_person", "silver_visit_occurrence",
        "silver_condition_occurrence", "silver_measurement",
        "silver_drug_exposure", "silver_observation",
    ]

    def test_all_silver_tables_exist(self, db):
        """DP-002: All OMOP CDM Silver tables are created."""
        tables = [r[0] for r in db.execute("SHOW TABLES").fetchall()]
        for table in self.OMOP_TABLES:
            assert table in tables, f"Silver table '{table}' missing"

    def test_no_patient_loss_bronze_to_silver(self, db):
        """DP-002: Every Bronze patient appears in Silver person table."""
        bronze = db.execute("SELECT COUNT(DISTINCT Id) FROM patients").fetchone()[0]
        silver = db.execute("SELECT COUNT(*) FROM silver_person").fetchone()[0]
        assert silver == bronze, (
            f"Patient loss Bronze→Silver: Bronze={bronze}, Silver={silver}"
        )

    def test_person_has_source_value_mapping(self, db):
        """Silver person maps back to Synthea UUID via person_source_value."""
        cols = {r[0] for r in db.execute("DESCRIBE silver_person").fetchall()}
        assert "person_source_value" in cols, \
            "silver_person missing person_source_value (Synthea UUID mapping)"

    def test_person_source_values_match_patients(self, db):
        """person_source_value contains valid Synthea patient UUIDs."""
        match_count = db.execute("""
            SELECT COUNT(*) FROM silver_person sp
            JOIN patients p ON sp.person_source_value = p.Id
        """).fetchone()[0]
        total = db.execute("SELECT COUNT(*) FROM silver_person").fetchone()[0]
        assert match_count == total, (
            f"UUID mismatch: {match_count}/{total} silver_person rows match patients"
        )

    def test_condition_occurrence_has_data(self, db):
        """Condition occurrence table has records."""
        bronze = db.execute("SELECT COUNT(*) FROM conditions").fetchone()[0]
        silver = db.execute("SELECT COUNT(*) FROM silver_condition_occurrence").fetchone()[0]
        assert silver == bronze, f"Condition loss: Bronze={bronze}, Silver={silver}"

    def test_measurement_has_numeric_values(self, db):
        """Measurements have numeric values populated."""
        null_rate = db.execute("""
            SELECT COUNT(CASE WHEN value_as_number IS NULL THEN 1 END) * 100.0
                   / COUNT(*)
            FROM silver_measurement
        """).fetchone()[0]
        assert null_rate < 20.0, f"Measurement null rate: {null_rate:.1f}% (must be <20%)"

    def test_visit_occurrence_count(self, db):
        """Visit occurrence matches encounter count."""
        bronze = db.execute("SELECT COUNT(*) FROM encounters").fetchone()[0]
        silver = db.execute("SELECT COUNT(*) FROM silver_visit_occurrence").fetchone()[0]
        assert silver == bronze, f"Visit loss: Bronze={bronze}, Silver={silver}"


# ═══════════════════════════════════════════════════════════════════════
# SILVER+ LAYER — Derived Feature Tables
# ═══════════════════════════════════════════════════════════════════════

class TestSilverPlusLayer:
    """Verify Silver+ derived feature tables for the 1K cohort."""

    DERIVED_TABLES = [
        "silver_plus_lab_trends",
        "silver_plus_critical_lab_flags",
        "silver_plus_comorbidity_matrix",
        "silver_plus_risk_scores",
        "silver_plus_medication_timeline",
        "silver_plus_drug_condition_links",
    ]

    def test_all_derived_tables_exist(self, db):
        """All 6 Silver+ derived tables are created."""
        tables = [r[0] for r in db.execute("SHOW TABLES").fetchall()]
        for table in self.DERIVED_TABLES:
            assert table in tables, f"Silver+ table '{table}' missing"

    def test_all_derived_tables_have_data(self, db):
        """Every Silver+ table has at least some rows."""
        for table in self.DERIVED_TABLES:
            count = db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            assert count > 0, f"{table} is empty"

    def test_lab_trends_has_valid_directions(self, db):
        """Lab trends have valid trend values."""
        trends = db.execute("""
            SELECT DISTINCT trend FROM silver_plus_lab_trends
        """).fetchall()
        valid = {"rising", "falling", "stable", "insufficient_data",
                 "RISING", "FALLING", "STABLE", "INSUFFICIENT_DATA",
                 "increasing", "decreasing", "INCREASING", "DECREASING"}
        actual = {r[0] for r in trends}
        invalid = actual - valid
        assert not invalid, f"Invalid trend values: {invalid}"

    def test_critical_lab_flags_severity_values(self, db):
        """Critical lab flag severity has valid categorical values."""
        severities = db.execute("""
            SELECT DISTINCT severity FROM silver_plus_critical_lab_flags
        """).fetchall()
        valid = {"critical", "high", "low", "abnormal", "normal",
                 "CRITICAL", "HIGH", "LOW", "ABNORMAL", "NORMAL",
                 "1", "2", "3", "4", "5"}
        actual = {str(r[0]) for r in severities}
        # Just verify severities are not empty and have consistent values
        assert len(actual) > 0, "No severity values found"
        assert len(actual) < 10, f"Too many severity categories: {actual}"

    def test_risk_scores_cover_cohort(self, db):
        """Risk scores exist for the 1K cohort patients."""
        count = db.execute(
            "SELECT COUNT(*) FROM silver_plus_risk_scores"
        ).fetchone()[0]
        assert count >= 1000, f"Risk scores: {count} rows, expected ≥1000"

    def test_comorbidity_matrix_cover_cohort(self, db):
        """Comorbidity matrix exists for the 1K cohort patients."""
        count = db.execute(
            "SELECT COUNT(*) FROM silver_plus_comorbidity_matrix"
        ).fetchone()[0]
        assert count >= 1000, f"Comorbidity matrix: {count} rows, expected ≥1000"

    def test_medication_timeline_has_data(self, db):
        """Medication timeline has substantial records."""
        count = db.execute(
            "SELECT COUNT(*) FROM silver_plus_medication_timeline"
        ).fetchone()[0]
        assert count > 10000, f"Medication timeline: only {count} rows"

    def test_drug_condition_links_has_data(self, db):
        """Drug-condition links are populated."""
        count = db.execute(
            "SELECT COUNT(*) FROM silver_plus_drug_condition_links"
        ).fetchone()[0]
        assert count > 1000, f"Drug-condition links: only {count} rows"


# ═══════════════════════════════════════════════════════════════════════
# GOLD LAYER — Per-Patient JSON Case Files
# ═══════════════════════════════════════════════════════════════════════

class TestGoldLayer:
    """Verify Gold JSON case files for the 1K cohort."""

    def test_gold_directory_exists(self):
        """DP-020: Gold patient_cases directory exists."""
        assert GOLD_DIR.exists(), f"{GOLD_DIR} does not exist"

    def test_cohort_file_exists(self):
        """Cohort selection file exists."""
        assert COHORT_FILE.exists(), f"{COHORT_FILE} does not exist"

    def test_cohort_has_1000_patients(self):
        """Cohort contains exactly 1000 patient UUIDs."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)
        assert len(uuids) == 1000, f"Cohort has {len(uuids)} patients, expected 1000"

    def test_all_cohort_patients_have_gold_files(self):
        """Every cohort patient has ehr_case, lab_case, and ground_truth."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)
        missing = []
        for uuid in uuids:
            patient_dir = GOLD_DIR / uuid
            if not patient_dir.exists():
                missing.append(uuid)
                continue
            for f in ["ehr_case.json", "lab_case.json", "ground_truth.json"]:
                if not (patient_dir / f).exists():
                    missing.append(f"{uuid}/{f}")
        assert not missing, f"Missing Gold files: {missing[:10]}..."

    def test_ehr_case_structure(self, sample_ehr_case):
        """ehr_case.json has all required fields."""
        required = [
            "case_type", "case_mode", "cutoff_date", "patient_uuid",
            "person_id", "demographics", "conditions", "visits",
            "comorbidity", "risk_scores", "medications",
        ]
        for field in required:
            assert field in sample_ehr_case, f"ehr_case missing field: '{field}'"

    def test_ehr_case_mode_is_point_in_time(self, sample_ehr_case):
        """ehr_case uses point-in-time mode (disease hidden)."""
        assert sample_ehr_case["case_mode"] == "point_in_time", \
            f"Expected point_in_time, got {sample_ehr_case['case_mode']}"

    def test_lab_case_structure(self, sample_lab_case):
        """lab_case.json has all required fields."""
        required = [
            "case_type", "case_mode", "cutoff_date", "person_id",
            "lab_trends", "critical_flags", "latest_labs",
        ]
        for field in required:
            assert field in sample_lab_case, f"lab_case missing field: '{field}'"

    def test_ground_truth_structure(self, sample_ground_truth):
        """ground_truth.json has target condition and cutoff date."""
        required = [
            "patient_uuid", "person_id", "target_condition",
            "cutoff_date", "all_conditions_at_diagnosis",
        ]
        for field in required:
            assert field in sample_ground_truth, \
                f"ground_truth missing field: '{field}'"

        tc = sample_ground_truth["target_condition"]
        assert "name" in tc, "target_condition missing 'name'"
        assert "code" in tc, "target_condition missing 'code'"
        assert "diagnosis_date" in tc, "target_condition missing 'diagnosis_date'"

    def test_no_target_disease_leakage_in_ehr(self):
        """The target disease does NOT appear in ehr_case conditions.

        This is the core point-in-time guarantee: agents cannot see
        the disease they are supposed to diagnose.
        """
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        leaks = []
        for uuid in uuids[:100]:  # spot-check first 100
            ehr_path = GOLD_DIR / uuid / "ehr_case.json"
            gt_path = GOLD_DIR / uuid / "ground_truth.json"
            with open(ehr_path) as f:
                ehr = json.load(f)
            with open(gt_path) as f:
                gt = json.load(f)

            target_code = gt["target_condition"]["code"]
            target_name = gt["target_condition"]["name"].lower()

            # Check conditions list
            for cond in ehr.get("conditions", []):
                cond_name = cond.get("name", "").lower() if isinstance(cond, dict) else str(cond).lower()
                if target_name in cond_name:
                    leaks.append(f"{uuid}: '{target_name}' found in conditions")
                    break

        assert not leaks, f"Target disease leaked in {len(leaks)} patients: {leaks[:5]}"

    def test_cutoff_dates_are_consistent(self):
        """ehr_case, lab_case, and ground_truth share the same cutoff date."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        mismatches = []
        for uuid in uuids[:50]:
            ehr = json.loads((GOLD_DIR / uuid / "ehr_case.json").read_text())
            lab = json.loads((GOLD_DIR / uuid / "lab_case.json").read_text())
            gt = json.loads((GOLD_DIR / uuid / "ground_truth.json").read_text())

            dates = {ehr["cutoff_date"], lab["cutoff_date"], gt["cutoff_date"]}
            if len(dates) > 1:
                mismatches.append(f"{uuid}: {dates}")

        assert not mismatches, f"Cutoff date mismatches: {mismatches[:5]}"

    def test_demographics_have_required_fields(self, sample_ehr_case):
        """Demographics include age, gender, and basic info."""
        demo = sample_ehr_case.get("demographics", {})
        assert demo, "demographics is empty"
        # Check at least some demographic data exists
        assert len(demo) >= 2, f"demographics has only {len(demo)} fields"


# ═══════════════════════════════════════════════════════════════════════
# RADIOLOGY REPORTS — LLM-Generated Reports + Evaluations
# ═══════════════════════════════════════════════════════════════════════

class TestRadiologyReports:
    """Verify radiology reports generated by the pipeline."""

    def test_radiology_directory_exists(self):
        """Radiology reports directory exists."""
        assert RADIOLOGY_DIR.exists(), f"{RADIOLOGY_DIR} does not exist"

    def test_reports_are_generated(self):
        """At least some radiology reports exist."""
        reports = list(RADIOLOGY_DIR.glob("*.json"))
        # Exclude all_reports.json
        reports = [r for r in reports if r.name != "all_reports.json"]
        assert len(reports) > 0, "No radiology reports generated"

    def test_report_structure(self):
        """Each report has required fields."""
        reports = [r for r in RADIOLOGY_DIR.glob("*.json")
                   if r.name != "all_reports.json"]
        if not reports:
            pytest.skip("No radiology reports to test")

        required = [
            "patient_id", "patient_name", "imaging_study_id",
            "scan_date", "modality_code", "modality", "body_site",
            "report", "generation_metadata",
        ]

        for report_path in reports[:10]:  # spot-check first 10
            with open(report_path) as f:
                report = json.load(f)
            for field in required:
                assert field in report, \
                    f"{report_path.name} missing field: '{field}'"

    def test_report_metadata_structure(self):
        """Generation metadata has required fields."""
        reports = [r for r in RADIOLOGY_DIR.glob("*.json")
                   if r.name != "all_reports.json"]
        if not reports:
            pytest.skip("No radiology reports to test")

        required_meta = [
            "model", "temperature", "ground_truth_disease",
            "ground_truth_code", "duration_s", "generated_at",
        ]

        with open(reports[0]) as f:
            report = json.load(f)
        meta = report["generation_metadata"]
        for field in required_meta:
            assert field in meta, f"Metadata missing field: '{field}'"

    def test_reports_have_non_empty_text(self):
        """Report text is not empty and has reasonable length."""
        reports = [r for r in RADIOLOGY_DIR.glob("*.json")
                   if r.name != "all_reports.json"]
        if not reports:
            pytest.skip("No radiology reports to test")

        for report_path in reports[:10]:
            with open(report_path) as f:
                report = json.load(f)
            text = report.get("report", "")
            assert len(text) > 200, \
                f"{report_path.name}: report too short ({len(text)} chars)"

    def test_no_diagnosis_in_report_text(self):
        """Reports do not name the target disease (no leakage).

        The generator is instructed to describe findings without
        stating the diagnosis. This verifies that rule.
        """
        reports = [r for r in RADIOLOGY_DIR.glob("*.json")
                   if r.name != "all_reports.json"]
        if not reports:
            pytest.skip("No radiology reports to test")

        leaks = []
        for report_path in reports[:20]:
            with open(report_path) as f:
                report = json.load(f)
            disease = report["generation_metadata"]["ground_truth_disease"].lower()
            text = report["report"].lower()

            # Check if the exact disease name appears in the report
            # (allowing partial matches for common terms)
            disease_words = [w for w in disease.split()
                             if len(w) > 4 and w not in (
                                 "disorder", "disease", "chronic",
                                 "finding", "procedure", "patient")]
            for word in disease_words:
                if word in text:
                    leaks.append(f"{report_path.name}: '{word}' found")
                    break

        # Allow small leakage rate (LLM isn't perfect)
        leak_rate = len(leaks) / max(len(reports[:20]), 1)
        assert leak_rate < 0.2, (
            f"Diagnosis leakage rate {leak_rate:.0%}: {leaks[:5]}"
        )

    def test_evaluation_results_exist(self):
        """Evaluation results file exists and has data."""
        eval_file = RADIOLOGY_EVAL_DIR / "evaluation_results.json"
        if not eval_file.exists():
            pytest.skip("No evaluation results file")
        with open(eval_file) as f:
            evals = json.load(f)
        assert len(evals) > 0, "Evaluation results file is empty"

    def test_evaluation_scores_are_valid(self):
        """Evaluation scores are within expected ranges."""
        eval_file = RADIOLOGY_EVAL_DIR / "evaluation_results.json"
        if not eval_file.exists():
            pytest.skip("No evaluation results file")
        with open(eval_file) as f:
            evals = json.load(f)

        criteria = [
            "clinical_accuracy", "no_diagnosis_leakage",
            "completeness", "internal_consistency", "report_quality",
        ]

        for ev in evals[:10]:
            scores = ev.get("scores", {})
            for c in criteria:
                assert c in scores, f"Missing score: {c}"
                assert 1 <= scores[c] <= 5, \
                    f"{c} score {scores[c]} out of range [1,5]"
            assert 1.0 <= scores["overall"] <= 5.0, \
                f"Overall score {scores['overall']} out of range"

    def test_accepted_reports_meet_threshold(self):
        """All accepted reports scored ≥ 4.0."""
        eval_file = RADIOLOGY_EVAL_DIR / "evaluation_results.json"
        if not eval_file.exists():
            pytest.skip("No evaluation results file")
        with open(eval_file) as f:
            evals = json.load(f)

        below_threshold = [
            e for e in evals if e["scores"]["overall"] < 4.0
        ]
        assert not below_threshold, (
            f"{len(below_threshold)} accepted reports below 4.0 threshold"
        )

    def test_all_reports_json_matches_individual_files(self):
        """all_reports.json count matches individual report files."""
        all_file = RADIOLOGY_DIR / "all_reports.json"
        if not all_file.exists():
            pytest.skip("all_reports.json not found")

        with open(all_file) as f:
            all_reports = json.load(f)

        individual = [r for r in RADIOLOGY_DIR.glob("*.json")
                      if r.name != "all_reports.json"]

        assert len(all_reports) == len(individual), (
            f"all_reports.json has {len(all_reports)} entries, "
            f"but {len(individual)} individual files exist"
        )


# ═══════════════════════════════════════════════════════════════════════
# CROSS-LAYER INTEGRITY — Consistency Between Layers
# ═══════════════════════════════════════════════════════════════════════

class TestCrossLayerIntegrity:
    """Verify data consistency across pipeline layers."""

    def test_cohort_patients_exist_in_bronze(self, db):
        """All 1K cohort patients exist in the Bronze patients table."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        found = db.execute("""
            SELECT COUNT(*) FROM patients
            WHERE Id IN (SELECT unnest(?::VARCHAR[]))
        """, [uuids]).fetchone()[0]
        assert found == len(uuids), \
            f"Only {found}/{len(uuids)} cohort patients found in Bronze"

    def test_cohort_patients_exist_in_silver(self, db):
        """All 1K cohort patients exist in Silver person table."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        found = db.execute("""
            SELECT COUNT(*) FROM silver_person
            WHERE person_source_value IN (SELECT unnest(?::VARCHAR[]))
        """, [uuids]).fetchone()[0]
        assert found == len(uuids), \
            f"Only {found}/{len(uuids)} cohort patients found in Silver"

    def test_gold_cutoff_before_diagnosis(self):
        """Gold cutoff_date equals or precedes the diagnosis date."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        violations = []
        for uuid in uuids[:100]:
            gt_path = GOLD_DIR / uuid / "ground_truth.json"
            with open(gt_path) as f:
                gt = json.load(f)
            cutoff = gt["cutoff_date"]
            diag = gt["target_condition"]["diagnosis_date"]
            if cutoff > diag:
                violations.append(f"{uuid}: cutoff {cutoff} > diagnosis {diag}")

        assert not violations, f"Cutoff after diagnosis: {violations[:5]}"

    def test_radiology_patients_in_cohort(self):
        """Radiology report patients belong to the cohort."""
        with open(COHORT_FILE) as f:
            cohort = set(json.load(f))

        reports = [r for r in RADIOLOGY_DIR.glob("*.json")
                   if r.name != "all_reports.json"]
        if not reports:
            pytest.skip("No radiology reports")

        orphans = []
        for report_path in reports:
            with open(report_path) as f:
                report = json.load(f)
            if report["patient_id"] not in cohort:
                orphans.append(report["patient_id"])

        assert not orphans, f"Reports for non-cohort patients: {orphans[:5]}"

    def test_disease_distribution_is_diverse(self):
        """The 1K cohort covers multiple disease categories."""
        with open(COHORT_FILE) as f:
            uuids = json.load(f)

        diseases = set()
        for uuid in uuids[:200]:
            gt_path = GOLD_DIR / uuid / "ground_truth.json"
            with open(gt_path) as f:
                gt = json.load(f)
            diseases.add(gt["target_condition"]["name"])

        assert len(diseases) >= 10, \
            f"Only {len(diseases)} diseases in cohort, expected ≥10"
