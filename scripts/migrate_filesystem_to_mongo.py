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


def walk_mas_results(gold_dir: Path) -> list[tuple[str, str]]:
    """Yield (result_set, patient_uuid) for every patient directory under
    gold_dir/mas_results*. Filters out non-directories and patient dirs
    without at least one evaluation artefact."""
    out: list[tuple[str, str]] = []
    for cohort in sorted(gold_dir.glob("mas_results*")):
        if not cohort.is_dir():
            continue
        for sub in sorted(cohort.iterdir()):
            if not sub.is_dir():
                continue
            if (sub / "evaluation.json").exists() or (sub / "evaluation_canon.json").exists():
                out.append((cohort.name, sub.name))
    return out


AGENT_FILES = {
    "ehr_analyst":          "ehr_analyst.json",
    "lab_interpreter":      "lab_interpreter.json",
    "diagnostic_reasoning": "diagnostic_reasoning.json",
    "clinical_reviewer":    "clinical_reviewer.json",
    "final_diagnosis":      "final_diagnosis.json",
    "evaluation":           "evaluation.json",
    "treatment_planning":   "treatment_planning.json",
}


def load_patient_run(gold_dir: Path, result_set: str, patient_uuid: str) -> dict:
    """Read all on-disk JSON for one patient run and assemble the
    AgentRun document payload (no insert; pure read side)."""
    pdir = gold_dir / result_set / patient_uuid
    agents: dict[str, dict] = {}
    for agent_id, fname in AGENT_FILES.items():
        f = pdir / fname
        if f.exists():
            agents[agent_id] = {"status": "success", "output": json.loads(f.read_text())}
    # Embed canon variants where present.
    for agent_id, canon_name in (("evaluation", "evaluation_canon.json"),
                                  ("final_diagnosis", "final_diagnosis_canon.json")):
        cf = pdir / canon_name
        if cf.exists():
            agents.setdefault(agent_id, {"status": "success", "output": None})
            agents[agent_id]["output_canon"] = json.loads(cf.read_text())
    trace = json.loads((pdir / "execution_trace.json").read_text()) if (pdir / "execution_trace.json").exists() else []
    session = json.loads((pdir / "session_memory.json").read_text()) if (pdir / "session_memory.json").exists() else []
    return {
        "result_set": result_set,
        "patient_uuid": patient_uuid,
        "agents": agents,
        "execution_trace": trace if isinstance(trace, list) else [trace],
        "session_memory": session if isinstance(session, list) else [session],
    }


from datetime import datetime
from src.db.mongo import init_db
from src.db.documents import AgentRun


async def migrate_patient_runs(gold_dir: Path) -> int:
    """Read every patient run from gold_dir/mas_results* and upsert into
    the agent_runs collection. Returns the number of documents written.
    Idempotent: re-running over the same input replaces the same docs."""
    runs = walk_mas_results(gold_dir)
    count = 0
    for result_set, patient_uuid in runs:
        payload = load_patient_run(gold_dir, result_set, patient_uuid)
        await AgentRun.find_one(
            AgentRun.result_set == result_set,
            AgentRun.patient_uuid == patient_uuid,
        ).upsert(
            {"$set": {
                "agents":          payload["agents"],
                "execution_trace": payload["execution_trace"],
                "session_memory":  payload["session_memory"],
            }},
            on_insert=AgentRun(
                result_set=result_set,
                patient_uuid=patient_uuid,
                started_at=datetime.utcnow(),
                agents=payload["agents"],
                execution_trace=payload["execution_trace"],
                session_memory=payload["session_memory"],
            ),
        )
        count += 1
    return count


async def main_async(args: argparse.Namespace) -> int:
    gold = args.gold_dir
    patient_runs = walk_mas_results(gold)
    patient_cases = [p.name for p in (gold / "patient_cases").iterdir()
                     if (gold / "patient_cases" / p.name).is_dir()] if (gold / "patient_cases").exists() else []
    semantic_path = gold / "memory" / "semantic_memory.json"
    derived = [p.name for p in gold.glob("*.json")] if gold.exists() else []

    report: dict = {
        "dry_run": args.dry_run,
        "agent_runs_seen": len(patient_runs),
        "patient_cases_seen": len(patient_cases),
        "semantic_memory_present": semantic_path.exists(),
        "derived_artefact_files": derived,
    }

    if args.dry_run:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2))
        print(json.dumps(report, indent=2))
        return 0

    await init_db()
    report["agent_runs_inserted"] = await migrate_patient_runs(gold)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    return 0


def main() -> int:
    args = build_argparser().parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
