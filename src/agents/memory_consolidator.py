"""Memory consolidation node — Stage 7.

Runs after Treatment Planning. Folds the run's outcome into TWO long-term
stores so the next run starts smarter:

  - Tier 3 (semantic) — per-disease aggregate stats in
    data/gold/memory/semantic_memory.json
  - Tier 4 (case-based) — the patient's clinical-feature embedding +
    outcome upserted into the Qdrant `patient_cases` collection

Reads:  agent_outputs.evaluation, agent_outputs.final_diagnosis,
        agent_outputs.ehr_analyst, agent_outputs.lab_interpreter,
        patient_context (ehr_case, lab_case)
Writes: session_memory (one completion event), Tier-3 JSON, Tier-4 Qdrant.

If MEMORY_ENABLED is false, this node is a no-op (returns an empty trace
entry only) so before/after experiments compare cleanly.
"""

from __future__ import annotations

import time

import structlog

from src.config import cfg
from src.memory import EpisodicMemory, SemanticMemory, get_case_based_memory

logger = structlog.get_logger()


def memory_consolidation_node(state: dict) -> dict:
    """LangGraph node — fold this run's outcome into Tier-3 semantic memory."""
    start = time.time()
    trace_entry = {
        "agent_id": "memory_consolidation",
        "status": "skipped",
        "execution_ms": 0,
        "llm_calls": 0,
        "error": None,
    }

    if not cfg.MEMORY_ENABLED:
        logger.info("memory_consolidation_disabled")
        trace_entry["execution_ms"] = int((time.time() - start) * 1000)
        return {"execution_trace": [trace_entry]}

    agent_outputs = state.get("agent_outputs") or {}
    evaluation = agent_outputs.get("evaluation") or {}
    final = agent_outputs.get("final_diagnosis") or {}

    match_type = evaluation.get("match_type") or "MISS"
    rank = evaluation.get("rank")
    matched = (
        evaluation.get("matched_diagnosis")
        or final.get("primary_diagnosis")
        or "Unknown"
    )

    primary_confidence: float | None = None
    diff = final.get("differential") or []
    if diff and isinstance(diff[0], dict):
        prob = diff[0].get("probability")
        if isinstance(prob, (int, float)):
            primary_confidence = float(prob) * 100.0

    evidence_patterns = _extract_evidence_patterns(final)

    # Tier 3 — disease-level aggregate stats on disk.
    semantic_ok = False
    try:
        store = SemanticMemory(cfg.SEMANTIC_MEMORY_PATH)
        insight = store.consolidate(
            disease=matched,
            match_type=match_type,
            rank_when_found=rank,
            primary_confidence=primary_confidence,
            evidence_patterns=evidence_patterns,
        )
        logger.info(
            "memory_consolidated_t3",
            disease=matched,
            match_type=match_type,
            runs_observed=insight.runs_observed,
            direct_rate=round(insight.direct_rate, 3),
        )
        semantic_ok = True
    except Exception as e:  # noqa: BLE001 — never fail the pipeline on memory write
        logger.error("memory_consolidation_t3_failed", error=str(e)[:200])

    # Tier 4 — patient-case vector upsert in Qdrant.
    case_ok = False
    try:
        ehr_case = (state.get("patient_context") or {}).get("ehr_case") or {}
        lab_case = (state.get("patient_context") or {}).get("lab_case") or {}
        ehr_summary = agent_outputs.get("ehr_analyst") or {}
        lab_summary = agent_outputs.get("lab_interpreter") or {}
        patient_uuid = (
            ehr_case.get("patient_uuid")
            or ehr_case.get("patient_id")
            or "unknown"
        )
        case_store = get_case_based_memory()
        case_ok = case_store.index_patient(
            patient_uuid=patient_uuid,
            ehr_case=ehr_case,
            lab_case=lab_case,
            matched_diagnosis=matched,
            match_type=match_type,
            rank_when_found=rank,
            primary_confidence=primary_confidence,
            evidence_patterns=evidence_patterns,
            ehr_summary=ehr_summary,
            lab_summary=lab_summary,
        )
        if case_ok:
            logger.info(
                "memory_consolidated_t4",
                patient=patient_uuid[:12],
                disease=matched, match_type=match_type,
            )
        else:
            logger.info(
                "memory_consolidation_t4_skipped",
                reason="qdrant unavailable or model not loaded",
            )
    except Exception as e:  # noqa: BLE001
        logger.error("memory_consolidation_t4_failed", error=str(e)[:200])

    if semantic_ok or case_ok:
        trace_entry["status"] = "success"
    else:
        trace_entry["status"] = "error"
        trace_entry["error"] = "both Tier-3 and Tier-4 consolidation failed"

    trace_entry["execution_ms"] = int((time.time() - start) * 1000)

    completion_event = EpisodicMemory.write(
        event_type="agent_complete",
        agent_id="memory_consolidation",
        summary=f"Consolidated outcome for '{matched}' ({match_type})",
        payload={
            "match_type": match_type,
            "matched_diagnosis": matched,
            "rank": rank,
        },
        tags=["memory", "consolidation"],
    )

    return {
        "execution_trace": [trace_entry],
        "session_memory": [completion_event],
    }


def _extract_evidence_patterns(final: dict) -> list[str]:
    """Pull short evidence-pattern strings from the final differential.

    These get aggregated into SemanticInsight.common_evidence_patterns so
    later runs can see "this evidence pattern was observed in N prior cases".
    Kept short to avoid a JSON file that grows without bound.
    """
    patterns: list[str] = []
    diff = final.get("differential") or []
    if not diff:
        return patterns
    top = diff[0] if isinstance(diff[0], dict) else {}
    for ev in top.get("supporting_evidence") or []:
        if isinstance(ev, dict):
            finding = (ev.get("finding") or "").strip()
            if finding:
                patterns.append(finding[:80])
        elif isinstance(ev, str):
            patterns.append(ev[:80])
    return patterns[:4]
