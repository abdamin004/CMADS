# Tester — Patient Builder & Test Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a third top-level journey "Tester (build & run)" to the CMADS doctor console — a clinician can build a synthetic patient from scratch OR clone-and-edit a cohort patient, then one-click "Save & run" persists them to a separate Mongo collection and immediately runs the seven-agent pipeline against them. Past test patients live forever in a revisit list.

**Architecture:** New Mongo collection `test_patients` for storage (separate from `patient_cases`), pipeline runs land in cohort `mas_results_test` (separate from research cohorts), nine new REST endpoints under `/api/tests/*`, one branch in `load_patient_case()` to consume test patients, seven new React components, one tile added to the splash. The existing SSE stream, `_tasks` in-memory store, and thread-local-overrides concurrency mechanism are all reused — no new SSE wiring, no new locks.

**Tech Stack:** Python 3.12, FastAPI, Beanie ODM + sync PyMongo, MongoDB 7, React 19 + Vite + TypeScript + TailwindCSS + framer-motion, pytest + pytest-asyncio.

**Spec reference:** [`docs/superpowers/specs/2026-05-23-tester-patient-builder-design.md`](../specs/2026-05-23-tester-patient-builder-design.md).

---

## File Structure

**New files:**
| Path | Purpose |
|---|---|
| `tests/test_test_patient.py` | Unit tests: `TestPatient` Beanie roundtrip + lifecycle field stamping |
| `tests/test_vocabulary.py` | Unit tests: extractor produces deduped sorted lists; substring filter ranks exact-prefix first |
| `tests/integration/test_tests_api.py` | Integration: 9 new REST endpoints + concurrency regression |
| `tests/integration/test_tester_e2e.py` | E2E smoke: build patient → save → run → verify Mongo state |
| `doctor_console/frontend/src/components/TesterJourney.tsx` | Top-level route; segmented control cohort/scratch + my-test-patients link |
| `doctor_console/frontend/src/components/PatientPicker.tsx` | Cohort browser: facets sidebar + list + preview pane |
| `doctor_console/frontend/src/components/PatientBuilderEditor.tsx` | Two-pane editor shell: navigator + focused section editor |
| `doctor_console/frontend/src/components/VocabularyCombobox.tsx` | Reusable debounced typeahead over the cohort vocabulary |
| `doctor_console/frontend/src/components/tester/DemographicsForm.tsx` | Age/gender/race/BMI editor |
| `doctor_console/frontend/src/components/tester/ConditionsForm.tsx` | Chips of conditions, autocomplete add |
| `doctor_console/frontend/src/components/tester/MedicationsForm.tsx` | Chips of medications, autocomplete add |
| `doctor_console/frontend/src/components/tester/LabsForm.tsx` | Structured lab rows (test_name + value + unit + flag) |
| `doctor_console/frontend/src/components/tester/VisitsForm.tsx` | Numeric inputs for visit totals |
| `doctor_console/frontend/src/components/tester/GroundTruthForm.tsx` | 8-disease dropdown + Other + Leave blank |
| `doctor_console/frontend/src/components/MyTestPatientsList.tsx` | Revisit table |

**Modified files:**
| Path | Change |
|---|---|
| `src/db/documents.py` | Add `TestPatient` Document class |
| `src/db/mongo.py` | Add 5 sync write/read helpers (`write_test_patient_sync`, `update_test_patient_sync`, `stamp_test_run_sync`, `get_test_patient_sync`, `delete_test_patient_sync`) and 1 vocabulary builder (`build_vocabularies`) |
| `src/orchestrator/graph.py` | Extend `load_patient_case()` with the `test_patients` branch |
| `doctor_console/backend/app.py` | Add 9 endpoints, vocabulary cache, request/response Pydantic models, `_run_patient_task` `result_set` kwarg |
| `doctor_console/frontend/src/api.ts` | Add 9 client functions matching the new endpoints |
| `doctor_console/frontend/src/types.ts` | Add `TestPatient`, `CohortBrowseRow`, `VocabularyItem`, `TestPatientSummary` types |
| `doctor_console/frontend/src/components/ModeChooser.tsx` | Add the third "Tester" tile |
| `doctor_console/frontend/src/App.tsx` | Route the Tester journey and the runtime view's `/tester/run/{task_id}` |

**Untouched:** Synthea Bronze, OMOP DuckDB Silver, Qdrant, prompt YAML files, the 7 agents, the LangGraph graph definition, the SSE stream endpoint, the `_tasks` store, the existing Doctor/Researcher journeys.

---

## Phase 1 — Backend foundations (TestPatient + sync helpers + vocabulary)

### Task 1: `TestPatient` Beanie Document (TDD)

**Files:**
- Modify: `src/db/documents.py`
- Create: `tests/test_test_patient.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_test_patient.py`:

```python
"""Unit tests for the TestPatient Beanie Document."""
import pytest
from datetime import datetime

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_test_patient_roundtrip(mongo_db):
    """TestPatient saves with all 15 PatientCase mirror fields + lifecycle
    fields and round-trips identically."""
    from src.db.documents import TestPatient

    now = datetime.utcnow()
    doc = TestPatient(
        id="ttest-001",
        label="70yo CKD-4 + new HF onset",
        source_uuid="04ad2732-b952-4fbb-d2c6-aa6c25f9462f",
        created_at=now,
        updated_at=now,
        person_id=0,
        cutoff_date=datetime(2024, 1, 1),
        case_type="ehr+lab",
        demographics={"age": 70, "gender": "F", "race": "white"},
        conditions={"active": [{"condition": "CKD stage 4", "code": "431857002"}]},
        medications={"active": []},
        visits={"total": 12},
        labs={"latest_labs": [{"test_name": "eGFR", "value": "22", "unit": "mL/min"}]},
        ground_truth={"target_condition": {"name": "End-stage renal disease"}},
        assembled_at=now,
    )
    await doc.insert()

    loaded = await TestPatient.get("ttest-001")
    assert loaded is not None
    assert loaded.label == "70yo CKD-4 + new HF onset"
    assert loaded.source_uuid == "04ad2732-b952-4fbb-d2c6-aa6c25f9462f"
    assert loaded.demographics["age"] == 70
    assert loaded.ground_truth["target_condition"]["name"] == "End-stage renal disease"
    assert loaded.run_count == 0
    assert loaded.last_run_at is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_test_patient.py::test_test_patient_roundtrip -v`
Expected: FAIL with `ImportError: cannot import name 'TestPatient'` or similar.

- [ ] **Step 3: Add `TestPatient` to `src/db/documents.py`**

Append to `src/db/documents.py` (after `DerivedArtefact`):

```python
class TestPatient(Document):
    """Custom patient built (or cloned) by the clinician in the Tester
    journey. Schema mirrors PatientCase plus authorship + lifecycle
    metadata. Lives in its own collection so research aggregations
    never see it.

    See docs/superpowers/specs/2026-05-23-tester-patient-builder-design.md
    """
    id: str = Field(alias="_id")          # test_uuid (uuid4 hex, "ttest-" prefix)
    label: str
    source_uuid: str | None = None        # cohort uuid if cloned; None for scratch
    created_at: datetime
    updated_at: datetime
    last_run_at: datetime | None = None
    run_count: int = 0

    # PatientCase mirror — same field names + shapes so load_patient_case
    # can consume a TestPatient with one extra branch and no schema xlate.
    person_id: int = 0
    cutoff_date: datetime
    case_type: str = "ehr+lab"
    demographics: dict[str, Any]
    conditions: dict[str, Any] = Field(default_factory=dict)
    medications: dict[str, Any] = Field(default_factory=dict)
    visits: dict[str, Any] | list[dict[str, Any]] = Field(default_factory=dict)
    comorbidity: dict[str, Any] = Field(default_factory=dict)
    risk_scores: dict[str, Any] = Field(default_factory=dict)
    labs: dict[str, Any] = Field(default_factory=dict)
    ground_truth: dict[str, Any] = Field(default_factory=dict)
    case_stats: dict[str, Any] = Field(default_factory=dict)
    assembled_at: datetime
    pipeline_version: str = "tester-1.0"

    class Settings:
        name = "test_patients"
        indexes = ["created_at", "last_run_at"]
```

- [ ] **Step 4: Register `TestPatient` in `src/db/mongo.py`**

Open `src/db/mongo.py`. Find the line `from src.db.documents import (` and add `TestPatient` to the import list. Find `_DOCUMENT_MODELS = [...]` and add `TestPatient` to that list. Both edits in the same block at the top of the file.

- [ ] **Step 5: Update `tests/integration/conftest_mongo.py` to bind `TestPatient`**

Open `tests/integration/conftest_mongo.py`. Find the import that lists the four existing Document classes and add `TestPatient`:

```python
from src.db.documents import PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact, TestPatient
```

Then update the `document_models=[...]` list passed to `init_beanie` in the fixture to include `TestPatient`.

- [ ] **Step 6: Run test to verify it passes**

Run: `pytest tests/test_test_patient.py::test_test_patient_roundtrip -v`
Expected: PASS in <2s.

- [ ] **Step 7: Commit**

```bash
git add src/db/documents.py src/db/mongo.py tests/test_test_patient.py tests/integration/conftest_mongo.py
git commit -m "db: add TestPatient document for the Tester journey

Separate collection 'test_patients' keeps clinician-built patients
out of the research aggregations. Schema mirrors PatientCase plus
lifecycle fields (created_at, updated_at, last_run_at, run_count,
label, optional source_uuid)."
```

---

### Task 2: Sync write helpers in `src/db/mongo.py` (TDD)

**Files:**
- Modify: `src/db/mongo.py`
- Modify: `tests/test_test_patient.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/test_test_patient.py`:

```python
def test_write_test_patient_sync_creates_doc():
    """write_test_patient_sync upserts and stamps created_at/updated_at."""
    from src.db.mongo import write_test_patient_sync, get_test_patient_sync, _coll
    _coll("test_patients").delete_many({"_id": "ttest-sync-1"})

    write_test_patient_sync({
        "_id": "ttest-sync-1",
        "label": "sync test",
        "demographics": {"age": 50, "gender": "M"},
        "labs": {"latest_labs": []},
        "cutoff_date": "2024-01-01",
    })

    loaded = get_test_patient_sync("ttest-sync-1")
    assert loaded is not None
    assert loaded["label"] == "sync test"
    assert loaded["created_at"] is not None
    assert loaded["updated_at"] is not None
    assert loaded["run_count"] == 0
    assert loaded["last_run_at"] is None
    _coll("test_patients").delete_one({"_id": "ttest-sync-1"})


def test_update_test_patient_sync_advances_updated_at():
    """PUT-style update bumps updated_at but preserves created_at."""
    import time
    from src.db.mongo import (
        write_test_patient_sync, update_test_patient_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-2"})
    write_test_patient_sync({
        "_id": "ttest-sync-2",
        "label": "original",
        "demographics": {"age": 50, "gender": "M"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })
    original = get_test_patient_sync("ttest-sync-2")
    time.sleep(0.01)  # ensure updated_at changes

    update_test_patient_sync("ttest-sync-2", {"label": "edited"})
    edited = get_test_patient_sync("ttest-sync-2")

    assert edited["label"] == "edited"
    assert edited["created_at"] == original["created_at"]
    assert edited["updated_at"] > original["updated_at"]
    _coll("test_patients").delete_one({"_id": "ttest-sync-2"})


def test_stamp_test_run_sync_increments_run_count():
    """stamp_test_run_sync sets last_run_at and increments run_count."""
    from src.db.mongo import (
        write_test_patient_sync, stamp_test_run_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-3"})
    write_test_patient_sync({
        "_id": "ttest-sync-3",
        "label": "x",
        "demographics": {"age": 30, "gender": "F"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })

    stamp_test_run_sync("ttest-sync-3")
    stamp_test_run_sync("ttest-sync-3")
    d = get_test_patient_sync("ttest-sync-3")

    assert d["run_count"] == 2
    assert d["last_run_at"] is not None
    _coll("test_patients").delete_one({"_id": "ttest-sync-3"})


def test_delete_test_patient_sync_removes_doc():
    """delete_test_patient_sync removes only the doc, not derived runs."""
    from src.db.mongo import (
        write_test_patient_sync, delete_test_patient_sync, get_test_patient_sync, _coll,
    )
    _coll("test_patients").delete_many({"_id": "ttest-sync-4"})
    write_test_patient_sync({
        "_id": "ttest-sync-4",
        "label": "del-me",
        "demographics": {"age": 30, "gender": "F"},
        "labs": {},
        "cutoff_date": "2024-01-01",
    })
    assert get_test_patient_sync("ttest-sync-4") is not None

    delete_test_patient_sync("ttest-sync-4")
    assert get_test_patient_sync("ttest-sync-4") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_test_patient.py -v -k sync`
