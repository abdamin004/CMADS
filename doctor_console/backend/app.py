"""FastAPI backend for the doctor-facing CMADS console.

The API is intentionally read-heavy: it serves existing Gold cases and saved
MAS run artifacts without changing the agent pipeline. A live run endpoint is
available, but it only executes when a user explicitly clicks Run in the UI.
"""

from __future__ import annotations

import json
import threading
import time
import uuid
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


ROOT = Path(__file__).resolve().parents[2]
DATA_GOLD = ROOT / "data" / "gold"
PATIENT_CASES = DATA_GOLD / "patient_cases"
ANNOTATIONS_DIR = DATA_GOLD / "annotations"
STATIC_DIR = ROOT / "doctor_console" / "frontend" / "dist"

# The "multi_level" virtual result set unions every multi-level-memory run
# (improved_b3 + improved_50 + improved_extra60 + improved_10) so the doctor
# sees every patient the system has run with the full 4-tier memory
# subsystem, regardless of which batch they came from. Order is precedence:
# first match wins.
MULTI_LEVEL_KEY = "multi_level"
MULTI_LEVEL_RESULT_DIRS: tuple[str, ...] = (
    "mas_results_improved_b3",
    "mas_results_improved_50",
    "mas_results_improved_extra60",
    "mas_results_improved_10",
)

AGENT_ORDER = [
    "ehr_analyst",
    "lab_interpreter",
    "diagnostic_reasoning",
    "clinical_reviewer",
    "final_diagnosis",
    "evaluation",
    "treatment_planning",
    "memory_consolidation",
]

AGENT_FILES = {
    "ehr_analyst": "ehr_analyst.json",
    "lab_interpreter": "lab_interpreter.json",
    "diagnostic_reasoning": "diagnostic_reasoning.json",
    "clinical_reviewer": "clinical_reviewer.json",
    "final_diagnosis": "final_diagnosis.json",
    "evaluation": "evaluation.json",
    "treatment_planning": "treatment_planning.json",
}

AGENT_LABELS = {
    "ehr_analyst": "EHR Analyst",
    "lab_interpreter": "Lab Interpreter",
    "diagnostic_reasoning": "Diagnostic Reasoning",
    "clinical_reviewer": "Clinical Reviewer",
    "final_diagnosis": "Diagnostic Refiner",
    "evaluation": "LLM Evaluator",
    "treatment_planning": "Treatment Planning",
    "memory_consolidation": "Memory Consolidation",
}

RESULT_SET_LABELS = {
    "mas_results": "Original MAS results",
    "mas_results_case_based_50": "Case-based memory run (50)",
    "mas_results_with_memory": "Memory ON run (20)",
    "mas_results_baseline_no_mem": "Memory OFF baseline (20)",
    "mas_results_improved_10": "Improved memory run (10)",
    "mas_results_improved_b3": "Multi-level memory · batch_3 (50)",
    "mas_results_improved_50": "Multi-level memory · batch_4 (50)",
    "mas_results_improved_extra60": "Multi-level memory · extra60 (60)",
    "mas_results_paired95_single_level": "Paired baseline · single-level (95)",
    "mas_results_single_llm_baseline": "Single-LLM baseline (160)",
    "mas_results_med42": "Med42 comparison",
    "mas_results_deepseek_v4_pro": "DeepSeek comparison",
}

_tasks: dict[str, dict[str, Any]] = {}
_tasks_lock = threading.Lock()


class RunRequest(BaseModel):
    patient_uuid: str


class AnnotationPayload(BaseModel):
    """Doctor-supplied review of an agent run.

    Persisted to data/gold/annotations/<uuid>.json. Always overwrites: one
    annotation per patient at a time (later versions can extend to a list).
    """

    agreement: str = "uncertain"  # "agree" | "disagree" | "uncertain"
    reviewed: bool = True
    notes: str = ""
    reviewer: str = ""  # free-form, e.g. "AM"


