"""Integration tests for the /api/tests/* REST surface."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_vocabulary_returns_filtered_items(mongo_db, monkeypatch):
    """GET /api/tests/vocabulary?kind=medication&q=metf returns prefix-first matches."""
    from datetime import datetime
    await mongo_db["patient_cases"].insert_one({
        "_id": "seed-1",
        "person_id": 1, "cutoff_date": datetime(2024, 1, 1), "case_type": "ehr+lab",
        "demographics": {}, "conditions": {"active": [{"condition": "Metabolic syndrome", "code": "X1"}]},
        "medications": {"active": [{"medication": "Metformin", "rx_code": "861007"}]},
        "visits": {}, "comorbidity": {}, "risk_scores": {}, "labs": {"latest_labs": []},
        "ground_truth": {}, "case_stats": {}, "assembled_at": datetime.utcnow(),
        "pipeline_version": "x",
    })

    monkeypatch.setenv("USE_MONGO", "true")
    monkeypatch.setenv("MONGO_DB", mongo_db.name)

    # Re-import the app so the lifespan re-runs against the test DB and the
    # _vocab_cache global is reset to None for this test.
    from importlib import reload
    import doctor_console.backend.app as app_mod
    import src.db.mongo as mongo_mod
    # Reset vocab cache and sync client so _coll() picks up the new MONGO_DB
    app_mod._vocab_cache = None
    mongo_mod._sync_client = None
    reload(app_mod)

    client = TestClient(app_mod.app, raise_server_exceptions=True)
    r = client.get("/api/tests/vocabulary?kind=medication&q=metf")
    assert r.status_code == 200
    items = r.json()
    assert any(it["label"] == "Metformin" for it in items)
