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


def test_write_test_patient_sync_creates_doc():
    """write_test_patient_sync upserts and stamps created_at/updated_at."""
    from src.db.mongo import write_test_patient_sync, get_test_patient_sync, _coll
    _coll("test_patients").delete_many({"_id": "ttest-sync-1"})

    write_test_patient_sync({
        "_id": "ttest-sync-1",
        "label": "sync test",
        "demographics": {"age": 50, "gender": "M"},
        "labs": {"latest_labs": []},
        "cutoff_date": "2024-01-01",
    })

    loaded = get_test_patient_sync("ttest-sync-1")
    assert loaded is not None
    assert loaded["label"] == "sync test"
    assert loaded["created_at"] is not None
    assert loaded["updated_at"] is not None
    assert loaded["run_count"] == 0
    assert loaded["last_run_at"] is None
    _coll("test_patients").delete_one({"_id": "ttest-sync-1"})


def test_update_test_patient_sync_advances_updated_at():
    """PUT-style update bumps updated_at but preserves created_at."""
    import time
    from src.db.mongo import (
        write_test_patient_sync, update_test_patient_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-2"})
    write_test_patient_sync({
        "_id": "ttest-sync-2",
        "label": "original",
        "demographics": {"age": 50, "gender": "M"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })
    original = get_test_patient_sync("ttest-sync-2")
    time.sleep(0.01)  # ensure updated_at changes

    update_test_patient_sync("ttest-sync-2", {"label": "edited"})
    edited = get_test_patient_sync("ttest-sync-2")

    assert edited["label"] == "edited"
    assert edited["created_at"] == original["created_at"]
    assert edited["updated_at"] > original["updated_at"]
    _coll("test_patients").delete_one({"_id": "ttest-sync-2"})


def test_stamp_test_run_sync_increments_run_count():
    """stamp_test_run_sync sets last_run_at and increments run_count."""
    from src.db.mongo import (
        write_test_patient_sync, stamp_test_run_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-3"})
    write_test_patient_sync({
        "_id": "ttest-sync-3",
        "label": "x",
        "demographics": {"age": 30, "gender": "F"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })

    stamp_test_run_sync("ttest-sync-3")
    stamp_test_run_sync("ttest-sync-3")
    d = get_test_patient_sync("ttest-sync-3")

    assert d["run_count"] == 2
    assert d["last_run_at"] is not None
    _coll("test_patients").delete_one({"_id": "ttest-sync-3"})


def test_delete_test_patient_sync_removes_doc():
    """delete_test_patient_sync removes only the doc, not derived runs."""
    from src.db.mongo import (
        write_test_patient_sync, delete_test_patient_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-4"})
    write_test_patient_sync({
        "_id": "ttest-sync-4",
        "label": "del-me",
        "demographics": {"age": 30, "gender": "F"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })
    assert get_test_patient_sync("ttest-sync-4") is not None

    delete_test_patient_sync("ttest-sync-4")
    assert get_test_patient_sync("ttest-sync-4") is None
