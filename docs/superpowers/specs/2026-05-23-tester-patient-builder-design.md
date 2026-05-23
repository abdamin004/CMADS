# Tester — Patient Builder & Test Runner

**Date:** 2026-05-23
**Status:** Approved (brainstorming complete), ready for implementation planning
**Scope:** A third top-level journey in the CMADS doctor console alongside *Doctor (runtime)* and *Researcher (statistics)*. Lets a clinician build (or clone-and-edit) a synthetic patient and immediately run the seven-agent pipeline against them, with the results scoped to a separate `mas_results_test` cohort so research statistics are never polluted.

---

## 1. Motivation

The existing Doctor (runtime) journey requires the patient to already exist as a directory under `data/gold/patient_cases/<uuid>/`. That works for the 3348 Synthea-derived patients in the cohort but blocks two valuable clinician workflows:

1. **"Here's a patient I just saw — what would CMADS say?"** The clinician sketches in the patient's age, gender, the conditions they have, the labs that look off, and runs the pipeline. The clinician wants the agents' differential as a second opinion. Ground truth may be unknown.
2. **"Start from a similar cohort patient and tweak."** The clinician finds a Synthea patient with the relevant chronic disease, sees what the cohort's ground truth says, then clones the patient and changes a few fields (added comorbidity, different lab values) to probe how CMADS reacts to the perturbation.

Both are blocked today because (a) there's no editor, (b) custom patients would land in `patient_cases` and corrupt research statistics, and (c) custom-patient runs would land in `mas_results` and skew the Memory A/B contingency. The Tester journey solves all three.

## 2. Scope and confirmed decisions

| Question | Decision |
|---|---|
| Who is the primary user? | Clinician second-opinion sketcher, with optional clone-from-cohort start. |
| Where does ground truth come from? | Inherited from source (editable) when cloned; optional dropdown of the 8 thesis diseases (or free-text) when scratch; leaving it blank skips the LLM Evaluator stage. |
| Form layout? | Two-pane: collapsible-section navigator on the left, focused section editor on the right. |
| Cohort browse? | Faceted filters (disease + age range + gender). |
| Storage namespace? | Separate Mongo collection `test_patients`. Pipeline outputs land in `mas_results_test` (Mongo + disk). |
| Field input style? | Autocomplete over the existing cohort vocabulary (conditions / medications / labs) with a free-text "Use anyway" fallback marked with a warning. |
| Where in the console? | Third top-level journey alongside Doctor and Researcher. New `Tester` tile on the splash. |
| Save-to-run flow? | One sticky button at the bottom: **Save & run pipeline →**. Sibling **Save draft** button persists without running. |

## 3. Architecture overview

```
                          ┌─────────────────────────┐
   Splash / ModeChooser ──┼─▶ Tester journey         │
                          │                          │
                          │   ◉ Start from cohort    │
                          │   ◯ Start from scratch   │
                          │                          │
                          │   [ My test patients ]   │
                          └────────────┬─────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
    PatientPicker         PatientBuilderEditor          MyTestPatientsList
    (cohort browse)       (two-pane edit)               (revisit / re-run / delete)
              │                        │                        │
              └─────► Save & run ──────┴────────┐               │
                                                ▼               │
                              POST /api/tests/patients          │
                              POST /api/tests/runs              │
                                                ▼               ▼
                                       _run_patient_task (existing worker)
                                                │
                                                ▼
                                  LangGraph 7-agent pipeline
                                                │
                              ┌─────────────────┴───────────────┐
                              ▼                                 ▼
                  data/gold/mas_results_test/<uuid>/     cmads.agent_runs
                  (filesystem journal)                   (result_set="mas_results_test")
```

**Untouched:** Synthea Bronze pipeline, OMOP DuckDB Silver, Qdrant collections, the existing 7 agents, the LangGraph orchestration graph (a single function gains a second branch — see §6).

## 4. Data model

A new Beanie `Document` class lives in `src/db/documents.py` next to the existing `PatientCase` / `AgentRun` / `SemanticMemoryEntry` / `DerivedArtefact`:

