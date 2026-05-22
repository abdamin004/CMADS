# MongoDB Storage Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate CMADS per-agent JSON outputs, Gold patient cases, and semantic memory from the filesystem (`data/gold/mas_results*/`, `data/gold/patient_cases/`, `data/gold/memory/`) to a local Docker MongoDB instance via Beanie ODM, with a one-time backfill and a 30-day rollback contract.

**Architecture:** Four Mongo collections (`patient_cases`, `agent_runs`, `semantic_memory`, `derived_artefacts`) per the approved schema in §5 of the design spec. One `agent_runs` document per `(result_set, patient_uuid)` aggregate. Backend keeps API contracts byte-identical so the React frontend doesn't change. A `USE_MONGO` config flag preserves the filesystem read path for 30 days as the rollback artefact.

**Tech Stack:** MongoDB 7 (Docker), Beanie 1.x (async ODM, Pydantic v2 native), Motor (async PyMongo), `pytest-asyncio` for tests, existing FastAPI + LangGraph + Pydantic v2 stack untouched.

**Spec reference:** [`docs/superpowers/specs/2026-05-22-mongodb-migration-design.md`](../specs/2026-05-22-mongodb-migration-design.md).

---

## File Structure

**New files:**
| Path | Purpose |
|---|---|
| `docker-compose.yml` | Mongo service (file does not yet exist at repo root) |
| `src/db/__init__.py` | Package marker |
| `src/db/mongo.py` | Singleton client, `init_db()`, `get_sync_db()` |
| `src/db/documents.py` | Four Beanie `Document` classes |
| `scripts/migrate_filesystem_to_mongo.py` | Backfill CLI |
| `tests/test_db_documents.py` | Beanie model unit tests |
| `tests/integration/test_migrate_filesystem.py` | Backfill verifier tests |
| `tests/integration/test_app_aggregations_equiv.py` | Mongo-vs-filesystem aggregation equivalence |
| `tests/integration/conftest_mongo.py` | Test fixtures: per-test DB + seeded cohort |

**Modified files:**
| Path | Change |
|---|---|
| `requirements.txt` | Add `motor`, `beanie` |
| `.env.example` | Add `MONGO_URI`, `MONGO_DB`, `USE_MONGO` |
| `src/config.py` | Add `MONGO_URI`, `MONGO_DB`, `USE_MONGO` properties |
| `src/agents/base.py` | Refactor `__call__` to upsert into `AgentRun` |
| `src/orchestrator/graph.py` | End-of-run trace/session writes → `$set` on `AgentRun` |
| `pipeline/gold.py` | `PatientCase.find_one_and_replace(..., upsert=True)` |
| `src/memory/semantic.py` | `consolidate()` → atomic `$inc` on `SemanticMemoryEntry` |
| `doctor_console/backend/app.py` | All aggregation helpers + `result_detail` + `_patient_list_item` + `_memory_ab_comparison` |

**Untouched:** all Pydantic schemas in `src/schemas/`, all prompts in `prompts/`, all Synthea/Bronze/DuckDB code, all Qdrant code (Tier-4 + NICE retrieval), the entire React frontend in `doctor_console/frontend/`.

---

## Phase 0 — Foundation: deps, config, Docker

### Task 1: Add dependencies

**Files:** Modify `requirements.txt`

- [ ] **Step 1: Append Mongo deps**

Edit `requirements.txt`, append:
```
motor>=3.5.0,<4.0.0
beanie>=1.27.0,<2.0.0
```

- [ ] **Step 2: Install**

Run: `pip install -r requirements.txt`
Expected: motor + beanie installed without conflict.

- [ ] **Step 3: Verify versions**

Run: `python -c "import beanie, motor; print(beanie.__version__, motor.__version__)"`
Expected: prints two version strings, no ImportError.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: add motor + beanie for mongodb storage migration"
```

---

### Task 2: Add `docker-compose.yml`

**Files:** Create `docker-compose.yml`

- [ ] **Step 1: Create the file**

```yaml
# docker-compose.yml
# Local-only development services for CMADS.
# Bind to loopback explicitly — no auth, never expose to the public network.
services:
  mongo:
    image: mongo:7
    container_name: cmads-mongo
    ports:
      - "127.0.0.1:27017:27017"
    volumes:
      - ./data/mongo:/data/db
    healthcheck:
      test: ["CMD", "mongosh", "--quiet", "--eval", "db.runCommand({ping:1}).ok"]
      interval: 10s
      timeout: 3s
      retries: 5
    restart: unless-stopped
```

- [ ] **Step 2: Bring it up**

Run: `docker compose up -d mongo`
Expected: container `cmads-mongo` running.

- [ ] **Step 3: Verify connectivity**

Run: `docker exec cmads-mongo mongosh --quiet --eval "db.runCommand({ping:1}).ok"`
Expected output: `1`

- [ ] **Step 4: Add `data/mongo/` to `.gitignore`**

Append to `.gitignore`:
```
# Local Mongo data volume
data/mongo/
```

- [ ] **Step 5: Commit**

```bash
git add docker-compose.yml .gitignore
git commit -m "infra: add local mongo service via docker-compose"
```

---

### Task 3: Config knobs in `src/config.py`

**Files:** Modify `src/config.py`, `.env.example`

- [ ] **Step 1: Add to `.env.example`**

Append:
```
# ══════════════════════════════════════════════════════════
# MONGODB (local development)
# ══════════════════════════════════════════════════════════
MONGO_URI=mongodb://localhost:27017
MONGO_DB=cmads

# Toggle: when true, all runtime reads/writes use MongoDB.
# When false (or unset), the system falls back to the filesystem
# layout in data/gold/. Kept for 30 days post-migration as the
# documented rollback path; removed after the soak window closes.
USE_MONGO=false
```

- [ ] **Step 2: Add config properties**

Open `src/config.py`. After the existing `MEMORY_CASE_TOP_K` property, add:

```python
    # ── MongoDB storage ─────────────────────────────────────
    @property
    def MONGO_URI(self) -> str:
        return _env("MONGO_URI", "mongodb://localhost:27017")

    @property
    def MONGO_DB(self) -> str:
        return _env("MONGO_DB", "cmads")

    @property
    def USE_MONGO(self) -> bool:
        """Master flag for the filesystem→Mongo migration. When false,
        the runtime reads and writes the on-disk JSON tree as before.
        See docs/superpowers/specs/2026-05-22-mongodb-migration-design.md."""
        return _env("USE_MONGO", "false").lower() in ("1", "true", "yes", "on")
```

- [ ] **Step 3: Smoke-test the config**

Run: `python -c "from src.config import cfg; print(cfg.MONGO_URI, cfg.MONGO_DB, cfg.USE_MONGO)"`
Expected: `mongodb://localhost:27017 cmads False`

- [ ] **Step 4: Commit**

```bash
git add src/config.py .env.example
git commit -m "config: add MONGO_URI, MONGO_DB, USE_MONGO knobs"
```

---

## Phase 1 — Beanie document classes (TDD)

### Task 4: `PatientCase` document (TDD)

**Files:**
- Create: `src/db/__init__.py`
- Create: `src/db/documents.py`
- Create: `tests/test_db_documents.py`
- Create: `tests/integration/conftest_mongo.py`

- [ ] **Step 1: Create test fixture for Mongo**

Create `tests/integration/conftest_mongo.py`:

```python
"""Per-test MongoDB fixture — connects to MONGO_URI, uses a unique DB name
per test session, drops the DB on teardown so tests are isolated."""
import os, uuid as _uuid
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from src.config import cfg
from src.db.documents import PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact

@pytest_asyncio.fixture
async def mongo_db():
    """Spin up a fresh Beanie-bound test database for one test."""
    db_name = f"cmads_test_{_uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(cfg.MONGO_URI)
    await init_beanie(
        database=client[db_name],
        document_models=[PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact],
    )
    yield client[db_name]
    await client.drop_database(db_name)
    client.close()
```

- [ ] **Step 2: Write the failing test for `PatientCase`**

Create `tests/test_db_documents.py`:

```python
"""Unit tests for Beanie Document classes."""
import pytest
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_patient_case_roundtrip(mongo_db):
    """A PatientCase saved with all field types round-trips identically."""
    from src.db.documents import PatientCase

    doc = PatientCase(
        id="abc-123",
        person_id=4388,
        cutoff_date=datetime(2021, 10, 18),
        case_type="ehr+lab",
        demographics={"age": 62, "gender": "F", "race": "white"},
        conditions={"active": [{"name": "T2DM"}], "history": []},
        medications={"active": [{"medication": "metformin"}], "history": []},
        visits=[],
        comorbidity={"has_dm": True},
        risk_scores={"ascvd_10yr": 12.3},
        labs={"recent_vitals": [], "latest_labs": [], "critical_flags": []},
        ground_truth={"target_condition": {"name": "Diabetes mellitus type 2"}},
        case_stats={"activeConditions": 1, "activeMedications": 1, "labTrends": 0, "criticalFlags": 0},
        assembled_at=datetime.utcnow(),
        pipeline_version="gold-3.4",
    )
    await doc.insert()

    loaded = await PatientCase.get("abc-123")
    assert loaded is not None
    assert loaded.demographics["age"] == 62
    assert loaded.ground_truth["target_condition"]["name"] == "Diabetes mellitus type 2"
    assert loaded.case_stats["activeConditions"] == 1
```

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_db_documents.py::test_patient_case_roundtrip -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.db'`

- [ ] **Step 4: Create `src/db/__init__.py`**

Create empty `src/db/__init__.py`:
```python
```

- [ ] **Step 5: Create `src/db/documents.py` with `PatientCase` only**

```python
"""Beanie Document classes for the MongoDB storage layer.

Schema mirrors docs/superpowers/specs/2026-05-22-mongodb-migration-design.md §5.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any
from beanie import Document
from pydantic import Field
from pymongo import IndexModel


class PatientCase(Document):
    id: str = Field(alias="_id")          # patient_uuid
    person_id: int
    cutoff_date: datetime
    case_type: str
    demographics: dict[str, Any]
    conditions: dict[str, Any]
    medications: dict[str, Any]
    visits: list[dict[str, Any]]
    comorbidity: dict[str, Any]
    risk_scores: dict[str, Any]
    labs: dict[str, Any]
    ground_truth: dict[str, Any]
    case_stats: dict[str, Any]
    assembled_at: datetime
    pipeline_version: str

    class Settings:
        name = "patient_cases"
        indexes = ["ground_truth.target_condition.name"]
```

- [ ] **Step 6: Run test again — still fails (other docs missing)**

Run: `pytest tests/test_db_documents.py::test_patient_case_roundtrip -v`
Expected: FAIL importing `AgentRun, SemanticMemoryEntry, DerivedArtefact` in the fixture.

- [ ] **Step 7: Add the other three Document stubs to `src/db/documents.py`**

Append:

```python
class AgentRun(Document):
    """Per-(result_set, patient_uuid) aggregate document. One row =
    one full patient run with every agent's output embedded under
    `agents.<agent_id>`. Schema §5.2 of the design spec.

    Note: the spec's compound `_id = {result_set, patient_uuid}` is
    implemented here as a UNIQUE compound index on two separate fields,
    because Beanie ergonomics prefer a single-value `_id` (auto-assigned
    ObjectId) over a compound document. The uniqueness guarantee is the
    same; the field-level access just reads more naturally as
    `doc.result_set` than `doc.id.result_set`."""
    result_set: str
    patient_uuid: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_s: float | None = None
    pipeline_version: str = ""
    model_config: dict[str, Any] = Field(default_factory=dict)
    agents: dict[str, dict[str, Any]] = Field(default_factory=dict)
    execution_trace: list[dict[str, Any]] = Field(default_factory=list)
    session_memory: list[dict[str, Any]] = Field(default_factory=list)
    canonicalizer_fired: bool = False

    class Settings:
        name = "agent_runs"
        indexes = [
            IndexModel([("result_set", 1), ("patient_uuid", 1)], unique=True),
            [("result_set", 1), ("agents.evaluation.output.match_type", 1)],
            [("patient_uuid", 1)],
            [("agents.final_diagnosis.output.primary_diagnosis", 1)],
        ]


class SemanticMemoryEntry(Document):
    """One document per disease. Per-disease counts updated by the
    Stage-7 memory consolidator. Schema §5.3."""
    id: str = Field(alias="_id")          # disease name (verbatim Synthea label)
    counts: dict[str, int] = Field(default_factory=dict)
    rank1_when_found: int = 0
    evidence_patterns: list[dict[str, Any]] = Field(default_factory=list)
    updated_at: datetime

    class Settings:
        name = "semantic_memory"


class DerivedArtefact(Document):
    """Catch-all for derived JSON (paired_160_mcnemar, sensitivity
    summaries, cohort_summary:<result_set>, ...). Schema §5.4."""
    id: str = Field(alias="_id")
    payload: dict[str, Any]
    produced_by: str
    produced_at: datetime
    source_cohort: str | None = None

    class Settings:
        name = "derived_artefacts"
```

- [ ] **Step 8: Run test — now passes**

Run: `pytest tests/test_db_documents.py::test_patient_case_roundtrip -v`
Expected: PASS in <2 s.

- [ ] **Step 9: Commit**

```bash
git add src/db tests/test_db_documents.py tests/integration/conftest_mongo.py
git commit -m "db: add Beanie Document classes with patient_case roundtrip test"
```

---

### Task 5: `AgentRun` compound-key test

**Files:** Modify `tests/test_db_documents.py`

- [ ] **Step 1: Add the failing test**

Append to `tests/test_db_documents.py`:

```python
@pytest.mark.asyncio
async def test_agent_run_compound_lookup(mongo_db):
    """AgentRun is keyed by (result_set, patient_uuid). Both halves of
    the key must be queryable via the index without scanning."""
    from src.db.documents import AgentRun
    from datetime import datetime

    doc = AgentRun(
        result_set="mas_results_improved_b3",
        patient_uuid="uuid-1",
        started_at=datetime.utcnow(),
        agents={"ehr_analyst": {"status": "success", "output": {"x": 1}}},
    )
    await doc.insert()

    # By result_set + patient_uuid (the primary access pattern)
    loaded = await AgentRun.find_one(
        AgentRun.result_set == "mas_results_improved_b3",
        AgentRun.patient_uuid == "uuid-1",
    )
    assert loaded is not None
    assert loaded.agents["ehr_analyst"]["output"]["x"] == 1

    # By patient_uuid alone (cross-cohort lookup)
    cross = await AgentRun.find(AgentRun.patient_uuid == "uuid-1").to_list()
    assert len(cross) == 1
```

- [ ] **Step 2: Run — expect PASS (no implementation change needed)**

Run: `pytest tests/test_db_documents.py::test_agent_run_compound_lookup -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_db_documents.py
git commit -m "test: agent_run compound-key lookup test"
```

---

### Task 6: Atomic `$set` on nested agent envelope

**Files:** Modify `tests/test_db_documents.py`

- [ ] **Step 1: Failing test**

Append:

```python
@pytest.mark.asyncio
async def test_agent_envelope_partial_update(mongo_db):
    """Each agent should be able to write only its own slot without
    touching siblings. This is the atomicity guarantee the design depends on."""
    from src.db.documents import AgentRun
    from datetime import datetime

    await AgentRun(
        result_set="r1",
        patient_uuid="u1",
        started_at=datetime.utcnow(),
        agents={
            "ehr_analyst":     {"status": "success", "output": {"a": 1}},
            "lab_interpreter": {"status": "success", "output": {"b": 2}},
        },
    ).insert()

    # Refiner writes ONLY its envelope. Sibling agents must survive.
    await AgentRun.find_one(
        AgentRun.result_set == "r1", AgentRun.patient_uuid == "u1",
    ).update({"$set": {"agents.final_diagnosis": {"status": "success", "output": {"c": 3}}}})

    after = await AgentRun.find_one(AgentRun.result_set == "r1", AgentRun.patient_uuid == "u1")
    assert after.agents["ehr_analyst"]["output"]["a"] == 1
    assert after.agents["lab_interpreter"]["output"]["b"] == 2
    assert after.agents["final_diagnosis"]["output"]["c"] == 3
```

- [ ] **Step 2: Run — expect PASS**

Run: `pytest tests/test_db_documents.py::test_agent_envelope_partial_update -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_db_documents.py
git commit -m "test: agent envelope partial update preserves siblings"
```

---

## Phase 2 — Mongo client module

### Task 7: `src/db/mongo.py` init module (TDD)

**Files:**
- Create: `src/db/mongo.py`
- Modify: `tests/test_db_documents.py`

- [ ] **Step 1: Failing test**

Append to `tests/test_db_documents.py`:

```python
@pytest.mark.asyncio
async def test_init_db_initialises_all_collections():
    """init_db() should bind all four collections to Beanie."""
    from motor.motor_asyncio import AsyncIOMotorClient
    from src.config import cfg
    from src.db.mongo import init_db
    from src.db.documents import PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact

    test_db = f"cmads_test_init_{__import__('uuid').uuid4().hex[:6]}"
    client = AsyncIOMotorClient(cfg.MONGO_URI)
    try:
        await init_db(client[test_db])
        # If init succeeded, we can insert + retrieve from all 4 collections.
        from datetime import datetime
        await PatientCase(id="x", person_id=1, cutoff_date=datetime.utcnow(),
                          case_type="ehr+lab", demographics={}, conditions={},
                          medications={}, visits=[], comorbidity={}, risk_scores={},
                          labs={}, ground_truth={}, case_stats={},
                          assembled_at=datetime.utcnow(), pipeline_version="t").insert()
        assert await PatientCase.get("x") is not None
    finally:
        await client.drop_database(test_db)
        client.close()
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/test_db_documents.py::test_init_db_initialises_all_collections -v`
Expected: FAIL with `cannot import name 'init_db' from 'src.db.mongo'`.

