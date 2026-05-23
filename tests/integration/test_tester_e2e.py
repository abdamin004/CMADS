"""End-to-end smoke for the Tester journey: build → save → run → verify."""
import pytest
import pytest_asyncio
import time

pytestmark = pytest.mark.slow

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_build_save_run_verify(mongo_db, monkeypatch):
    """Save a minimal scratch patient → trigger run via the API surface
    → poll until completion → verify TestPatient.last_run_at and the
    mas_results_test AgentRun doc both exist."""
    from importlib import reload
    monkeypatch.setenv("USE_MONGO", "true")
    monkeypatch.setenv("MONGO_DB", mongo_db.name)
    # Reset the sync client + vocab cache so the reload picks up the test DB
    import src.db.mongo as mongo_mod
    mongo_mod._sync_client = None
    import doctor_console.backend.app as app_mod
    app_mod._vocab_cache = None  # type: ignore[attr-defined]
    reload(app_mod)

    from fastapi.testclient import TestClient
    client = TestClient(app_mod.app)

    # Build + save
    created = client.post("/api/tests/patients", json={
        "label": "e2e smoke",
        "demographics": {"age": 70, "gender": "F"},
        "conditions": {"active": [{"condition": "Hypertension", "code": "59621000"}]},
        "labs": {"latest_labs": [{"test_name": "HbA1c", "value": "8.2"}]},
    }).json()
    test_uuid = created["test_uuid"]

    # Run
    run_resp = client.post("/api/tests/runs", json={"test_uuid": test_uuid}).json()
    task_id = run_resp["taskId"]

    # Poll for completion (or 4-minute budget)
    deadline = time.time() + 240
    r = {"status": "unknown"}
    while time.time() < deadline:
        r = client.get(f"/api/runs/{task_id}").json()
        if r["status"] in ("completed", "error"):
            break
        time.sleep(5)

    assert r["status"] == "completed", f"run did not complete: {r}"

    # Verify TestPatient stamped
    tp = mongo_db["test_patients"].find_one({"_id": test_uuid})
    assert tp["run_count"] == 1
    assert tp["last_run_at"] is not None

    # Verify AgentRun doc landed in the test cohort, not the research one
    ar = mongo_db["agent_runs"].find_one({
        "patient_uuid": test_uuid,
        "result_set":   "mas_results_test",
    })
    assert ar is not None
    assert len(ar.get("agents", {})) >= 3  # at least 3 of the 7 agents populated