```python
class TestPatient(Document):
    """Custom patient built (or cloned) by the clinician in the Tester
    journey. Schema mirrors PatientCase plus authorship + lifecycle
    metadata. Lives in its own collection so research aggregations
    never see it."""
    id: str = Field(alias="_id")             # test_uuid (uuid4 hex)
    label: str                                # human-readable, ≤100 chars
    source_uuid: str | None = None            # cohort patient if cloned; None for scratch
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    run_count: int = 0

    # PatientCase mirror (same field names, same shapes — keeps load_patient_case simple)
    person_id: int = 0
    cutoff_date: datetime
    case_type: str = "ehr+lab"
    demographics: dict[str, Any]
    conditions: dict[str, Any]
    medications: dict[str, Any]
    visits: dict[str, Any] | list[dict[str, Any]]
    comorbidity: dict[str, Any] = Field(default_factory=dict)
    risk_scores: dict[str, Any] = Field(default_factory=dict)
    labs: dict[str, Any]
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    case_stats: dict[str, Any] = Field(default_factory=dict)
    assembled_at: datetime
    pipeline_version: str = "tester-1.0"

    class Settings:
        name = "test_patients"
        indexes = ["created_at", "last_run_at"]
```

**Compatibility note:** the field shapes match `PatientCase` exactly, so `load_patient_case()` in `src/orchestrator/graph.py` only needs one extra `if`-branch to consume a `TestPatient` doc — no schema translation step.

## 5. Backend REST surface

New endpoints under `/api/tests/*`, all served by `doctor_console/backend/app.py`:

| Method | Path | Body / Query | Returns |
|---|---|---|---|
| `GET` | `/api/tests/vocabulary?kind=…&q=…` | `kind ∈ {condition, medication, lab}`; optional `q` substring | up to 20 items `{label, code?}` |
| `GET` | `/api/tests/cohort?disease=&age_min=&age_max=&gender=` | facet filters | list of `{uuid, age, gender, disease, active_count}` summaries |
| `GET` | `/api/tests/cohort/{uuid}` | — | full clone-template payload (cohort patient as a `TestPatient`-shaped dict, no `_id` yet) |
| `POST` | `/api/tests/patients` | full `TestPatient` payload (no `_id`) | `{test_uuid, label, created_at}` |
| `GET` | `/api/tests/patients` | optional `q` substring filter on label | list of summaries `{test_uuid, label, created_at, last_run_at, run_count, latest_match_type?}` |
| `GET` | `/api/tests/patients/{test_uuid}` | — | full `TestPatient` doc |
| `PUT` | `/api/tests/patients/{test_uuid}` | full or partial `TestPatient` payload | updated doc; `updated_at` stamped server-side |
| `DELETE` | `/api/tests/patients/{test_uuid}?with_runs=…` | optional `with_runs=true` to also purge `mas_results_test` docs for this uuid | `{deleted: true}` |
| `POST` | `/api/tests/runs` | `{test_uuid, top_k, accuracy_mode}` (same shape as `/api/runs`) | `{task_id, status, resultSet:"mas_results_test"}` — frontend then opens the existing SSE stream `/api/runs/{task_id}/stream` |

**API contract reuse:** the runtime view's SSE endpoint (`GET /api/runs/{task_id}/stream`) and the `_tasks` in-memory store are shared between Doctor and Tester runs — no parallel pipe to maintain.

## 6. Pipeline glue (the one change to existing core code)

`src/orchestrator/graph.py::load_patient_case(patient_uuid: str) -> dict` currently looks up the on-disk JSON tree. It grows one branch:

```python
def load_patient_case(patient_uuid: str) -> dict:
    # NEW: prefer test_patients collection when present
    if cfg.USE_MONGO:
        from src.db.mongo import _coll  # sync PyMongo helper
        test_doc = _coll("test_patients").find_one({"_id": patient_uuid})
        if test_doc:
            return _build_pipeline_state_from_doc(test_doc)
    # existing on-disk path
    return _build_pipeline_state_from_disk(patient_uuid)
```

`_build_pipeline_state_from_doc` is a small helper that assembles the same `PipelineState`-shaped dict the on-disk loader produces. The agents see no difference.

`_run_patient_task` in `app.py` accepts a new optional `result_set` kwarg (default `"mas_results"`, override `"mas_results_test"` from `/api/tests/runs`). The `MAS_RESULTS_DIR` override is set via the existing thread-local config overrides from the concurrency fix — no global lock.

## 7. UI surface

### 7.1 Splash tile

Adds one card to `ModeChooser.tsx` next to the Doctor and Researcher cards. Same hover lift, same icon family, label "Tester — build & run", subtitle "Build your own patient and watch CMADS reason about them in seconds."