- [ ] **Step 3: Implement `src/db/mongo.py`**

```python
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
)

_DOCUMENT_MODELS = [PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact]
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


def get_sync_db() -> Any:
    """Synchronous bootstrap for scripts. Initialises the global client
    and runs ``init_db`` once via ``asyncio.run``. Subsequent calls in
    the same process are idempotent."""
    global _client
    if _client is None:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(init_db())
    return _client[cfg.MONGO_DB]
```

- [ ] **Step 4: Run test — should pass**

Run: `pytest tests/test_db_documents.py::test_init_db_initialises_all_collections -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db/mongo.py tests/test_db_documents.py
git commit -m "db: add mongo client lifecycle module (init_db, get_sync_db)"
```

---

## Phase 3 — Backfill script (TDD)

### Task 8: Skeleton CLI

**Files:** Create `scripts/migrate_filesystem_to_mongo.py`, create `tests/integration/test_migrate_filesystem.py`

- [ ] **Step 1: Failing test — CLI parses --dry-run**

Create `tests/integration/test_migrate_filesystem.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_dry_run_help_works -v`
Expected: FAIL (file does not exist).

- [ ] **Step 3: Implement minimal CLI**

Create `scripts/migrate_filesystem_to_mongo.py`:

```python
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
```

- [ ] **Step 4: Make it executable**

Run: `chmod +x scripts/migrate_filesystem_to_mongo.py`

- [ ] **Step 5: Run test — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_dry_run_help_works -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: backfill script CLI skeleton with --help working"
```

---

### Task 9: Discover artefacts (read side, no Mongo)

**Files:** Modify `scripts/migrate_filesystem_to_mongo.py`, add tests

- [ ] **Step 1: Failing test for filesystem discovery**

Append to `tests/integration/test_migrate_filesystem.py`:

```python
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
```

- [ ] **Step 2: Run — expect ImportError**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_walk_mas_results_finds_expected_directories -v`
Expected: FAIL (`walk_mas_results` not found).

- [ ] **Step 3: Implement walk + load helpers**

Add to `scripts/migrate_filesystem_to_mongo.py` above `main_async`:

```python
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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_walk_mas_results_finds_expected_directories -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: filesystem discovery + patient-run loader"
```

---

### Task 10: `--dry-run` mode

**Files:** Modify `scripts/migrate_filesystem_to_mongo.py`, tests

- [ ] **Step 1: Failing test**

Append to `tests/integration/test_migrate_filesystem.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL (NotImplementedError raised)**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_dry_run_emits_report_without_touching_mongo -v`
Expected: FAIL.

- [ ] **Step 3: Implement `main_async` for dry-run only**

Replace `main_async` in `scripts/migrate_filesystem_to_mongo.py`:

```python
async def main_async(args: argparse.Namespace) -> int:
    gold = args.gold_dir
    patient_runs = walk_mas_results(gold)
    patient_cases = [p.name for p in (gold / "patient_cases").iterdir()
                     if (gold / "patient_cases" / p.name).is_dir()] if (gold / "patient_cases").exists() else []
    semantic_path = gold / "memory" / "semantic_memory.json"
    derived = [p.name for p in gold.glob("*.json")] if gold.exists() else []

    report = {
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

    raise NotImplementedError("Real migration implemented in Task 11+.")
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_dry_run_emits_report_without_touching_mongo -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: --dry-run mode emits structured report"
```

---

### Task 11: Real migration — `agent_runs` upserts

**Files:** Modify `scripts/migrate_filesystem_to_mongo.py`, tests

- [ ] **Step 1: Failing test — real migration writes to Mongo**

Append to `tests/integration/test_migrate_filesystem.py`:

```python
import pytest
import pytest_asyncio

pytest_plugins = ["tests.integration.conftest_mongo"]


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
```

- [ ] **Step 2: Run — expect FAIL (`migrate_patient_runs` not found)**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_real_migration_inserts_agent_runs -v`
Expected: FAIL.

- [ ] **Step 3: Implement `migrate_patient_runs`**

Append to `scripts/migrate_filesystem_to_mongo.py`:

```python
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
```

Update `main_async` to call `init_db` then `migrate_patient_runs` when not in dry-run:

```python
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
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_real_migration_inserts_agent_runs -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: real-mode agent_runs upsert with idempotency"
```

---

### Task 12: `patient_cases` migration

**Files:** Modify migrate script + tests

- [ ] **Step 1: Failing test**

Append:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_migrate_patient_cases -v`
Expected: FAIL.

- [ ] **Step 3: Implement `migrate_patient_cases`**

Append to `scripts/migrate_filesystem_to_mongo.py`:

```python
from src.db.documents import PatientCase


async def migrate_patient_cases(gold_dir: Path) -> int:
    """Load ehr_case.json + lab_case.json + ground_truth.json per
    UUID and upsert as a single PatientCase document."""
    root = gold_dir / "patient_cases"
    if not root.exists():
        return 0
    count = 0
    for sub in sorted(root.iterdir()):
        if not sub.is_dir():
            continue
        ehr_path = sub / "ehr_case.json"
        if not ehr_path.exists():
            continue
        ehr = json.loads(ehr_path.read_text())
        lab_path = sub / "lab_case.json"
        lab = json.loads(lab_path.read_text()) if lab_path.exists() else {}
        gt_path = sub / "ground_truth.json"
        gt = json.loads(gt_path.read_text()) if gt_path.exists() else {}
        case_stats = {
            "activeConditions":  len((ehr.get("conditions",  {}) or {}).get("active", []) or []),
            "activeMedications": len((ehr.get("medications", {}) or {}).get("active", []) or []),
            "labTrends":         len((lab.get("latest_labs")  or [])),
            "criticalFlags":     len((lab.get("critical_flags") or [])),
        }
        doc = PatientCase(
            id=sub.name,
            person_id=int(ehr.get("person_id", 0)),
            cutoff_date=datetime.fromisoformat(str(ehr.get("cutoff_date", "1970-01-01"))[:10]),
            case_type=str(ehr.get("case_type", "ehr+lab")),
            demographics=ehr.get("demographics", {}),
            conditions=ehr.get("conditions", {}),
            medications=ehr.get("medications", {}),
            visits=ehr.get("visits", []),
            comorbidity=ehr.get("comorbidity", {}),
            risk_scores=ehr.get("risk_scores", {}),
            labs=lab,
            ground_truth=gt,
            case_stats=case_stats,
            assembled_at=datetime.utcnow(),
            pipeline_version="gold-3.4",
        )
        await PatientCase.find_one(PatientCase.id == sub.name).upsert(
            {"$set": doc.model_dump(by_alias=True, exclude={"_id"})},
            on_insert=doc,
        )
        count += 1
    return count
```

Hook into `main_async` right after `migrate_patient_runs`:

```python
    report["patient_cases_inserted"] = await migrate_patient_cases(gold)
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_migrate_patient_cases -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: patient_cases backfill from gold JSON tree"
```

---

### Task 13: `semantic_memory` + `derived_artefacts` migration

**Files:** Modify migrate script + tests

- [ ] **Step 1: Failing test**

Append:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_migrate_semantic_and_derived -v`
Expected: FAIL.

- [ ] **Step 3: Implement migrators**

Append:

```python
from src.db.documents import SemanticMemoryEntry, DerivedArtefact


async def migrate_semantic_memory(gold_dir: Path) -> int:
    path = gold_dir / "memory" / "semantic_memory.json"
    if not path.exists():
        return 0
    data = json.loads(path.read_text())
    count = 0
    for disease, payload in data.items():
        doc = SemanticMemoryEntry(
            id=disease,
            counts=payload.get("counts", {}),
            rank1_when_found=payload.get("rank1_when_found", 0),
            evidence_patterns=payload.get("evidence_patterns", []),
            updated_at=datetime.utcnow(),
        )
        await SemanticMemoryEntry.find_one(SemanticMemoryEntry.id == disease).upsert(
            {"$set": doc.model_dump(by_alias=True, exclude={"_id"})},
            on_insert=doc,
        )
        count += 1
    return count


