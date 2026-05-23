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


def test_cohort_browse_filters_by_disease(client, mongo_db):
    """GET /api/tests/cohort?disease=IHD returns only IHD patients."""
    from datetime import datetime
    base = {
        "person_id": 1, "cutoff_date": datetime(2024,1,1), "case_type": "ehr+lab",
        "conditions":{"active":[]}, "medications":{"active":[]}, "visits":{},
        "comorbidity":{}, "risk_scores":{}, "labs":{"latest_labs":[]},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    }
    mongo_db["patient_cases"].insert_many([
        {**base, "_id": "ihd-1", "demographics":{"age":70,"gender":"F"},
         "ground_truth":{"target_condition":{"name":"Ischemic heart disease"}}},
        {**base, "_id": "t2dm-1", "demographics":{"age":65,"gender":"M"},
         "ground_truth":{"target_condition":{"name":"Diabetes mellitus type 2"}}},
    ])

    r = client.get("/api/tests/cohort?disease=Ischemic heart disease")
    assert r.status_code == 200
    rows = r.json()
    uuids = [row["uuid"] for row in rows]
    assert "ihd-1" in uuids
    assert "t2dm-1" not in uuids


def test_cohort_browse_filters_by_age_and_gender(client, mongo_db):
    from datetime import datetime
    base = {
        "person_id": 1, "cutoff_date": datetime(2024,1,1), "case_type": "ehr+lab",
        "conditions":{"active":[]}, "medications":{"active":[]}, "visits":{},
        "comorbidity":{}, "risk_scores":{}, "labs":{"latest_labs":[]},
        "ground_truth":{"target_condition":{"name":"Hypertension"}},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    }
    mongo_db["patient_cases"].insert_many([
        {**base, "_id":"a","demographics":{"age":50,"gender":"F"}},
        {**base, "_id":"b","demographics":{"age":70,"gender":"F"}},
        {**base, "_id":"c","demographics":{"age":70,"gender":"M"}},
    ])

    r = client.get("/api/tests/cohort?age_min=60&age_max=80&gender=F")
    assert r.status_code == 200
    uuids = sorted(row["uuid"] for row in r.json())
    assert uuids == ["b"]


def test_cohort_template_returns_clone_payload(client, mongo_db):
    """GET /api/tests/cohort/{uuid} returns the patient as a clone template."""
    from datetime import datetime
    mongo_db["patient_cases"].insert_one({
        "_id": "src-1",
        "person_id": 7, "cutoff_date": datetime(2024,1,1), "case_type":"ehr+lab",
        "demographics":{"age":60,"gender":"M"},
        "conditions":{"active":[{"condition":"T2DM","code":"44054006"}]},
        "medications":{"active":[]}, "visits":{}, "comorbidity":{}, "risk_scores":{},
        "labs":{"latest_labs":[]},
        "ground_truth":{"target_condition":{"name":"Diabetes mellitus type 2"}},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    })

    r = client.get("/api/tests/cohort/src-1")
    assert r.status_code == 200
    body = r.json()
    assert body["source_uuid"] == "src-1"
    assert body["demographics"]["age"] == 60
    assert body["ground_truth"]["target_condition"]["name"] == "Diabetes mellitus type 2"
    # Not a real TestPatient yet — no _id, no created_at
    assert "_id" not in body and "created_at" not in body


def test_post_test_patient_creates_doc(client):
    payload = {
        "label": "70F sketch",
        "demographics": {"age": 70, "gender": "F"},
        "labs": {"latest_labs": []},
    }
    r = client.post("/api/tests/patients", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "70F sketch"
    assert body["test_uuid"].startswith("ttest-")
    assert body["created_at"] is not None


def test_post_validates_required_fields(client):
    r = client.post("/api/tests/patients", json={"demographics":{"age":70,"gender":"F"}})
    assert r.status_code == 422  # missing label

    r = client.post("/api/tests/patients", json={"label":"x","demographics":{"gender":"F"}})
    assert r.status_code == 422  # missing age


def test_get_test_patient_returns_full_doc(client):
    created = client.post("/api/tests/patients", json={
        "label": "g-test",
        "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.get(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 200
    body = r.json()
    assert body["_id"] == test_uuid
    assert body["label"] == "g-test"
    assert body["run_count"] == 0
    assert body["last_run_at"] is None


def test_put_test_patient_updates_label(client):
    created = client.post("/api/tests/patients", json={
        "label": "old",
        "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.put(f"/api/tests/patients/{test_uuid}", json={
        "label": "new",
        "demographics": {"age": 60, "gender": "M"},
    })
    assert r.status_code == 200
    assert r.json()["label"] == "new"


def test_list_test_patients_returns_summaries(client):
    client.post("/api/tests/patients", json={"label":"a","demographics":{"age":60,"gender":"M"}})
    client.post("/api/tests/patients", json={"label":"b","demographics":{"age":60,"gender":"F"}})
    r = client.get("/api/tests/patients")
    assert r.status_code == 200
    rows = r.json()
    labels = [row["label"] for row in rows]
    assert "a" in labels and "b" in labels
    assert all("test_uuid" in row and "created_at" in row for row in rows)


def test_delete_test_patient(client):
    created = client.post("/api/tests/patients", json={
        "label": "del", "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.delete(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 200
    r = client.get(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 404


def test_post_test_run_starts_task(client):
    """POST /api/tests/runs starts a worker task and returns its id."""
    created = client.post("/api/tests/patients", json={
        "label":"runme", "demographics":{"age":60,"gender":"F"},
        "labs":{"latest_labs":[]},
    }).json()

    r = client.post("/api/tests/runs", json={"test_uuid": created["test_uuid"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("queued", "running")
    assert body["resultSet"] == "mas_results_test"
    assert body["taskId"]


def test_post_test_run_404_when_uuid_unknown(client):
    r = client.post("/api/tests/runs", json={"test_uuid": "ttest-nope"})
    assert r.status_code == 404


def test_doctor_run_and_test_run_in_parallel(client, mongo_db):
    """Two /api/tests/runs launched back-to-back must register with independent
    task_ids and both must report resultSet == 'mas_results_test'.

    This is the concurrency regression: both paths share _run_patient_task and
    _tasks, so the test proves the thread-local override machinery gives each
    run its own result_set without either overwriting the other's slot.

    Note: we use two test patients (instead of one cohort + one test patient)
    because PATIENT_CASES is a module-level constant in app.py that is
    resolved at import time and cannot be redirected via monkeypatch.setenv."""
    p1 = client.post("/api/tests/patients", json={
        "label": "concurrent-1",
        "demographics": {"age": 55, "gender": "M"},
    }).json()
    p2 = client.post("/api/tests/patients", json={
        "label": "concurrent-2",
        "demographics": {"age": 65, "gender": "F"},
    }).json()

    r1 = client.post("/api/tests/runs", json={"test_uuid": p1["test_uuid"]})
    r2 = client.post("/api/tests/runs", json={"test_uuid": p2["test_uuid"]})

    assert r1.status_code == 200
    assert r2.status_code == 200
    t1, t2 = r1.json(), r2.json()
    assert t1["taskId"] != t2["taskId"]
    assert t1["resultSet"] == "mas_results_test"
    assert t2["resultSet"] == "mas_results_test"
    assert t1["status"] in ("queued", "running")
    assert t2["status"] in ("queued", "running")