### 7.2 Tester journey landing

Top header bar:
- Left: back arrow → splash, title "Tester (build & run)".
- Right: link "My test patients (N)".

Body switches on a segmented control:
- **◉ Start from cohort** → renders `PatientPicker`.
- **◯ Start from scratch** → renders empty `PatientBuilderEditor`.

### 7.3 PatientPicker

Three-column layout:
- **Left (filters):** disease radio list with counts (sourced from `GET /api/tests/cohort` with all-but-disease facets fixed); age range slider; gender radio.
- **Middle (results list):** scrollable list of summary rows; each row shows uuid prefix, age + gender, disease label, active-condition count. Click a row to mark it selected and preview it.
- **Right (preview pane):** the selected patient's headline info (demographics, top 5 active conditions, latest critical labs) plus a primary button **"Use as template →"** that fetches the full clone-template payload via `GET /api/tests/cohort/{uuid}`, switches to the editor view, and pre-populates every section.

### 7.4 PatientBuilderEditor (two-pane)

- **Left navigator** (sticky sidebar, ≤30% width): six collapsible sections, each shows a 1-line current-content summary:
  - Demographics
  - Active conditions
  - Active medications
  - Recent labs
  - Visits summary
  - Ground truth
- **Right editor pane**: renders the focused section's editor form. One section is "open" at any time; clicking another in the navigator switches focus.
- **Sticky bottom action bar**: **Save draft** (just persists) + **Save & run pipeline →** (persists then triggers `/api/tests/runs`).

Section editors:
- `DemographicsForm`: age slider 0–120, gender radio (M/F/Other), race dropdown, BMI input, location free-text.
- `ConditionsForm`: list of chips; "+ Add condition" opens `VocabularyCombobox(kind="condition")`; each chip shows label + SNOMED code badge + date + ✕.
- `MedicationsForm`: same chip pattern with `VocabularyCombobox(kind="medication")`.
- `LabsForm`: structured rows of `{test_name, value, unit, reference_range, flag}`. Test name uses `VocabularyCombobox(kind="lab")`; value/unit/flag are plain inputs.
- `VisitsForm`: numeric inputs for total / emergency / inpatient / outpatient / wellness; optional first/last visit dates.
- `GroundTruthForm`: dropdown of the 8 thesis diseases + "Other (free text)" + "Leave blank (skip evaluator)". Pre-populated and editable when cloned.

### 7.5 VocabularyCombobox

Reusable React component. Props: `kind`, `onPick(item)`, optional `placeholder`. Internals: debounced 200ms input, fetches `/api/tests/vocabulary?kind=…&q=…`, renders dropdown with keyboard navigation and a "Use anyway: <typed text>" footer when no match. The footer entry, when clicked, commits the typed string as a chip with a small ⚠ marker.

### 7.6 Runtime view (reused)

After **Save & run**, the frontend navigates to `/tester/run/{task_id}`. The runtime view component is the same one the Doctor journey uses (`RuntimeRunningView.tsx`); a small header tag "Test patient: {label}" replaces the cohort label. SSE wiring is unchanged.

### 7.7 MyTestPatientsList

Table accessed via the header link:

| Label | Created | Last run | Latest verdict | Actions |
|---|---|---|---|---|
| `string`, click to open | relative time | relative time or "—" | DIRECT / INDIRECT / MISS / "—" | **Re-run** / **Edit** / **✕** |

`+ New from scratch` button in the top-right opens the empty editor.

## 8. Vocabulary autocomplete (details)

### Extraction

At backend startup (or on first vocabulary request, then cached for the process lifetime), the backend reads all `patient_cases` docs from MongoDB and builds three deduped sorted lists:

```python
def _build_vocabularies():
    conditions, meds, labs = set(), set(), set()
    for doc in patient_cases_collection.find({}, {"conditions":1, "medications":1, "labs":1}):
        for c in (doc.get("conditions") or {}).get("active", []):
            conditions.add((c.get("condition"), c.get("code")))
        for m in (doc.get("medications") or {}).get("active", []):
            meds.add((m.get("medication"), m.get("rx_code")))
        for lab in (doc.get("labs") or {}).get("latest_labs", []):
            labs.add(lab.get("test_name"))
    return {
        "condition":   sorted(conditions),
        "medication":  sorted(meds),
        "lab":         sorted(labs),
    }
```