async def migrate_derived_artefacts(gold_dir: Path) -> int:
    """Pick up any top-level data/gold/*.json that isn't directly handled
    by the other migrators (e.g. paired_160_mcnemar.json, sensitivity
    summaries). Skips known-internal helpers like migration_progress.json."""
    SKIP = {"migration_progress.json", "migration_report.json"}
    count = 0
    for p in sorted(gold_dir.glob("*.json")):
        if p.name in SKIP:
            continue
        payload = json.loads(p.read_text())
        key = p.stem
        doc = DerivedArtefact(
            id=key,
            payload=payload,
            produced_by="scripts/migrate_filesystem_to_mongo.py",
            produced_at=datetime.utcnow(),
        )
        await DerivedArtefact.find_one(DerivedArtefact.id == key).upsert(
            {"$set": doc.model_dump(by_alias=True, exclude={"_id"})},
            on_insert=doc,
        )
        count += 1
    return count
```

Hook into `main_async`:
```python
    report["semantic_memory_inserted"] = await migrate_semantic_memory(gold)
    report["derived_artefacts_inserted"] = await migrate_derived_artefacts(gold)
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_migrate_semantic_and_derived -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: semantic_memory + derived_artefacts backfill"
```

---

### Task 14: `--verify` mode (SHA-256 round-trip)

**Files:** Modify migrate script + tests

- [ ] **Step 1: Failing test**

Append:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_verify_detects_intact_roundtrip -v`
Expected: FAIL.

- [ ] **Step 3: Implement verifier**

Append to `scripts/migrate_filesystem_to_mongo.py`:

```python
import hashlib


def _stable_json(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def _sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


async def verify_patient_runs(gold_dir: Path, sample_all: bool = False) -> list[dict]:
    """For every patient run on disk, reload it, then compare a SHA-256
    digest of its assembled payload against the corresponding Mongo
    document's same fields. Returns the list of divergences (empty on
    a clean migration)."""
    import random
    runs = walk_mas_results(gold_dir)
    if not sample_all:
        # 10% sample
        runs = random.sample(runs, max(1, len(runs) // 10))
    divergences: list[dict] = []
    for result_set, patient_uuid in runs:
        disk = load_patient_run(gold_dir, result_set, patient_uuid)
        doc = await AgentRun.find_one(
            AgentRun.result_set == result_set,
            AgentRun.patient_uuid == patient_uuid,
        )
        if doc is None:
            divergences.append({"result_set": result_set, "patient_uuid": patient_uuid,
                                "reason": "no_mongo_doc"})
            continue
        for key in ("agents", "execution_trace", "session_memory"):
            disk_hash = _sha256(_stable_json(disk[key]))
            mongo_hash = _sha256(_stable_json(getattr(doc, key)))
            if disk_hash != mongo_hash:
                divergences.append({"result_set": result_set, "patient_uuid": patient_uuid,
                                    "field": key, "disk": disk_hash, "mongo": mongo_hash})
    return divergences
```

Hook into `main_async`:
```python
    if args.verify or args.verify_all:
        divs = await verify_patient_runs(gold, sample_all=args.verify_all)
        report["verifier_divergences"] = divs
        if divs:
            print(f"WARNING: {len(divs)} divergences", file=sys.stderr)
            return 2
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_migrate_filesystem.py::test_verify_detects_intact_roundtrip -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_filesystem_to_mongo.py tests/integration/test_migrate_filesystem.py
git commit -m "migrate: --verify mode with SHA-256 round-trip check"
```

---

## Phase 4 — Read-path equivalence tests (TDD baseline)

These tests are the safety net. They lock in that Mongo aggregations return identical numbers to the existing filesystem aggregations. Run them on the live cohort before flipping `USE_MONGO`.

### Task 15: Baseline snapshot of current filesystem aggregations

**Files:** Create `tests/integration/test_app_aggregations_equiv.py`

- [ ] **Step 1: Capture the current numbers as the gold reference**

Create `tests/integration/test_app_aggregations_equiv.py`:

```python
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
```

- [ ] **Step 2: Run to confirm baselines compile**

Run: `pytest tests/integration/test_app_aggregations_equiv.py -v`
Expected: PASS (the baseline-documenting test).

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_app_aggregations_equiv.py
git commit -m "test: pin pre-migration baseline numbers for equivalence checks"
```

---

### Task 16: Mongo aggregation: `_aggregate_result_set`

**Files:**
- Modify: `doctor_console/backend/app.py`
- Modify: `tests/integration/test_app_aggregations_equiv.py`

- [ ] **Step 1: Failing test — Mongo aggregate matches baseline**

Replace the placeholder in `test_app_aggregations_equiv.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL (`_aggregate_result_set_mongo` not found)**

Run: `pytest tests/integration/test_app_aggregations_equiv.py::test_overview_multi_level_direct_unchanged -v`
Expected: FAIL.

- [ ] **Step 3: Implement Mongo aggregation in `app.py`**

Open `doctor_console/backend/app.py`. Above the existing `_aggregate_result_set` function, add:

```python
async def _aggregate_result_set_mongo(
    result_sets: list[str],
    uuid_filter: "set[str] | None" = None,
) -> dict[str, Any]:
    """Mongo-backed counterpart of _aggregate_result_set. Uses the
    indexed (result_set, agents.evaluation.output.match_type) index for
    sub-100ms aggregates even at 100k documents."""
    from src.db.documents import AgentRun
    match_stage: dict[str, Any] = {"result_set": {"$in": result_sets}}
    if uuid_filter is not None:
        match_stage["patient_uuid"] = {"$in": sorted(uuid_filter)}
    pipeline = [
        {"$match": match_stage},
        # Deduplicate UUIDs across the union (multi_level joins 3 dirs).
        {"$group": {"_id": "$patient_uuid", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$group": {
            "_id": None,
            "n":        {"$sum": 1},
            "direct":   {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "DIRECT"]},   1, 0]}},
            "indirect": {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "INDIRECT"]}, 1, 0]}},
            "miss":     {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "MISS"]},     1, 0]}},
            "rank1":    {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$agents.evaluation.output.match_type", ["DIRECT", "INDIRECT"]]},
                    {"$eq": ["$agents.evaluation.output.rank", 1]},
                ]},
                1, 0]}},
            "rank2":    {"$sum": {"$cond": [
                {"$and": [
                    {"$in": ["$agents.evaluation.output.match_type", ["DIRECT", "INDIRECT"]]},
                    {"$in": ["$agents.evaluation.output.rank", [1, 2]]},
                ]},
                1, 0]}},
            "duration_total": {"$sum": "$duration_s"},
            "durations":      {"$push": "$duration_s"},
        }},
    ]
    rows = await AgentRun.aggregate(pipeline).to_list()
    if not rows:
        return {"n": 0, "direct": 0, "indirect": 0, "miss": 0, "found": 0, "rank1": 0,
                "directPct": 0.0, "indirectPct": 0.0, "missPct": 0.0, "foundPct": 0.0,
                "rank1PctOfFound": 0.0, "rank2PctOfFound": 0.0,
                "avgTimeS": 0.0, "medianTimeS": 0.0}
    row = rows[0]
    n = row["n"]; direct = row["direct"]; indirect = row["indirect"]; miss = row["miss"]
    found = direct + indirect
    durs = sorted(d for d in (row.get("durations") or []) if isinstance(d, (int, float)))
    median = durs[len(durs)//2] if durs else 0.0
    avg = (row.get("duration_total") or 0.0) / len(durs) if durs else 0.0
    return {
        "n": n, "direct": direct, "indirect": indirect, "miss": miss,
        "found": found, "rank1": row["rank1"], "rank2": row.get("rank2", 0),
        "directPct":        100.0 * direct   / n if n else 0.0,
        "indirectPct":      100.0 * indirect / n if n else 0.0,
        "missPct":          100.0 * miss     / n if n else 0.0,
        "foundPct":         100.0 * found    / n if n else 0.0,
        "rank1PctOfFound":  100.0 * row["rank1"]        / found if found else 0.0,
        "rank2PctOfFound":  100.0 * row.get("rank2", 0) / found if found else 0.0,
        "avgTimeS": avg, "medianTimeS": median,
    }
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/integration/test_app_aggregations_equiv.py::test_overview_multi_level_direct_unchanged -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_app_aggregations_equiv.py
git commit -m "backend: mongo _aggregate_result_set_mongo with equivalence test"
```

---

### Task 17: Mongo aggregation: `_rank_distribution` + `_per_disease_breakdown` + `_top_diagnoses`

**Files:** Modify `doctor_console/backend/app.py`, tests

- [ ] **Step 1: Failing tests**

Append to `tests/integration/test_app_aggregations_equiv.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_app_aggregations_equiv.py::test_rank_distribution_buckets tests/integration/test_app_aggregations_equiv.py::test_per_disease_breakdown_groups_by_target -v`
Expected: FAIL.