Expected: 4 FAIL on `ImportError: cannot import name 'write_test_patient_sync'`.

- [ ] **Step 3: Implement the five helpers**

Open `src/db/mongo.py`. After the existing `semantic_inc_sync` function, append:

```python
# ── Tester-journey sync helpers ────────────────────────────────────

def write_test_patient_sync(payload: dict) -> None:
    """Upsert a TestPatient document. Stamps created_at on insert,
    updated_at on every write. Defaults run_count=0, last_run_at=None.
    The caller supplies `_id` (test_uuid)."""
    from datetime import datetime
    now = datetime.utcnow()
    doc = dict(payload)  # copy so we don't mutate the caller's dict
    doc.setdefault("created_at", now)
    doc["updated_at"] = now
    doc.setdefault("run_count", 0)
    doc.setdefault("last_run_at", None)
    doc.setdefault("assembled_at", now)
    doc.setdefault("pipeline_version", "tester-1.0")
    # cutoff_date arrives as a string from the REST layer; normalise to dt
    if isinstance(doc.get("cutoff_date"), str):
        doc["cutoff_date"] = datetime.fromisoformat(doc["cutoff_date"][:10])
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_test_patient.py -v -k sync`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db/mongo.py tests/test_test_patient.py
git commit -m "db: add sync test_patients write/read helpers

Five sync PyMongo helpers for the Tester journey:
write/update/stamp_run/get/delete. Same thread-safe sync pattern
the agent path already uses (no asyncio loop binding)."
```

---

### Task 3: Vocabulary extractor + filter (TDD)

**Files:**
- Modify: `src/db/mongo.py`
- Create: `tests/test_vocabulary.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_vocabulary.py`:

```python
"""Unit tests for the cohort vocabulary extractor + filter."""
import pytest


def test_build_vocabularies_dedups_and_sorts():
    """build_vocabularies returns three deduped sorted lists keyed by kind."""
    from src.db.mongo import build_vocabularies

    docs = [
        {"conditions":  {"active": [{"condition": "Hypertension", "code": "59621000"},
                                     {"condition": "T2DM",         "code": "44054006"}]},
         "medications": {"active": [{"medication": "Metformin", "rx_code": "861007"}]},
         "labs":        {"latest_labs": [{"test_name": "HbA1c"},
                                         {"test_name": "LDL cholesterol"}]}},
        {"conditions":  {"active": [{"condition": "Hypertension", "code": "59621000"}]},
         "medications": {"active": [{"medication": "Lisinopril", "rx_code": "29046"}]},
         "labs":        {"latest_labs": [{"test_name": "HbA1c"}]}},
    ]
    vocab = build_vocabularies(docs)

    assert vocab["condition"] == [
        {"label": "Hypertension", "code": "59621000"},
        {"label": "T2DM",         "code": "44054006"},
    ]
    assert vocab["medication"] == [
        {"label": "Lisinopril", "code": "29046"},
        {"label": "Metformin",  "code": "861007"},
    ]
    assert vocab["lab"] == [
        {"label": "HbA1c",           "code": None},
        {"label": "LDL cholesterol", "code": None},
    ]


def test_filter_vocabulary_exact_prefix_first():
    """filter_vocabulary returns prefix-matches before substring-matches."""
    from src.db.mongo import filter_vocabulary

    vocab = [
        {"label": "Ametformin XR", "code": "1"},   # substring match
        {"label": "Metformin",     "code": "2"},   # prefix match
        {"label": "Metformin XR",  "code": "3"},   # prefix match
        {"label": "Aspirin",       "code": "4"},   # no match
    ]
    out = filter_vocabulary(vocab, "metf", limit=20)
    labels = [it["label"] for it in out]
    assert labels == ["Metformin", "Metformin XR", "Ametformin XR"]


def test_filter_vocabulary_empty_query_returns_first_n():
    """Empty q returns the first `limit` items alphabetically."""
    from src.db.mongo import filter_vocabulary
    vocab = [{"label": f"item{i:03d}", "code": str(i)} for i in range(30)]
    out = filter_vocabulary(vocab, "", limit=5)
    assert [it["label"] for it in out] == ["item000","item001","item002","item003","item004"]


def test_filter_vocabulary_case_insensitive():
    from src.db.mongo import filter_vocabulary
    vocab = [{"label": "Metformin", "code": "x"}]
    assert filter_vocabulary(vocab, "METF", limit=5)[0]["label"] == "Metformin"
    assert filter_vocabulary(vocab, "metf", limit=5)[0]["label"] == "Metformin"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vocabulary.py -v`
Expected: 4 FAIL on `ImportError`.

- [ ] **Step 3: Implement the extractor + filter**

Append to `src/db/mongo.py`:

```python
# ── Vocabulary extractor for the Tester journey autocomplete ──────────

def build_vocabularies(patient_case_docs: list[dict]) -> dict[str, list[dict]]:
    """Walk a list of patient_cases-shaped dicts and produce three
    deduped sorted lists. Pass it the output of
    list(_coll("patient_cases").find({}, {projection}))."""
    cond_set: set[tuple[str, str | None]] = set()
    med_set:  set[tuple[str, str | None]] = set()
    lab_set:  set[str] = set()

    for doc in patient_case_docs:
        for c in (doc.get("conditions",  {}) or {}).get("active", []) or []:
            label = c.get("condition")
            if label:
                cond_set.add((label, c.get("code")))
        for m in (doc.get("medications", {}) or {}).get("active", []) or []:
            label = m.get("medication")
            if label:
                med_set.add((label, m.get("rx_code")))
        for lab in (doc.get("labs", {}) or {}).get("latest_labs", []) or []:
            name = lab.get("test_name")
            if name:
                lab_set.add(name)

    return {
        "condition":  [{"label": l, "code": c} for l, c in sorted(cond_set)],
        "medication": [{"label": l, "code": c} for l, c in sorted(med_set)],
        "lab":        [{"label": l, "code": None} for l in sorted(lab_set)],
    }


