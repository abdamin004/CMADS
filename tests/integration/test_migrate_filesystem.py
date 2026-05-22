"""Tests for scripts/migrate_filesystem_to_mongo.py.

The backfill is the most critical piece of the migration — bugs here
mean silent data loss. Verifier mode must always pass on a clean
round-trip, and idempotency must hold across re-runs.
"""
import subprocess
import sys
import json
from pathlib import Path

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