- [ ] **Step 3: Implement the two Mongo helpers**

Append to `app.py`:

```python
async def _rank_distribution_mongo(
    result_sets: list[str],
    uuid_filter: "set[str] | None" = None,
) -> list[dict[str, Any]]:
    from src.db.documents import AgentRun
    match: dict[str, Any] = {"result_set": {"$in": result_sets}}
    if uuid_filter is not None:
        match["patient_uuid"] = {"$in": sorted(uuid_filter)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$patient_uuid", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$project": {
            "bucket": {"$switch": {"branches": [
                {"case": {"$eq": ["$agents.evaluation.output.match_type", "MISS"]}, "then": "miss"},
                {"case": {"$eq": ["$agents.evaluation.output.rank", 1]}, "then": "1"},
                {"case": {"$eq": ["$agents.evaluation.output.rank", 2]}, "then": "2"},
                {"case": {"$eq": ["$agents.evaluation.output.rank", 3]}, "then": "3"},
                {"case": {"$in": ["$agents.evaluation.output.rank", [4, 5]]}, "then": "4-5"},
            ], "default": "miss"}},
        }},
        {"$group": {"_id": "$bucket", "count": {"$sum": 1}}},
    ]
    rows = await AgentRun.aggregate(pipeline).to_list()
    counts = {r["_id"]: r["count"] for r in rows}
    return [{"label": k, "count": counts.get(k, 0)}
            for k in ("1", "2", "3", "4-5", "miss")]


async def _per_disease_breakdown_mongo(
    result_sets: list[str],
    uuid_filter: "set[str] | None" = None,
) -> list[dict[str, Any]]:
    from src.db.documents import AgentRun
    match: dict[str, Any] = {"result_set": {"$in": result_sets}}
    if uuid_filter is not None:
        match["patient_uuid"] = {"$in": sorted(uuid_filter)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$patient_uuid", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$lookup": {"from": "patient_cases", "localField": "patient_uuid",
                     "foreignField": "_id", "as": "case"}},
        {"$addFields": {"case": {"$arrayElemAt": ["$case", 0]}}},
        {"$group": {
            "_id": "$case.ground_truth.target_condition.name",
            "n":        {"$sum": 1},
            "direct":   {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "DIRECT"]},   1, 0]}},
            "indirect": {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "INDIRECT"]}, 1, 0]}},
            "miss":     {"$sum": {"$cond": [{"$eq": ["$agents.evaluation.output.match_type", "MISS"]},     1, 0]}},
            "ranks":    {"$push": "$agents.evaluation.output.rank"},
        }},
    ]
    rows = await AgentRun.aggregate(pipeline).to_list()
    out: list[dict[str, Any]] = []
    for r in rows:
        n = r["n"]; found = r["direct"] + r["indirect"]
        ranks = [v for v in r.get("ranks") or [] if isinstance(v, int) and v > 0]
        avg_rank = sum(ranks) / len(ranks) if ranks else None
        out.append({
            "disease": r["_id"] or "Unknown",
            "n": n,
            "direct":   r["direct"],
            "indirect": r["indirect"],
            "miss":     r["miss"],
            "foundPct": (100.0 * found / n) if n else 0.0,
            "avgRank":  avg_rank,
        })
    return out


async def _top_diagnoses_mongo(
    result_sets: list[str],
    uuid_filter: "set[str] | None" = None,
    top: int = 8,
) -> list[dict[str, Any]]:
    from src.db.documents import AgentRun
    match: dict[str, Any] = {"result_set": {"$in": result_sets}}
    if uuid_filter is not None:
        match["patient_uuid"] = {"$in": sorted(uuid_filter)}
    pipeline = [
        {"$match": match},
        {"$group": {"_id": "$patient_uuid", "doc": {"$first": "$$ROOT"}}},
        {"$replaceRoot": {"newRoot": "$doc"}},
        {"$group": {"_id": "$agents.final_diagnosis.output.primary_diagnosis",
                    "count": {"$sum": 1}}},
        {"$sort": {"count": -1}},
        {"$limit": top},
    ]
    rows = await AgentRun.aggregate(pipeline).to_list()
    return [{"diagnosis": r["_id"] or "?", "count": r["count"]} for r in rows]
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_app_aggregations_equiv.py -v -k "rank_distribution or per_disease"`
Expected: PASS for both tests.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_app_aggregations_equiv.py
git commit -m "backend: mongo rank_distribution + per_disease + top_diagnoses aggregations"
```

---

### Task 18: Mongo helper: `_patient_list_item_mongo` + `_result_detail_mongo`

**Files:** Modify `doctor_console/backend/app.py`, tests

- [ ] **Step 1: Failing test**

Append:

```python
@pytest.mark.asyncio
async def test_result_detail_mongo_serves_canon_when_present(mongo_db):
    """When agents.evaluation.output_canon exists, the detail helper
    returns it as the evaluation; same for final_diagnosis."""
    from src.db.documents import AgentRun, PatientCase
    from doctor_console.backend.app import _result_detail_mongo
    from datetime import datetime

    await PatientCase(id="u1", person_id=1, cutoff_date=datetime.utcnow(),
                       case_type="ehr+lab", demographics={}, conditions={},
                       medications={}, visits=[], comorbidity={}, risk_scores={},
                       labs={}, ground_truth={"target_condition": {"name": "ESRD"}},
                       case_stats={}, assembled_at=datetime.utcnow(),
                       pipeline_version="t").insert()
    await AgentRun(
        result_set="r", patient_uuid="u1", started_at=datetime.utcnow(),
        agents={
            "evaluation": {
                "status": "success",
                "output":       {"match_type": "INDIRECT", "rank": 2},
                "output_canon": {"match_type": "DIRECT",   "rank": 1, "matched_diagnosis": "ESRD"},
            },
            "final_diagnosis": {"status": "success",
                                 "output": {"primary_diagnosis": "CKD stage 4"},
                                 "output_canon": {"primary_diagnosis": "End-stage renal disease"}},
        },
    ).insert()

    detail = await _result_detail_mongo("r", "u1")
    assert detail["evaluation"]["match_type"] == "DIRECT"
    assert detail["finalDiagnosis"]["primary_diagnosis"] == "End-stage renal disease"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_app_aggregations_equiv.py::test_result_detail_mongo_serves_canon_when_present -v`
Expected: FAIL.

- [ ] **Step 3: Implement helpers**

Append to `app.py`:

```python
async def _patient_list_item_mongo(result_set: str, patient_uuid: str) -> dict[str, Any]:
    from src.db.documents import AgentRun, PatientCase
    run = await AgentRun.find_one(
        AgentRun.result_set == result_set, AgentRun.patient_uuid == patient_uuid,
    )
    case = await PatientCase.get(patient_uuid)
    eval_envelope = (run.agents.get("evaluation") if run else {}) or {}
    evaluation = eval_envelope.get("output_canon") or eval_envelope.get("output") or {}
    final_dx = (run.agents.get("final_diagnosis") or {}).get("output_canon") \
              or (run.agents.get("final_diagnosis") or {}).get("output") \
              or {} if run else {}
    return {
        "uuid": patient_uuid,
        "age":    (case.demographics if case else {}).get("age"),
        "gender": (case.demographics if case else {}).get("gender"),
        "race":   (case.demographics if case else {}).get("race"),
        "hasRun": run is not None,
        "matchType":        evaluation.get("match_type"),
        "primaryDiagnosis": final_dx.get("primary_diagnosis"),
        "durationS":        run.duration_s if run else None,
    }


async def _result_detail_mongo(result_set: str, patient_uuid: str) -> dict[str, Any]:
    from src.db.documents import AgentRun, PatientCase
    run = await AgentRun.find_one(
        AgentRun.result_set == result_set, AgentRun.patient_uuid == patient_uuid,
    )
    if run is None:
        raise HTTPException(status_code=404,
                            detail=f"No saved run for {patient_uuid} in {result_set}")
    case = await PatientCase.get(patient_uuid)
    # Prefer canon variants where present (matches filesystem behaviour).
    eval_envelope = run.agents.get("evaluation") or {}
    evaluation = eval_envelope.get("output_canon") or eval_envelope.get("output") or {}
    final_envelope = run.agents.get("final_diagnosis") or {}
    final_dx = final_envelope.get("output_canon") or final_envelope.get("output") or {}

    return {
        "patient": (case.model_dump() if case else {"uuid": patient_uuid}),
        "resultSet": {"id": result_set, "label": result_set,
                       "category": "", "model": "", "path": "", "patientCount": 0,
                       "runtime": False},
        "case":            (case.model_dump() if case else {}),
        "evaluation":      evaluation,
        "finalDiagnosis":  final_dx,
        "treatment":       (run.agents.get("treatment_planning") or {}).get("output") or {},
        "agentOutputs":    {aid: env.get("output") for aid, env in run.agents.items()},
        "trace":           {"agents": run.execution_trace, "duration_s": run.duration_s},
        "sessionMemory":   run.session_memory,
    }