def create_app() -> FastAPI:
    app = FastAPI(title="CMADS Doctor Console API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {
            "ok": True,
            "root": str(ROOT),
            "patient_cases": PATIENT_CASES.exists(),
            "result_sets": len(_result_sets()),
        }

    @app.get("/api/result-sets")
    def result_sets() -> list[dict[str, Any]]:
        return _result_sets()

    @app.get("/api/dashboard")
    def dashboard(result_set: str = Query("mas_results")) -> dict[str, Any]:
        result_dir = _resolve_result_set(result_set)
        return _dashboard_summary(result_dir)

    @app.get("/api/patients")
    def patients(
        result_set: str = Query(MULTI_LEVEL_KEY),
        query: str = Query("", max_length=80),
        limit: int = Query(2000, ge=1, le=2000),
    ) -> list[dict[str, Any]]:
        result_dirs = _resolve_result_dirs(result_set)
        # Union of UUIDs that have a run in *any* of the listed dirs.
        run_uuids: set[str] = set()
        for d in result_dirs:
            run_uuids.update(p.name for p in d.iterdir() if p.is_dir())

        # For the virtual "multi_level" cohort the doctor only ever cares
        # about patients the system has actually processed with the 4-tier
        # memory subsystem — no point listing the rest of the Gold layer.
        # For a specific result set, fall back to the legacy behaviour
        # (every Gold patient, marked with hasRun=true/false) so the run
        # button stays usable for not-yet-processed patients.
        if result_set == MULTI_LEVEL_KEY:
            uuids = sorted(run_uuids)
        else:
            uuids = sorted(
                (p.name for p in PATIENT_CASES.iterdir() if p.is_dir()),
                key=lambda value: (value not in run_uuids, value),
            )
        if query:
            q = query.lower()
            uuids = [u for u in uuids if q in u.lower()]
        out = []
        for patient_uuid in uuids[:limit]:
            patient_dir = _patient_dir_for(patient_uuid, result_dirs)
            host_dir = patient_dir.parent if patient_dir is not None else result_dirs[0]
            out.append(_patient_list_item(patient_uuid, host_dir))
        return out

    @app.get("/api/patients/{patient_uuid}/case")
    def patient_case(patient_uuid: str) -> dict[str, Any]:
        return _load_case_bundle(patient_uuid)

    @app.get("/api/annotations/{patient_uuid}")
    def get_annotation(patient_uuid: str) -> dict[str, Any]:
        path = ANNOTATIONS_DIR / f"{patient_uuid}.json"
        if not path.exists():
            return {"patientUuid": patient_uuid, "exists": False}
        data = _load_json(path) or {}
        data["patientUuid"] = patient_uuid
        data["exists"] = True
        return data

    @app.put("/api/annotations/{patient_uuid}")
    def put_annotation(patient_uuid: str, payload: AnnotationPayload) -> dict[str, Any]:
        if not (PATIENT_CASES / patient_uuid).exists():
            raise HTTPException(status_code=404, detail="Unknown patient UUID")
        ANNOTATIONS_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            **payload.model_dump(),
            "patientUuid": patient_uuid,
            "updatedAt": _now_iso(),
        }
        path = ANNOTATIONS_DIR / f"{patient_uuid}.json"
        path.write_text(json.dumps(record, indent=2, ensure_ascii=False))
        record["exists"] = True
        return record

    @app.delete("/api/annotations/{patient_uuid}")
    def delete_annotation(patient_uuid: str) -> dict[str, Any]:
        path = ANNOTATIONS_DIR / f"{patient_uuid}.json"
        if path.exists():
            path.unlink()
        return {"patientUuid": patient_uuid, "exists": False}

    @app.get("/api/patients/{patient_uuid}/similar")
    def similar_cases(
        patient_uuid: str,
        top_k: int = Query(5, ge=1, le=20),
        match_filter: str = Query("", max_length=80),
        exclude_self: bool = Query(True),
        result_set: str = Query("mas_results"),
    ) -> dict[str, Any]:
        """Vector-search the case-based memory layer (Qdrant) and return
        the top-K most similar past patients to this one, with full
        metadata for the doctor to compare against the current case."""
        return _similar_cases(
            patient_uuid,
            top_k=top_k,
            match_filter=match_filter,
            exclude_self=exclude_self,
            result_set=result_set,
        )

    @app.get("/api/results/{result_set}/{patient_uuid}")
    def result_detail(result_set: str, patient_uuid: str) -> dict[str, Any]:
        result_dirs = _resolve_result_dirs(result_set)
        patient_dir = _patient_dir_for(patient_uuid, result_dirs)
        if patient_dir is None:
            raise HTTPException(
                status_code=404,
                detail=f"No saved run for {patient_uuid} in {result_set}",
            )
        result_dir = patient_dir.parent
        case = _load_case_bundle(patient_uuid)
        outputs = {
            agent_id: _load_json(patient_dir / filename)
            for agent_id, filename in AGENT_FILES.items()
        }
        trace = _load_json(patient_dir / "execution_trace.json") or {}
        session_memory = _load_json(patient_dir / "session_memory.json") or {}
        evaluation = outputs.get("evaluation") or {}
        final_dx = outputs.get("final_diagnosis") or {}

        return {
            "patient": case["patient"],
            "resultSet": _result_set_meta(result_dir),
            "case": case,
            "evaluation": evaluation,
            "finalDiagnosis": final_dx,
            "treatment": outputs.get("treatment_planning") or {},
            "agents": _agent_cards(outputs, trace),
            "agentOutputs": outputs,
            "agentNarratives": {
                agent_id: _agent_doctor_view(agent_id, outputs.get(agent_id))
                for agent_id in AGENT_ORDER
            },
            "trace": trace,
            "sessionMemory": session_memory.get("events") or [],
            "semanticMemory": _semantic_matches(result_set, final_dx, evaluation),
            "sharedMemory": _shared_memory_summary(outputs, session_memory, trace),
        }

    @app.post("/api/runs")
    def start_run(request: RunRequest) -> dict[str, Any]:
        if not (PATIENT_CASES / request.patient_uuid).exists():
            raise HTTPException(status_code=404, detail="Unknown patient UUID")
        task_id = str(uuid.uuid4())
        _tasks[task_id] = {
            "taskId": task_id,
            "patientUuid": request.patient_uuid,
            "status": "queued",
            "startedAt": None,
            "finishedAt": None,
            "error": None,
            "resultSet": "mas_results",
            "activeAgentId": None,
            "agents": _initial_run_agents(),
            "agentNarratives": {},
            "events": [{
                "timestamp": time.time(),
                "agentId": None,
                "title": "Run queued",
                "message": "Waiting to start the multi-agent diagnostic workflow.",
            }],
        }
        thread = threading.Thread(
            target=_run_patient_task,
            args=(task_id, request.patient_uuid),
            daemon=True,
        )
        thread.start()
        return _tasks[task_id]

    @app.get("/api/runs/{task_id}")
    def run_status(task_id: str) -> dict[str, Any]:
        task = _tasks.get(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Unknown task")
        return deepcopy(task)

    @app.get("/api/runs/{task_id}/stream")
    def run_stream(task_id: str) -> StreamingResponse:
        def events():
            last_payload = ""
            while True:
                task = _tasks.get(task_id)
                if not task:
                    yield "event: error\ndata: {\"detail\":\"Unknown task\"}\n\n"
                    return
                payload = json.dumps(deepcopy(task), default=str)
                if payload != last_payload:
                    yield f"data: {payload}\n\n"
                    last_payload = payload
                if task.get("status") in {"completed", "error"}:
                    return
                time.sleep(1)

        return StreamingResponse(events(), media_type="text/event-stream")

    if STATIC_DIR.exists():
        app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")

        @app.get("/{full_path:path}")
        def spa(full_path: str) -> FileResponse:
            target = STATIC_DIR / full_path
            if full_path and target.exists() and target.is_file():
                return FileResponse(target)
            return FileResponse(STATIC_DIR / "index.html")

    return app


app = create_app()


def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _result_sets() -> list[dict[str, Any]]:
    dirs = sorted(p for p in DATA_GOLD.glob("mas_results*") if p.is_dir())
    return [_result_set_meta(p) for p in dirs]


def _result_set_meta(path: Path) -> dict[str, Any]:
    patient_count = sum(1 for p in path.iterdir() if p.is_dir()) if path.exists() else 0
    return {
        "id": path.name,
        "label": RESULT_SET_LABELS.get(path.name, path.name.replace("_", " ")),
        "path": str(path.relative_to(ROOT)),
        "patientCount": patient_count,
    }


def _resolve_result_dirs(result_set: str) -> list[Path]:
    """Resolve a result_set name to one or more on-disk directories.

    Special value ``multi_level`` aggregates the multi-level-memory runs
    listed in ``MULTI_LEVEL_RESULT_DIRS``. Any other value resolves to a
    single concrete directory.
    """
    if result_set == MULTI_LEVEL_KEY:
        dirs = [DATA_GOLD / d for d in MULTI_LEVEL_RESULT_DIRS]
        existing = [d for d in dirs if d.exists() and d.is_dir()]
        if not existing:
            raise HTTPException(
                status_code=404,
                detail="No multi-level memory result directories exist yet.",
            )
        return existing
    safe = Path(result_set).name
    result_dir = DATA_GOLD / safe
    if not result_dir.exists() or not result_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"Unknown result set: {result_set}")
    return [result_dir]


