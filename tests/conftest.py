# tests/conftest.py
"""Root-level pytest configuration and shared fixtures."""

import json
import pytest
import duckdb
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "data" / "clinical.duckdb"
GOLD_DIR = PROJECT_ROOT / "data" / "gold" / "patient_cases"
RADIOLOGY_DIR = PROJECT_ROOT / "data" / "gold" / "radiology_reports"
RADIOLOGY_EVAL_DIR = PROJECT_ROOT / "data" / "gold" / "radiology_evaluations"
COHORT_FILE = PROJECT_ROOT / "data" / "gold" / "cohort_verified.json"


@pytest.fixture(scope="session")
def db():
    """Connect to the DuckDB database (read-only)."""
    con = duckdb.connect(str(DB_PATH), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def cohort_uuids():
    """Load the 1K cohort patient UUIDs."""
    with open(COHORT_FILE) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_patient_uuid():
    """Return one patient UUID from the cohort for spot-checks."""
    with open(COHORT_FILE) as f:
        uuids = json.load(f)
    return uuids[0]


@pytest.fixture(scope="session")
def sample_ehr_case(sample_patient_uuid):
    """Load a sample ehr_case.json."""
    path = GOLD_DIR / sample_patient_uuid / "ehr_case.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_lab_case(sample_patient_uuid):
    """Load a sample lab_case.json."""
    path = GOLD_DIR / sample_patient_uuid / "lab_case.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_ground_truth(sample_patient_uuid):
    """Load a sample ground_truth.json."""
    path = GOLD_DIR / sample_patient_uuid / "ground_truth.json"
    with open(path) as f:
        return json.load(f)