```

(The existing `_result_set_meta`, `_agent_cards`, `_agent_doctor_view` continue to work — those operate on the outputs dict, not the filesystem, and remain unchanged.)

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_app_aggregations_equiv.py::test_result_detail_mongo_serves_canon_when_present -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_app_aggregations_equiv.py
git commit -m "backend: mongo result_detail + patient_list_item with canon preference"
```

---

### Task 19: Wire `USE_MONGO` flag into FastAPI handlers

**Files:** Modify `doctor_console/backend/app.py`

- [ ] **Step 1: Update `lifespan` to call `init_db` when flag is on**

In `doctor_console/backend/app.py`, find the FastAPI app instantiation (search for `app = FastAPI(`). Add (or update) a lifespan handler above it:

```python
from contextlib import asynccontextmanager
from src.config import cfg

@asynccontextmanager
async def lifespan(app: FastAPI):
    if cfg.USE_MONGO:
        from src.db.mongo import init_db
        await init_db()
    yield

# ... existing `app = FastAPI(...)` becomes `app = FastAPI(..., lifespan=lifespan)`
```

- [ ] **Step 2: Switch `_aggregate_result_set` to delegate to Mongo when flag is on**

Replace the existing `_aggregate_result_set` body with a dispatcher:

```python
async def _aggregate_result_set(
    result_dir,  # Path | list[Path] | str | list[str]
    uuid_filter: "set[str] | None" = None,
) -> dict[str, Any]:
    if cfg.USE_MONGO:
        if isinstance(result_dir, list):
            ids = [p.name if hasattr(p, "name") else str(p) for p in result_dir]
        else:
            ids = [result_dir.name if hasattr(result_dir, "name") else str(result_dir)]
        return await _aggregate_result_set_mongo(ids, uuid_filter)
    # Fallback: existing filesystem code, unchanged.
    return _aggregate_result_set_fs(result_dir, uuid_filter)
```

Rename the original filesystem function to `_aggregate_result_set_fs` (search-and-replace the function definition only — the call sites all go through the new dispatcher).

- [ ] **Step 3: Add the dispatcher for each of the remaining 5 helpers**

Each function below: (a) rename the existing implementation to `<name>_fs`, (b) add a thin async wrapper. The wrappers are async — every caller route handler in the API layer (`/api/stats/overview`, `/api/patients`, `/api/results/{result_set}/{patient_uuid}`, `/api/comparisons/memory-ab`) must be converted from `def` to `async def` and use `await` on the call site. FastAPI accepts both.

```python
async def _rank_distribution(
    result_dir, uuid_filter: "set[str] | None" = None,
) -> list[dict[str, Any]]:
    if cfg.USE_MONGO:
        ids = [p.name if hasattr(p, "name") else str(p)
               for p in (result_dir if isinstance(result_dir, list) else [result_dir])]
        return await _rank_distribution_mongo(ids, uuid_filter)
    return _rank_distribution_fs(result_dir, uuid_filter)


async def _per_disease_breakdown(
    result_dir, uuid_filter: "set[str] | None" = None,
) -> list[dict[str, Any]]:
    if cfg.USE_MONGO:
        ids = [p.name if hasattr(p, "name") else str(p)
               for p in (result_dir if isinstance(result_dir, list) else [result_dir])]
        return await _per_disease_breakdown_mongo(ids, uuid_filter)
    return _per_disease_breakdown_fs(result_dir, uuid_filter)


async def _top_diagnoses(
    result_dir, uuid_filter: "set[str] | None" = None, top: int = 8,
) -> list[dict[str, Any]]:
    if cfg.USE_MONGO:
        ids = [p.name if hasattr(p, "name") else str(p)
               for p in (result_dir if isinstance(result_dir, list) else [result_dir])]
        return await _top_diagnoses_mongo(ids, uuid_filter, top)
    return _top_diagnoses_fs(result_dir, uuid_filter, top)


async def _patient_list_item(patient_uuid: str, result_dir) -> dict[str, Any]:
    if cfg.USE_MONGO:
        result_set = result_dir.name if hasattr(result_dir, "name") else str(result_dir)
        return await _patient_list_item_mongo(result_set, patient_uuid)
    return _patient_list_item_fs(patient_uuid, result_dir)
```

The `/api/results/{result_set}/{patient_uuid}` route handler is the one place where the dispatcher reshapes the call site directly (the function body becomes the dispatch):

```python
@app.get("/api/results/{result_set}/{patient_uuid}")
async def result_detail(result_set: str, patient_uuid: str) -> dict[str, Any]:
    if cfg.USE_MONGO:
        return await _result_detail_mongo(result_set, patient_uuid)
    return _result_detail_fs(result_set, patient_uuid)
```

For each of the existing route handlers that calls a now-async helper, change the signature from `def` to `async def` and prefix the helper call with `await`. There are 6 such routes; mechanical change.

- [ ] **Step 4: Smoke test the dispatcher with USE_MONGO=false (filesystem path still works)**

Run: `USE_MONGO=false pytest tests/test_mas_pipeline.py tests/test_offline.py -v -x`
Expected: existing tests pass (filesystem path unchanged when flag is off).

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py
git commit -m "backend: USE_MONGO dispatcher gating Mongo helpers vs filesystem fallback"
```

---

## Phase 5 — Write-path refactor

### Task 20: `pipeline/gold.py` → `PatientCase` upsert

**Files:** Modify `pipeline/gold.py`, add a test

- [ ] **Step 1: Add a failing test**

Create `tests/integration/test_gold_mongo_write.py`:

```python
"""Verify that pipeline/gold.py writes to PatientCase when USE_MONGO=true."""
import json, os
import pytest
import pytest_asyncio
from datetime import datetime
from pathlib import Path

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_gold_writes_patient_case_to_mongo(mongo_db, monkeypatch, tmp_path):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import PatientCase
    from pipeline.gold import write_patient_case_to_mongo

    payload = {
        "patient_uuid": "uuid-z",
        "person_id": 99,
        "cutoff_date": "2020-01-01",
        "case_type": "ehr+lab",
        "demographics": {"age": 50},
        "conditions": {"active": [], "history": []},
        "medications": {"active": [], "history": []},
        "visits": [], "comorbidity": {}, "risk_scores": {},
        "lab_case": {"recent_vitals": [], "latest_labs": [], "critical_flags": []},
        "ground_truth": {"target_condition": {"name": "Hypertension"}},
    }
    await write_patient_case_to_mongo(payload)
    doc = await PatientCase.get("uuid-z")
    assert doc is not None
    assert doc.demographics["age"] == 50
    assert doc.ground_truth["target_condition"]["name"] == "Hypertension"
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_gold_mongo_write.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `write_patient_case_to_mongo` in `pipeline/gold.py`**

Open `pipeline/gold.py`. Append:

```python
async def write_patient_case_to_mongo(payload: dict) -> None:
    """Write one Gold case to the PatientCase collection. Called from
    assemble_gold() when USE_MONGO is set; the filesystem write path
    remains the default until the cutover."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import PatientCase

    await init_db()
    case_stats = {
        "activeConditions":  len((payload.get("conditions",  {}) or {}).get("active", []) or []),
        "activeMedications": len((payload.get("medications", {}) or {}).get("active", []) or []),
        "labTrends":         len((payload.get("lab_case", {}) or {}).get("latest_labs", []) or []),
        "criticalFlags":     len((payload.get("lab_case", {}) or {}).get("critical_flags", []) or []),
    }
    doc = PatientCase(
        id=str(payload["patient_uuid"]),
        person_id=int(payload.get("person_id", 0)),
        cutoff_date=datetime.fromisoformat(str(payload.get("cutoff_date", "1970-01-01"))[:10]),
        case_type=str(payload.get("case_type", "ehr+lab")),
        demographics=payload.get("demographics", {}),
        conditions=payload.get("conditions", {}),
        medications=payload.get("medications", {}),
        visits=payload.get("visits", []),
        comorbidity=payload.get("comorbidity", {}),
        risk_scores=payload.get("risk_scores", {}),
        labs=payload.get("lab_case", {}),
        ground_truth=payload.get("ground_truth", {}),
        case_stats=case_stats,
        assembled_at=datetime.utcnow(),
        pipeline_version="gold-3.4",
    )
    await PatientCase.find_one(PatientCase.id == doc.id).upsert(
        {"$set": doc.model_dump(by_alias=True, exclude={"_id"})},
        on_insert=doc,
    )
```