def _resolve_result_set(result_set: str) -> Path:
    """Backwards-compatible single-dir resolver. For ``multi_level`` returns
    the first listed multi-level dir; callers that need the full set should
    use ``_resolve_result_dirs`` instead."""
    return _resolve_result_dirs(result_set)[0]


def _patient_dir_for(patient_uuid: str, dirs: list[Path]) -> Path | None:
    """Return the first dir in the list that contains a sub-folder for
    ``patient_uuid`` with at least an ``evaluation.json``. Falls back to any
    directory containing the UUID, then None."""
    for d in dirs:
        sub = d / patient_uuid
        if (sub / "evaluation.json").exists():
            return sub
    for d in dirs:
        sub = d / patient_uuid
        if sub.exists():
            return sub
    return None


def _dashboard_summary(result_dir: Path) -> dict[str, Any]:
    patient_dirs = sorted(p for p in result_dir.iterdir() if p.is_dir())
    match_counts: Counter[str] = Counter()
    diagnosis_counts: Counter[str] = Counter()
    durations: list[float] = []
    completed_agents: Counter[str] = Counter()

    for patient_dir in patient_dirs:
        evaluation = _load_json(patient_dir / "evaluation.json") or {}
        final_dx = _load_json(patient_dir / "final_diagnosis.json") or {}
        trace = _load_json(patient_dir / "execution_trace.json") or {}

        match_type = str(evaluation.get("match_type") or "UNEVALUATED").upper()
        match_counts[match_type] += 1

        primary = final_dx.get("primary_diagnosis") or evaluation.get("primary_diagnosis")
        if primary:
            diagnosis_counts[str(primary)] += 1

        duration = trace.get("duration_s")
        if isinstance(duration, (int, float)):
            durations.append(float(duration))

        for agent_id, filename in AGENT_FILES.items():
            if (patient_dir / filename).exists():
                completed_agents[agent_id] += 1
        if (patient_dir / "session_memory.json").exists():
            completed_agents["memory_consolidation"] += 1

    saved_runs = len(patient_dirs)
    direct = match_counts.get("DIRECT", 0)
    indirect = match_counts.get("INDIRECT", 0)
    miss = match_counts.get("MISS", 0)
    clinically_useful = direct + indirect
    semantic_path = _semantic_path_for_result_set(result_dir.name)
    semantic_store = _load_json(semantic_path) or {}
    semantic_entries = len(semantic_store) if isinstance(semantic_store, dict) else 0

    return {
        "resultSet": _result_set_meta(result_dir),
        "totalGoldPatients": sum(1 for p in PATIENT_CASES.iterdir() if p.is_dir()),
        "savedRuns": saved_runs,
        "directMatches": direct,
        "indirectMatches": indirect,
        "misses": miss,
        "unevaluated": max(saved_runs - direct - indirect - miss, 0),
        "directRate": _ratio(direct, saved_runs),
        "usefulRate": _ratio(clinically_useful, saved_runs),
        "averageDurationS": round(sum(durations) / len(durations), 1) if durations else None,
        "matchDistribution": [
            {"label": "DIRECT", "count": direct, "rate": _ratio(direct, saved_runs)},
            {"label": "INDIRECT", "count": indirect, "rate": _ratio(indirect, saved_runs)},
            {"label": "MISS", "count": miss, "rate": _ratio(miss, saved_runs)},
            {
                "label": "UNEVALUATED",
                "count": max(saved_runs - direct - indirect - miss, 0),
                "rate": _ratio(max(saved_runs - direct - indirect - miss, 0), saved_runs),
            },
        ],
        "agentCompletion": [
            {
                "agentId": agent_id,
                "label": AGENT_LABELS.get(agent_id, agent_id),
                "completed": completed_agents.get(agent_id, 0),
                "rate": _ratio(completed_agents.get(agent_id, 0), saved_runs),
            }
            for agent_id in AGENT_ORDER
        ],
        "topDiagnoses": [
            {"diagnosis": diagnosis, "count": count}
            for diagnosis, count in diagnosis_counts.most_common(8)
        ],
        "memoryStore": {
            "path": str(semantic_path.relative_to(ROOT)) if semantic_path.exists() else str(semantic_path),
            "exists": semantic_path.exists(),
            "semanticEntries": semantic_entries,
            "updatedAt": semantic_path.stat().st_mtime if semantic_path.exists() else None,
        },
    }


