"""Verify that BaseAgent.__call__ upserts the agent envelope to AgentRun
when USE_MONGO=true, without disturbing the existing PipelineState API."""
import pytest, pytest_asyncio, asyncio
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_base_agent_upserts_envelope(mongo_db, monkeypatch):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import AgentRun
    from src.agents.base import write_agent_envelope_to_mongo

    await write_agent_envelope_to_mongo(
        result_set="rsX", patient_uuid="uuidX",
        agent_id="ehr_analyst",
        envelope={"status": "success", "output": {"hello": "world"}, "duration_ms": 12},
    )
    doc = await AgentRun.find_one(
        AgentRun.result_set == "rsX", AgentRun.patient_uuid == "uuidX",
    )
    assert doc is not None
    assert doc.agents["ehr_analyst"]["output"] == {"hello": "world"}
