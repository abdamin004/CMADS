# tests/conftest.py
"""Root-level pytest configuration and shared fixtures."""

import json
import pytest
import duckdb

from src.config import cfg


@pytest.fixture(scope="session")
def db():
    """Connect to the DuckDB database (read-only)."""
    con = duckdb.connect(str(cfg.DUCKDB_PATH), read_only=True)
    yield con
    con.close()


@pytest.fixture(scope="session")
def cohort_uuids():
    """Load the verified cohort patient UUIDs."""
    cohort_file = cfg.GOLD_DIR.parent / "cohort_verified.json"
    with open(cohort_file) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_patient_uuid(cohort_uuids):
    """Return one patient UUID from the cohort for spot-checks."""
    return cohort_uuids[0]


@pytest.fixture(scope="session")
def sample_ehr_case(sample_patient_uuid):
    """Load a sample ehr_case.json."""
    path = cfg.GOLD_DIR / sample_patient_uuid / "ehr_case.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_lab_case(sample_patient_uuid):
    """Load a sample lab_case.json."""
    path = cfg.GOLD_DIR / sample_patient_uuid / "lab_case.json"
    with open(path) as f:
        return json.load(f)


@pytest.fixture(scope="session")
def sample_ground_truth(sample_patient_uuid):
    """Load a sample ground_truth.json."""
    path = cfg.GOLD_DIR / sample_patient_uuid / "ground_truth.json"
    with open(path) as f:
        return json.load(f)
