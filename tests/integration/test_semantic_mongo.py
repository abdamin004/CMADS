import pytest, pytest_asyncio
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_semantic_inc_atomic(mongo_db, monkeypatch):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import SemanticMemoryEntry
    from src.memory.semantic import consolidate_to_mongo

    await consolidate_to_mongo("End-stage renal disease", match_type="DIRECT", at_rank_1=True)
    await consolidate_to_mongo("End-stage renal disease", match_type="DIRECT", at_rank_1=False)
    await consolidate_to_mongo("End-stage renal disease", match_type="MISS",  at_rank_1=False)

    doc = await SemanticMemoryEntry.get("End-stage renal disease")
    assert doc.counts["direct"] == 2
    assert doc.counts["miss"] == 1
    assert doc.rank1_when_found == 1
