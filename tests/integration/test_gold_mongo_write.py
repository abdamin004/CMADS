"""Verify that pipeline/gold.py writes to PatientCase when USE_MONGO=true."""
import json, os
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_gold_writes_patient_case_to_mongo(mongo_db, monkeypatch, tmp_path):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import PatientCase
    from pipeline.gold import write_patient_case_to_mongo

    payload = {
        "patient_uuid": "uuid-z",
        "person_id": 99,
        "cutoff_date": "2020-01-01",
        "case_type": "ehr+lab",
        "demographics": {"age": 50},
        "conditions": {"active": [], "history": []},
        "medications": {"active": [], "history": []},
        "visits": [], "comorbidity": {}, "risk_scores": {},
        "lab_case": {"recent_vitals": [], "latest_labs": [], "critical_flags": []},
        "ground_truth": {"target_condition": {"name": "Hypertension"}},
    }
    await write_patient_case_to_mongo(payload)
    doc = await PatientCase.get("uuid-z")
    assert doc is not None
    assert doc.demographics["age"] == 50
    assert doc.ground_truth["target_condition"]["name"] == "Hypertension"
