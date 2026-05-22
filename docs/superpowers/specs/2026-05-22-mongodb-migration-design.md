# CMADS Storage Migration: Filesystem JSON → MongoDB

**Date:** 2026-05-22
**Status:** Approved design — ready for implementation planning
**Scope:** Move per-agent JSON outputs, Gold patient cases, and semantic memory from the on-disk JSON tree to a MongoDB database. Synthea Bronze, OMOP CDM Silver (DuckDB), Qdrant vector collections, and prompt YAML files remain on disk unchanged.

---

## 1. Motivation

The current storage layout writes everything to `data/gold/mas_results*/<uuid>/{agent_id}.json` plus sibling `execution_trace.json`, `session_memory.json`, `evaluation.json`, `evaluation_canon.json`, `final_diagnosis_canon.json`, and assorted derived artefacts. The FastAPI doctor-console backend reads these files on every page load by walking the directory tree — `_iter_patient_dirs`, `_aggregate_result_set`, `_rank_distribution`, `_per_disease_breakdown`, `_top_diagnoses`, `_dashboard_summary`, `_memory_ab_comparison`, `_patient_list_item`, and the per-patient `result_detail` endpoint all do this. With ~415 patients × ~10 JSON files per run, this already amounts to ~5 k disk reads per Researcher Overview page load.

The user's stated motivation is **scaling**: this code should be ready to handle ~1 k → ~10 k patients without filesystem-scan latency, and should be architecturally prepared for an eventual real-EHR replication on MIMIC-IV or similar (with the regulatory / clinical-IT work that entails — out of scope for this design).

The migration is therefore **aspirational future-proofing** at scenario-A scale: ~1 k synthetic patients on a single workstation today, with a clean architectural runway to ~10 k+. It is not a real-EHR deployment.

## 2. Scope decisions (confirmed during brainstorming)

| Question | Decision |
|---|---|
| Which database? | MongoDB. (Mongoose is Node-only; pipeline is Python, so MongoDB via PyMongo / Motor with the **Beanie** ODM.) |
| Hosting? | Local Docker container in `docker-compose.yml`. No Atlas. |
| What moves to Mongo? | **Option B**: agent run outputs, Gold patient cases, semantic memory. (Synthea Bronze, OMOP CDM Silver in DuckDB, Qdrant vectors stay on disk.) |
| Migration strategy? | **Hard cutover** with a one-time backfill script. No dual-write. Tarball of the filesystem is kept for 30 days as the rollback artefact. |
| Schema shape? | **Option B (per-run aggregate)**: 4 collections — `patient_cases`, `agent_runs`, `semantic_memory`, `derived_artefacts`. One document per `(result_set, patient_uuid)` for agent runs. |

## 3. Architecture overview

```
                    ┌────────────────────────┐
Synthea ──Bronze──▶│  DuckDB (OMOP Silver)  │──▶ pipeline/gold.py ──▶ patient_cases (Mongo)
                    └────────────────────────┘                                │
                                                                              ▼
                              ┌──────────────────────────────┐    ┌───────────────────────┐
prompts/*.yaml ─────────────▶│ LangGraph orchestrator + 7   │───▶│  agent_runs (Mongo)   │
                              │  agents (BaseAgent.__call__) │    └───────────────────────┘
                              └───────────┬──────────────────┘                │
                                          │                                   │
                              ┌───────────▼────────────┐                      │
                              │ semantic memory writes │───────▶ semantic_memory (Mongo)
                              │  + Tier-4 case recall  │
                              └───────────┬────────────┘
                                          │
                                          ▼
                              ┌───────────────────────┐
                              │  Qdrant (vectors)     │    ← unchanged
                              │  patient_cases coll.  │
                              │  nice_guidelines      │
                              └───────────────────────┘

                              ┌──────────────────────────────┐
React doctor console ◀──HTTP──│ FastAPI backend              │──── Mongo aggregations
                              │  (doctor_console/backend/    │     for KPI tiles,
                              │   app.py)                    │     per-disease, ranks,
                              └──────────────────────────────┘     memory A/B contingency
```

