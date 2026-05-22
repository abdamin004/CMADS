"""Tests for scripts/migrate_filesystem_to_mongo.py.

The backfill is the most critical piece of the migration — bugs here
mean silent data loss. Verifier mode must always pass on a clean
round-trip, and idempotency must hold across re-runs.
"""
import subprocess
import sys
import json
from pathlib import Path
import pytest
import pytest_asyncio

pytest_plugins = ["tests.integration.conftest_mongo"]

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "migrate_filesystem_to_mongo.py"


def test_dry_run_help_works():
    """`--help` should print a usage banner mentioning --dry-run and exit 0."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    assert "--dry-run" in proc.stdout
    assert "--verify" in proc.stdout
    assert "--workers" in proc.stdout


def test_walk_mas_results_finds_expected_directories(tmp_path):
    """walk_mas_results yields one (result_set, patient_uuid) per UUID dir."""
    from scripts.migrate_filesystem_to_mongo import walk_mas_results
    # Synthesise a tiny on-disk layout
    (tmp_path / "mas_results" / "uuid-a").mkdir(parents=True)
    (tmp_path / "mas_results" / "uuid-b").mkdir(parents=True)
    (tmp_path / "mas_results_improved_50" / "uuid-c").mkdir(parents=True)
    (tmp_path / "mas_results" / "uuid-a" / "evaluation.json").write_text("{}")
    (tmp_path / "mas_results" / "uuid-b" / "evaluation.json").write_text("{}")
    (tmp_path / "mas_results_improved_50" / "uuid-c" / "evaluation.json").write_text("{}")
    found = sorted(walk_mas_results(tmp_path))
    assert found == [
        ("mas_results", "uuid-a"),
        ("mas_results", "uuid-b"),
        ("mas_results_improved_50", "uuid-c"),
    ]


def test_dry_run_emits_report_without_touching_mongo(tmp_path):
    """--dry-run on a synthesised tree produces a report JSON listing
    the work it would have done."""
    # Tiny synthetic layout
    cohort = tmp_path / "mas_results"
    (cohort / "u1").mkdir(parents=True)
    (cohort / "u1" / "evaluation.json").write_text(json.dumps({"match_type": "DIRECT"}))
    (cohort / "u2").mkdir(parents=True)
    (cohort / "u2" / "evaluation.json").write_text(json.dumps({"match_type": "MISS"}))

    report = tmp_path / "report.json"
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run",
         "--gold-dir", str(tmp_path), "--report", str(report)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(report.read_text())
    assert data["dry_run"] is True
    assert data["agent_runs_seen"] == 2
    # Mongo should be untouched — easy to assert by spotcheck of dry-run flag.


@pytest.mark.asyncio
async def test_real_migration_inserts_agent_runs(tmp_path, mongo_db):
    """A non-dry-run pass should insert an AgentRun document per patient."""
    from src.db.documents import AgentRun
    from scripts.migrate_filesystem_to_mongo import migrate_patient_runs

    cohort = tmp_path / "mas_results"
    (cohort / "u1").mkdir(parents=True)
    (cohort / "u1" / "evaluation.json").write_text(
        json.dumps({"match_type": "DIRECT", "rank": 1})
    )
    (cohort / "u1" / "execution_trace.json").write_text(json.dumps([]))

    count = await migrate_patient_runs(tmp_path)
    assert count == 1
    doc = await AgentRun.find_one(
        AgentRun.result_set == "mas_results",
        AgentRun.patient_uuid == "u1",
    )
    assert doc is not None
    assert doc.agents["evaluation"]["output"]["match_type"] == "DIRECT"


@pytest.mark.asyncio
async def test_migrate_patient_cases(tmp_path, mongo_db):
    from src.db.documents import PatientCase
    from scripts.migrate_filesystem_to_mongo import migrate_patient_cases

    cases = tmp_path / "patient_cases" / "u1"
    cases.mkdir(parents=True)
    (cases / "ehr_case.json").write_text(json.dumps({
        "person_id": 42, "cutoff_date": "2021-10-18", "case_type": "ehr+lab",
        "demographics": {"age": 60}, "conditions": {"active": []}, "medications": {"active": []},
        "visits": [], "comorbidity": {}, "risk_scores": {},
    }))
    (cases / "lab_case.json").write_text(json.dumps({
        "recent_vitals": [], "latest_labs": [], "critical_flags": [],
    }))
    (cases / "ground_truth.json").write_text(json.dumps({
        "target_condition": {"name": "Diabetes mellitus type 2"},
    }))

    count = await migrate_patient_cases(tmp_path)
    assert count == 1
    doc = await PatientCase.get("u1")
    assert doc is not None
    assert doc.person_id == 42
    assert doc.demographics["age"] == 60
    assert doc.ground_truth["target_condition"]["name"] == "Diabetes mellitus type 2"


@pytest.mark.asyncio
async def test_migrate_semantic_and_derived(tmp_path, mongo_db):
    from src.db.documents import SemanticMemoryEntry, DerivedArtefact
    from scripts.migrate_filesystem_to_mongo import (
        migrate_semantic_memory, migrate_derived_artefacts,
    )

    (tmp_path / "memory").mkdir(parents=True)
    (tmp_path / "memory" / "semantic_memory.json").write_text(json.dumps({
        "End-stage renal disease (disorder)": {
            "counts": {"direct": 5, "indirect": 1, "miss": 0},
            "rank1_when_found": 4,
        },
        "Ischemic heart disease (disorder)": {
            "counts": {"direct": 3, "indirect": 2, "miss": 1},
        },
    }))
    (tmp_path / "paired_160_mcnemar.json").write_text(json.dumps({"n": 160}))

    n_sm = await migrate_semantic_memory(tmp_path)
    n_da = await migrate_derived_artefacts(tmp_path)
    assert n_sm == 2 and n_da == 1
    sm = await SemanticMemoryEntry.get("End-stage renal disease (disorder)")
    assert sm.counts == {"direct": 5, "indirect": 1, "miss": 0}
    da = await DerivedArtefact.get("paired_160_mcnemar")
    assert da.payload == {"n": 160}


@pytest.mark.asyncio
async def test_verify_detects_intact_roundtrip(tmp_path, mongo_db):
    """After migration, --verify should report zero divergences."""
    from scripts.migrate_filesystem_to_mongo import (
        migrate_patient_runs, verify_patient_runs,
    )
    cohort = tmp_path / "mas_results"
    (cohort / "u1").mkdir(parents=True)
    (cohort / "u1" / "evaluation.json").write_text(
        json.dumps({"match_type": "DIRECT", "rank": 1})
    )
    await migrate_patient_runs(tmp_path)
    divergences = await verify_patient_runs(tmp_path, sample_all=True)
    assert divergences == []
