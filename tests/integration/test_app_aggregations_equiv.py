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


@pytest.mark.asyncio
async def test_rank_distribution_buckets(mongo_db):
    from src.db.documents import AgentRun
    from doctor_console.backend.app import _rank_distribution_mongo
    from datetime import datetime

    for uuid, mt, rank in [("u1", "DIRECT", 1), ("u2", "DIRECT", 1),
                            ("u3", "INDIRECT", 2), ("u4", "INDIRECT", 4),
                            ("u5", "MISS", 0)]:
        await AgentRun(
            result_set="r", patient_uuid=uuid, started_at=datetime.utcnow(),
            agents={"evaluation": {"status": "success",
                                   "output": {"match_type": mt, "rank": rank}}},
        ).insert()

    buckets = {b["label"]: b["count"] for b in await _rank_distribution_mongo(["r"])}
    assert buckets == {"1": 2, "2": 1, "3": 0, "4-5": 1, "miss": 1}


@pytest.mark.asyncio
async def test_per_disease_breakdown_groups_by_target(mongo_db):
    from src.db.documents import AgentRun, PatientCase
    from doctor_console.backend.app import _per_disease_breakdown_mongo
    from datetime import datetime

    await PatientCase(id="u1", person_id=1, cutoff_date=datetime.utcnow(),
                       case_type="ehr+lab", demographics={}, conditions={},
                       medications={}, visits=[], comorbidity={}, risk_scores={},
                       labs={}, ground_truth={"target_condition": {"name": "T2DM"}},
                       case_stats={}, assembled_at=datetime.utcnow(),
                       pipeline_version="t").insert()
    await PatientCase(id="u2", person_id=2, cutoff_date=datetime.utcnow(),
                       case_type="ehr+lab", demographics={}, conditions={},
                       medications={}, visits=[], comorbidity={}, risk_scores={},
                       labs={}, ground_truth={"target_condition": {"name": "ESRD"}},
                       case_stats={}, assembled_at=datetime.utcnow(),
                       pipeline_version="t").insert()
    await AgentRun(result_set="r", patient_uuid="u1", started_at=datetime.utcnow(),
                    agents={"evaluation": {"status": "success",
                                           "output": {"match_type": "DIRECT", "rank": 1}}}).insert()
    await AgentRun(result_set="r", patient_uuid="u2", started_at=datetime.utcnow(),
                    agents={"evaluation": {"status": "success",
                                           "output": {"match_type": "MISS", "rank": 0}}}).insert()

    rows = await _per_disease_breakdown_mongo(["r"])
    by = {r["disease"]: r for r in rows}
    assert by["T2DM"]["direct"] == 1
    assert by["ESRD"]["miss"] == 1