At the end of the existing `assemble_gold()` function, add the dispatch:

```python
    if cfg.USE_MONGO:
        import asyncio
        asyncio.run(write_patient_case_to_mongo({
            "patient_uuid": patient_uuid, "person_id": person_id,
            "cutoff_date": cutoff_date, "case_type": case_type,
            "demographics": demographics, "conditions": conditions,
            "medications": medications, "visits": visits,
            "comorbidity": comorbidity, "risk_scores": risk_scores,
            "lab_case": lab_case, "ground_truth": ground_truth,
        }))
```

- [ ] **Step 4: Run test — expect PASS**

Run: `pytest tests/integration/test_gold_mongo_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/gold.py tests/integration/test_gold_mongo_write.py
git commit -m "pipeline: gold.py writes PatientCase to mongo when USE_MONGO"
```

---

### Task 21: `BaseAgent.__call__` → `AgentRun` upsert

**Files:** Modify `src/agents/base.py`, add a test

- [ ] **Step 1: Failing test**

Create `tests/integration/test_base_agent_mongo_write.py`:

```python
"""Verify that BaseAgent.__call__ upserts the agent envelope to AgentRun
when USE_MONGO=true, without disturbing the existing PipelineState API."""
import pytest, pytest_asyncio, asyncio
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_base_agent_upserts_envelope(mongo_db, monkeypatch):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import AgentRun
    from src.agents.base import write_agent_envelope_to_mongo

    await write_agent_envelope_to_mongo(
        result_set="rsX", patient_uuid="uuidX",
        agent_id="ehr_analyst",
        envelope={"status": "success", "output": {"hello": "world"}, "duration_ms": 12},
    )
    doc = await AgentRun.find_one(
        AgentRun.result_set == "rsX", AgentRun.patient_uuid == "uuidX",
    )
    assert doc is not None
    assert doc.agents["ehr_analyst"]["output"] == {"hello": "world"}
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_base_agent_mongo_write.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `write_agent_envelope_to_mongo` and hook into `__call__`**

Open `src/agents/base.py`. Append (above the `BaseAgent` class or in a sibling module):

```python
async def write_agent_envelope_to_mongo(
    *,
    result_set: str,
    patient_uuid: str,
    agent_id: str,
    envelope: dict,
) -> None:
    """Atomic per-agent upsert into AgentRun. Called from BaseAgent.__call__
    after the agent emits its envelope, when USE_MONGO is set."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import AgentRun

    await init_db()
    await AgentRun.find_one(
        AgentRun.result_set == result_set, AgentRun.patient_uuid == patient_uuid,
    ).upsert(
        {"$set": {f"agents.{agent_id}": envelope}},
        on_insert=AgentRun(
            result_set=result_set, patient_uuid=patient_uuid,
            started_at=datetime.utcnow(),
            agents={agent_id: envelope},
        ),
    )
```

In `BaseAgent.__call__`, immediately after the existing `(MAS_RESULTS_DIR / patient_uuid / f"{self.agent_id}.json").write_text(...)` call, add the Mongo path:

```python
        if cfg.USE_MONGO:
            import asyncio
            asyncio.run(write_agent_envelope_to_mongo(
                result_set=cfg.MAS_RESULTS_DIR.name,
                patient_uuid=patient_uuid,
                agent_id=self.agent_id,
                envelope=envelope_dict,    # the same dict that was written to disk
            ))
```

(Where `envelope_dict` is whatever the existing JSON write serialised — usually `output.model_dump()` plus status/duration fields. If the existing code dumps a Pydantic model, dump it to a dict on the line above the file write so both writers see the same dict.)

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_base_agent_mongo_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agents/base.py tests/integration/test_base_agent_mongo_write.py
git commit -m "agents: BaseAgent.__call__ upserts envelope to AgentRun when USE_MONGO"
```

---

### Task 22: `orchestrator/graph.py` end-of-run writes

**Files:** Modify `src/orchestrator/graph.py`, add a test

- [ ] **Step 1: Failing test**

Create `tests/integration/test_graph_mongo_write.py`:

```python
import pytest, pytest_asyncio
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_finalise_run_writes_trace_and_session(mongo_db, monkeypatch):
    monkeypatch.setenv("USE_MONGO", "true")
    from src.db.documents import AgentRun
    from src.orchestrator.graph import finalise_run_to_mongo

    await finalise_run_to_mongo(
        result_set="rs", patient_uuid="u",
        trace=[{"agent_id": "ehr_analyst", "status": "success", "duration_s": 1.0}],
        session_memory=[{"event_type": "note", "agent_id": "x", "summary": "..."}],
        duration_s=12.5,
    )
    doc = await AgentRun.find_one(AgentRun.result_set == "rs", AgentRun.patient_uuid == "u")
    assert doc.execution_trace[0]["agent_id"] == "ehr_analyst"
    assert doc.session_memory[0]["summary"] == "..."
    assert doc.duration_s == 12.5
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_graph_mongo_write.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `finalise_run_to_mongo` in `graph.py`**

Append to `src/orchestrator/graph.py`:

```python
async def finalise_run_to_mongo(
    *, result_set: str, patient_uuid: str,
    trace: list[dict], session_memory: list[dict],
    duration_s: float | None,
) -> None:
    """End-of-run writer for the trace + session memory + duration. Called
    by run_single_patient() after the graph completes when USE_MONGO is set."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import AgentRun

    await init_db()
    await AgentRun.find_one(
        AgentRun.result_set == result_set, AgentRun.patient_uuid == patient_uuid,
    ).upsert(
        {"$set": {
            "execution_trace": trace,
            "session_memory":  session_memory,
            "finished_at":     datetime.utcnow(),
            "duration_s":      duration_s,
        }},
        on_insert=AgentRun(
            result_set=result_set, patient_uuid=patient_uuid,
            started_at=datetime.utcnow(),
            execution_trace=trace, session_memory=session_memory,
            duration_s=duration_s,
        ),
    )
```

In the existing end-of-run block (where `execution_trace.json` and `session_memory.json` get written to disk), add:

```python
    if cfg.USE_MONGO:
        import asyncio
        asyncio.run(finalise_run_to_mongo(
            result_set=cfg.MAS_RESULTS_DIR.name,
            patient_uuid=patient_uuid,
            trace=trace_entries,             # the same list passed to the JSON write
            session_memory=session_events,
            duration_s=run_duration_s,
        ))
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_graph_mongo_write.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/orchestrator/graph.py tests/integration/test_graph_mongo_write.py
git commit -m "graph: finalise_run_to_mongo end-of-run writes when USE_MONGO"
```

---

### Task 23: `memory/semantic.py` atomic `$inc`

**Files:** Modify `src/memory/semantic.py`, add a test

- [ ] **Step 1: Failing test**

Create `tests/integration/test_semantic_mongo.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `pytest tests/integration/test_semantic_mongo.py -v`
Expected: FAIL.

- [ ] **Step 3: Implement `consolidate_to_mongo`**

Append to `src/memory/semantic.py`:

```python
async def consolidate_to_mongo(
    disease: str, *, match_type: str, at_rank_1: bool,
) -> None:
    """Atomic per-disease increment. Replaces the previous read-modify-write
    on semantic_memory.json (which was unsafe under parallel consolidation)."""
    from datetime import datetime
    from src.db.mongo import init_db
    from src.db.documents import SemanticMemoryEntry

    await init_db()
    field = {"DIRECT": "direct", "INDIRECT": "indirect", "MISS": "miss"}.get(match_type, "miss")
    inc: dict[str, int] = {f"counts.{field}": 1}
    if at_rank_1 and match_type in ("DIRECT", "INDIRECT"):
        inc["rank1_when_found"] = 1
    await SemanticMemoryEntry.find_one(SemanticMemoryEntry.id == disease).upsert(
        {"$inc": inc, "$set": {"updated_at": datetime.utcnow()}},
        on_insert=SemanticMemoryEntry(id=disease, counts={field: 1},
                                       rank1_when_found=(1 if at_rank_1 and match_type != "MISS" else 0),
                                       updated_at=datetime.utcnow()),
    )
```

In the existing `consolidate()` function, dispatch on the flag:

```python
    if cfg.USE_MONGO:
        import asyncio
        asyncio.run(consolidate_to_mongo(disease, match_type=match_type,
                                          at_rank_1=(rank == 1)))
        return
    # Existing read-modify-write filesystem path follows.
```

- [ ] **Step 4: Run — expect PASS**

Run: `pytest tests/integration/test_semantic_mongo.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/semantic.py tests/integration/test_semantic_mongo.py
git commit -m "memory: atomic $inc on SemanticMemoryEntry when USE_MONGO"
```

---

## Phase 6 — End-to-end + cutover