def _ratio(num: int, den: int) -> float:
    if den <= 0:
        return 0.0
    return round(num / den, 3)


def _patient_list_item(patient_uuid: str, result_dir: Path) -> dict[str, Any]:
    case = _load_case_bundle(patient_uuid)
    evaluation = _load_json(result_dir / patient_uuid / "evaluation.json") or {}
    final_dx = _load_json(result_dir / patient_uuid / "final_diagnosis.json") or {}
    trace = _load_json(result_dir / patient_uuid / "execution_trace.json") or {}
    annotation_path = ANNOTATIONS_DIR / f"{patient_uuid}.json"
    annotation = _load_json(annotation_path) if annotation_path.exists() else None
    return {
        "uuid": patient_uuid,
        "age": case["patient"].get("age"),
        "gender": case["patient"].get("gender"),
        "race": case["patient"].get("race"),
        "hasRun": (result_dir / patient_uuid).exists(),
        "matchType": evaluation.get("match_type"),
        "primaryDiagnosis": final_dx.get("primary_diagnosis") or evaluation.get("primary_diagnosis"),
        "durationS": trace.get("duration_s"),
        "reviewed": bool(annotation and annotation.get("reviewed")),
        "agreement": (annotation or {}).get("agreement"),
    }


def _now_iso() -> str:
    """Local-time ISO timestamp without microseconds — easier to read."""
    from datetime import datetime
    return datetime.now().isoformat(timespec="seconds")


def _load_case_bundle(patient_uuid: str) -> dict[str, Any]:
    patient_dir = PATIENT_CASES / patient_uuid
    if not patient_dir.exists():
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_uuid}")
    ehr = _load_json(patient_dir / "ehr_case.json") or {}
    lab = _load_json(patient_dir / "lab_case.json") or {}
    ground_truth = _load_json(patient_dir / "ground_truth.json") or {}
    demo = ehr.get("demographics") or {}
    target = (ground_truth.get("target_condition") or {}).get("name")
    return {
        "patient": {
            "uuid": patient_uuid,
            "age": demo.get("age"),
            "gender": demo.get("gender") or demo.get("sex"),
            "race": demo.get("race"),
            "ethnicity": demo.get("ethnicity"),
            "cutoffDate": ehr.get("cutoff_date") or lab.get("cutoff_date"),
            "targetCondition": target,
        },
        "ehrCase": ehr,
        "labCase": lab,
        "groundTruth": ground_truth,
        "caseStats": {
            "activeConditions": _count_active(ehr.get("conditions")),
            "activeMedications": _count_active(ehr.get("medications")),
            "labTrends": len(lab.get("lab_trends") or []),
            "criticalFlags": _count_critical_flags(lab.get("critical_flags")),
            "recentVitals": len(lab.get("recent_vitals") or []),
        },
    }