def filter_vocabulary(vocab: list[dict], q: str, limit: int = 20) -> list[dict]:
    """Filter a single-category vocab list. Empty `q` returns the first
    `limit` items unchanged (already alphabetical from build_vocabularies).
    Otherwise: case-insensitive; prefix matches ranked before substring
    matches; up to `limit` items returned."""
    if not q:
        return vocab[:limit]
    q_lower = q.lower()
    prefix:   list[dict] = []
    contains: list[dict] = []
    for item in vocab:
        lbl = (item.get("label") or "").lower()
        if lbl.startswith(q_lower):
            prefix.append(item)
        elif q_lower in lbl:
            contains.append(item)
    return (prefix + contains)[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vocabulary.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/db/mongo.py tests/test_vocabulary.py
git commit -m "db: vocabulary extractor + filter for Tester autocomplete

build_vocabularies walks patient_cases-shaped dicts and emits three
deduped sorted lists (conditions with SNOMED codes, medications with
rxcui codes, lab test names). filter_vocabulary ranks exact-prefix
matches before substring matches, case-insensitive, capped at limit."
```

---

## Phase 2 — Backend REST endpoints

### Task 4: Pydantic request/response models for the new endpoints

**Files:**
- Modify: `doctor_console/backend/app.py`

- [ ] **Step 1: Locate the existing model block**

Open `doctor_console/backend/app.py`. Find the existing `class RunRequest(BaseModel):` definition (around line 130-170 in the current file; use `grep -n 'class RunRequest' doctor_console/backend/app.py` to locate exactly). The new test-patient models go immediately after it.

- [ ] **Step 2: Add the new Pydantic models**

After `class RunRequest(BaseModel):`, append:

```python
class TestPatientPayload(BaseModel):
    """Body for POST /api/tests/patients and PUT /api/tests/patients/{id}.
    The validation here is the server-side mirror of the client-side
    rules in PatientBuilderEditor.tsx. Required: label, demographics
    with age + gender. Everything else optional."""
    label:         str = Field(..., min_length=1, max_length=100)
    source_uuid:   str | None = None
    demographics:  dict[str, Any]
    conditions:    dict[str, Any] | None = None
    medications:   dict[str, Any] | None = None
    visits:        dict[str, Any] | list[dict[str, Any]] | None = None
    comorbidity:   dict[str, Any] | None = None
    risk_scores:   dict[str, Any] | None = None
    labs:          dict[str, Any] | None = None
    ground_truth:  dict[str, Any] | None = None
    case_stats:    dict[str, Any] | None = None
    cutoff_date:   str | None = None   # ISO yyyy-mm-dd; backend defaults to today if missing

    @field_validator("demographics")
    @classmethod
    def _validate_demographics(cls, v: dict) -> dict:
        if "age" not in v:
            raise ValueError("demographics.age is required")
        age = v["age"]
        if not isinstance(age, (int, float)) or not (0 <= age <= 120):
            raise ValueError("demographics.age must be a number between 0 and 120")
        if v.get("gender") not in ("M", "F", "Other"):
            raise ValueError("demographics.gender must be one of M / F / Other")
        return v


class TestRunRequest(BaseModel):
    """Body for POST /api/tests/runs."""
    test_uuid:     str
    top_k:         int = 5
    accuracy_mode: str = "recommended"   # same vocab as RunRequest
    provider:      str | None = None
    model:         str | None = None
    preset_id:     str | None = None
```

Make sure `field_validator` is imported at the top of `app.py` (`from pydantic import BaseModel, Field, field_validator`).

- [ ] **Step 3: Smoke import**

Run: `python3 -c "from doctor_console.backend.app import TestPatientPayload, TestRunRequest; print('models ok')"`
Expected: `models ok`.

- [ ] **Step 4: Commit**

```bash
git add doctor_console/backend/app.py
git commit -m "backend: add Pydantic models for the Tester REST surface

TestPatientPayload validates label + demographics.age + demographics.gender;
everything else optional. TestRunRequest mirrors RunRequest's shape."
```

---

### Task 5: `GET /api/tests/vocabulary` endpoint

**Files:**
- Modify: `doctor_console/backend/app.py`
- Modify: `tests/integration/test_tests_api.py` (created here)

- [ ] **Step 1: Create the integration test file with a failing first test**

Create `tests/integration/test_tests_api.py`:

```python
"""Integration tests for the /api/tests/* REST surface."""
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.fixture
def client(mongo_db, monkeypatch):
    """Build a fresh TestClient for each test. Monkeypatches USE_MONGO=true
    and points the backend at the per-test mongo_db fixture's database."""
    monkeypatch.setenv("USE_MONGO", "true")
    monkeypatch.setenv("MONGO_DB", mongo_db.name)
    # Re-import the app so the lifespan re-runs against the test DB
    from importlib import reload
    import doctor_console.backend.app as app_mod
    reload(app_mod)
    return TestClient(app_mod.app)


def test_vocabulary_returns_filtered_items(client, mongo_db):
    """GET /api/tests/vocabulary?kind=condition&q=metf returns prefix-first matches."""
    # Seed a couple of patient_cases docs with vocab the test can find
    from datetime import datetime
    mongo_db["patient_cases"].insert_one({
        "_id": "seed-1",
        "person_id": 1, "cutoff_date": datetime(2024,1,1), "case_type": "ehr+lab",
        "demographics": {}, "conditions": {"active":[{"condition":"Metabolic syndrome","code":"X1"}]},
        "medications": {"active":[{"medication":"Metformin","rx_code":"861007"}]},
        "visits": {}, "comorbidity":{}, "risk_scores":{}, "labs":{"latest_labs":[]},
        "ground_truth":{}, "case_stats":{}, "assembled_at": datetime.utcnow(),
        "pipeline_version": "x",
    })

    r = client.get("/api/tests/vocabulary?kind=medication&q=metf")
    assert r.status_code == 200
    items = r.json()
    assert any(it["label"] == "Metformin" for it in items)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/integration/test_tests_api.py::test_vocabulary_returns_filtered_items -v`
Expected: FAIL with 404 on the endpoint.

- [ ] **Step 3: Implement the endpoint**

Open `doctor_console/backend/app.py`. Find a sensible insertion point near the other `@app.get(...)` decorators (around line 800-900, after the existing comparison endpoints; use grep to locate). Add a module-level vocabulary cache and the endpoint:

```python
# ── Tester journey: vocabulary cache + endpoint ──────────────────────

_vocab_cache: dict[str, list[dict]] | None = None
_vocab_lock = threading.Lock()


def _get_vocab() -> dict[str, list[dict]]:
    """Build the autocomplete vocabulary on first call, then cache for
    process lifetime. Walks every doc in patient_cases — runs once per
    backend process, takes <1s on the 3348-doc cohort."""
    global _vocab_cache
    if _vocab_cache is not None:
        return _vocab_cache
    with _vocab_lock:
        if _vocab_cache is None:
            from src.db.mongo import build_vocabularies, _coll
            cursor = _coll("patient_cases").find(
                {}, {"conditions": 1, "medications": 1, "labs": 1},
            )
            _vocab_cache = build_vocabularies(list(cursor))
    return _vocab_cache


@app.get("/api/tests/vocabulary")
def tester_vocabulary(kind: str = Query(..., regex="^(condition|medication|lab)$"),
                      q: str = Query("")) -> list[dict[str, Any]]:
    """Autocomplete dictionary for the Tester journey forms."""
    from src.db.mongo import filter_vocabulary
    vocab = _get_vocab().get(kind, [])
    return filter_vocabulary(vocab, q, limit=20)
```

`threading` and `Query` are both already imported in `app.py`. If `Query` isn't, add `from fastapi import Query`.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/integration/test_tests_api.py::test_vocabulary_returns_filtered_items -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_tests_api.py
git commit -m "backend: GET /api/tests/vocabulary for autocomplete

In-memory cache lazily built on first request from the live
patient_cases collection. Filter is case-insensitive with
prefix-matches ranked first, capped at 20 items per query."
```

---

### Task 6: `GET /api/tests/cohort` + `GET /api/tests/cohort/{uuid}` endpoints

**Files:**
- Modify: `doctor_console/backend/app.py`
- Modify: `tests/integration/test_tests_api.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_tests_api.py`:

```python
def test_cohort_browse_filters_by_disease(client, mongo_db):
    """GET /api/tests/cohort?disease=IHD returns only IHD patients."""
    from datetime import datetime
    base = {
        "person_id": 1, "cutoff_date": datetime(2024,1,1), "case_type": "ehr+lab",
        "conditions":{"active":[]}, "medications":{"active":[]}, "visits":{},
        "comorbidity":{}, "risk_scores":{}, "labs":{"latest_labs":[]},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    }
    mongo_db["patient_cases"].insert_many([
        {**base, "_id": "ihd-1", "demographics":{"age":70,"gender":"F"},
         "ground_truth":{"target_condition":{"name":"Ischemic heart disease"}}},
        {**base, "_id": "t2dm-1", "demographics":{"age":65,"gender":"M"},
         "ground_truth":{"target_condition":{"name":"Diabetes mellitus type 2"}}},
    ])

    r = client.get("/api/tests/cohort?disease=Ischemic heart disease")
    assert r.status_code == 200
    rows = r.json()
    uuids = [row["uuid"] for row in rows]
    assert "ihd-1" in uuids
    assert "t2dm-1" not in uuids


def test_cohort_browse_filters_by_age_and_gender(client, mongo_db):
    from datetime import datetime
    base = {
        "person_id": 1, "cutoff_date": datetime(2024,1,1), "case_type": "ehr+lab",
        "conditions":{"active":[]}, "medications":{"active":[]}, "visits":{},
        "comorbidity":{}, "risk_scores":{}, "labs":{"latest_labs":[]},
        "ground_truth":{"target_condition":{"name":"Hypertension"}},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    }
    mongo_db["patient_cases"].insert_many([
        {**base, "_id":"a","demographics":{"age":50,"gender":"F"}},
        {**base, "_id":"b","demographics":{"age":70,"gender":"F"}},
        {**base, "_id":"c","demographics":{"age":70,"gender":"M"}},
    ])

    r = client.get("/api/tests/cohort?age_min=60&age_max=80&gender=F")
    assert r.status_code == 200
    uuids = sorted(row["uuid"] for row in r.json())
    assert uuids == ["b"]


def test_cohort_template_returns_clone_payload(client, mongo_db):
    """GET /api/tests/cohort/{uuid} returns the patient as a clone template."""
    from datetime import datetime
    mongo_db["patient_cases"].insert_one({
        "_id": "src-1",
        "person_id": 7, "cutoff_date": datetime(2024,1,1), "case_type":"ehr+lab",
        "demographics":{"age":60,"gender":"M"},
        "conditions":{"active":[{"condition":"T2DM","code":"44054006"}]},
        "medications":{"active":[]}, "visits":{}, "comorbidity":{}, "risk_scores":{},
        "labs":{"latest_labs":[]},
        "ground_truth":{"target_condition":{"name":"Diabetes mellitus type 2"}},
        "case_stats":{}, "assembled_at": datetime.utcnow(), "pipeline_version":"x",
    })

    r = client.get("/api/tests/cohort/src-1")
    assert r.status_code == 200
    body = r.json()
    assert body["source_uuid"] == "src-1"
    assert body["demographics"]["age"] == 60
    assert body["ground_truth"]["target_condition"]["name"] == "Diabetes mellitus type 2"
    # Not a real TestPatient yet — no _id, no created_at
    assert "_id" not in body and "created_at" not in body
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_tests_api.py -v -k cohort`
Expected: 3 FAIL with 404.

- [ ] **Step 3: Implement the endpoints**

Add to `doctor_console/backend/app.py` near the vocabulary endpoint:

```python
@app.get("/api/tests/cohort")
def tester_cohort_browse(
    disease:  str | None = Query(None),
    age_min:  int | None = Query(None, ge=0, le=120),
    age_max:  int | None = Query(None, ge=0, le=120),
    gender:   str | None = Query(None, regex="^(M|F|Other)$"),
    limit:    int = Query(50, ge=1, le=200),
) -> list[dict[str, Any]]:
    """Faceted browse of patient_cases for the Tester journey's
    clone-from-cohort flow. Returns summary rows; full payload via
    /api/tests/cohort/{uuid}."""
    from src.db.mongo import _coll
    q: dict[str, Any] = {}
    if disease:
        q["ground_truth.target_condition.name"] = disease
    if age_min is not None or age_max is not None:
        age_q: dict[str, Any] = {}
        if age_min is not None: age_q["$gte"] = age_min
        if age_max is not None: age_q["$lte"] = age_max
        q["demographics.age"] = age_q
    if gender:
        q["demographics.gender"] = gender

    rows: list[dict[str, Any]] = []
    for d in _coll("patient_cases").find(q).limit(limit):
        active_count = len(((d.get("conditions") or {}).get("active") or []))
        rows.append({
            "uuid":          d["_id"],
            "age":           (d.get("demographics") or {}).get("age"),
            "gender":        (d.get("demographics") or {}).get("gender"),
            "disease":       ((d.get("ground_truth") or {}).get("target_condition") or {}).get("name"),
            "active_count":  active_count,
        })
    return rows


@app.get("/api/tests/cohort/{uuid}")
def tester_cohort_template(uuid: str) -> dict[str, Any]:
    """Load a single cohort patient as a clone-template payload. The
    response is shaped like a TestPatientPayload (no _id, no
    created_at) with source_uuid set so the frontend's POST can record
    the lineage."""
    from src.db.mongo import _coll
    d = _coll("patient_cases").find_one({"_id": uuid})
    if not d:
        raise HTTPException(status_code=404, detail=f"Unknown cohort uuid: {uuid}")
    # Strip server-managed fields, prepare for the editor
    keep = {"demographics", "conditions", "medications", "visits",
            "comorbidity", "risk_scores", "labs", "ground_truth",
            "case_stats", "cutoff_date", "case_type"}
    out = {k: d[k] for k in keep if k in d}
    if isinstance(out.get("cutoff_date"), datetime):
        out["cutoff_date"] = out["cutoff_date"].date().isoformat()
    out["source_uuid"] = uuid
    out["label"] = f"Clone of {uuid[:11]}"
    return out
```

`datetime` is already imported (from the existing `from datetime import datetime` at the top of app.py).

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_tests_api.py -v -k cohort`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_tests_api.py
git commit -m "backend: GET /api/tests/cohort + cohort/{uuid} for clone flow

Faceted browse over patient_cases by disease/age/gender; clone-template
endpoint returns a TestPatientPayload-shaped dict (no _id, no
created_at, source_uuid prefilled) so the editor pre-populates."
```

---

### Task 7: `POST` / `GET` / `PUT` / `DELETE` `/api/tests/patients` endpoints

**Files:**
- Modify: `doctor_console/backend/app.py`
- Modify: `tests/integration/test_tests_api.py`

- [ ] **Step 1: Append failing tests**

Append to `tests/integration/test_tests_api.py`:

```python
def test_post_test_patient_creates_doc(client):
    payload = {
        "label": "70F sketch",
        "demographics": {"age": 70, "gender": "F"},
        "labs": {"latest_labs": []},
    }
    r = client.post("/api/tests/patients", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["label"] == "70F sketch"
    assert body["test_uuid"].startswith("ttest-")
    assert body["created_at"] is not None


def test_post_validates_required_fields(client):
    r = client.post("/api/tests/patients", json={"demographics":{"age":70,"gender":"F"}})
    assert r.status_code == 422  # missing label

    r = client.post("/api/tests/patients", json={"label":"x","demographics":{"gender":"F"}})
    assert r.status_code == 422  # missing age


def test_get_test_patient_returns_full_doc(client):
    created = client.post("/api/tests/patients", json={
        "label": "g-test",
        "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.get(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 200
    body = r.json()
    assert body["_id"] == test_uuid
    assert body["label"] == "g-test"
    assert body["run_count"] == 0
    assert body["last_run_at"] is None


def test_put_test_patient_updates_label(client):
    created = client.post("/api/tests/patients", json={
        "label": "old",
        "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.put(f"/api/tests/patients/{test_uuid}", json={
        "label": "new",
        "demographics": {"age": 60, "gender": "M"},
    })
    assert r.status_code == 200
    assert r.json()["label"] == "new"


def test_list_test_patients_returns_summaries(client):
    client.post("/api/tests/patients", json={"label":"a","demographics":{"age":60,"gender":"M"}})
    client.post("/api/tests/patients", json={"label":"b","demographics":{"age":60,"gender":"F"}})
    r = client.get("/api/tests/patients")
    assert r.status_code == 200
    rows = r.json()
    labels = [row["label"] for row in rows]
    assert "a" in labels and "b" in labels
    # Summaries don't carry the full payload — just headline fields
    assert all("test_uuid" in row and "created_at" in row for row in rows)


def test_delete_test_patient(client):
    created = client.post("/api/tests/patients", json={
        "label": "del", "demographics": {"age": 60, "gender": "M"},
    }).json()
    test_uuid = created["test_uuid"]

    r = client.delete(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 200
    r = client.get(f"/api/tests/patients/{test_uuid}")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/integration/test_tests_api.py -v -k 'post_test_patient or post_validates or get_test_patient or put_test_patient or list_test_patients or delete_test_patient'`
Expected: 6 FAIL with 404 on most.

- [ ] **Step 3: Implement the endpoints**

Add to `doctor_console/backend/app.py` near the cohort endpoints:

```python
import uuid as _uuid_pkg


def _new_test_uuid() -> str:
    return f"ttest-{_uuid_pkg.uuid4().hex[:16]}"


@app.post("/api/tests/patients")
def tester_create_patient(payload: TestPatientPayload) -> dict[str, Any]:
    """Create a new TestPatient. Generates a `ttest-` uuid, stamps
    created_at + updated_at. Returns the summary {test_uuid, label,
    created_at} so the frontend can immediately POST /api/tests/runs."""
    from src.db.mongo import write_test_patient_sync, get_test_patient_sync

    test_uuid = _new_test_uuid()
    doc = payload.model_dump(exclude_unset=False)
    doc["_id"] = test_uuid
    if not doc.get("cutoff_date"):
        doc["cutoff_date"] = datetime.utcnow().date().isoformat()
    # Ensure dict default for empty fields the schema expects
    for k in ("conditions", "medications", "visits", "comorbidity",
              "risk_scores", "labs", "ground_truth", "case_stats"):
        if doc.get(k) is None:
            doc[k] = {}
    write_test_patient_sync(doc)
    created = get_test_patient_sync(test_uuid)
    return {
        "test_uuid":  test_uuid,
        "label":      created["label"],
        "created_at": created["created_at"],
    }


@app.get("/api/tests/patients")
def tester_list_patients(q: str | None = Query(None)) -> list[dict[str, Any]]:
    """List all test patients as summaries, newest first."""
    from src.db.mongo import _coll
    query: dict[str, Any] = {}
    if q:
        query["label"] = {"$regex": q, "$options": "i"}
    rows: list[dict[str, Any]] = []
    for d in _coll("test_patients").find(query).sort("created_at", -1):
        rows.append({
            "test_uuid":     d["_id"],
            "label":         d.get("label"),
            "created_at":    d.get("created_at"),
            "updated_at":    d.get("updated_at"),
            "last_run_at":   d.get("last_run_at"),
            "run_count":     d.get("run_count", 0),
            "source_uuid":   d.get("source_uuid"),
        })
    return rows


@app.get("/api/tests/patients/{test_uuid}")
def tester_get_patient(test_uuid: str) -> dict[str, Any]:
    from src.db.mongo import get_test_patient_sync
    d = get_test_patient_sync(test_uuid)
    if not d:
        raise HTTPException(status_code=404, detail=f"Unknown test_uuid: {test_uuid}")
    return d


@app.put("/api/tests/patients/{test_uuid}")
def tester_update_patient(test_uuid: str, payload: TestPatientPayload) -> dict[str, Any]:
    from src.db.mongo import (
        update_test_patient_sync, get_test_patient_sync,
    )
    existing = get_test_patient_sync(test_uuid)
    if not existing:
        raise HTTPException(status_code=404, detail=f"Unknown test_uuid: {test_uuid}")
    patch = payload.model_dump(exclude_unset=False)
    for k in ("conditions", "medications", "visits", "comorbidity",
              "risk_scores", "labs", "ground_truth", "case_stats"):
        if patch.get(k) is None:
            patch[k] = {}
    update_test_patient_sync(test_uuid, patch)
    return get_test_patient_sync(test_uuid)


@app.delete("/api/tests/patients/{test_uuid}")
def tester_delete_patient(test_uuid: str,
                          with_runs: bool = Query(False)) -> dict[str, Any]:
    from src.db.mongo import delete_test_patient_sync, _coll
    delete_test_patient_sync(test_uuid)
    if with_runs:
        _coll("agent_runs").delete_many({
            "patient_uuid": test_uuid,
            "result_set":   "mas_results_test",
        })
    return {"deleted": True}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/integration/test_tests_api.py -v -k 'post_test_patient or post_validates or get_test_patient or put_test_patient or list_test_patients or delete_test_patient'`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add doctor_console/backend/app.py tests/integration/test_tests_api.py
git commit -m "backend: CRUD /api/tests/patients endpoints

POST creates with ttest-<hex> uuid, PUT mutates label + content
(preserves created_at/source_uuid/run_count), GET returns full doc,
LIST returns summaries newest-first, DELETE removes the doc and
optionally purges past mas_results_test runs (with_runs=true)."
```

---

### Task 8: `POST /api/tests/runs` endpoint (with pipeline glue)

**Files:**
- Modify: `doctor_console/backend/app.py`
- Modify: `src/orchestrator/graph.py`
- Modify: `tests/integration/test_tests_api.py`

- [ ] **Step 1: Extend `load_patient_case` first**

Open `src/orchestrator/graph.py`. Find the existing `def load_patient_case(patient_uuid: str)` function. Add the `test_patients` branch at the top of its body, before the existing on-disk lookup:

```python
def load_patient_case(patient_uuid: str) -> dict:
    """..."""
    # Tester-journey branch: when USE_MONGO and the uuid matches a
    # test_patients doc, build the PipelineState from Mongo. Same
    # PipelineState shape the agents expect — they see no difference.
    from src.config import cfg
    if cfg.USE_MONGO:
        from src.db.mongo import get_test_patient_sync
        test_doc = get_test_patient_sync(patient_uuid)
        if test_doc is not None:
            return _build_pipeline_state_from_test_doc(test_doc)
    # ... existing on-disk lookup ...
```

Add the helper at the bottom of `src/orchestrator/graph.py` (or near the existing private helpers — use grep to find where the existing on-disk loader's helpers live):

```python
def _build_pipeline_state_from_test_doc(test_doc: dict) -> dict:
    """Assemble a PipelineState-shaped dict from a TestPatient Mongo doc.
    Mirrors the on-disk loader's output exactly — the agents must not
    see a difference between a cohort patient and a test patient."""
    return {
        "patient_uuid":  test_doc["_id"],
        "ehr_case": {
            "patient_uuid":   test_doc["_id"],
            "person_id":      test_doc.get("person_id", 0),
            "cutoff_date":    (test_doc.get("cutoff_date").isoformat()
                               if hasattr(test_doc.get("cutoff_date"), "isoformat")
                               else test_doc.get("cutoff_date")),
            "case_type":      test_doc.get("case_type", "ehr+lab"),
            "demographics":   test_doc.get("demographics", {}),
            "conditions":     test_doc.get("conditions", {}),
            "medications":    test_doc.get("medications", {}),
            "visits":         test_doc.get("visits", {}),
            "comorbidity":    test_doc.get("comorbidity", {}),
            "risk_scores":    test_doc.get("risk_scores", {}),
        },
        "lab_case":       test_doc.get("labs", {}),
        "ground_truth":   test_doc.get("ground_truth", {}),
    }
```

- [ ] **Step 2: Append the failing run test**

Append to `tests/integration/test_tests_api.py`:

```python
def test_post_test_run_starts_task(client):
    """POST /api/tests/runs starts a worker task and returns its id."""
    created = client.post("/api/tests/patients", json={
        "label":"runme", "demographics":{"age":60,"gender":"F"},
        "labs":{"latest_labs":[]},
    }).json()

    r = client.post("/api/tests/runs", json={"test_uuid": created["test_uuid"]})
    # The pipeline run itself takes minutes; we only verify the dispatcher
    # accepts the request, registers a task, and returns the right shape.
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("queued", "running")
    assert body["resultSet"] == "mas_results_test"
    assert body["taskId"]


def test_post_test_run_404_when_uuid_unknown(client):
    r = client.post("/api/tests/runs", json={"test_uuid": "ttest-nope"})
    assert r.status_code == 404
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/integration/test_tests_api.py -v -k post_test_run`
Expected: 2 FAIL with 404 on the endpoint.

- [ ] **Step 4: Implement the endpoint**

Add to `doctor_console/backend/app.py` near the other run endpoints (find `@app.post("/api/runs")` with grep):

```python
@app.post("/api/tests/runs")
def tester_start_run(request: TestRunRequest) -> dict[str, Any]:
    """Start a pipeline run against a TestPatient. Reuses the existing
    _tasks store + SSE stream + _run_patient_task worker, but writes
    output to result_set=mas_results_test so it doesn't pollute
    research statistics."""
    from src.db.mongo import get_test_patient_sync
    if get_test_patient_sync(request.test_uuid) is None:
        raise HTTPException(status_code=404,
                            detail=f"Unknown test_uuid: {request.test_uuid}")

    # Resolve model preset (reuses the same logic as the Doctor /api/runs path)
    resolved_provider, resolved_model = request.provider, request.model
    if request.preset_id:
        preset = next((p for p in discover_model_presets()
                       if p.get("id") == request.preset_id), None)
        if not preset or not preset.get("available", False):
            raise HTTPException(status_code=400,
                                detail=f"Engine '{request.preset_id}' is unavailable")
        resolved_provider, resolved_model = preset["provider"], preset["model"]

    accuracy_mode  = request.accuracy_mode
    memory_enabled = accuracy_mode == "recommended"
    canonicalizer_enabled = accuracy_mode == "recommended"

    task_id = str(uuid.uuid4())
    _tasks[task_id] = {
        "taskId":         task_id,
        "patientUuid":    request.test_uuid,
        "topK":           max(1, min(int(request.top_k or 5), 10)),
        "accuracyMode":   accuracy_mode,
        "status":         "queued",
        "startedAt":      None,
        "finishedAt":     None,
        "error":          None,
        "resultSet":      "mas_results_test",
        "activeAgentId":  None,
        "agents":         _initial_run_agents(),
        "agentNarratives": {},
        "modelOverride":  None,
        "events":         [{
            "timestamp": time.time(),
            "agentId":   None,
            "title":     "Test run queued",
            "message":   f"Tester pipeline launching with {resolved_model or 'default model'}.",
        }],
    }
    thread = threading.Thread(
        target=_run_patient_task,
        args=(task_id, request.test_uuid, resolved_provider, resolved_model,
              max(1, min(int(request.top_k or 5), 10)),
              memory_enabled, canonicalizer_enabled,
              "mas_results_test"),  # <-- the new result_set kwarg
        daemon=True,
    )
    thread.start()
    return _tasks[task_id]
```

- [ ] **Step 5: Teach `_run_patient_task` to accept the new `result_set` kwarg**

Open `doctor_console/backend/app.py` again. Find `def _run_patient_task(` (around line 2960 currently). Update the signature and the override block:

```python
def _run_patient_task(
    task_id: str,
    patient_uuid: str,
    provider_override: str | None = None,
    model_override: str | None = None,
    top_k: int = 5,
    memory_enabled: bool = True,
    canonicalizer_enabled: bool = True,
    result_set: str = "mas_results",        # <-- new
) -> None:
    # ...
```

In the same function, find the `_overrides: dict[str, str] = {}` setup. Add the `MAS_RESULTS_DIR` override:

```python
_overrides["MAS_RESULTS_DIR"] = (
    str(RUNTIME_RESULT_DIR.parent / result_set)
    if result_set != "mas_results"
    else str(RUNTIME_RESULT_DIR)
)
```

Find the `save_patient_results(patient_uuid, result, duration, base_dir=RUNTIME_RESULT_DIR)` call. Change it to use the per-run `base_dir`:

```python
base_dir = (DATA_GOLD / result_set) if result_set != "mas_results" else RUNTIME_RESULT_DIR
base_dir.mkdir(parents=True, exist_ok=True)
save_patient_results(patient_uuid, result, duration, base_dir=base_dir)
```

After the `save_patient_results` call (still inside the `try:` block), add the test-patient run-count stamp:

```python
if result_set == "mas_results_test":
    from src.db.mongo import stamp_test_run_sync
    stamp_test_run_sync(patient_uuid)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/integration/test_tests_api.py -v -k post_test_run`
Expected: 2 PASS.

- [ ] **Step 7: Commit**

```bash
git add doctor_console/backend/app.py src/orchestrator/graph.py tests/integration/test_tests_api.py
git commit -m "backend+graph: POST /api/tests/runs + pipeline glue

load_patient_case gains the test_patients branch; _run_patient_task
accepts a result_set kwarg that gates the MAS_RESULTS_DIR override
and the post-run stamp_test_run_sync call. The tester run reuses
_tasks + the SSE stream so the frontend's runtime view component
is unchanged."
```

---

### Task 9: Concurrency regression test — Doctor run + Tester run in parallel

**Files:**
- Modify: `tests/integration/test_tests_api.py`

- [ ] **Step 1: Append the regression test**

```python
def test_doctor_run_and_test_run_in_parallel(client, mongo_db, tmp_path, monkeypatch):
    """A /api/runs (cohort) and /api/tests/runs (test) launched within
    1s of each other must both register as running with independent
    task_ids and result_sets."""
    from datetime import datetime
    # Seed a cohort patient on disk + in Mongo so /api/runs accepts it
    cohort_uuid = "cohort-parallel-1"
    pcdir = tmp_path / "patient_cases" / cohort_uuid
    pcdir.mkdir(parents=True)
    import json
    (pcdir / "ehr_case.json").write_text(json.dumps({
        "patient_uuid": cohort_uuid, "person_id": 1,
        "cutoff_date":"2024-01-01","case_type":"ehr+lab",
        "demographics":{"age":60,"gender":"M"},
        "conditions":{"active":[]}, "medications":{"active":[]},
        "visits":{}, "comorbidity":{}, "risk_scores":{},
    }))
    (pcdir / "lab_case.json").write_text(json.dumps({"latest_labs":[]}))
    (pcdir / "ground_truth.json").write_text(json.dumps({}))
    monkeypatch.setenv("GOLD_DIR", str(tmp_path / "patient_cases"))

    # Create a test patient
    created = client.post("/api/tests/patients", json={
        "label":"par","demographics":{"age":70,"gender":"F"},
    }).json()
    test_uuid = created["test_uuid"]

    # Fire both runs back-to-back
    doctor_resp = client.post("/api/runs", json={"patient_uuid": cohort_uuid})
    tester_resp = client.post("/api/tests/runs", json={"test_uuid": test_uuid})

    assert doctor_resp.status_code == 200
    assert tester_resp.status_code == 200
    d, t = doctor_resp.json(), tester_resp.json()
    assert d["taskId"] != t["taskId"]
    assert d["resultSet"] != t["resultSet"]
    assert t["resultSet"] == "mas_results_test"
```

- [ ] **Step 2: Run the test**

Run: `pytest tests/integration/test_tests_api.py::test_doctor_run_and_test_run_in_parallel -v`
Expected: PASS — both POSTs accepted, two distinct task_ids, two distinct result_sets.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_tests_api.py
git commit -m "test: regression — doctor + tester runs concurrent via thread-local overrides"
```

---

## Phase 3 — Frontend foundations (types + API client)

### Task 10: TypeScript types

**Files:**
- Modify: `doctor_console/frontend/src/types.ts`

- [ ] **Step 1: Append the new types**

Open `doctor_console/frontend/src/types.ts`. At the end of the file, append:

```typescript
// ── Tester journey ──────────────────────────────────────────────

export interface VocabularyItem {
  label: string;
  code: string | null;
}

export interface CohortBrowseRow {
  uuid: string;
  age: number | null;
  gender: string | null;
  disease: string | null;
  active_count: number;
}

export interface TestPatientPayload {
  label: string;
  source_uuid?: string | null;
  demographics: { age: number; gender: string; race?: string; bmi?: number; location?: string };
  conditions?:  { active?: Array<{ condition: string; code?: string; start_date?: string }> };
  medications?: { active?: Array<{ medication: string; rx_code?: string; start_date?: string }> };
  visits?:      { total?: number; emergency?: number; inpatient?: number;
                  outpatient?: number; wellness?: number;
                  first_visit?: string; last_visit?: string };
  labs?:        { latest_labs?: Array<{ test_name: string; value?: string;
                                         unit?: string; reference_range?: string;
                                         flag?: string }> };
  ground_truth?: { target_condition?: { name?: string } };
  comorbidity?: Record<string, unknown>;
  risk_scores?: Record<string, unknown>;
  case_stats?:  Record<string, unknown>;
  cutoff_date?: string;
}

export interface TestPatientSummary {
  test_uuid: string;
  label: string;
  created_at: string;
  updated_at?: string;
  last_run_at?: string | null;
  run_count: number;
  source_uuid?: string | null;
}

export interface TestPatientDoc extends TestPatientPayload {
  _id: string;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  run_count: number;
  assembled_at: string;
  pipeline_version: string;
}
```

- [ ] **Step 2: Verify the file still parses**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: no errors related to types.ts.

- [ ] **Step 3: Commit**

```bash
git add doctor_console/frontend/src/types.ts
git commit -m "types: add Tester journey TypeScript interfaces"
```

---

### Task 11: API client functions

**Files:**
- Modify: `doctor_console/frontend/src/api.ts`

- [ ] **Step 1: Find the existing `apiFetch` pattern**

Open `doctor_console/frontend/src/api.ts`. Find one existing endpoint (e.g. `getPatients`) to see the shape of the helper used to make fetch calls (look for `apiFetch`, `fetch(`, or a similar wrapper). The new functions follow that exact pattern.

- [ ] **Step 2: Append the nine new functions**

At the bottom of `doctor_console/frontend/src/api.ts`:

```typescript
import type {
  VocabularyItem, CohortBrowseRow, TestPatientPayload,
  TestPatientSummary, TestPatientDoc, RunTask,
} from "./types";

export function getVocabulary(
  kind: "condition" | "medication" | "lab",
  q: string,
): Promise<VocabularyItem[]> {
  const params = new URLSearchParams({ kind, q });
  return apiFetch(`/api/tests/vocabulary?${params}`);
}

export function browseCohort(filters: {
  disease?: string;
  age_min?: number;
  age_max?: number;
  gender?: string;
  limit?: number;
}): Promise<CohortBrowseRow[]> {
  const params = new URLSearchParams();
  if (filters.disease) params.set("disease", filters.disease);
  if (filters.age_min != null) params.set("age_min", String(filters.age_min));
  if (filters.age_max != null) params.set("age_max", String(filters.age_max));
  if (filters.gender) params.set("gender", filters.gender);
  if (filters.limit != null) params.set("limit", String(filters.limit));
  return apiFetch(`/api/tests/cohort?${params}`);
}

export function getCohortTemplate(uuid: string): Promise<TestPatientPayload> {
  return apiFetch(`/api/tests/cohort/${encodeURIComponent(uuid)}`);
}

export function createTestPatient(payload: TestPatientPayload):
    Promise<{ test_uuid: string; label: string; created_at: string }> {
  return apiFetch("/api/tests/patients", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
}

export function listTestPatients(): Promise<TestPatientSummary[]> {
  return apiFetch("/api/tests/patients");
}

export function getTestPatient(testUuid: string): Promise<TestPatientDoc> {
  return apiFetch(`/api/tests/patients/${encodeURIComponent(testUuid)}`);
}

export function updateTestPatient(testUuid: string, payload: TestPatientPayload):
    Promise<TestPatientDoc> {
  return apiFetch(`/api/tests/patients/${encodeURIComponent(testUuid)}`, {
    method:  "PUT",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify(payload),
  });
}

export function deleteTestPatient(testUuid: string, withRuns = false):
    Promise<{ deleted: true }> {
  return apiFetch(
    `/api/tests/patients/${encodeURIComponent(testUuid)}?with_runs=${withRuns}`,
    { method: "DELETE" },
  );
}

export function startTestRun(testUuid: string, opts: {
  topK?: number; accuracyMode?: "recommended" | "fast"; presetId?: string;
} = {}): Promise<RunTask> {
  return apiFetch("/api/tests/runs", {
    method:  "POST",
    headers: { "Content-Type": "application/json" },
    body:    JSON.stringify({
      test_uuid:     testUuid,
      top_k:         opts.topK ?? 5,
      accuracy_mode: opts.accuracyMode ?? "recommended",
      preset_id:     opts.presetId,
    }),
  });
}
```

If `apiFetch` is named differently in `api.ts`, use the actual name. If it's an inline `fetch` pattern, follow that.

- [ ] **Step 3: Verify TypeScript compiles**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: no errors related to api.ts.

- [ ] **Step 4: Commit**

```bash
git add doctor_console/frontend/src/api.ts
git commit -m "api: nine client functions for the Tester REST surface"
```

---

## Phase 4 — Frontend components

### Task 12: `VocabularyCombobox` — reusable typeahead

**Files:**
- Create: `doctor_console/frontend/src/components/VocabularyCombobox.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useRef, useState } from "react";
import { getVocabulary } from "../api";
import type { VocabularyItem } from "../types";

interface Props {
  kind: "condition" | "medication" | "lab";
  placeholder?: string;
  onPick: (item: VocabularyItem) => void;
}

export function VocabularyCombobox({ kind, placeholder, onPick }: Props) {
  const [q, setQ] = useState("");
  const [items, setItems] = useState<VocabularyItem[]>([]);
  const [open, setOpen] = useState(false);
  const [highlight, setHighlight] = useState(0);
  const debounce = useRef<number>();

  useEffect(() => {
    if (!open) return;
    window.clearTimeout(debounce.current);
    debounce.current = window.setTimeout(() => {
      getVocabulary(kind, q).then(setItems).catch(() => setItems([]));
    }, 200);
    return () => window.clearTimeout(debounce.current);
  }, [q, open, kind]);

  const exactMatch = items.some(
    (it) => it.label.toLowerCase() === q.toLowerCase(),
  );

  function handleKey(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlight((h) => Math.min(h + 1, items.length /* + 1 for fallback */));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlight((h) => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (highlight < items.length) {
        onPick(items[highlight]);
      } else if (q && !exactMatch) {
        onPick({ label: q, code: null }); // "Use anyway" fallback
      }
      setQ("");
      setOpen(false);
      setHighlight(0);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  return (
    <div className="relative">
      <input
        className="w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm
                   text-slate-100 placeholder-slate-500 focus:border-emerald-500
                   focus:outline-none focus:ring-1 focus:ring-emerald-500"
        placeholder={placeholder || "Type to search…"}
        value={q}
        onFocus={() => setOpen(true)}
        onBlur={() => window.setTimeout(() => setOpen(false), 100)}
        onChange={(e) => { setQ(e.target.value); setOpen(true); setHighlight(0); }}
        onKeyDown={handleKey}
      />
      {open && (q || items.length > 0) && (
        <ul className="absolute z-10 mt-1 max-h-60 w-full overflow-y-auto rounded-md
                       border border-slate-700 bg-slate-900 shadow-lg">
          {items.map((it, i) => (
            <li
              key={`${it.label}-${it.code ?? "-"}`}
              className={`cursor-pointer px-3 py-1.5 text-sm
                          ${i === highlight ? "bg-emerald-600/20 text-emerald-200"
                                            : "text-slate-200 hover:bg-slate-800"}`}
              onMouseDown={(e) => { e.preventDefault(); onPick(it);
                                    setQ(""); setOpen(false); setHighlight(0); }}
            >
              <span>{it.label}</span>
              {it.code && (
                <span className="ml-2 text-xs text-slate-500">{it.code}</span>
              )}
            </li>
          ))}
          {q && !exactMatch && (
            <li
              className={`cursor-pointer border-t border-slate-700 px-3 py-1.5 text-sm
                          ${highlight === items.length ? "bg-amber-600/20 text-amber-200"
                                                       : "text-amber-300 hover:bg-slate-800"}`}
              onMouseDown={(e) => { e.preventDefault();
                                    onPick({ label: q, code: null });
                                    setQ(""); setOpen(false); setHighlight(0); }}
            >
              <span className="mr-2">⚠</span>Use anyway: <span className="italic">{q}</span>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: no errors related to VocabularyCombobox.tsx.

- [ ] **Step 3: Commit**

```bash
git add doctor_console/frontend/src/components/VocabularyCombobox.tsx
git commit -m "ui: VocabularyCombobox — debounced typeahead with use-anyway fallback"
```

---

### Task 13: Six section editors

**Files:**
- Create: `doctor_console/frontend/src/components/tester/DemographicsForm.tsx`
- Create: `doctor_console/frontend/src/components/tester/ConditionsForm.tsx`
- Create: `doctor_console/frontend/src/components/tester/MedicationsForm.tsx`
- Create: `doctor_console/frontend/src/components/tester/LabsForm.tsx`
- Create: `doctor_console/frontend/src/components/tester/VisitsForm.tsx`
- Create: `doctor_console/frontend/src/components/tester/GroundTruthForm.tsx`

- [ ] **Step 1: Create `DemographicsForm.tsx`**

```typescript
import type { TestPatientPayload } from "../../types";

interface Props {
  value: TestPatientPayload["demographics"];
  onChange: (next: TestPatientPayload["demographics"]) => void;
}

export function DemographicsForm({ value, onChange }: Props) {
  function set<K extends keyof typeof value>(k: K, v: (typeof value)[K]) {
    onChange({ ...value, [k]: v });
  }
  return (
    <div className="space-y-4">
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Age</span>
        <input type="number" min={0} max={120} value={value.age ?? ""}
          onChange={(e) => set("age", Number(e.target.value))}
          className="mt-1 block w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Gender</span>
        <div className="mt-1 flex gap-3">
          {(["M","F","Other"] as const).map(g => (
            <button key={g}
              onClick={() => set("gender", g)}
              className={`rounded-md px-3 py-1 text-sm
                         ${value.gender === g ? "bg-emerald-600 text-white"
                                              : "bg-slate-800 text-slate-300"}`}>
              {g}
            </button>
          ))}
        </div>
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">Race (optional)</span>
        <input type="text" value={value.race ?? ""}
          onChange={(e) => set("race", e.target.value)}
          className="mt-1 block w-64 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
      <label className="block">
        <span className="text-xs uppercase tracking-wide text-slate-400">BMI (optional)</span>
        <input type="number" step="0.1" value={value.bmi ?? ""}
          onChange={(e) => set("bmi", Number(e.target.value))}
          className="mt-1 block w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
      </label>
    </div>
  );
}
```

- [ ] **Step 2: Create `ConditionsForm.tsx`**

```typescript
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["conditions"];
  onChange: (next: TestPatientPayload["conditions"]) => void;
}

export function ConditionsForm({ value, onChange }: Props) {
  const active = value?.active ?? [];
  function add(item: VocabularyItem) {
    onChange({ active: [...active, { condition: item.label,
                                      code: item.code ?? undefined }] });
  }
  function remove(idx: number) {
    onChange({ active: active.filter((_, i) => i !== idx) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="condition" placeholder="Type a condition…" onPick={add} />
      <ul className="space-y-2">
        {active.map((c, i) => (
          <li key={i} className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm">
            <span className="flex-1">{c.condition}</span>
            {c.code && <span className="text-xs text-slate-500">{c.code}</span>}
            <button onClick={() => remove(i)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 3: Create `MedicationsForm.tsx`** — same pattern as Conditions but for medications:

```typescript
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["medications"];
  onChange: (next: TestPatientPayload["medications"]) => void;
}

export function MedicationsForm({ value, onChange }: Props) {
  const active = value?.active ?? [];
  function add(item: VocabularyItem) {
    onChange({ active: [...active, { medication: item.label,
                                      rx_code: item.code ?? undefined }] });
  }
  function remove(idx: number) {
    onChange({ active: active.filter((_, i) => i !== idx) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="medication" placeholder="Type a medication…" onPick={add} />
      <ul className="space-y-2">
        {active.map((m, i) => (
          <li key={i} className="flex items-center gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-1.5 text-sm">
            <span className="flex-1">{m.medication}</span>
            {m.rx_code && <span className="text-xs text-slate-500">{m.rx_code}</span>}
            <button onClick={() => remove(i)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Create `LabsForm.tsx`** (structured rows, autocomplete on test_name)

```typescript
import { VocabularyCombobox } from "../VocabularyCombobox";
import type { TestPatientPayload, VocabularyItem } from "../../types";

interface Props {
  value: TestPatientPayload["labs"];
  onChange: (next: TestPatientPayload["labs"]) => void;
}

export function LabsForm({ value, onChange }: Props) {
  const rows = value?.latest_labs ?? [];
  function setRow(i: number, patch: Partial<(typeof rows)[number]>) {
    onChange({ latest_labs: rows.map((r, j) => j === i ? { ...r, ...patch } : r) });
  }
  function add(item: VocabularyItem) {
    onChange({ latest_labs: [...rows, { test_name: item.label, value: "", unit: "" }] });
  }
  function remove(i: number) {
    onChange({ latest_labs: rows.filter((_, j) => j !== i) });
  }
  return (
    <div className="space-y-4">
      <VocabularyCombobox kind="lab" placeholder="Add a lab test…" onPick={add} />
      <ul className="space-y-2">
        {rows.map((r, i) => (
          <li key={i} className="flex gap-2 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm">
            <span className="flex-[2] text-slate-200">{r.test_name}</span>
            <input className="flex-1 rounded bg-slate-800 px-2 py-1 text-slate-100"
              placeholder="value" value={r.value ?? ""}
              onChange={(e) => setRow(i, { value: e.target.value })} />
            <input className="flex-1 rounded bg-slate-800 px-2 py-1 text-slate-100"
              placeholder="unit" value={r.unit ?? ""}
              onChange={(e) => setRow(i, { unit: e.target.value })} />
            <select className="rounded bg-slate-800 px-2 py-1 text-slate-100"
              value={r.flag ?? ""}
              onChange={(e) => setRow(i, { flag: e.target.value })}>
              <option value="">—</option>
              <option value="H">H (high)</option>
              <option value="L">L (low)</option>
              <option value="HH">HH</option>
              <option value="LL">LL</option>
            </select>
            <button onClick={() => remove(i)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 5: Create `VisitsForm.tsx`**

```typescript
import type { TestPatientPayload } from "../../types";

interface Props {
  value: TestPatientPayload["visits"];
  onChange: (next: TestPatientPayload["visits"]) => void;
}

export function VisitsForm({ value, onChange }: Props) {
  const v = (value as Record<string, number | undefined>) ?? {};
  function set(k: string, n: number) {
    onChange({ ...v, [k]: n });
  }
  const fields: Array<[string,string]> = [
    ["total","Total"], ["emergency","Emergency"], ["inpatient","Inpatient"],
    ["outpatient","Outpatient"], ["wellness","Wellness"],
  ];
  return (
    <div className="grid grid-cols-2 gap-4">
      {fields.map(([k, label]) => (
        <label key={k} className="block">
          <span className="text-xs uppercase tracking-wide text-slate-400">{label}</span>
          <input type="number" min={0} value={v[k] ?? ""}
            onChange={(e) => set(k, Number(e.target.value))}
            className="mt-1 block w-32 rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100" />
        </label>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Create `GroundTruthForm.tsx`**

```typescript
import { useState } from "react";
import type { TestPatientPayload } from "../../types";

const THESIS_DISEASES = [
  "Ischemic heart disease",
  "Chronic congestive heart failure",
  "Essential hypertension",
  "Diabetes mellitus type 2",
  "End-stage renal disease",
  "Chronic kidney disease stage 3",
  "Chronic kidney disease stage 2",
  "Metabolic syndrome X",
];

interface Props {
  value: TestPatientPayload["ground_truth"];
  onChange: (next: TestPatientPayload["ground_truth"]) => void;
}

export function GroundTruthForm({ value, onChange }: Props) {
  const name = value?.target_condition?.name ?? "";
  const isThesis = THESIS_DISEASES.includes(name);
  const [mode, setMode] = useState<"dropdown"|"other"|"blank">(
    !name ? "blank" : isThesis ? "dropdown" : "other"
  );

  function set(n: string) {
    if (!n) onChange({});
    else onChange({ target_condition: { name: n } });
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-2">
        {(["dropdown","other","blank"] as const).map(m => (
          <button key={m}
            onClick={() => { setMode(m); if (m==="blank") set(""); }}
            className={`rounded-md px-3 py-1 text-xs uppercase tracking-wide
                       ${mode === m ? "bg-emerald-600 text-white" : "bg-slate-800 text-slate-300"}`}>
            {m === "dropdown" ? "Thesis disease" : m === "other" ? "Other (free text)" : "Leave blank"}
          </button>
        ))}
      </div>
      {mode === "dropdown" && (
        <select className="block w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          value={isThesis ? name : ""}
          onChange={(e) => set(e.target.value)}>
          <option value="">— pick one —</option>
          {THESIS_DISEASES.map(d => <option key={d} value={d}>{d}</option>)}
        </select>
      )}
      {mode === "other" && (
        <input type="text"
          className="block w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
          placeholder="Disease name (free text)"
          value={!isThesis ? name : ""}
          onChange={(e) => set(e.target.value)} />
      )}
      {mode === "blank" && (
        <p className="text-sm text-slate-400">
          Evaluator (Stage 5) will be skipped — pipeline still produces a ranked
          differential but there's no DIRECT/INDIRECT/MISS verdict.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 7: Verify all compile**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: no errors in any of the new section editor files.

- [ ] **Step 8: Commit**

```bash
git add doctor_console/frontend/src/components/tester/
git commit -m "ui: six section editors for the Tester patient builder

DemographicsForm / ConditionsForm / MedicationsForm / LabsForm /
VisitsForm / GroundTruthForm. Conditions / medications / labs use
the shared VocabularyCombobox. Ground truth offers three modes:
thesis-disease dropdown, free text, or leave blank."
```

---

### Task 14: `PatientBuilderEditor` — two-pane shell

**Files:**
- Create: `doctor_console/frontend/src/components/PatientBuilderEditor.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useState } from "react";
import { DemographicsForm } from "./tester/DemographicsForm";
import { ConditionsForm }   from "./tester/ConditionsForm";
import { MedicationsForm }  from "./tester/MedicationsForm";
import { LabsForm }         from "./tester/LabsForm";
import { VisitsForm }       from "./tester/VisitsForm";
import { GroundTruthForm }  from "./tester/GroundTruthForm";
import type { TestPatientPayload } from "../types";

type Section = "demographics" | "conditions" | "medications"
              | "labs" | "visits" | "ground_truth";

const SECTIONS: Array<[Section, string, (p: TestPatientPayload) => string]> = [
  ["demographics", "Demographics",
    (p) => `${p.demographics?.age ?? "?"} · ${p.demographics?.gender ?? "?"}`],
  ["conditions", "Active conditions",
    (p) => `${(p.conditions?.active ?? []).length} active`],
  ["medications", "Active medications",
    (p) => `${(p.medications?.active ?? []).length} active`],
  ["labs", "Recent labs",
    (p) => `${(p.labs?.latest_labs ?? []).length} labs`],
  ["visits", "Visits summary",
    (p) => `${(p.visits as { total?: number })?.total ?? 0} total`],
  ["ground_truth", "Ground truth",
    (p) => p.ground_truth?.target_condition?.name ?? "(blank)"],
];

interface Props {
  payload:     TestPatientPayload;
  onChange:    (p: TestPatientPayload) => void;
  onSaveDraft: () => void;
  onSaveAndRun: () => void;
  saving?:     boolean;
}

export function PatientBuilderEditor({ payload, onChange, onSaveDraft, onSaveAndRun, saving }: Props) {
  const [section, setSection] = useState<Section>("demographics");

  function patch<K extends keyof TestPatientPayload>(k: K, v: TestPatientPayload[K]) {
    onChange({ ...payload, [k]: v });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex flex-1 gap-4 overflow-hidden p-4">
        {/* LEFT: navigator */}
        <aside className="w-64 shrink-0 space-y-1 border-r border-slate-800 pr-3">
          <input type="text"
            className="mb-3 w-full rounded-md border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100"
            placeholder="Label (required)"
            value={payload.label}
            onChange={(e) => onChange({ ...payload, label: e.target.value })} />
          {SECTIONS.map(([key, title, summary]) => (
            <button key={key} onClick={() => setSection(key)}
              className={`block w-full rounded-md px-3 py-2 text-left text-sm
                         ${section === key ? "bg-emerald-600/20 text-emerald-200"
                                           : "text-slate-300 hover:bg-slate-800"}`}>
              <div className="font-medium">{title}</div>
              <div className="mt-0.5 truncate text-xs text-slate-500">{summary(payload)}</div>
            </button>
          ))}
        </aside>
        {/* RIGHT: focused section */}
        <section className="flex-1 overflow-y-auto pr-2">
          {section === "demographics"  && <DemographicsForm value={payload.demographics}
              onChange={(v) => patch("demographics", v)} />}
          {section === "conditions"    && <ConditionsForm value={payload.conditions}
              onChange={(v) => patch("conditions", v)} />}
          {section === "medications"   && <MedicationsForm value={payload.medications}
              onChange={(v) => patch("medications", v)} />}
          {section === "labs"          && <LabsForm value={payload.labs}
              onChange={(v) => patch("labs", v)} />}
          {section === "visits"        && <VisitsForm value={payload.visits}
              onChange={(v) => patch("visits", v)} />}
          {section === "ground_truth"  && <GroundTruthForm value={payload.ground_truth}
              onChange={(v) => patch("ground_truth", v)} />}
        </section>
      </div>
      {/* BOTTOM action bar */}
      <div className="flex items-center justify-end gap-3 border-t border-slate-800 bg-slate-950 px-4 py-3">
        <button onClick={onSaveDraft} disabled={saving || !payload.label}
          className="rounded-md border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800 disabled:opacity-40">
          Save draft
        </button>
        <button onClick={onSaveAndRun} disabled={saving || !payload.label}
          className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500 disabled:opacity-40">
          {saving ? "Saving…" : "Save & run pipeline →"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add doctor_console/frontend/src/components/PatientBuilderEditor.tsx
git commit -m "ui: PatientBuilderEditor two-pane shell

Left navigator (sticky, with per-section 1-line summary), right pane
hosts the focused section editor. Sticky bottom bar with Save draft +
Save & run pipeline buttons."
```

---

### Task 15: `PatientPicker` — cohort browser

**Files:**
- Create: `doctor_console/frontend/src/components/PatientPicker.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useState } from "react";
import { browseCohort, getCohortTemplate } from "../api";
import type { CohortBrowseRow, TestPatientPayload } from "../types";

const DISEASES = [
  "Ischemic heart disease",
  "Chronic congestive heart failure",
  "Essential hypertension",
  "Diabetes mellitus type 2",
  "End-stage renal disease",
  "Chronic kidney disease stage 3",
  "Chronic kidney disease stage 2",
  "Metabolic syndrome X",
];

interface Props {
  onTemplate: (payload: TestPatientPayload) => void;
}

export function PatientPicker({ onTemplate }: Props) {
  const [disease, setDisease] = useState<string>("");
  const [ageRange, setAgeRange] = useState<[number, number]>([0, 120]);
  const [gender, setGender] = useState<string>("");
  const [rows, setRows] = useState<CohortBrowseRow[]>([]);
  const [selected, setSelected] = useState<CohortBrowseRow | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    browseCohort({
      disease: disease || undefined,
      age_min: ageRange[0], age_max: ageRange[1],
      gender:  gender || undefined,
      limit:   50,
    }).then((r) => { setRows(r); setSelected(null); })
      .finally(() => setLoading(false));
  }, [disease, ageRange[0], ageRange[1], gender]);

  async function useTemplate() {
    if (!selected) return;
    const payload = await getCohortTemplate(selected.uuid);
    onTemplate(payload);
  }

  return (
    <div className="flex h-full gap-4 p-4">
      {/* LEFT: facets */}
      <aside className="w-60 shrink-0 space-y-5 border-r border-slate-800 pr-3 text-sm">
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Disease</div>
          {DISEASES.map(d => (
            <label key={d} className="mb-1 flex items-center gap-2">
              <input type="radio" name="disease" checked={disease === d}
                onChange={() => setDisease(d === disease ? "" : d)} />
              <span className="text-slate-300">{d}</span>
            </label>
          ))}
          {disease && (
            <button onClick={() => setDisease("")}
              className="mt-1 text-xs text-slate-500 underline">clear</button>
          )}
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Age</div>
          <div className="flex items-center gap-2 text-slate-300">
            <input type="number" min={0} max={120} value={ageRange[0]}
              onChange={(e) => setAgeRange([Number(e.target.value), ageRange[1]])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center" />
            <span className="text-slate-500">–</span>
            <input type="number" min={0} max={120} value={ageRange[1]}
              onChange={(e) => setAgeRange([ageRange[0], Number(e.target.value)])}
              className="w-16 rounded bg-slate-800 px-2 py-1 text-center" />
          </div>
        </div>
        <div>
          <div className="mb-2 text-xs uppercase tracking-wide text-slate-400">Gender</div>
          <div className="flex gap-2">
            {["", "M", "F", "Other"].map((g) => (
              <button key={g || "any"}
                onClick={() => setGender(g === gender ? "" : g)}
                className={`rounded-md px-3 py-1 text-xs
                           ${gender === g ? "bg-emerald-600 text-white"
                                          : "bg-slate-800 text-slate-300"}`}>
                {g || "Any"}
              </button>
            ))}
          </div>
        </div>
      </aside>
      {/* MIDDLE: list */}
      <section className="w-80 shrink-0 overflow-y-auto border-r border-slate-800 pr-2">
        <div className="mb-2 text-xs text-slate-400">
          {loading ? "Loading…" : `${rows.length} patient${rows.length === 1 ? "" : "s"}`}
        </div>
        <ul className="space-y-1">
          {rows.map(row => (
            <li key={row.uuid}>
              <button onClick={() => setSelected(row)}
                className={`block w-full rounded-md px-3 py-2 text-left text-sm
                           ${selected?.uuid === row.uuid
                              ? "bg-emerald-600/20 text-emerald-200"
                              : "text-slate-300 hover:bg-slate-800"}`}>
                <div className="font-mono text-xs text-slate-500">{row.uuid.slice(0,11)}</div>
                <div>{row.age ?? "?"}{row.gender ?? "?"} · {row.disease ?? "—"}</div>
                <div className="mt-0.5 text-xs text-slate-500">{row.active_count} active conditions</div>
              </button>
            </li>
          ))}
        </ul>
      </section>
      {/* RIGHT: preview */}
      <section className="flex-1 overflow-y-auto pr-2">
        {!selected && (
          <div className="grid h-full place-items-center text-sm text-slate-500">
            Select a patient on the left to preview, then "Use as template" to start editing.
          </div>
        )}
        {selected && (
          <div className="space-y-4">
            <div>
              <div className="text-xs uppercase tracking-wide text-slate-400">Selected patient</div>
              <div className="font-mono text-sm text-slate-400">{selected.uuid}</div>
              <div className="mt-1 text-slate-100">
                {selected.age}{selected.gender} · {selected.disease}
              </div>
              <div className="mt-0.5 text-sm text-slate-500">
                {selected.active_count} active conditions
              </div>
            </div>
            <button onClick={useTemplate}
              className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500">
              Use as template →
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
```

- [ ] **Step 2: Verify compile**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -20`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add doctor_console/frontend/src/components/PatientPicker.tsx
git commit -m "ui: PatientPicker — facets + list + preview for cohort clone path"
```

---

### Task 16: `MyTestPatientsList` — revisit table

**Files:**
- Create: `doctor_console/frontend/src/components/MyTestPatientsList.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useState } from "react";
import { deleteTestPatient, listTestPatients, startTestRun } from "../api";
import type { TestPatientSummary } from "../types";

interface Props {
  onEdit:  (testUuid: string) => void;
  onRun:   (taskId: string) => void;
  onNew:   () => void;
}

export function MyTestPatientsList({ onEdit, onRun, onNew }: Props) {
  const [rows, setRows] = useState<TestPatientSummary[]>([]);
  const [busy, setBusy] = useState<string | null>(null);

  function load() { listTestPatients().then(setRows); }
  useEffect(load, []);

  async function rerun(uuid: string) {
    setBusy(uuid);
    const task = await startTestRun(uuid);
    setBusy(null);
    onRun(task.taskId);
  }

  async function remove(uuid: string) {
    if (!window.confirm("Delete this test patient? Past run results stay in the audit trail."))
      return;
    await deleteTestPatient(uuid);
    load();
  }

  function relative(iso?: string | null): string {
    if (!iso) return "—";
    const d = (Date.now() - new Date(iso).getTime()) / 1000;
    if (d < 60)        return `${Math.round(d)}s ago`;
    if (d < 3600)      return `${Math.round(d/60)}min ago`;
    if (d < 86400)     return `${Math.round(d/3600)}h ago`;
    return `${Math.round(d/86400)}d ago`;
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-medium text-slate-100">My test patients</h2>
        <button onClick={onNew}
          className="rounded-md bg-emerald-600 px-3 py-2 text-sm font-medium text-white hover:bg-emerald-500">
          + New from scratch
        </button>
      </div>
      {rows.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-700 p-8 text-center text-sm text-slate-500">
          No test patients yet. Build one from scratch or clone a cohort patient to get started.
        </div>
      )}
      <ul className="divide-y divide-slate-800">
        {rows.map(r => (
          <li key={r.test_uuid} className="flex items-center gap-4 py-3 text-sm">
            <div className="flex-1">
              <div className="text-slate-100">{r.label}</div>
              <div className="text-xs text-slate-500">
                created {relative(r.created_at)} · {r.run_count} run{r.run_count === 1 ? "" : "s"}
                {r.last_run_at && ` · last run ${relative(r.last_run_at)}`}
                {r.source_uuid && ` · cloned from ${r.source_uuid.slice(0,11)}`}
              </div>
            </div>
            <button onClick={() => rerun(r.test_uuid)} disabled={busy === r.test_uuid}
              className="rounded-md bg-emerald-600 px-3 py-1 text-xs text-white hover:bg-emerald-500 disabled:opacity-40">
              {r.last_run_at ? "Re-run" : "Run"}
            </button>
            <button onClick={() => onEdit(r.test_uuid)}
              className="rounded-md border border-slate-700 px-3 py-1 text-xs text-slate-300 hover:bg-slate-800">
              Edit
            </button>
            <button onClick={() => remove(r.test_uuid)}
              className="text-slate-500 hover:text-rose-400">×</button>
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 2: Verify compile + commit**

Run: `cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -10`
Expected: clean.

```bash
git add doctor_console/frontend/src/components/MyTestPatientsList.tsx
git commit -m "ui: MyTestPatientsList — revisit table with re-run / edit / delete"
```

---

### Task 17: `TesterJourney` — top-level route

**Files:**
- Create: `doctor_console/frontend/src/components/TesterJourney.tsx`

- [ ] **Step 1: Create the component**

```typescript
import { useEffect, useState } from "react";
import { PatientPicker }         from "./PatientPicker";
import { PatientBuilderEditor }  from "./PatientBuilderEditor";
import { MyTestPatientsList }    from "./MyTestPatientsList";
import { createTestPatient, getTestPatient, listTestPatients,
         startTestRun, updateTestPatient } from "../api";
import type { TestPatientPayload } from "../types";

const EMPTY: TestPatientPayload = {
  label: "",
  demographics: { age: 60, gender: "M" },
  conditions:   { active: [] },
  medications:  { active: [] },
  visits:       {},
  labs:         { latest_labs: [] },
  ground_truth: {},
};

type View = "splash" | "picker" | "editor" | "my-tests";

interface Props {
  onBack:        () => void;
  onRunStarted:  (taskId: string) => void;
}

export function TesterJourney({ onBack, onRunStarted }: Props) {
  const [view, setView]         = useState<View>("splash");
  const [payload, setPayload]   = useState<TestPatientPayload>(EMPTY);
  const [editingUuid, setEditingUuid] = useState<string | null>(null);
  const [saving, setSaving]     = useState(false);
  const [testCount, setTestCount] = useState(0);

  useEffect(() => { listTestPatients().then(rs => setTestCount(rs.length)); }, [view]);

  async function saveOnly(): Promise<string | null> {
    setSaving(true);
    try {
      if (editingUuid) {
        await updateTestPatient(editingUuid, payload);
        return editingUuid;
      }
      const created = await createTestPatient(payload);
      setEditingUuid(created.test_uuid);
      return created.test_uuid;
    } finally { setSaving(false); }
  }

  async function saveAndRun() {
    const uuid = await saveOnly();
    if (!uuid) return;
    const task = await startTestRun(uuid);
    onRunStarted(task.taskId);
  }

  async function startEdit(uuid: string) {
    const doc = await getTestPatient(uuid);
    setPayload({
      label: doc.label,
      source_uuid: doc.source_uuid,
      demographics: doc.demographics as any,
      conditions:   doc.conditions   as any,
      medications:  doc.medications  as any,
      visits:       doc.visits       as any,
      labs:         doc.labs         as any,
      ground_truth: doc.ground_truth as any,
    });
    setEditingUuid(uuid);
    setView("editor");
  }

  return (
    <div className="flex h-screen flex-col bg-slate-950 text-slate-100">
      <header className="flex items-center justify-between border-b border-slate-800 px-4 py-3">
        <div className="flex items-center gap-3">
          <button onClick={onBack} className="text-slate-400 hover:text-slate-100">←</button>
          <h1 className="text-lg font-medium">Tester (build &amp; run)</h1>
        </div>
        <button onClick={() => setView("my-tests")}
          className="text-sm text-emerald-300 hover:text-emerald-200">
          My test patients ({testCount})
        </button>
      </header>

      {view === "splash" && (
        <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8">
          <h2 className="text-2xl text-slate-100">How would you like to start?</h2>
          <div className="flex gap-4">
            <button
              onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("picker"); }}
              className="rounded-lg border border-slate-700 bg-slate-900 px-6 py-8 text-left hover:border-emerald-600">
              <div className="text-lg font-medium">Start from cohort</div>
              <div className="mt-1 text-sm text-slate-400">
                Filter the 3.3k Synthea patients by disease, age, and gender, preview, and clone one as a template.
              </div>
            </button>
            <button
              onClick={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
              className="rounded-lg border border-slate-700 bg-slate-900 px-6 py-8 text-left hover:border-emerald-600">
              <div className="text-lg font-medium">Start from scratch</div>
              <div className="mt-1 text-sm text-slate-400">
                Open an empty patient and fill in only the details that matter.
              </div>
            </button>
          </div>
        </div>
      )}

      {view === "picker" && (
        <div className="flex-1 overflow-hidden">
          <PatientPicker onTemplate={(p) => { setPayload({ ...EMPTY, ...p }); setView("editor"); }} />
        </div>
      )}

      {view === "editor" && (
        <div className="flex-1 overflow-hidden">
          <PatientBuilderEditor
            payload={payload}
            onChange={setPayload}
            onSaveDraft={saveOnly}
            onSaveAndRun={saveAndRun}
            saving={saving}
          />
        </div>
      )}

      {view === "my-tests" && (
        <div className="flex-1 overflow-y-auto">
          <MyTestPatientsList
            onEdit={startEdit}
            onRun={onRunStarted}
            onNew={() => { setPayload(EMPTY); setEditingUuid(null); setView("editor"); }}
          />
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify compile + commit**

```bash
cd doctor_console/frontend && npx tsc --noEmit 2>&1 | head -10
cd ../..
git add doctor_console/frontend/src/components/TesterJourney.tsx
git commit -m "ui: TesterJourney top-level route — picker / editor / my-tests"
```

---

### Task 18: Add Tester tile to `ModeChooser` and route in `App.tsx`

**Files:**
- Modify: `doctor_console/frontend/src/components/ModeChooser.tsx`
- Modify: `doctor_console/frontend/src/App.tsx`

- [ ] **Step 1: Add the Tester tile to `ModeChooser.tsx`**

Open `doctor_console/frontend/src/components/ModeChooser.tsx`. Find the two existing tiles (Doctor and Researcher — look for `<button` calls). Add a third tile of the same shape:

```typescript
<button
  onClick={() => onChoose("tester")}
  className="group rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-left transition
             hover:-translate-y-1 hover:border-emerald-600 hover:bg-slate-900 hover:shadow-xl">
  <div className="mb-2 text-xs uppercase tracking-wider text-emerald-400">build &amp; run</div>
  <div className="mb-3 text-2xl font-medium text-slate-100">Tester</div>
  <p className="text-sm text-slate-400">
    Build your own patient and watch CMADS reason about them in seconds.
  </p>
</button>
```

If the existing `onChoose` signature is `(mode: "doctor" | "researcher") => void`, extend it to `(mode: "doctor" | "researcher" | "tester") => void`. The `Props` type at the top of the file needs the same update.

- [ ] **Step 2: Wire the new mode in `App.tsx`**

Open `doctor_console/frontend/src/App.tsx`. Find where `ModeChooser` is used and where the existing Doctor/Researcher state branches are. Add a `tester` branch that renders `<TesterJourney />`:

```typescript
import { TesterJourney } from "./components/TesterJourney";

// inside the App component, alongside the existing 'doctor' / 'researcher' branches:
{mode === "tester" && (
  <TesterJourney
    onBack={() => setMode(null)}
    onRunStarted={(taskId) => {
      setRuntimeTaskId(taskId);
      setMode("doctor");  // reuse the doctor runtime view to stream the test run
    }}
  />
)}
```

The exact state names (`mode`, `setMode`, `runtimeTaskId`, `setRuntimeTaskId`) match what's already in `App.tsx` — read the file to find the actual identifiers and use those. If the existing runtime-view state is structured differently, mirror that.

- [ ] **Step 3: Smoke-build the frontend**

Run: `cd doctor_console/frontend && npm run build 2>&1 | tail -10`
Expected: build succeeds.

- [ ] **Step 4: Commit**

```bash
git add doctor_console/frontend/src/components/ModeChooser.tsx doctor_console/frontend/src/App.tsx
git commit -m "ui: third Tester tile on splash + route to TesterJourney

ModeChooser gains the third button alongside Doctor and Researcher.
App.tsx routes 'tester' mode to <TesterJourney>; when a tester run
starts, the existing runtime view streams it (same SSE endpoint)."
```

---

## Phase 5 — E2E smoke + acceptance

### Task 19: E2E smoke test

**Files:**
- Create: `tests/integration/test_tester_e2e.py`

- [ ] **Step 1: Create the smoke test**

```python
"""End-to-end smoke for the Tester journey: build → save → run → verify."""
import pytest
import pytest_asyncio
import time

pytest_plugins = ["tests.integration.conftest_mongo"]


@pytest.mark.asyncio
async def test_build_save_run_verify(mongo_db, monkeypatch):
    """Save a minimal scratch patient → trigger run via the API surface
    → poll until completion → verify TestPatient.last_run_at and the
    mas_results_test AgentRun doc both exist."""
    from importlib import reload
    monkeypatch.setenv("USE_MONGO", "true")
    monkeypatch.setenv("MONGO_DB", mongo_db.name)
    import doctor_console.backend.app as app_mod
    reload(app_mod)
    from fastapi.testclient import TestClient
    client = TestClient(app_mod.app)

    # Build + save
    created = client.post("/api/tests/patients", json={
        "label": "e2e smoke",
        "demographics": {"age": 70, "gender": "F"},
        "conditions": {"active": [{"condition": "Hypertension", "code": "59621000"}]},
        "labs": {"latest_labs": [{"test_name": "HbA1c", "value": "8.2"}]},
    }).json()
    test_uuid = created["test_uuid"]

    # Run
    run_resp = client.post("/api/tests/runs", json={"test_uuid": test_uuid}).json()
    task_id = run_resp["taskId"]

    # Poll for completion (or 4-minute budget)
    deadline = time.time() + 240
    while time.time() < deadline:
        r = client.get(f"/api/runs/{task_id}").json()
        if r["status"] in ("completed", "error"):
            break
        time.sleep(5)

    assert r["status"] == "completed", f"run did not complete: {r}"

    # Verify TestPatient stamped
    tp = mongo_db["test_patients"].find_one({"_id": test_uuid})
    assert tp["run_count"] == 1
    assert tp["last_run_at"] is not None

    # Verify AgentRun doc landed in the test cohort, not the research one
    ar = mongo_db["agent_runs"].find_one({
        "patient_uuid": test_uuid,
        "result_set":   "mas_results_test",
    })
    assert ar is not None
    assert len(ar.get("agents", {})) >= 5  # at least 5 of the 7 agents populated
```

This test runs the real pipeline against a real LLM provider — it requires `GROQ_API_KEY` in the env and ~2 minutes per execution. Mark it as a slow/integration test so it's excluded from the default `pytest` run.

- [ ] **Step 2: Mark it as slow**

At the top of `tests/integration/test_tester_e2e.py`, add a pytest marker:

```python
pytestmark = pytest.mark.slow
```

Edit `pytest.ini` (or `pyproject.toml` `[tool.pytest.ini_options]`) to register the `slow` marker if it isn't already:

```ini
[tool:pytest]
markers =
    slow: marks tests that hit live LLM providers (deselect with '-m "not slow"')
```

- [ ] **Step 3: Run the smoke test (manual; expensive)**

Run: `pytest tests/integration/test_tester_e2e.py -v -m slow`
Expected: ~2-minute wall time, PASS. Requires `GROQ_API_KEY` configured.

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_tester_e2e.py pytest.ini
git commit -m "test: E2E smoke for Tester journey — build, save, run, verify"
```

---

### Task 20: Manual acceptance walk-through (no commit)

- [ ] **Step 1: Restart backend + frontend**

```bash
kill -TERM $(cat /tmp/cmads_backend.pid /tmp/cmads_vite.pid 2>/dev/null) 2>/dev/null
sleep 2
lsof -iTCP:8010 -iTCP:5173 -sTCP:LISTEN -n -P 2>/dev/null | awk 'NR>1{print $2}' | xargs -I{} kill -9 {} 2>/dev/null
nohup uvicorn doctor_console.backend.app:app --host 127.0.0.1 --port 8010 > /tmp/cmads_backend.log 2>&1 &
echo $! > /tmp/cmads_backend.pid
nohup npm --prefix doctor_console/frontend run dev > /tmp/cmads_vite.log 2>&1 &
echo $! > /tmp/cmads_vite.pid
sleep 5
curl -sf http://127.0.0.1:8010/api/stats/overview?result_set=multi_level >/dev/null && echo "backend OK"
curl -sf -o /dev/null -w "vite: HTTP %{http_code}\n" http://127.0.0.1:5173/
open http://127.0.0.1:5173/
```

- [ ] **Step 2: Verify each acceptance criterion from spec §13**

Run through each criterion manually in the browser:

1. **Tester tile appears on the splash** → click it → Tester journey opens.
2. **From scratch:** click "Start from scratch" → set age=70, gender=F, add one condition (autocomplete-picked), add one lab (autocomplete-picked), leave ground truth blank → click **Save & run pipeline** → runtime view opens, all agent stages light up, evaluator is skipped (ground truth blank), differential renders.
3. **From cohort:** back to Tester → "Start from cohort" → filter IHD + 60-80 + F → preview a patient → "Use as template" → editor opens pre-populated → set label → Save & run → independent `mas_results_test` doc lands in Mongo.
4. **Research statistics unchanged:** open Researcher → Overview → confirm DIRECT=78.1%, Found=95.0% on `multi_level`. Open Memory A/B → confirm contingency `70/16/53/21`. Both must be unchanged.
5. **Re-run:** Tester → My test patients → click **Re-run** on a row → second `agent_runs` doc appears in Mongo; `run_count` increments to 2.
6. **Concurrency:** open Doctor in tab A, paste a known UUID, click Run. Within 1 s, open Tester in tab B, click "Start from scratch", fill minimum fields, Save & run. Verify the backend log shows interleaved `agent_step` lines for two different patients; verify both runs complete with independent `agent_runs` docs.

Record pass/fail per criterion. Any failure → file a follow-up issue and patch in a new commit before declaring the feature complete.

- [ ] **Step 3: Tarball-free wrap**

The feature is shippable when criteria 1–6 pass. No tarball needed (the on-disk filesystem is unchanged — only Mongo gained a new `test_patients` collection, and that's namespace-isolated by design).

---

## Acceptance checklist

| # | Acceptance criterion (from spec §13) | Verified |
|---|---|---|
| 1 | Tester tile on splash opens new journey | ☐ |
| 2 | Scratch patient → Save & run → 7 agents → runtime view | ☐ |
| 3 | Cohort clone → Save & run → independent mas_results_test doc | ☐ |
| 4 | Researcher Overview/Memory A/B numbers unchanged | ☐ |
| 5 | Re-run from MyTestPatients increments run_count | ☐ |
| 6 | Doctor + Tester runs in parallel both complete | ☐ |
