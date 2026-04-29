"""Memory consolidation node — Stage 7.

Runs after Treatment Planning. Distills the run's outcome into the cross-session
semantic memory store (Tier 3). This is the only place where one run's results
flow into the next run's context.

Reads:  agent_outputs.evaluation, agent_outputs.final_diagnosis,
        agent_outputs.diagnostic_reasoning
Writes: session_memory (a single completion event), and updates
        data/gold/memory/semantic_memory.json on disk.

If MEMORY_ENABLED is false, this node is a no-op (returns an empty trace
entry only) so before/after experiments compare cleanly.
"""

from __future__ import annotations

import time

import structlog

from src.config import cfg
from src.memory import EpisodicMemory, SemanticMemory

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
            "memory_consolidated",
            disease=matched,
            match_type=match_type,
            runs_observed=insight.runs_observed,
            direct_rate=round(insight.direct_rate, 3),
        )
        trace_entry["status"] = "success"
    except Exception as e:  # noqa: BLE001 — never fail the pipeline on memory write
        trace_entry["status"] = "error"
        trace_entry["error"] = str(e)[:200]
        logger.error("memory_consolidation_failed", error=str(e)[:200])

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
