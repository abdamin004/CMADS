"""MongoDB client lifecycle.

Two entry points:
  * Async ``init_db(db)`` — register Beanie models on a Motor database.
    Called from FastAPI lifespan and from script entry points.
  * Sync ``get_sync_db()`` — convenience for the non-async pipeline
    scripts. Spins up its own loop boundary; the caller does not need
    to know it is talking to async code.
"""
from __future__ import annotations
import asyncio
from typing import Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from src.config import cfg
from src.db.documents import (
    PatientCase,
    AgentRun,
    SemanticMemoryEntry,
    DerivedArtefact,
    TestPatient,
)

_DOCUMENT_MODELS = [PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact, TestPatient]
_client: AsyncIOMotorClient | None = None


async def init_db(database: AsyncIOMotorDatabase | None = None) -> AsyncIOMotorDatabase:
    """Bind Beanie to ``database``. When ``database`` is None, opens
    the configured ``MONGO_URI`` / ``MONGO_DB`` and binds to that."""
    global _client
    if database is None:
        if _client is None:
            _client = AsyncIOMotorClient(cfg.MONGO_URI)
        database = _client[cfg.MONGO_DB]
    await init_beanie(database=database, document_models=_DOCUMENT_MODELS)
    return database


async def ensure_db_initialized() -> None:
    """Initialize Beanie only when it has not been initialized yet.

    This is the safe entry point for helper functions that may be called from
    both production code (where nothing is set up yet) and from tests (where
    the conftest has already called init_beanie on a test database). Re-calling
    init_db in tests would re-bind document models to a new Motor client whose
    event loop is the one from the previous test, causing 'Event loop is closed'
    errors on subsequent test runs.
    """
    from beanie.exceptions import CollectionWasNotInitialized
    try:
        # If any document model has its Motor collection bound, Beanie is up.
        AgentRun.get_motor_collection()
    except CollectionWasNotInitialized:
        await init_db()


def get_sync_db() -> Any:
    """Synchronous bootstrap for scripts. Initialises the global client
    and runs ``init_db`` once via ``asyncio.run``. Subsequent calls in
    the same process are idempotent."""
    global _client
    if _client is None:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(init_db())
    return _client[cfg.MONGO_DB]


import threading

_sync_client = None  # pymongo.MongoClient — created lazily
_sync_client_lock = threading.Lock()


def _get_sync_client():
    """Lazy singleton PyMongo client for sync write paths.

    Why sync PyMongo and not Motor: Motor's ``AsyncIOMotorClient`` is
    loop-bound and the FastAPI lifespan already binds Beanie/Motor to
    the FastAPI event loop. The agent code path (``BaseAgent.__call__``
    and friends) runs sync inside a worker thread spawned by the
    runtime; the loop on that thread is different (or absent), so
    Motor calls there hit "Task pending" and never complete.

    PyMongo is the official sync driver, ships with motor as a
    transitive dep, has no asyncio at all, and is safe to call from any
    thread. We use it for the four agent-side write paths (the four
    ``run_mongo_write_*`` helpers below). The FastAPI read path keeps
    using Motor/Beanie because it lives natively on the FastAPI loop.
    """
    global _sync_client
    with _sync_client_lock:
        if _sync_client is None:
            from pymongo import MongoClient
            _sync_client = MongoClient(cfg.MONGO_URI)
        return _sync_client


def _coll(name: str):
    """Get a sync pymongo Collection handle for the configured DB."""
    return _get_sync_client()[cfg.MONGO_DB][name]


# ── Sync write helpers — these are what BaseAgent / graph / gold / semantic call ──

def write_agent_envelope_sync(*, result_set: str, patient_uuid: str,
                              agent_id: str, envelope: dict) -> None:
    """Atomic per-agent upsert. Compound-key by (result_set, patient_uuid)."""
    from datetime import datetime
    _coll("agent_runs").update_one(
        {"result_set": result_set, "patient_uuid": patient_uuid},
        {
            "$set": {f"agents.{agent_id}": envelope},
            "$setOnInsert": {"started_at": datetime.utcnow()},
        },
        upsert=True,
    )


def finalise_run_sync(*, result_set: str, patient_uuid: str,
                      trace: list[dict], session_memory: list[dict],
                      duration_s: float | None) -> None:
    """End-of-run write: trace + session memory + finished_at + duration."""
    from datetime import datetime
    _coll("agent_runs").update_one(
        {"result_set": result_set, "patient_uuid": patient_uuid},
        {
            "$set": {
                "execution_trace": trace,
                "session_memory":  session_memory,
                "finished_at":     datetime.utcnow(),
                "duration_s":      duration_s,
            },
            "$setOnInsert": {"started_at": datetime.utcnow()},
        },
        upsert=True,
    )


