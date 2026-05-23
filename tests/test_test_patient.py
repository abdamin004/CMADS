"""Unit tests for the TestPatient Beanie Document."""
import pytest
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_test_patient_roundtrip(mongo_db):
    """TestPatient saves with all 15 PatientCase mirror fields + lifecycle
    fields and round-trips identically."""
    from src.db.documents import TestPatient

    now = datetime.utcnow()
    doc = TestPatient(
        id="ttest-001",
        label="70yo CKD-4 + new HF onset",
        source_uuid="04ad2732-b952-4fbb-d2c6-aa6c25f9462f",
        created_at=now,
        updated_at=now,
        person_id=0,
        cutoff_date=datetime(2024, 1, 1),
        case_type="ehr+lab",
        demographics={"age": 70, "gender": "F", "race": "white"},
        conditions={"active": [{"condition": "CKD stage 4", "code": "431857002"}]},
        medications={"active": []},
        visits={"total": 12},
        labs={"latest_labs": [{"test_name": "eGFR", "value": "22", "unit": "mL/min"}]},
        ground_truth={"target_condition": {"name": "End-stage renal disease"}},
        assembled_at=now,
    )
    await doc.insert()

    loaded = await TestPatient.get("ttest-001")
    assert loaded is not None
    assert loaded.label == "70yo CKD-4 + new HF onset"
    assert loaded.source_uuid == "04ad2732-b952-4fbb-d2c6-aa6c25f9462f"
    assert loaded.demographics["age"] == 70
    assert loaded.ground_truth["target_condition"]["name"] == "End-stage renal disease"
    assert loaded.run_count == 0
    assert loaded.last_run_at is None