## 4. Hosting, ODM, and connection management

**MongoDB** as a Docker Compose service: `mongo:7` (or pinned latest LTS at implementation time), exposed on `127.0.0.1:27017`, data volume `./data/mongo/`. Add a healthcheck that pings the database. **No authentication** in the local dev container — bind to loopback only; document this explicitly so it doesn't drift into production by accident.

`.env.example` additions:
```
MONGO_URI=mongodb://localhost:27017
MONGO_DB=cmads
```

**ODM: Beanie** (Pydantic-v2-native, async, integrates with FastAPI lifespan handlers). The project already uses Pydantic v2 across `src/schemas/`, so Beanie's `Document` (subclass of Pydantic `BaseModel`) requires the smallest refactor.

**Client lifecycle:** a new module `src/db/mongo.py` owns the singleton. Two entry points:
- Async `init_db()` — initialises Beanie with the four `Document` classes. Called from the FastAPI `lifespan` handler and from each script entry point via `asyncio.run()`.
- Sync `get_sync_db()` — for the non-async pipeline scripts (`pipeline/gold.py`, the orchestrator's CLI mode). Wraps a Motor client inside `asyncio.run()` at script boundaries; we don't convert the pipeline to async.

## 5. Data model

Four Beanie `Document` classes, one per collection.

### 5.1 `patient_cases`

```python
class PatientCase(Document):
    id: str = Field(alias="_id")           # patient_uuid
    person_id: int
    cutoff_date: datetime
    case_type: str                          # "ehr+lab"
    demographics: dict
    conditions: dict                        # {"active": [...], "history": [...]}
    medications: dict
    visits: list[dict]
    comorbidity: dict
    risk_scores: dict
    labs: dict                              # {"recent_vitals": [...], "latest_labs": [...], "critical_flags": [...]}
    ground_truth: dict                      # target_condition, person_id, cutoff_date, visits_before_diagnosis, ...
    case_stats: dict                        # activeConditions, activeMedications, labTrends, criticalFlags
    assembled_at: datetime
    pipeline_version: str

    class Settings:
        name = "patient_cases"
        indexes = ["ground_truth.target_condition.name"]
```

### 5.2 `agent_runs`

```python
class AgentRunKey(BaseModel):
    result_set: str
    patient_uuid: str

class AgentEnvelope(BaseModel):
    status: Literal["success", "partial", "error", "skipped"]
    output: dict | None
    output_canon: dict | None = None        # populated only for evaluation + final_diagnosis when canonicalizer fires
    duration_ms: int | None
    error: str | None = None

class TraceEntry(BaseModel):
    agent_id: str
    status: str
    duration_s: float
    error: str | None = None
    ts: datetime

class SessionEvent(BaseModel):
    event_type: str
    agent_id: str
    summary: str
    payload: dict
    tags: list[str]
    ts: datetime

class AgentRun(Document):
    id: AgentRunKey = Field(alias="_id")
    result_set: str
    patient_uuid: str
    started_at: datetime
    finished_at: datetime | None
    duration_s: float | None
    pipeline_version: str
    model_config: dict                      # {reasoning_model, judge_model, memory_enabled, canonicalizer_enabled, ...}
    agents: dict[str, AgentEnvelope]        # keys: ehr_analyst, lab_interpreter, ...
    execution_trace: list[TraceEntry]
    session_memory: list[SessionEvent]
    canonicalizer_fired: bool = False

    class Settings:
        name = "agent_runs"
        indexes = [
            [("result_set", 1), ("patient_uuid", 1)],        # primary key, unique
            [("result_set", 1), ("agents.evaluation.output.match_type", 1)],
            [("patient_uuid", 1)],
            [("agents.final_diagnosis.output.primary_diagnosis", 1)],
        ]
```

### 5.3 `semantic_memory`

```python
class SemanticMemoryEntry(Document):
    id: str = Field(alias="_id")            # disease name (verbatim Synthea label)
    counts: dict                            # {"direct": int, "indirect": int, "miss": int}
    rank1_when_found: int
    evidence_patterns: list[dict]
    updated_at: datetime

    class Settings:
        name = "semantic_memory"
```

### 5.4 `derived_artefacts`

```python
class DerivedArtefact(Document):
    id: str = Field(alias="_id")            # e.g. "paired_160_mcnemar"
    payload: dict                            # verbatim original JSON
    produced_by: str                         # script path
    produced_at: datetime
    source_cohort: str | None = None

    class Settings:
        name = "derived_artefacts"
```

## 6. Write-path changes

Five files change in the existing codebase:

1. **`src/db/mongo.py`** *(new)* — singleton client, `init_db()`, `get_sync_db()`, document class registration.

2. **`src/agents/base.py::BaseAgent.__call__`** — the per-agent file write becomes one upsert:
   ```python
   await AgentRun.find_one(
       {"_id": {"result_set": result_set, "patient_uuid": patient_uuid}}
   ).upsert(
       {"$set": {f"agents.{self.agent_id}": envelope.model_dump()}},
       on_insert=AgentRun(...)
   )
   ```

3. **`src/orchestrator/graph.py`** — the end-of-run `execution_trace.json` + `session_memory.json` writes become one `$set` on the same `AgentRun` document. The cohort-level `run_summary.json` becomes a `$inc` on a `cohort_summary` doc in `derived_artefacts`.

4. **`pipeline/gold.py`** — the three-file Gold write (`ehr_case.json`, `lab_case.json`, `ground_truth.json`) becomes one `PatientCase.find_one_and_replace({_id: uuid}, doc, upsert=True)`.

5. **`src/memory/semantic.py`** — `consolidate()` swaps its read-modify-write of `semantic_memory.json` for an atomic `$inc` (which incidentally fixes a latent concurrency bug — file RMW is unsafe under parallel consolidation; Mongo `$inc` isn't).

**Unchanged:** all Pydantic schemas in `src/schemas/`, all agent prompts in `prompts/`, all Synthea/Bronze/OMOP-Silver code in `pipeline/`, all Qdrant code (Tier-4 case-based memory and NICE retrieval), all CLI orchestration entry points.

**Estimated LOC:** +150 (new mongo module + Beanie documents), -30 (filesystem writes in 4 places).

## 7. Read-path changes (FastAPI backend)

`doctor_console/backend/app.py` is the only Python file in the backend that changes. The React frontend is **untouched** — every API response shape stays byte-identical.

Three categories of change:

- **Aggregates** — `_aggregate_result_set`, `_rank_distribution`, `_per_disease_breakdown`, `_top_diagnoses`, and the comparable helpers in `_memory_ab_comparison` and `_dashboard_summary` swap their filesystem-scan loops for Mongo aggregation pipelines. The Researcher Overview page goes from "scan N patient dirs, read N×10 JSONs" to one indexed `$group` query. This is where the scaling win lands.

- **Per-patient detail** — the `/api/results/{result_set}/{patient_uuid}` endpoint becomes two `get()` calls (one `AgentRun`, one `PatientCase`). The current preference logic for `evaluation_canon.json` / `final_diagnosis_canon.json` disappears: the canon variants are embedded fields (`agents.evaluation.output_canon` / `agents.final_diagnosis.output_canon`), and the handler picks them when present.

- **Virtual cohorts** — `_resolve_result_dirs` now returns a list of `result_set` IDs (not Paths). Aggregations use `$match: {result_set: {$in: [...]}}` and de-duplicate UUIDs across the union with a `$group: {_id: "$patient_uuid", doc: {$first: "$$ROOT"}}` step.

**API contracts:** unchanged. `/api/stats/overview`, `/api/patients`, `/api/results/...`, `/api/comparisons/memory-ab`, `/api/comparisons/model-comparison`, `/api/comparisons/mas-vs-single-llm`, `/api/agents/{agent_id}/prompt` (which reads YAML, not JSON, so it's unaffected), `/api/patients/{uuid}/similar` (Qdrant, unaffected) — every response shape stays identical.

**Estimated LOC:** -400 (filesystem-scan helpers removed), +200 (Mongo aggregations). Net -200.

## 8. Backfill script

A single one-shot script: **`scripts/migrate_filesystem_to_mongo.py`**.

**Algorithm:**
- Iterate every `data/gold/mas_results*/<uuid>/` directory. For each UUID, load all per-agent JSON files into an `agents.<id>` envelope, load `execution_trace.json` and `session_memory.json` (if present), embed `evaluation_canon.json` and `final_diagnosis_canon.json` (if present) under `agents.evaluation.output_canon` / `agents.final_diagnosis.output_canon`, then upsert one `AgentRun` document keyed by `(result_set, patient_uuid)`.
- Iterate `data/gold/patient_cases/<uuid>/`. For each UUID, load `ehr_case.json` + `lab_case.json` + `ground_truth.json`, merge into one document, upsert as `PatientCase`.
- Read `data/gold/memory/semantic_memory.json`, split per disease, upsert each as a `SemanticMemoryEntry`.
- Iterate `data/gold/*.json` (paired_160_mcnemar.json, sensitivity summaries, etc.), upsert each as a `DerivedArtefact`.

**Safety guarantees:**
- **Idempotent**: upsert by primary key; re-running produces identical documents.
- **Restartable**: progress file at `data/gold/migration_progress.json` records each `(result_set, patient_uuid)` already migrated; a crash mid-way means the next run picks up from where it left off.
- **Dry-run mode** (`--dry-run`): walks the filesystem, prints document counts that would be inserted, doesn't touch Mongo.
- **Verify mode** (`--verify` / `--verify-all`): recomputes the SHA-256 of the JSON serialisation of each Mongo document and compares against the SHA-256 of the original file content. Logs any divergences. Default samples 10%; `--verify-all` does the full sweep.
- **Parallel mode** (`--workers N`, default 8): `ThreadPoolExecutor` over patient UUIDs; Motor calls are I/O-bound. Full 415-patient migration is < 30 seconds.
- **Structured report** (`--report path.json`): per-`result_set` counts, total bytes read/written, skipped files with reasons. Logs go through the existing `structlog` setup to `data/gold/migration.log`.

## 9. Cutover sequence

Linear seven-step cutover. If any step fails, stop and rewind to the previous one.

1. **Stand up MongoDB.** `docker compose up -d mongo`. Verify with `mongosh --eval "db.runCommand({ping:1})"`. Add `MONGO_URI` and `MONGO_DB` to `.env`. *Rollback*: `docker compose down mongo`.
2. **Merge code changes to `main`.** All Section 6 + 7 edits land on `feat/mongo-migration`, CI green, merge. Code is ready to read Mongo but Mongo is still empty (handlers gated on `USE_MONGO`). *Rollback*: revert merge.
3. **Tar the filesystem.** `tar -czf data/gold-fs-backup-$(date +%Y%m%d).tar.gz data/gold/mas_results* data/gold/patient_cases data/gold/memory data/gold/*.json`. Verify archive opens and contains every UUID. Record SHA-256. *Rollback*: untar.
4. **Dry-run migration.** `python scripts/migrate_filesystem_to_mongo.py --dry-run --report dryrun.json`. Confirm every `result_set` and patient accounted for. *Rollback*: noop.
5. **Real migration.** `python scripts/migrate_filesystem_to_mongo.py --workers 8 --report real.json`, then `--verify-all`. If divergences > 0, *stop*. *Rollback*: `db.dropDatabase()`, fix, re-run.
6. **Smoke-test read path.** Hit `/api/stats/overview?result_set=multi_level`; expect DIRECT = 78.1%, n = 160. Open Memory A/B; expect contingency 70/16/53/21 and McNemar p ≈ 9.1e-6. If numbers differ, *stop* (aggregation bug, not data bug). *Rollback*: flip `USE_MONGO=false`.
7. **Smoke-test write path.** `make run-patient UUID=...`. Verify `AgentRun` document materialises and the React Reasoning tab loads the full narrative. *Rollback*: same flag.

## 10. Rollback plan

For the first 30 days post-cutover:

- **Tarball kept** at `data/gold-fs-backup-YYYYMMDD.tar.gz`. Do not delete.
- **`USE_MONGO` flag kept** in `src/config.py` with `false`-branch helpers intact. Flipping it back to filesystem mode is a one-line `.env` change + backend restart, ≤ 5 minutes.
- **No `mas_results*/` or `patient_cases/` deletions yet.** The on-disk tree remains untouched (Mongo is the source of truth, but the disk copy is the recovery image).

After 30 days of green operation:
- Delete the `USE_MONGO` flag (remove the dead filesystem helpers from `app.py`).
- Delete the tarball.
- Delete `data/gold/mas_results*/` and `data/gold/patient_cases/`.
- Synthea Bronze (`data/bronze/...`), DuckDB Silver (`data/clinical.duckdb`), Qdrant volumes, and prompt YAML in `prompts/` remain untouched throughout.

## 11. What stays out of scope

- **Real-EHR / MIMIC-IV replication.** Out of scope; addressed by future-work item in `conclusion.tex`.
- **Authentication, RBAC, encryption at rest, audit-log immutability.** Out of scope; the local dev container is loopback-only and explicitly not production-shaped.
- **Sharding / replication / change streams.** Out of scope at scenario-A scale. Single Mongo container is sufficient.
- **Atlas / managed hosting.** Out of scope; local Docker only.
- **DuckDB Silver layer → Mongo.** Explicitly *not* migrated. OMOP CDM is rigidly relational; SQL workflow stays.
- **Qdrant vector collections → Mongo Atlas Vector Search.** Explicitly *not* migrated. Qdrant is purpose-built and faster at this scale.
- **Removing the prompt YAML files.** Stay on disk; they're version-controlled with the code.

## 12. Acceptance criteria

The migration is "done" when:

1. `docker compose up` brings up Mongo with persisted volume.
2. The backfill script completes with zero verifier divergences on `--verify-all`.
3. The Researcher Overview page shows headline DIRECT = 78.1%, Found = 95.0%, Rank-1-of-found = 63.2% on `result_set=multi_level` — identical to pre-migration.
4. The Memory A/B page shows contingency 70/16/53/21 and McNemar p ≈ 9.1e-6 — identical to pre-migration.
5. A fresh `make run-patient UUID=...` produces a new `AgentRun` document and surfaces correctly in the React Reasoning tab.
6. The `USE_MONGO` flag toggles between Mongo and filesystem cleanly with a backend restart (sanity check before the 30-day window closes).
7. After 30 days of green operation, the cleanup branch (delete flag + tarball + on-disk JSON) merges and CI stays green.

## 13. Implementation order (high-level)

This is intentionally coarse; the writing-plans skill will produce the detailed task list.

1. New file `src/db/mongo.py` with Beanie init + four document classes.
2. New file `scripts/migrate_filesystem_to_mongo.py` with `--dry-run` and `--verify` modes.
3. Refactor `src/agents/base.py::BaseAgent.__call__` for upserts; add `USE_MONGO` gate.
4. Refactor `src/orchestrator/graph.py` end-of-run writes; same gate.
5. Refactor `pipeline/gold.py` for `PatientCase` upserts; same gate.
6. Refactor `src/memory/semantic.py` for atomic `$inc`; same gate.
7. Refactor `doctor_console/backend/app.py` helpers to read from Mongo when gate is on.
8. Add Mongo service to `docker-compose.yml`.
9. End-to-end smoke test on a small `result_set` before full backfill.
10. Run the cutover sequence (Section 9).
11. 30-day soak; then run the cleanup branch.
