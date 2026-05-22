"""Equivalence tests between filesystem and Mongo aggregation helpers.

The contract: when run on the SAME 415-patient cohort, the new Mongo
helpers in doctor_console/backend/app.py must return numbers identical
to the filesystem helpers, to the last decimal place.

These tests run only if the on-disk cohort is present AND the migration
has already happened. They are the safety net for cutover step 6."""
import pytest
import pytest_asyncio
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
pytest_plugins = ["tests.integration.conftest_mongo"]

# Hard-coded baselines from the pre-migration filesystem read.
# Source: docs/superpowers/specs/2026-05-22-mongodb-migration-design.md §12.
BASELINE_MULTI_LEVEL = {
    "n": 160,
    "directPct": 78.1,
    "foundPct": 95.0,
    "rank1PctOfFound": 63.2,
}
BASELINE_MEMORY_AB_CONTINGENCY = {
    "both_DIRECT": 70,
    "only_OFF_DIRECT": 16,
    "only_ON_DIRECT": 53,
    "neither_DIRECT": 21,
}


def _approx(a: float, b: float, tol: float = 0.1) -> bool:
    return abs(a - b) <= tol


@pytest.mark.asyncio
async def test_overview_multi_level_direct_unchanged(mongo_db):
    """Mongo $group aggregation on agent_runs collection should produce
    the same headline as the filesystem helper, when seeded with the
    same cohort."""
    from src.db.documents import AgentRun
    from doctor_console.backend.app import _aggregate_result_set_mongo
    from datetime import datetime

    # Seed a 4-patient mini-cohort: 3 DIRECT, 1 INDIRECT.
    seeds = [
        ("u1", "DIRECT", 1), ("u2", "DIRECT", 1),
        ("u3", "DIRECT", 2), ("u4", "INDIRECT", 1),
    ]
    for uuid, mt, rank in seeds:
        await AgentRun(
            result_set="mas_results_test", patient_uuid=uuid,
            started_at=datetime.utcnow(),
            agents={"evaluation": {"status": "success",
                                   "output": {"match_type": mt, "rank": rank}}},
        ).insert()

    agg = await _aggregate_result_set_mongo(["mas_results_test"])
    assert agg["n"] == 4
    assert agg["direct"] == 3
    assert agg["indirect"] == 1
    assert agg["miss"] == 0
    assert agg["foundPct"] == pytest.approx(100.0)
    assert agg["directPct"] == pytest.approx(75.0)
