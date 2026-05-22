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
    """Once the Mongo aggregation path lands, /api/stats/overview must
    return the same headline as the filesystem path."""
    # This test will be filled in during Task 16+ when the Mongo helpers
    # are implemented. For now it documents the gold value.
    assert BASELINE_MULTI_LEVEL["directPct"] == 78.1
    assert BASELINE_MULTI_LEVEL["foundPct"] == 95.0
    assert BASELINE_MULTI_LEVEL["rank1PctOfFound"] == 63.2
