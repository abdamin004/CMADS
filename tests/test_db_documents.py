"""Unit tests for Beanie Document classes."""
import pytest
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_patient_case_roundtrip(mongo_db):
    """A PatientCase saved with all field types round-trips identically."""
    from src.db.documents import PatientCase

    doc = PatientCase(
        id="abc-123",
        person_id=4388,
        cutoff_date=datetime(2021, 10, 18),
        case_type="ehr+lab",
        demographics={"age": 62, "gender": "F", "race": "white"},
        conditions={"active": [{"name": "T2DM"}], "history": []},
        medications={"active": [{"medication": "metformin"}], "history": []},
        visits=[],
        comorbidity={"has_dm": True},
        risk_scores={"ascvd_10yr": 12.3},
        labs={"recent_vitals": [], "latest_labs": [], "critical_flags": []},
        ground_truth={"target_condition": {"name": "Diabetes mellitus type 2"}},
        case_stats={"activeConditions": 1, "activeMedications": 1, "labTrends": 0, "criticalFlags": 0},
        assembled_at=datetime.utcnow(),
        pipeline_version="gold-3.4",
    )
    await doc.insert()

    loaded = await PatientCase.get("abc-123")
    assert loaded is not None
    assert loaded.demographics["age"] == 62
    assert loaded.ground_truth["target_condition"]["name"] == "Diabetes mellitus type 2"
    assert loaded.case_stats["activeConditions"] == 1
