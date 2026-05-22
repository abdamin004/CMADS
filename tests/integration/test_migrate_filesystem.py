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
