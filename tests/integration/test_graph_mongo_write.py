import pytest, pytest_asyncio
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_finalise_run_writes_trace_and_session(mongo_db, monkeypatch):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import AgentRun
    from src.orchestrator.graph import finalise_run_to_mongo

    await finalise_run_to_mongo(
        result_set="rs", patient_uuid="u",
        trace=[{"agent_id": "ehr_analyst", "status": "success", "duration_s": 1.0}],
        session_memory=[{"event_type": "note", "agent_id": "x", "summary": "..."}],
        duration_s=12.5,
    )
    doc = await AgentRun.find_one(AgentRun.result_set == "rs", AgentRun.patient_uuid == "u")
    assert doc.execution_trace[0]["agent_id"] == "ehr_analyst"
    assert doc.session_memory[0]["summary"] == "..."
    assert doc.duration_s == 12.5