def _similar_cases(
    patient_uuid: str,
    top_k: int = 5,
    match_filter: str = "",
    exclude_self: bool = True,
    result_set: str = "mas_results",
) -> dict[str, Any]:
    """Query Qdrant `patient_cases` for the top-K most similar past
    patients to the given one. Falls back gracefully when Qdrant is
    unreachable or the patient is not yet indexed."""
    if not (PATIENT_CASES / patient_uuid).exists():
        raise HTTPException(status_code=404, detail=f"Unknown patient: {patient_uuid}")

    try:
        from src.memory.case_based_memory import (
            PATIENT_COLLECTION,
            _get_client,
            _get_model,
            _stable_id_from_uuid,
            _to_list,
            build_case_text,
        )
    except ImportError as exc:
        return {
            "patientUuid": patient_uuid,
            "collection": "patient_cases",
            "totalIndexed": 0,
            "isPatientIndexed": False,
            "queryText": "",
            "error": f"case-based memory module not importable: {exc}",
            "results": [],
        }

    client = _get_client()
    if client is None:
        return {
            "patientUuid": patient_uuid,
            "collection": "patient_cases",
            "totalIndexed": 0,
            "isPatientIndexed": False,
            "queryText": "",
            "error": "Qdrant client unavailable (QDRANT_URL unset or unreachable)",
            "results": [],
        }

    collections = {c.name for c in client.get_collections().collections}
    if PATIENT_COLLECTION not in collections:
        return {
            "patientUuid": patient_uuid,
            "collection": PATIENT_COLLECTION,
            "totalIndexed": 0,
            "isPatientIndexed": False,
            "queryText": "",
            "error": "patient_cases collection does not exist yet",
            "results": [],
        }

    info = client.get_collection(PATIENT_COLLECTION)
    pid = _stable_id_from_uuid(patient_uuid)
    stored = client.retrieve(
        collection_name=PATIENT_COLLECTION,
        ids=[pid],
        with_payload=True,
        with_vectors=False,
    )

    if stored:
        query_text = (stored[0].payload or {}).get("case_text", "")
        is_indexed = True
    else:
        case = _load_case_bundle(patient_uuid)
        ehr_summary = None
        lab_summary = None
        try:
            result_dirs = _resolve_result_dirs(result_set)
            patient_dir = _patient_dir_for(patient_uuid, result_dirs)
            if patient_dir is not None:
                ehr_summary = _load_json(patient_dir / "ehr_analyst.json")
                lab_summary = _load_json(patient_dir / "lab_interpreter.json")
        except HTTPException:
            pass
        query_text = build_case_text(
            case.get("ehrCase") or {},
            case.get("labCase") or {},
            ehr_summary,
            lab_summary,
        )
        is_indexed = False

    if not query_text:
        return {
            "patientUuid": patient_uuid,
            "collection": PATIENT_COLLECTION,
            "totalIndexed": info.points_count or 0,
            "isPatientIndexed": is_indexed,
            "queryText": "",
            "error": "Unable to build a query text from the patient's data.",
            "results": [],
        }

    model = _get_model()
    if model is None:
        return {
            "patientUuid": patient_uuid,
            "collection": PATIENT_COLLECTION,
            "totalIndexed": info.points_count or 0,
            "isPatientIndexed": is_indexed,
            "queryText": query_text,
            "error": "Embedding model unavailable",
            "results": [],
        }

    filters = [f.strip().upper() for f in match_filter.split(",") if f.strip()] if match_filter else []
    try:
        embedding = _to_list(model.encode(query_text))
        raw = client.query_points(
            collection_name=PATIENT_COLLECTION,
            query=embedding,
            limit=max(top_k * 3, top_k + 5),
        )
    except Exception as exc:  # noqa: BLE001
        return {
            "patientUuid": patient_uuid,
            "collection": PATIENT_COLLECTION,
            "totalIndexed": info.points_count or 0,
            "isPatientIndexed": is_indexed,
            "queryText": query_text,
            "error": f"Vector search failed: {exc}",
            "results": [],
        }

    results: list[dict[str, Any]] = []
    for r in raw.points:
        pl = r.payload or {}
        sim_uuid = pl.get("patient_uuid")
        sim_mt = (pl.get("match_type") or "").upper()
        if exclude_self and sim_uuid == patient_uuid:
            continue
        if filters and sim_mt not in filters:
            continue
        results.append({
            "patientUuid": sim_uuid,
            "similarity": float(r.score),
            "matchedDiagnosis": pl.get("matched_diagnosis"),
            "rawDiagnosis": pl.get("raw_diagnosis") or pl.get("matched_diagnosis"),
            "canonicalFamily": pl.get("canonical_family"),
            "matchType": pl.get("match_type"),
            "rankWhenFound": pl.get("rank_when_found"),
            "primaryConfidence": pl.get("primary_confidence"),
            "caseText": (pl.get("case_text") or "")[:360],
            "evidencePatterns": pl.get("evidence_patterns") or [],
            "indexedAt": pl.get("indexed_at"),
        })
        if len(results) >= top_k:
            break

    return {
        "patientUuid": patient_uuid,
        "collection": PATIENT_COLLECTION,
        "totalIndexed": info.points_count or 0,
        "isPatientIndexed": is_indexed,
        "queryText": query_text,
        "error": None,
        "results": results,
    }


def _count_active(value: Any) -> int:
    if isinstance(value, dict):
        active = value.get("active")
        if isinstance(active, list):
            return len(active)
    if isinstance(value, list):
        return len(value)
    return 0


def _count_critical_flags(value: Any) -> int:
    if isinstance(value, dict):
        flags = value.get("flags")
        if isinstance(flags, list):
            return len(flags)
    if isinstance(value, list):
        return len(value)
    return 0


def _agent_cards(outputs: dict[str, Any], trace: dict[str, Any]) -> list[dict[str, Any]]:
    trace_by_id = {
        item.get("agent_id"): item
        for item in (trace.get("agents") or [])
        if isinstance(item, dict)
    }
    cards = []
    for agent_id in AGENT_ORDER:
        output = outputs.get(agent_id)
        trace_item = trace_by_id.get(agent_id, {})
        cards.append({
            "id": agent_id,
            "label": AGENT_LABELS.get(agent_id, agent_id),
            "status": trace_item.get("status") or ("success" if output else "missing"),
            "executionMs": trace_item.get("execution_ms"),
            "error": trace_item.get("error"),
            "summary": _agent_summary(agent_id, output),
            "hasOutput": output is not None,
        })
    return cards


def _agent_summary(agent_id: str, output: Any) -> str:
    if not isinstance(output, dict):
        return "No saved output"
    if agent_id == "ehr_analyst":
        problems = len(output.get("active_problems") or [])
        meds = len(output.get("active_medications") or [])
        impression = output.get("clinical_impression") or output.get("risk_factor_summary") or ""
        return _short(f"{problems} problems, {meds} meds. {impression}")
    if agent_id == "lab_interpreter":
        findings = len(output.get("findings") or [])
        alerts = len(output.get("critical_alerts") or [])
        return _short(f"{findings} findings, {alerts} alerts. {output.get('overall_assessment', '')}")
    if agent_id in {"diagnostic_reasoning", "final_diagnosis"}:
        primary = output.get("primary_diagnosis") or "No primary diagnosis"
        diff_count = len(output.get("differential") or [])
        return _short(f"{primary}. {diff_count} diagnoses in differential.")
    if agent_id == "clinical_reviewer":
        recommended = output.get("recommended_primary") or "No recommendation"
        confidence = output.get("overall_confidence")
        return _short(f"{recommended}. Confidence {confidence}.")
    if agent_id == "evaluation":
        return _short(
            f"{output.get('match_type', '?')} at rank {output.get('rank', '?')}: "
            f"{output.get('matched_diagnosis', '')}"
        )
    if agent_id == "treatment_planning":
        meds = len(output.get("medications") or [])
        return _short(f"{meds} medications. {output.get('treatment_summary', '')}")
    return "Stage completed"