Expected size on the current cohort: a few hundred unique strings per category. Cached in process memory; invalidated on backend restart.

### Filter

`GET /api/tests/vocabulary?kind=condition&q=metf` runs a case-insensitive substring match on the cached list, sorts hits with exact-prefix matches first, returns up to 20. No `q` → returns the first 20 alphabetical.

### Free-text fallback

When the user types something no suggestion matches and clicks the "Use anyway: <typed text>" dropdown footer, the chip renders with a ⚠ marker. The agents can still consume the string; the marker just signals to the clinician that the agents weren't trained on this exact label.

## 9. Save & run wiring

End-to-end sequence for **Save & run pipeline**:

1. Frontend `POST /api/tests/patients` with the full payload. Backend validates via Pydantic, generates a uuid4 hex as `test_uuid`, stamps `created_at`/`updated_at`, upserts into `test_patients`. Returns `{test_uuid, label, created_at}`.
2. Frontend `POST /api/tests/runs` with `{test_uuid, top_k, accuracy_mode}`. Backend creates a `_tasks[task_id]` entry (same shape as `/api/runs`), spawns `threading.Thread(target=_run_patient_task, daemon=True)` with `result_set="mas_results_test"`. Returns `{task_id, status:"running"}`.
3. Frontend navigates to `/tester/run/{task_id}`. The runtime view component opens `EventSource("/api/runs/{task_id}/stream")` — same SSE endpoint Doctor uses.
4. Inside the worker thread:
   - `set_thread_overrides({"MAS_RESULTS_DIR": "data/gold/mas_results_test", "MEMORY_ENABLED": …, "CANONICALIZER_ENABLED": …})` (using the thread-local override mechanism from the concurrency fix).
   - `load_patient_case(test_uuid)` hits the new branch, returns a `PipelineState` built from the Mongo doc.
   - The 7-agent pipeline streams through LangGraph. Each agent's envelope is persisted to `agent_runs.<doc>.agents.<agent_id>` via `write_agent_envelope_sync` with `result_set="mas_results_test"`. The disk JSON write goes to `data/gold/mas_results_test/<test_uuid>/` (created if absent).
   - `finalise_run_sync` stamps `finished_at` + `duration_s` on the `AgentRun` doc.
   - The worker also stamps `last_run_at` and increments `run_count` on the `TestPatient` doc.
   - `clear_thread_overrides()` in `finally`.

**Concurrency:** because the overrides are thread-local, a Doctor run and a Tester run can run in parallel without contention. This is verified by the regression test in §11.

## 10. Edit / re-run / delete flows

- **Edit:** from MyTestPatients, clicking **Edit** opens `/tester/edit/{test_uuid}`. The editor is the same component as the new-patient path, pre-populated via `GET /api/tests/patients/{test_uuid}`. **Save draft** sends `PUT`; **Save & run** sends `PUT` then `POST /api/tests/runs`.
- **Re-run:** from MyTestPatients, clicking **Re-run** is a one-click `POST /api/tests/runs` against the existing `test_uuid` — no editor step.
- **Delete:** `DELETE /api/tests/patients/{test_uuid}` removes only the doc. Past runs in `mas_results_test` are preserved as an audit trail. A `with_runs=true` query param triggers an additional `agent_runs.deleteMany({patient_uuid: test_uuid, result_set: "mas_results_test"})` and a filesystem `rm` of the runtime dir.

## 11. Validation and error handling

Validation rules (all enforced both client-side for immediate feedback and server-side via Pydantic):

| Field | Rule |
|---|---|
| `label` | required, 1–100 chars |
| `demographics.age` | required, 0–120 |
| `demographics.gender` | required, one of `M/F/Other` |
| `conditions.active`, `medications.active`, `labs.latest_labs` | optional, allowed empty |
| `ground_truth.target_condition.name` | optional; if present, free string |
| `cutoff_date` | defaults to today (UTC) if blank |

Error handling:

- **Vocabulary endpoint unreachable** → 503, frontend disables the dropdown and falls back to free-text-only mode with the standard ⚠ marker.
- **POST/PUT validation failure** → 422 with a Pydantic-style errors array; the editor highlights each failing field and the corresponding navigator section.
- **`/api/tests/runs` against missing uuid** → 404; the runtime view shows "patient not found" (reused from the Doctor journey).
- **Pipeline run crash mid-flight** → existing `BaseAgent.__call__` graceful degradation; the runtime view's per-stage red-cross UX already covers this.
- **Concurrent edits to the same `test_uuid`** → last-write-wins, but the editor compares `updated_at` on submit and shows a "modified externally" toast if the server's value is newer than the client's start-of-edit snapshot.