### Task 24: End-to-end smoke test on a small cohort

**Files:** New ad-hoc script — not committed

- [ ] **Step 1: Tar the filesystem (safety net)**

Run:
```bash
tar -czf data/gold-fs-backup-$(date +%Y%m%d).tar.gz \
    data/gold/mas_results* data/gold/patient_cases data/gold/memory data/gold/*.json
shasum -a 256 data/gold-fs-backup-*.tar.gz
```
Record the SHA-256 in a scratch note.

- [ ] **Step 2: Bring up Mongo (if not already)**

Run: `docker compose up -d mongo`
Expected: container healthy.

- [ ] **Step 3: Dry-run the full migration**

Run: `python scripts/migrate_filesystem_to_mongo.py --dry-run --report data/gold/dryrun_report.json`
Expected: stdout report shows `agent_runs_seen` matching `ls -1 data/gold/mas_results*/*/ | wc -l` / 2 roughly. No Mongo writes.

- [ ] **Step 4: Real migration**

Run: `python scripts/migrate_filesystem_to_mongo.py --workers 8 --verify --report data/gold/migration_report.json`
Expected: `verifier_divergences: []` in the report. Exit 0.

- [ ] **Step 5: Spot-check Mongo content**

Run:
```bash
docker exec cmads-mongo mongosh cmads --quiet --eval '
  print("agent_runs:", db.agent_runs.estimatedDocumentCount());
  print("patient_cases:", db.patient_cases.estimatedDocumentCount());
  print("semantic_memory:", db.semantic_memory.estimatedDocumentCount());
  print("derived_artefacts:", db.derived_artefacts.estimatedDocumentCount());
'
```
Expected: agent_runs ≈ 415, patient_cases ≈ 415, semantic_memory ≥ 7, derived_artefacts ≥ 3.

- [ ] **Step 6: No commit — this is a one-off run check.**

---

### Task 25: Flip `USE_MONGO=true`, smoke-test acceptance criteria

**Files:** `.env`

- [ ] **Step 1: Flip the flag**

Edit `.env`, set `USE_MONGO=true`. Restart the FastAPI backend (`make doctor-console-api`).

- [ ] **Step 2: Smoke-test the Overview endpoint**

Run:
```bash
curl -sf 'http://127.0.0.1:8010/api/stats/overview?result_set=multi_level' \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['aggregates']; print(f'n={d[\"n\"]} DIRECT={d[\"directPct\"]:.1f}% Found={d[\"foundPct\"]:.1f}% Rank1={d[\"rank1PctOfFound\"]:.1f}%')"
```
Expected: `n=160 DIRECT=78.1% Found=95.0% Rank1=63.2%` (matches §12 acceptance criteria).

- [ ] **Step 3: Smoke-test the Memory A/B endpoint**

Run:
```bash
curl -sf 'http://127.0.0.1:8010/api/comparisons/memory-ab' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('contingency:', d['contingency']); print('mcnemar p:', d['mcnemar']['p_value_two_sided'])"
```
Expected: `contingency: {'both_DIRECT': 70, 'only_OFF_DIRECT': 16, 'only_ON_DIRECT': 53, 'neither_DIRECT': 21}` and `mcnemar p: 9.1e-06`.

- [ ] **Step 4: Smoke-test a write — fresh patient run**

Pick one UUID from `data/gold/patient_cases/` that hasn't been run recently. Run:
```bash
make run-patient UUID=<uuid>
```
Then:
```bash
docker exec cmads-mongo mongosh cmads --quiet --eval \
  "db.agent_runs.find({patient_uuid: '<uuid>'}, {result_set:1, 'agents.evaluation.output.match_type':1}).pretty()"
```
Expected: the new run's `AgentRun` document exists with all 7 agents populated.

- [ ] **Step 5: Open the React Reasoning tab for that UUID**

Navigate to `http://127.0.0.1:5173/?mode=researcher&tab=patients&p=<uuid>&a=ehr_analyst`. Confirm each agent's narrative loads, raw output appears, and the prompt-template disclosure opens correctly.

- [ ] **Step 6: Confirm fallback still works**

Set `USE_MONGO=false`, restart backend, re-fetch `/api/stats/overview?result_set=multi_level` — should still return the same numbers (from filesystem). Re-set to `true` afterwards.

- [ ] **Step 7: No commit — this is a one-off validation pass.**

---

### Task 26: Documentation update

**Files:** Modify `README.md`, `CLAUDE.md`

- [ ] **Step 1: Add a "Storage" section to `README.md`**

After the "Configuration" section, add:

```markdown
## Storage

CMADS uses two persistence layers:

| Layer | Where | What |
|---|---|---|
| **Cold (immutable inputs)** | DuckDB at `data/clinical.duckdb`, Synthea FHIR JSON at `data/bronze/`, Qdrant volumes | OMOP CDM Silver tables, raw FHIR bundles, BioLORD embeddings, NICE guideline vectors |
| **Hot (run outputs)** | MongoDB (`docker compose up -d mongo`) — collections `patient_cases`, `agent_runs`, `semantic_memory`, `derived_artefacts` | Gold patient cases, per-agent run outputs, execution traces, evaluation verdicts, derived artefacts (`paired_160_mcnemar`, sensitivity summaries, cohort summaries) |

The `USE_MONGO=true` flag (in `.env`) gates the runtime read/write path. With it off, the system reads/writes the original on-disk `data/gold/mas_results*/` tree as a fallback during the 30-day soak window.
```

- [ ] **Step 2: Add Mongo to the "Common Commands" section of `CLAUDE.md`**

After `make doctor-console-web`, append:

```bash
docker compose up -d mongo                         # start local MongoDB (port 27017)
docker compose down mongo                          # stop it
python scripts/migrate_filesystem_to_mongo.py --dry-run     # show what would migrate
python scripts/migrate_filesystem_to_mongo.py --verify-all  # full backfill + SHA-256 verify
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: add storage section + mongo commands"
```

---

### Task 27: Append a note to `notes/decisions.md`

**Files:** Modify `notes/decisions.md`

- [ ] **Step 1: Append the decision**

```bash
cat >> notes/decisions.md <<'EOF'
- 2026-05-22 — **Migrated agent runs + Gold cases + semantic memory from on-disk JSON tree to local MongoDB.** Why: the FastAPI backend's filesystem-scan reads (Overview aggregates, patient list, Memory A/B) were already at ~5 k file reads per page load on the 415-patient cohort; without an index they scale linearly with patient count and would not survive a real-EHR replication. How to apply: agent code writes go through `src/db/documents.py::AgentRun`; backend reads dispatch via `cfg.USE_MONGO`. Synthea Bronze, DuckDB OMOP Silver, and Qdrant vector collections deliberately stay on disk (they are either rigidly relational or purpose-built). **Refs:** [`docs/superpowers/specs/2026-05-22-mongodb-migration-design.md`](../docs/superpowers/specs/2026-05-22-mongodb-migration-design.md), [`docs/superpowers/plans/2026-05-22-mongodb-migration.md`](../docs/superpowers/plans/2026-05-22-mongodb-migration.md). #decision #thesis
EOF
```

- [ ] **Step 2: Commit**

```bash
git add notes/decisions.md
git commit -m "notes: log mongodb migration decision"
```

---

### Task 28 (deferred — 30 days post-cutover): Cleanup branch

**Not run as part of this plan.** After the 30-day soak window:

- Delete `USE_MONGO` flag + filesystem fallback paths in `src/config.py` and `doctor_console/backend/app.py`.
- Delete `data/gold-fs-backup-YYYYMMDD.tar.gz`.
- Delete `data/gold/mas_results*/` and `data/gold/patient_cases/` (DuckDB Silver, Bronze, Qdrant, prompts all stay).
- Single commit: `cleanup: remove USE_MONGO fallback after 30-day soak window`.

---

## Acceptance criteria (from spec §12)

The plan is "done" when, after Task 25, all of these hold:

1. `docker compose up -d mongo` brings up Mongo with persisted volume.
2. `python scripts/migrate_filesystem_to_mongo.py --verify-all` completes with `verifier_divergences: []`.
3. `/api/stats/overview?result_set=multi_level` returns `directPct=78.1`, `foundPct=95.0`, `rank1PctOfFound=63.2`.
4. `/api/comparisons/memory-ab` returns contingency `70/16/53/21` and McNemar `p≈9.1e-6`.
5. `make run-patient UUID=...` produces an `AgentRun` document visible in the React Reasoning tab.
6. Flipping `USE_MONGO=false` in `.env` + backend restart cleanly falls back to the filesystem read path and `/api/stats/overview` still returns the same numbers.

After 30 days of green operation (Task 28 deferred), the cleanup commit removes the flag, the tarball, and the on-disk JSON tree.