def _agent_doctor_view(agent_id: str, output: Any) -> dict[str, Any]:
    """Convert raw agent JSON into a doctor-readable display model."""
    label = AGENT_LABELS.get(agent_id, agent_id)
    if not isinstance(output, dict):
        return {
            "agentId": agent_id,
            "title": label,
            "summary": "This stage has not produced a readable output yet.",
            "metrics": [],
            "callouts": [],
            "sections": [],
        }

    if agent_id == "ehr_analyst":
        problems = _records(output.get("active_problems"))
        meds = _records(output.get("active_medications"))
        return {
            "agentId": agent_id,
            "title": label,
            "summary": _first_text(
                output.get("clinical_impression"),
                output.get("chief_complaint"),
                output.get("risk_factor_summary"),
                fallback="EHR summary completed.",
            ),
            "metrics": [
                {"label": "Active problems", "value": len(problems)},
                {"label": "Active medications", "value": len(meds)},
            ],
            "callouts": _compact_list([output.get("risk_factor_summary"), output.get("social_determinants")], 2),
            "sections": [
                _section("History of present illness", [output.get("history_of_present_illness")]),
                _section("Active problems", [
                    _join_nonempty(
                        problem.get("name"),
                        problem.get("clinical_significance"),
                        problem.get("status"),
                    )
                    for problem in problems[:8]
                ]),
                _section("Medications", [
                    _join_nonempty(med.get("name"), med.get("dose"), med.get("frequency"))
                    for med in meds[:8]
                ], empty="No active medications were identified."),
            ],
        }

    if agent_id == "lab_interpreter":
        findings = _records(output.get("findings"))
        alerts = _records(output.get("critical_alerts"))
        return {
            "agentId": agent_id,
            "title": label,
            "summary": _first_text(output.get("overall_assessment"), fallback="Lab interpretation completed."),
            "metrics": [
                {"label": "Findings", "value": len(findings)},
                {"label": "Critical alerts", "value": len(alerts)},
            ],
            "callouts": [
                _join_nonempty(alert.get("test_name") or alert.get("lab_name"), alert.get("value"), alert.get("clinical_action"))
                for alert in alerts[:3]
            ],
            "sections": [
                _section("Key findings", [
                    _join_nonempty(
                        finding.get("test_name") or finding.get("lab_name"),
                        finding.get("value"),
                        finding.get("classification"),
                        finding.get("interpretation"),
                    )
                    for finding in findings[:10]
                ]),
                _section("Clinical action", _compact_list([
                    output.get("urgent_actions"),
                    output.get("recommended_followup"),
                    output.get("lab_pattern_summary"),
                ], 4)),
            ],
        }

    if agent_id in {"diagnostic_reasoning", "final_diagnosis"}:
        differential = _records(output.get("differential"))
        primary = output.get("primary_diagnosis") or "No primary diagnosis saved"
        return {
            "agentId": agent_id,
            "title": label,
            "summary": str(primary),
            "metrics": [
                {"label": "Differential size", "value": len(differential)},
                {"label": "Primary probability", "value": _format_probability(output.get("primary_probability"))},
            ],
            "callouts": _compact_list(output.get("unresolved_findings"), 4),
            "sections": [
                _section("Clinical reasoning", [output.get("clinical_reasoning_summary") or output.get("reasoning")]),
                _section("Ranked differential", [
                    _format_differential_row(dx, index)
                    for index, dx in enumerate(differential[:8])
                ]),
                _section("Recommended workup", _compact_list(output.get("recommended_workup"), 8)),
            ],
        }

    if agent_id == "clinical_reviewer":
        checks = _records(output.get("consistency_checks"))
        verifications = _records(output.get("diagnosis_verifications"))
        return {
            "agentId": agent_id,
            "title": label,
            "summary": _first_text(
                output.get("review_summary"),
                output.get("recommended_primary"),
                fallback="Clinical review completed.",
            ),
            "metrics": [
                {"label": "Overall confidence", "value": output.get("overall_confidence") or "not recorded"},
                {"label": "Diagnoses reviewed", "value": len(verifications)},
            ],
            "callouts": _compact_list(output.get("top_concerns"), 5),
            "sections": [
                _section("Reviewer recommendation", [
                    _join_nonempty(output.get("recommended_primary"), output.get("recommended_primary_confidence"))
                ]),
                _section("Consistency checks", [
                    _join_nonempty(check.get("area"), check.get("status"), check.get("detail"))
                    for check in checks[:8]
                ]),
                _section("Verification notes", [
                    _join_nonempty(v.get("diagnosis"), v.get("verdict"), v.get("evidence_strength"))
                    for v in verifications[:8]
                ]),
            ],
        }

    if agent_id == "evaluation":
        return {
            "agentId": agent_id,
            "title": label,
            "summary": _join_nonempty(
                output.get("match_type") or "not evaluated",
                output.get("matched_diagnosis"),
            ),
            "metrics": [
                {"label": "Match type", "value": output.get("match_type") or "not evaluated"},
                {"label": "Matched rank", "value": output.get("rank") or "not found"},
            ],
            "callouts": _compact_list([output.get("reason")], 2),
            "sections": [
                _section("Benchmark comparison", [
                    _join_nonempty("Target", output.get("target")),
                    _join_nonempty("Model primary", output.get("primary_diagnosis")),
                    _join_nonempty("Matched diagnosis", output.get("matched_diagnosis")),
                    _join_nonempty("Reason", output.get("reason")),
                ]),
            ],
        }

    if agent_id == "treatment_planning":
        meds = _records(output.get("medications"))
        return {
            "agentId": agent_id,
            "title": label,
            "summary": _first_text(output.get("treatment_summary"), fallback="Treatment stage completed."),
            "metrics": [
                {"label": "Medications", "value": len(meds)},
                {"label": "Diagnosis treated", "value": output.get("primary_diagnosis_treated") or "not recorded"},
            ],
            "callouts": _compact_list([output.get("safety_notes"), output.get("contraindications")], 4),
            "sections": [
                _section("Treatment summary", [output.get("treatment_summary")]),
                _section("Medication plan", [
                    _join_nonempty(med.get("medication"), med.get("dose"), med.get("purpose") or med.get("nice_justification"))
                    for med in meds[:8]
                ], empty="No medication plan was generated."),
                _section("Monitoring and follow-up", _compact_list([
                    output.get("monitoring_plan"),
                    output.get("follow_up"),
                    output.get("patient_advice"),
                ], 6)),
            ],
        }

    return {
        "agentId": agent_id,
        "title": label,
        "summary": _agent_summary(agent_id, output),
        "metrics": [],
        "callouts": [],
        "sections": [_section("Stage output", [_agent_summary(agent_id, output)])],
    }


