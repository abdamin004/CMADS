"""Unit tests for the multi-level memory subsystem.

Covers all four tiers: working, episodic, semantic, procedural. The tests
deliberately avoid any LLM call — memory is supposed to be deterministic and
recall-correctness tests should not depend on a live model.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory import (
    EpisodicMemory,
    MemoryManager,
    ProceduralMemory,
    SemanticInsight,
    SemanticMemory,
    SessionEvent,
    WorkingMemory,
)


# ───────────────────────── Working Memory (Tier 1) ────────────────────────────


def test_working_memory_isolates_per_agent():
    state: dict = {}
    a = WorkingMemory(state, "agent_a")
    b = WorkingMemory(state, "agent_b")
    a.put("k", 1)
    b.put("k", 2)
    assert a.get("k") == 1
    assert b.get("k") == 2
    # Underlying scratchpad has both slots
    assert state["scratchpad"]["agent_a"]["k"] == 1
    assert state["scratchpad"]["agent_b"]["k"] == 2


def test_working_memory_append_to_creates_list():
    state: dict = {}
    wm = WorkingMemory(state, "diagnostic_reasoning")
    wm.append_to("hypotheses", "diabetes")
    wm.append_to("hypotheses", "hypertension")
    assert wm.get("hypotheses") == ["diabetes", "hypertension"]


def test_working_memory_append_to_rejects_non_list():
    state: dict = {}
    wm = WorkingMemory(state, "x")
    wm.put("k", "scalar")
    with pytest.raises(TypeError):
        wm.append_to("k", "more")


def test_working_memory_snapshot_is_a_copy():
    state: dict = {}
    wm = WorkingMemory(state, "x")
    wm.put("a", 1)
    snap = wm.snapshot()
    snap["a"] = 999
    assert wm.get("a") == 1


# ───────────────────────── Episodic Memory (Tier 2) ───────────────────────────


def test_episodic_make_event_validates_via_pydantic():
    ev = EpisodicMemory.make_event(
        event_type="critique",
        agent_id="diagnostic_reasoning",
        summary="round 1 critique",
        payload={"round": 1, "confidence": 60},
        tags=["diagnostic"],
    )
    parsed = SessionEvent.model_validate(ev)
    assert parsed.event_type == "critique"
    assert parsed.agent_id == "diagnostic_reasoning"
    assert parsed.payload["round"] == 1


def test_episodic_filtering_and_summary():
    events = [
        EpisodicMemory.make_event("agent_start", "ehr_analyst", "started"),
        EpisodicMemory.make_event(
            "critique", "diagnostic_reasoning", "round 1",
            payload={"round": 1, "confidence": 60},
        ),
        EpisodicMemory.make_event(
            "critique", "diagnostic_reasoning", "round 2",
            payload={"round": 2, "confidence": 78},
            tags=["diagnostic", "critique"],
        ),
        EpisodicMemory.make_event("decision", "clinical_reviewer", "approved"),
    ]
    em = EpisodicMemory(events)
    assert len(em.by_agent("diagnostic_reasoning")) == 2
    assert len(em.by_type("critique")) == 2
    assert len(em.by_tag("critique")) == 1
    assert "round 2" in em.summarize()


def test_episodic_summarize_truncates_to_max_events():
    events = [
        EpisodicMemory.make_event("decision", "x", f"event {i}")
        for i in range(50)
    ]
    em = EpisodicMemory(events)
    summary = em.summarize(max_events=5)
    assert "event 49" in summary  # latest is included
    assert "event 0" not in summary
    assert "5 of 50" in summary


def test_episodic_write_returns_a_pydantic_compatible_dict():
    """The returned dict is what an agent appends to session_memory state."""
    payload = EpisodicMemory.write(
        event_type="decision",
        agent_id="final_diagnosis",
        summary="primary set",
    )
    SessionEvent.model_validate(payload)


# ───────────────────────── Semantic Memory (Tier 3) ───────────────────────────


def test_semantic_consolidate_starts_fresh(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    insight = store.consolidate(
        disease="Hypertension",
        match_type="DIRECT",
        rank_when_found=1,
        primary_confidence=88.0,
        evidence_patterns=["BP > 140/90", "ACE inhibitor prescribed"],
    )
    assert insight.runs_observed == 1
    assert insight.direct_matches == 1
    assert insight.rank1_when_found == 1
    assert insight.direct_rate == pytest.approx(1.0)
    assert insight.found_rate == pytest.approx(1.0)
    assert "BP > 140/90" in insight.common_evidence_patterns


def test_semantic_consolidate_aggregates_running_mean(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    store.consolidate("HTN", "DIRECT", 1, primary_confidence=80.0)
    store.consolidate("HTN", "MISS", None, primary_confidence=40.0)
    insight = store.recall("HTN")
    assert insight is not None
    assert insight.runs_observed == 2
    assert insight.direct_matches == 1
    assert insight.misses == 1
    # Running mean: (80 + 40) / 2 = 60.0
    assert insight.avg_primary_confidence == pytest.approx(60.0)


def test_semantic_consolidate_persists_to_disk(tmp_path):
    path = tmp_path / "sm.json"
    SemanticMemory(path).consolidate("Diabetes", "INDIRECT")
    # Reload via a fresh instance
    reloaded = SemanticMemory(path).recall("Diabetes")
    assert reloaded is not None
    assert reloaded.indirect_matches == 1


def test_semantic_recall_is_case_insensitive(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    store.consolidate("Essential hypertension", "DIRECT", 1)
    assert store.recall("essential hypertension") is not None
    assert store.recall("ESSENTIAL HYPERTENSION") is not None


def test_semantic_recall_for_diseases_returns_only_matches(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    store.consolidate("CKD-3", "DIRECT", 1)
    found = store.recall_for_diseases(["CKD-3", "Unknown disease"])
    assert "CKD-3" in found
    assert "Unknown disease" not in found


def test_semantic_summary_handles_empty_store(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    assert "no prior cross-session insights" in store.summarize_for_diseases(
        ["Whatever"]
    )


def test_semantic_evidence_pattern_cap(tmp_path):
    store = SemanticMemory(tmp_path / "sm.json")
    for i in range(20):
        store.consolidate(
            "X",
            "DIRECT",
            1,
            evidence_patterns=[f"pattern_{i}"],
            max_evidence_patterns=5,
        )
    insight = store.recall("X")
    assert insight is not None
    assert len(insight.common_evidence_patterns) <= 5
    # Most recent patterns retained
    assert "pattern_19" in insight.common_evidence_patterns


def test_semantic_recovers_from_corrupt_file(tmp_path):
    path = tmp_path / "sm.json"
    path.write_text("{this is not valid json")
    store = SemanticMemory(path)
    # Loading shouldn't raise; recall just returns None.
    assert store.recall("anything") is None


# ───────────────────────── Procedural Memory (Tier 4) ─────────────────────────


def test_procedural_recall_returns_empty_on_failure(monkeypatch):
    """When Qdrant is unreachable, the wrapper returns [] not an exception."""
    pm = ProceduralMemory()

    def boom(query, top_k):
        raise RuntimeError("qdrant down")

    # Patch the search function inside the wrapper's import path
    import src.vectordb.query_guidelines as qg
    monkeypatch.setattr(qg, "search_guidelines", boom)
    assert pm.recall("Hypertension") == []


def test_procedural_lookup_returns_none_when_no_match(monkeypatch):
    pm = ProceduralMemory()
    import src.vectordb.query_guidelines as qg
    monkeypatch.setattr(qg, "search_guidelines", lambda q, top_k: [])
    assert pm.lookup_disease("X") is None


# ─────────────────────── Memory Manager (facade) ──────────────────────────────


def test_memory_manager_bundles_all_tiers(tmp_path):
    state = {"session_memory": []}
    mm = MemoryManager(
        state=state,
        agent_id="diagnostic_reasoning",
        semantic_path=tmp_path / "sm.json",
    )
    assert isinstance(mm.working, WorkingMemory)
    assert isinstance(mm.episodic, EpisodicMemory)
    assert isinstance(mm.semantic, SemanticMemory)
    assert isinstance(mm.procedural, ProceduralMemory)


def test_memory_manager_context_block_contains_episodic_and_semantic(tmp_path):
    state = {
        "session_memory": [
            EpisodicMemory.make_event(
                "decision", "ehr_analyst", "EHR triaged"
            ),
        ]
    }
    semantic_path = tmp_path / "sm.json"
    SemanticMemory(semantic_path).consolidate(
        "Hypertension", "DIRECT", 1, primary_confidence=85.0
    )
    mm = MemoryManager(
        state=state,
        agent_id="clinical_reviewer",
        semantic_path=semantic_path,
    )
    ctx = mm.context_block(diseases_for_semantic=["Hypertension"])
    assert "Episodic memory" in ctx
    assert "EHR triaged" in ctx
    assert "Semantic memory" in ctx
    assert "Hypertension" in ctx


# ───────────────────── State / agent integration smoke ────────────────────────


def test_pipeline_state_has_session_memory_channels():
    """The state TypedDict must declare the memory channels the reducers use."""
    from src.orchestrator.state import PipelineState
    annotations = PipelineState.__annotations__
    assert "session_memory" in annotations
    assert "session_summary" in annotations
    assert "scratchpad" in annotations  # Tier 1


def test_graph_includes_memory_consolidation_node():
    from src.orchestrator.graph import compile_pipeline
    pipeline = compile_pipeline()
    nodes = set(pipeline.get_graph().nodes.keys())
    assert "memory_consolidation" in nodes


def test_memory_consolidation_no_op_when_disabled(monkeypatch, tmp_path):
    """With MEMORY_ENABLED=false the consolidator must not write to disk."""
    monkeypatch.setenv("MEMORY_ENABLED", "false")
    monkeypatch.setenv("SEMANTIC_MEMORY_PATH", str(tmp_path / "sm.json"))
    # Reload config for the env vars to take effect
    from importlib import reload
    import src.config as config_module
    reload(config_module)
    from src.agents.memory_consolidator import memory_consolidation_node

    state = {
        "agent_outputs": {
            "evaluation": {"match_type": "DIRECT", "rank": 1,
                           "matched_diagnosis": "Hypertension"},
            "final_diagnosis": {"primary_diagnosis": "Hypertension"},
        }
    }
    out = memory_consolidation_node(state)
    assert out["execution_trace"][0]["status"] == "skipped"
    assert not (tmp_path / "sm.json").exists()


def test_memory_consolidation_writes_when_enabled(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_MEMORY_PATH", str(tmp_path / "sm.json"))
    from importlib import reload
    import src.config as config_module
    reload(config_module)
    from src.agents.memory_consolidator import memory_consolidation_node

    state = {
        "agent_outputs": {
            "evaluation": {
                "match_type": "DIRECT",
                "rank": 1,
                "matched_diagnosis": "Hypertension",
            },
            "final_diagnosis": {
                "primary_diagnosis": "Hypertension",
                "differential": [
                    {
                        "rank": 1,
                        "name": "Hypertension",
                        "probability": 0.85,
                        "supporting_evidence": [
                            {"finding": "BP 158/96 (lab)"},
                        ],
                    }
                ],
            },
        }
    }
    out = memory_consolidation_node(state)
    assert out["execution_trace"][0]["status"] == "success"
    sm_path = tmp_path / "sm.json"
    assert sm_path.exists()
    payload = json.loads(sm_path.read_text())
    assert "Hypertension" in payload
    assert payload["Hypertension"]["direct_matches"] == 1