## 12. Testing strategy

**Unit (Python pytest):**
- `tests/test_test_patient.py` — Beanie roundtrip for `TestPatient`; lifecycle field stamping (`created_at`, `updated_at`, `last_run_at`, `run_count`).
- `tests/test_vocabulary.py` — extractor produces deduped sorted lists; substring filter is case-insensitive; exact-prefix ranking; empty cohort returns empty lists.

**Integration (Python pytest, hits the live Mongo via the existing `mongo_db` fixture):**
- `tests/integration/test_tests_api.py`
  - `POST /api/tests/patients` → `GET /api/tests/patients/{id}` roundtrip.
  - Clone path: `GET /api/tests/cohort/{uuid}` → submit → assert `source_uuid` recorded.
  - `PUT /api/tests/patients/{id}` mutates fields; `updated_at` advances; `created_at` unchanged.
  - `DELETE` preserves `mas_results_test` runs by default; `with_runs=true` purges them.
  - **Regression test for concurrency**: launch one `/api/runs` and one `/api/tests/runs` in parallel against different patients; assert both produce independent `agent_runs` docs in their respective `result_set`s.

**E2E smoke (Python pytest):**
- `tests/integration/test_tester_e2e.py` — minimal-field scratch patient → `POST /api/tests/patients` → `POST /api/tests/runs` → poll until completion → assert `TestPatient.last_run_at` and `run_count=1` are stamped, and a `mas_results_test` `AgentRun` doc has 7 agent slots populated.

**Frontend tests:** out of scope for the initial implementation — the existing console has no Vitest setup. Adding it is a separable decision. The Python integration suite + manual smoke through the live console gives sufficient coverage for thesis demonstration.

## 13. Acceptance criteria

The feature is "done" when:

1. The Tester tile appears on the splash and opens the new journey.
2. From scratch: enter age=70, gender=F, one condition (autocomplete-picked), one lab, no ground truth → Save & run → all 7 agents run → runtime view shows the differential.
3. From cohort: filter `disease=IHD, age 60–80, F` → preview a patient → "Use as template" → editor pre-populated → save & run → independent `mas_results_test` doc lands in Mongo.
4. The Researcher Overview/Memory A/B numbers (78.1%, 95.0%, 70/16/53/21) are **unchanged** after creating and running test patients — proves the namespace isolation.
5. From MyTestPatients: clicking **Re-run** against an existing test produces a second `agent_runs` doc; `run_count` increments to 2.
6. Concurrency regression: a Doctor run and a Tester run launched within 1s of each other both complete with independent `agent_runs` docs.

## 14. Out of scope

- Frontend test framework (Vitest + React Testing Library setup).
- Importing real EHR data (de-identified or otherwise) — Synthea-shaped only.
- Sharing test patients across users — single-user, single-machine for now.
- Re-deriving NICE retrieval embeddings for custom diseases — the Treatment Planning agent uses the existing Qdrant index; novel ground-truth labels may not match anything in the index, which is acceptable.
- Versioning of test patients (no edit history) — `updated_at` only.
- Bulk import (CSV upload of N patients) — one at a time.

## 15. Implementation order

This is a coarse hint; the writing-plans skill produces the detailed task list.

1. `TestPatient` Beanie document + sync write helpers in `src/db/mongo.py`.
2. `_build_vocabularies()` + the `/api/tests/vocabulary` endpoint.
3. `/api/tests/cohort` + `/api/tests/cohort/{uuid}` (the read-only browse + clone-template endpoints).
4. `POST /api/tests/patients` + `GET /api/tests/patients` + single-doc GET / PUT / DELETE.
5. `load_patient_case` extension in `src/orchestrator/graph.py`.
6. `POST /api/tests/runs` + `_run_patient_task` accepting the `result_set` override.
7. `VocabularyCombobox` React component + integration into the section editors.
8. `PatientPicker`, `PatientBuilderEditor`, section editors, `MyTestPatientsList`.
9. `TesterJourney` route + splash tile.
10. Validation rules client+server.
11. Tests (unit + integration + E2E).
12. Manual smoke on the live system + screenshot pass for the thesis.