def _section(title: str, items: list[Any], empty: str | None = None) -> dict[str, Any]:
    clean = _compact_list(items, 12)
    return {"title": title, "items": clean, "empty": empty or "No readable items saved."}


def _records(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _compact_list(value: Any, limit: int = 6) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, dict):
        return [
            _join_nonempty(k, v)
            for k, v in list(value.items())[:limit]
            if v not in (None, "", [], {})
        ]
    if isinstance(value, list):
        out: list[str] = []
        for item in value:
            if item in (None, "", [], {}):
                continue
            if isinstance(item, dict):
                rendered = _join_nonempty(*[v for v in item.values() if v not in (None, "", [], {})])
            else:
                rendered = str(item)
            if rendered:
                out.append(rendered)
            if len(out) >= limit:
                break
        return out
    return [str(value)]


def _first_text(*values: Any, fallback: str) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def _join_nonempty(*values: Any) -> str:
    parts = []
    for value in values:
        if value in (None, "", [], {}):
            continue
        parts.append(str(value))
    return " | ".join(parts)


def _format_probability(value: Any) -> str:
    if isinstance(value, (int, float)):
        return f"{round(value * 100)}%"
    return "not recorded"


def _format_differential_row(dx: dict[str, Any], index: int) -> str:
    rank = dx.get("rank") or index + 1
    probability = _format_probability(dx.get("probability"))
    confidence = dx.get("confidence")
    reasoning = dx.get("reasoning")
    return _join_nonempty(f"#{rank}", dx.get("name"), probability, confidence, reasoning)


