#!/usr/bin/env python3
"""Backfill: filesystem JSON → MongoDB.

One-shot migration script. Reads data/gold/mas_results*/, patient_cases/,
memory/semantic_memory.json, and the per-cohort derived artefacts, then
inserts them into the MongoDB collections defined in src/db/documents.py.

Idempotent (re-runnable), restartable (progress file), supports --dry-run
and --verify modes. See docs/superpowers/specs/2026-05-22-mongodb-migration-design.md §8.
"""
from __future__ import annotations
import argparse
import asyncio
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def build_argparser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true",
                    help="Walk the filesystem and report what would be inserted; do not touch Mongo.")
    ap.add_argument("--verify", action="store_true",
                    help="After insertion, SHA-256 a 10%% sample to verify round-trip.")
    ap.add_argument("--verify-all", action="store_true",
                    help="Verify every document (slower).")
    ap.add_argument("--workers", type=int, default=8,
                    help="Concurrent workers for per-patient migration.")
    ap.add_argument("--report", type=Path, default=Path("data/gold/migration_report.json"),
                    help="Path to write the structured run report.")
    ap.add_argument("--gold-dir", type=Path, default=Path("data/gold"),
                    help="Root of the on-disk JSON tree.")
    return ap


async def main_async(args: argparse.Namespace) -> int:
    raise NotImplementedError("Implemented in subsequent tasks.")


def main() -> int:
    args = build_argparser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