def write_patient_case_sync(payload: dict) -> None:
    """Upsert a Gold case into the patient_cases collection."""
    from datetime import datetime
    case_stats = {
        "activeConditions":  len((payload.get("conditions",  {}) or {}).get("active", []) or []),
        "activeMedications": len((payload.get("medications", {}) or {}).get("active", []) or []),
        "labTrends":         len((payload.get("lab_case", {}) or {}).get("latest_labs", []) or []),
        "criticalFlags":     len((payload.get("lab_case", {}) or {}).get("critical_flags", []) or []),
    }
    cutoff_raw = str(payload.get("cutoff_date", "1970-01-01"))[:10]
    doc = {
        "person_id":        int(payload.get("person_id", 0)),
        "cutoff_date":      datetime.fromisoformat(cutoff_raw),
        "case_type":        str(payload.get("case_type", "ehr+lab")),
        "demographics":     payload.get("demographics", {}),
        "conditions":       payload.get("conditions", {}),
        "medications":      payload.get("medications", {}),
        "visits":           payload.get("visits", []),
        "comorbidity":      payload.get("comorbidity", {}),
        "risk_scores":      payload.get("risk_scores", {}),
        "labs":             payload.get("lab_case", {}),
        "ground_truth":     payload.get("ground_truth", {}),
        "case_stats":       case_stats,
        "assembled_at":     datetime.utcnow(),
        "pipeline_version": "gold-3.4",
    }
    _coll("patient_cases").update_one(
        {"_id": str(payload["patient_uuid"])},
        {"$set": doc},
        upsert=True,
    )


def semantic_inc_sync(disease: str, *, match_type: str, at_rank_1: bool) -> None:
    """Atomic per-disease counter increment for semantic memory."""
    from datetime import datetime
    field = {"DIRECT": "direct", "INDIRECT": "indirect", "MISS": "miss"}.get(match_type, "miss")
    inc: dict[str, int] = {f"counts.{field}": 1}
    if at_rank_1 and match_type in ("DIRECT", "INDIRECT"):
        inc["rank1_when_found"] = 1
    _coll("semantic_memory").update_one(
        {"_id": disease},
        {"$inc": inc, "$set": {"updated_at": datetime.utcnow()}},
        upsert=True,
    )


# ── Tester-journey sync helpers ────────────────────────────────────

def write_test_patient_sync(payload: dict) -> None:
    """Upsert a TestPatient document. Stamps created_at on insert,
    updated_at on every write. Defaults run_count=0, last_run_at=None.
    The caller supplies `_id` (test_uuid)."""
    from datetime import datetime
    now = datetime.utcnow()
    doc = dict(payload)  # copy so we don't mutate the caller's dict
    doc["updated_at"] = now
    doc.setdefault("run_count", 0)
    doc.setdefault("last_run_at", None)
    doc.setdefault("assembled_at", now)
    doc.setdefault("pipeline_version", "tester-1.0")
    # cutoff_date arrives as a string from the REST layer; normalise to dt
    if isinstance(doc.get("cutoff_date"), str):
        doc["cutoff_date"] = datetime.fromisoformat(doc["cutoff_date"][:10])
    # created_at must NOT appear in $set — it belongs only in $setOnInsert
    # so that re-upserts don't overwrite it.
    doc.pop("created_at", None)
    _coll("test_patients").update_one(
        {"_id": doc["_id"]},
        {"$set": doc, "$setOnInsert": {"created_at": now}},
        upsert=True,
    )


def update_test_patient_sync(test_uuid: str, patch: dict) -> None:
    """Apply a partial update to a TestPatient. Advances updated_at.
    Does NOT touch created_at, last_run_at, run_count, or source_uuid."""
    from datetime import datetime
    patch = {k: v for k, v in patch.items()
             if k not in {"_id", "created_at", "last_run_at",
                          "run_count", "source_uuid"}}
    patch["updated_at"] = datetime.utcnow()
    if isinstance(patch.get("cutoff_date"), str):
        patch["cutoff_date"] = datetime.fromisoformat(patch["cutoff_date"][:10])
    _coll("test_patients").update_one(
        {"_id": test_uuid},
        {"$set": patch},
    )


def stamp_test_run_sync(test_uuid: str) -> None:
    """Called by the worker thread after a test run finishes.
    Sets last_run_at to now and increments run_count by 1."""
    from datetime import datetime
    _coll("test_patients").update_one(
        {"_id": test_uuid},
        {
            "$set": {"last_run_at": datetime.utcnow()},
            "$inc": {"run_count": 1},
        },
    )


def get_test_patient_sync(test_uuid: str) -> dict | None:
    """Read a single TestPatient as a plain dict (None if missing)."""
    return _coll("test_patients").find_one({"_id": test_uuid})


def delete_test_patient_sync(test_uuid: str) -> None:
    """Remove the TestPatient doc. Does NOT touch agent_runs."""
    _coll("test_patients").delete_one({"_id": test_uuid})