def _short(text: str, limit: int = 180) -> str:
    cleaned = " ".join(str(text).split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "..."


def _semantic_matches(result_set: str, final_dx: dict[str, Any], evaluation: dict[str, Any]) -> list[dict[str, Any]]:
    memory_path = _semantic_path_for_result_set(result_set)
    store = _load_json(memory_path) or {}
    if not isinstance(store, dict):
        return []
    needles = [
        final_dx.get("primary_diagnosis"),
        evaluation.get("matched_diagnosis"),
        evaluation.get("target"),
    ]
    out = []
    for disease, payload in store.items():
        if not isinstance(payload, dict):
            continue
        disease_norm = _norm(disease)
        if any(n and (_norm(n) == disease_norm or _norm(n) in disease_norm or disease_norm in _norm(n)) for n in needles):
            out.append({"disease": disease, **payload})
    return out[:8]


def _semantic_path_for_result_set(result_set: str) -> Path:
    if "case_based_50" in result_set:
        return DATA_GOLD / "memory_case_based_50" / "semantic_memory.json"
    if "with_memory" in result_set:
        return DATA_GOLD / "memory_with_memory" / "semantic_memory.json"
    return DATA_GOLD / "memory" / "semantic_memory.json"


def _norm(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("(disorder)", "").split())


def _shared_memory_summary(outputs: dict[str, Any], session_memory: dict[str, Any], trace: dict[str, Any]) -> dict[str, Any]:
    return {
        "patientContext": "Gold-layer EHR case + lab case loaded once by the orchestrator.",
        "agentOutputKeys": [k for k, v in outputs.items() if v],
        "sessionEvents": len(session_memory.get("events") or []),
        "traceEntries": len(trace.get("agents") or []),
        "notes": [
            "Stage 1 writes EHR and lab summaries in parallel.",
            "Diagnostic Reasoning consumes both summaries and writes the first differential.",
            "Clinical Reviewer and Diagnostic Refiner read upstream outputs and session memory.",
            "Memory Consolidation writes long-term semantic/case-based memory after the run.",
        ],
    }


def _initial_run_agents() -> list[dict[str, Any]]:
    return [
        {
            "id": agent_id,
            "label": AGENT_LABELS.get(agent_id, agent_id),
            "status": "pending",
            "executionMs": None,
            "error": None,
            "summary": "Waiting for upstream clinical context.",
            "hasOutput": False,
        }
        for agent_id in AGENT_ORDER
    ]


def _append_task_event(task: dict[str, Any], title: str, message: str, agent_id: str | None = None) -> None:
    task.setdefault("events", []).append({
        "timestamp": time.time(),
        "agentId": agent_id,
        "title": title,
        "message": message,
    })


def _set_agent_status(
    task: dict[str, Any],
    agent_id: str,
    status: str,
    summary: str | None = None,
    execution_ms: int | None = None,
    error: str | None = None,
) -> None:
    for agent in task.get("agents", []):
        if agent.get("id") == agent_id:
            agent["status"] = status
            if summary is not None:
                agent["summary"] = _short(summary)
            if execution_ms is not None:
                agent["executionMs"] = execution_ms
            if error is not None:
                agent["error"] = error
            if status in {"success", "completed", "skipped"}:
                agent["hasOutput"] = True
            break
    task["activeAgentId"] = agent_id if status == "running" else task.get("activeAgentId")


def _refresh_task_running_agents(task: dict[str, Any]) -> None:
    statuses = {agent["id"]: agent["status"] for agent in task.get("agents", [])}
    if statuses.get("ehr_analyst") == "pending":
        _set_agent_status(task, "ehr_analyst", "running", "Reading longitudinal EHR context.")
    if statuses.get("lab_interpreter") == "pending":
        _set_agent_status(task, "lab_interpreter", "running", "Interpreting labs, vitals, and critical flags.")

    sequence = [
        (("ehr_analyst", "lab_interpreter"), "diagnostic_reasoning", "Building the differential diagnosis."),
        (("diagnostic_reasoning",), "clinical_reviewer", "Checking evidence quality and diagnostic consistency."),
        (("clinical_reviewer",), "final_diagnosis", "Refining the final diagnosis and workup."),
        (("final_diagnosis",), "evaluation", "Comparing the output against the thesis benchmark."),
        (("evaluation",), "treatment_planning", "Preparing treatment guidance when the benchmark gate allows it."),
        (("treatment_planning",), "memory_consolidation", "Writing session and long-term memory updates."),
    ]
    completed = {"success", "completed", "skipped"}
    for prereqs, agent_id, summary in sequence:
        if all(statuses.get(prereq) in completed for prereq in prereqs) and statuses.get(agent_id) == "pending":
            _set_agent_status(task, agent_id, "running", summary)


def _merge_stream_update(state: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key in {"agent_outputs", "session_summary", "scratchpad"} and isinstance(value, dict):
            state.setdefault(key, {}).update(value)
        elif key in {"execution_trace", "session_memory", "conflicts"} and isinstance(value, list):
            state.setdefault(key, []).extend(value)
        else:
            state[key] = value


def _stream_patient_run(patient_uuid: str, task: dict[str, Any]) -> tuple[dict[str, Any], float]:
    from src.orchestrator.graph import compile_pipeline, load_patient_case

    pipeline = compile_pipeline()
    case = load_patient_case(patient_uuid)
    state: dict[str, Any] = {
        "patient_context": case,
        "agent_outputs": {},
        "conflicts": [],
        "execution_trace": [],
        "scratchpad": {},
        "session_memory": [],
        "session_summary": {},
    }
    start = time.time()
    with _tasks_lock:
        _set_agent_status(task, "ehr_analyst", "running", "Reading longitudinal EHR context.")
        _set_agent_status(task, "lab_interpreter", "running", "Interpreting labs, vitals, and critical flags.")
        _append_task_event(task, "Stage 1 started", "EHR Analyst and Lab Interpreter are running in parallel.")

    for chunk in pipeline.stream(
        state,
        config={"configurable": {"thread_id": f"doctor_console_{patient_uuid}_{uuid.uuid4()}"}},
        stream_mode="updates",
    ):
        if not isinstance(chunk, dict):
            continue
        for node_id, node_update in chunk.items():
            if node_id not in AGENT_ORDER or not isinstance(node_update, dict):
                continue
            _merge_stream_update(state, node_update)
            output = (node_update.get("agent_outputs") or {}).get(node_id)
            trace_items = node_update.get("execution_trace") or []
            trace_item = trace_items[-1] if trace_items and isinstance(trace_items[-1], dict) else {}
            status = trace_item.get("status") or ("success" if output else "completed")
            execution_ms = trace_item.get("execution_ms")
            error = trace_item.get("error")
            summary = _agent_summary(node_id, output)
            with _tasks_lock:
                if output:
                    task.setdefault("agentNarratives", {})[node_id] = _agent_doctor_view(node_id, output)
                _set_agent_status(
                    task,
                    node_id,
                    status,
                    summary=summary,
                    execution_ms=execution_ms,
                    error=error,
                )
                _append_task_event(
                    task,
                    f"{AGENT_LABELS.get(node_id, node_id)} {status}",
                    summary,
                    agent_id=node_id,
                )
                _refresh_task_running_agents(task)

    return state, time.time() - start


def _run_patient_task(task_id: str, patient_uuid: str) -> None:
    task = _tasks[task_id]
    with _tasks_lock:
        task["status"] = "running"
        task["startedAt"] = time.time()
        task["agents"] = _initial_run_agents()
        _append_task_event(task, "Run started", "The multi-agent workflow is now processing this patient.")
    try:
        from src.orchestrator.graph import save_patient_results

        result, duration = _stream_patient_run(patient_uuid, task)
        save_patient_results(patient_uuid, result, duration)
        outputs = result.get("agent_outputs") or {}
        trace = {"agents": result.get("execution_trace") or []}
        with _tasks_lock:
            task["status"] = "completed"
            task["agentNarratives"] = {
                agent_id: _agent_doctor_view(agent_id, outputs.get(agent_id))
                for agent_id in AGENT_ORDER
                if outputs.get(agent_id)
            }
            task["agents"] = _agent_cards(outputs, trace)
            task["activeAgentId"] = "final_diagnosis"
            _append_task_event(task, "Run completed", "The final diagnosis and downstream outputs are ready.")
    except Exception as exc:  # noqa: BLE001
        with _tasks_lock:
            task["status"] = "error"
            task["error"] = str(exc)
            _append_task_event(task, "Run failed", str(exc))
    finally:
        with _tasks_lock:
            task["finishedAt"] = time.time()
