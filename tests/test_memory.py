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
    CaseBasedMemory,
    EpisodicMemory,
    MemoryManager,
    ProceduralMemory,
    SemanticInsight,
    SemanticMemory,
    SessionEvent,
    WorkingMemory,
    build_case_text,
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


# ───── Procedural Memory (NICE guidelines — external knowledge base) ──────────


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


# ───────────── Case-Based Memory (Tier 4 — past patient cases) ────────────────


def test_case_text_handles_minimal_input():
    text = build_case_text(ehr_case={}, lab_case={})
    assert "no patient features" in text


def test_case_text_uses_agent_summaries_when_present():
    text = build_case_text(
        ehr_case={"demographics": {"age": 65, "sex": "male"}},
        lab_case={"latest_labs": [{"test_name": "HbA1c", "value": 8.2, "unit": "%"}]},
        ehr_summary={
            "active_problems": [{"name": "T2DM"}, {"name": "CKD-3"}],
            "active_medications": [{"name": "metformin"}],
            "risk_factor_summary": "Strong family history of CKD",
        },
        lab_summary={
            "findings": [
                {"test_name": "HbA1c", "value": "8.2%", "classification": "high"},
                {"test_name": "eGFR", "value": "45", "classification": "low"},
            ]
        },
    )
    assert "Demographics: age 65, male" in text
    assert "T2DM" in text and "CKD-3" in text
    assert "metformin" in text
    assert "HbA1c" in text and "high" in text
    assert "Strong family history" in text


def test_case_text_falls_back_to_raw_gold_when_summaries_missing():
    text = build_case_text(
        ehr_case={
            "demographics": {"age": 70, "sex": "female"},
            "conditions": [{"description": "Essential hypertension"}],
            "medications": [{"description": "Lisinopril 20mg"}],
        },
        lab_case={
            "latest_labs": [{"test_name": "BP_systolic", "value": 162, "unit": "mmHg"}]
        },
    )
    assert "70" in text
    assert "female" in text.lower()
    assert "Essential hypertension" in text
    assert "Lisinopril" in text
    assert "BP_systolic" in text


def test_case_text_handles_dict_shape_gold_layer():
    """Regression: Gold-layer conditions/medications are dicts, not lists.

    Originally the function did `ehr_case["conditions"][:12]` which threw
    `KeyError: slice(None, 12, None)` because the field is shaped
    ``{"active": [...], "resolved": [...]}`` in this project. The code
    now normalises that shape before slicing.
    """
    text = build_case_text(
        ehr_case={
            "demographics": {"age": 65, "gender": "M"},
            "conditions": {
                "active": [
                    {"condition": "Essential hypertension", "code": "59621000"},
                    {"condition": "Type 2 diabetes mellitus", "code": "44054006"},
                ],
                "active_count": 2,
                "resolved": [{"condition": "Acute viral pharyngitis"}],
                "resolved_count": 1,
            },
            "medications": {
                "active": [
                    {"description": "Lisinopril 10mg oral tablet"},
                    {"description": "Metformin 500mg oral tablet"},
                ],
                "active_count": 2,
            },
        },
        lab_case={
            "latest_labs": [
                {"test_name": "HbA1c", "value": 7.4, "unit": "%"},
            ],
        },
    )
    assert "Essential hypertension" in text
    assert "Type 2 diabetes mellitus" in text
    assert "Lisinopril" in text
    assert "Metformin" in text
    assert "HbA1c" in text
    # Resolved conditions also surface (so we don't silently drop them)
    assert "Acute viral pharyngitis" in text


def test_normalise_clinical_list_shapes():
    from src.memory.case_based_memory import _normalise_clinical_list
    assert _normalise_clinical_list(None) == []
    assert _normalise_clinical_list([1, 2]) == [1, 2]
    assert _normalise_clinical_list({"active": [1, 2], "resolved": [3]}) == [1, 2, 3]
    # Active comes first
    assert _normalise_clinical_list({"resolved": [3], "active": [1, 2]})[0] == 1
    # Non-list dict values are skipped, scalars are dropped
    assert _normalise_clinical_list({"active": [1], "active_count": 1}) == [1]
    assert _normalise_clinical_list("not a collection") == []


def test_case_based_recall_empty_when_qdrant_unconfigured(monkeypatch):
    """No QDRANT_URL → recall returns [] (graceful degradation)."""
    monkeypatch.setenv("QDRANT_URL", "")
    import src.memory.case_based_memory as cbm
    monkeypatch.setattr(cbm, "_client", None)
    monkeypatch.setattr(cbm, "_collection_ready", False)

    cb = CaseBasedMemory()
    out = cb.recall(patient_context={"ehr_case": {}, "lab_case": {}})
    assert out == []


def test_case_based_index_empty_when_qdrant_unconfigured(monkeypatch):
    monkeypatch.setenv("QDRANT_URL", "")
    import src.memory.case_based_memory as cbm
    monkeypatch.setattr(cbm, "_client", None)
    monkeypatch.setattr(cbm, "_collection_ready", False)

    cb = CaseBasedMemory()
    ok = cb.index_patient(
        patient_uuid="abc-123",
        ehr_case={"demographics": {"age": 60}},
        lab_case={},
        matched_diagnosis="Hypertension",
        match_type="DIRECT",
    )
    assert ok is False


def test_case_based_recall_uses_mocked_qdrant(monkeypatch):
    """Round-trip: patch client+model, confirm recall returns parsed payloads."""

    class _FakePoint:
        def __init__(self, payload, score):
            self.payload = payload
            self.score = score

    class _FakeResponse:
        def __init__(self, points):
            self.points = points

    class _FakeClient:
        def get_collections(self):
            class _CL:
                collections = []
            return _CL()
        def create_collection(self, **kwargs): pass
        def query_points(self, collection_name, query, limit):
            return _FakeResponse([
                _FakePoint(payload={
                    "patient_uuid": "uuid-1",
                    "case_text": "Demographics: age 70, male...",
                    "matched_diagnosis": "Hypertension",
                    "match_type": "DIRECT",
                    "rank_when_found": 1,
                    "primary_confidence": 88.0,
                    "evidence_patterns": ["BP > 140/90"],
                    "indexed_at": "2026-05-06T01:00:00+00:00",
                }, score=0.91),
                _FakePoint(payload={
                    "patient_uuid": "uuid-2",
                    "matched_diagnosis": "Diabetes type 2",
                    "match_type": "INDIRECT",
                }, score=0.74),
            ])

    class _FakeModel:
        def encode(self, text): return [0.0] * 4
        def get_sentence_embedding_dimension(self): return 4

    import src.memory.case_based_memory as cbm
    monkeypatch.setattr(cbm, "_client", _FakeClient())
    monkeypatch.setattr(cbm, "_model", _FakeModel())
    monkeypatch.setattr(cbm, "_collection_ready", True)

    out = CaseBasedMemory().recall(
        patient_context={"ehr_case": {"demographics": {"age": 65}}, "lab_case": {}},
        top_k=5,
    )
    assert len(out) == 2
    assert out[0]["patient_uuid"] == "uuid-1"
    assert out[0]["matched_diagnosis"] == "Hypertension"
    assert out[0]["match_type"] == "DIRECT"
    assert out[0]["score"] == 0.91
    assert "BP > 140/90" in out[0]["evidence_patterns"]


def test_case_based_recall_excludes_self_uuid(monkeypatch):
    """exclude_uuid filters out the current patient (self-match guard)."""

    class _FakePoint:
        def __init__(self, payload, score):
            self.payload = payload
            self.score = score

    class _FakeResponse:
        def __init__(self, points):
            self.points = points

    class _FakeClient:
        def get_collections(self):
            class _CL:
                collections = []
            return _CL()
        def create_collection(self, **k): pass
        def query_points(self, collection_name, query, limit):
            return _FakeResponse([
                _FakePoint(payload={"patient_uuid": "self-uuid",
                                    "matched_diagnosis": "X",
                                    "match_type": "DIRECT"}, score=1.0),
                _FakePoint(payload={"patient_uuid": "other-uuid",
                                    "matched_diagnosis": "Y",
                                    "match_type": "DIRECT"}, score=0.8),
            ])

    class _FakeModel:
        def encode(self, text): return [0.0, 0.0]
        def get_sentence_embedding_dimension(self): return 2

    import src.memory.case_based_memory as cbm
    monkeypatch.setattr(cbm, "_client", _FakeClient())
    monkeypatch.setattr(cbm, "_model", _FakeModel())
    monkeypatch.setattr(cbm, "_collection_ready", True)

    out = CaseBasedMemory().recall(
        patient_context={"ehr_case": {}, "lab_case": {}},
        top_k=5,
        exclude_uuid="self-uuid",
    )
    assert len(out) == 1
    assert out[0]["patient_uuid"] == "other-uuid"


def test_case_based_index_round_trip_via_mock(monkeypatch):
    """index_patient builds a payload via the fake client; returns True."""

    class _FakeClient:
        def __init__(self):
            self.upserted = None
        def get_collections(self):
            class _CL:
                collections = []
            return _CL()
        def create_collection(self, **k): pass
        def upsert(self, collection_name, points):
            self.upserted = (collection_name, points[0].payload)

    class _FakeModel:
        def encode(self, text): return [0.1, 0.2, 0.3]
        def get_sentence_embedding_dimension(self): return 3

    import src.memory.case_based_memory as cbm
    fake_client = _FakeClient()
    monkeypatch.setattr(cbm, "_client", fake_client)
    monkeypatch.setattr(cbm, "_model", _FakeModel())
    monkeypatch.setattr(cbm, "_collection_ready", True)

    ok = CaseBasedMemory().index_patient(
        patient_uuid="abc-123",
        ehr_case={"demographics": {"age": 60}},
        lab_case={},
        matched_diagnosis="Hypertension",
        match_type="DIRECT",
        rank_when_found=1,
        primary_confidence=82.0,
        evidence_patterns=["BP 158/96"],
    )
    assert ok is True
    coll, payload = fake_client.upserted
    assert coll == "patient_cases"
    assert payload["patient_uuid"] == "abc-123"
    assert payload["matched_diagnosis"] == "Hypertension"
    assert payload["match_type"] == "DIRECT"
    assert payload["evidence_patterns"] == ["BP 158/96"]
    assert "Demographics: age 60" in payload["case_text"]


def test_case_based_summarize_for_prompt_handles_empty():
    assert "no similar past patient cases" in CaseBasedMemory.summarize_for_prompt([])


def test_case_based_summarize_for_prompt_lists_top_results():
    summary = CaseBasedMemory.summarize_for_prompt([
        {"matched_diagnosis": "Hypertension", "match_type": "DIRECT",
         "score": 0.91, "rank_when_found": 1},
        {"matched_diagnosis": "Diabetes", "match_type": "INDIRECT",
         "score": 0.74, "rank_when_found": None},
    ])
    assert "Hypertension" in summary
    assert "DIRECT" in summary
    assert "rank-1" in summary
    assert "Diabetes" in summary
    assert "INDIRECT" in summary


def test_case_based_id_is_stable_across_calls():
    """Re-indexing the same patient must hit the same Qdrant point id."""
    from src.memory.case_based_memory import _stable_id_from_uuid
    uuid = "04d1f4cf-4c22-7b28-0296-6dc72983024e"
    assert _stable_id_from_uuid(uuid) == _stable_id_from_uuid(uuid)
    assert _stable_id_from_uuid(uuid) != _stable_id_from_uuid(uuid + "x")


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
    assert isinstance(mm.case_based, CaseBasedMemory)
    # Knowledge base = NICE guidelines wrapper, not part of the memory tiers.
    assert isinstance(mm.knowledge_base, ProceduralMemory)
    assert mm.procedural is mm.knowledge_base


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


def test_memory_consolidation_miss_does_not_aggregate_under_NONE(monkeypatch, tmp_path):
    """Regression: judge returns matched_diagnosis="NONE" for MISS cases.

    Previously the consolidator stored MISSes under disease="NONE",
    silently poisoning Tier-3 priors. The fix falls back to the agent's
    primary_diagnosis when matched_diagnosis is NONE/empty.
    """
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_MEMORY_PATH", str(tmp_path / "sm.json"))
    from importlib import reload
    import src.config as config_module
    reload(config_module)
    from src.agents.memory_consolidator import memory_consolidation_node

    state = {
        "agent_outputs": {
            "evaluation": {
                "match_type": "MISS",
                "rank": 0,
                "matched_diagnosis": "NONE",  # judge's miss sentinel
            },
            "final_diagnosis": {
                "primary_diagnosis": "Atherosclerotic cardiovascular disease",
                "differential": [
                    {"rank": 1, "name": "Atherosclerotic cardiovascular disease",
                     "probability": 0.62, "supporting_evidence": []},
                ],
            },
        },
        "patient_context": {
            "ehr_case": {"patient_uuid": "test-miss-uuid",
                         "demographics": {"age": 65}},
            "lab_case": {},
        },
    }
    out = memory_consolidation_node(state)
    sm_path = tmp_path / "sm.json"
    assert sm_path.exists(), "consolidation should still write Tier-3 even on MISS"
    payload = json.loads(sm_path.read_text())
    # The disease key must NOT be "NONE"
    assert "NONE" not in payload, (
        f"MISS aggregated under fake disease 'NONE': {list(payload.keys())}"
    )
    # Must aggregate under the canonical family of the predicted primary,
    # not under the LLM's verbose phrasing — "Atherosclerotic
    # cardiovascular disease" canonicalises to IHD.
    assert "IHD" in payload, (
        f"MISS should aggregate under canonical family 'IHD': "
        f"{list(payload.keys())}"
    )
    entry = payload["IHD"]
    assert entry["misses"] == 1, "MISS count should increment for the predicted family"
    assert entry["direct_matches"] == 0
    # The raw LLM phrasing is preserved as the first evidence pattern
    # so debug inspectors can see exactly what the model said.
    assert any("Atherosclerotic" in p for p in entry.get("common_evidence_patterns", []))


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
    # Canonicalised: "Hypertension" → "HTN" family
    assert "HTN" in payload, (
        f"Hypertension should canonicalise to HTN: {list(payload.keys())}"
    )
    assert payload["HTN"]["direct_matches"] == 1
    # Raw LLM phrasing preserved as evidence pattern for debugging.
    assert any("Hypertension" in p
               for p in payload["HTN"].get("common_evidence_patterns", []))


# ────────────── Disease canonicalizer (memory accuracy hardening) ────────────


def test_canonicalizer_collapses_known_families():
    """Canonicalizer must map the 8 ground-truth disease names to the 8
    canonical families used by aggregate_160.json."""
    from src.memory.disease_canonicalizer import canonicalize_disease
    cases = [
        # Ground-truth disease names (as they appear in aggregate_160.json)
        ("End-stage renal disease",                      "ESRD"),
        ("Metabolic syndrome X",                         "metabolic_syndrome"),
        ("Essential hypertension",                       "HTN"),
        ("Ischemic heart disease",                       "IHD"),
        ("CKD stage 3",                                  "CKD"),
        ("Diabetes mellitus type 2",                     "T2DM"),
        ("Chronic congestive heart failure",             "CHF"),
        ("Chronic kidney disease stage 2 (disorder)",    "CKD"),
        # Common LLM phrasings collapse to the right family
        ("Acute NSTEMI (type 1 myocardial infarction)",  "IHD"),
        ("Atherosclerotic cardiovascular disease",       "IHD"),
        ("Diabetic-hypertensive chronic kidney disease (CKD stage 4)", "CKD"),
        ("Diabetic nephropathy",                         "CKD"),
        ("Insulin-resistance-driven metabolic syndrome", "metabolic_syndrome"),
        ("Uncontrolled essential hypertension",          "HTN"),
        ("Untreated severe hypercholesterolemia",        "dyslipidemia"),
        # Things the system has no canonical bucket for
        ("Iron-deficiency anemia",                       "other"),
        ("Right-sided infective endocarditis",           "other"),
        ("Obstructive sleep apnea",                      "other"),
        # Defensive: empty / NONE / None
        ("",      "other"),
        ("NONE",  "other"),
        (None,    "other"),
    ]
    for raw, expected in cases:
        got = canonicalize_disease(raw)
        assert got == expected, f"{raw!r} → {got!r}, expected {expected!r}"


def test_canonicalizer_priority_specific_before_general():
    """Acute MI should map to IHD, not get caught by a generic
    cardiovascular catch-all. Stage-5 CKD should map to ESRD, not CKD."""
    from src.memory.disease_canonicalizer import canonicalize_disease
    assert canonicalize_disease(
        "Atherosclerotic coronary artery disease with recent STEMI"
    ) == "IHD"
    assert canonicalize_disease(
        "Diabetic nephropathy (stage 5 chronic kidney disease)"
    ) == "ESRD"
    # Hypertensive nephropathy is a kidney problem, not pure HTN
    assert canonicalize_disease(
        "Hypertensive nephropathy (CKD stage 4)"
    ) == "CKD"


def test_consolidator_skips_tier4_for_non_direct(monkeypatch, tmp_path):
    """Default MEMORY_WRITE_CASE_MATCH_TYPES=DIRECT means MISS / INDIRECT
    cases never get indexed into Qdrant, even though they DO update the
    Tier-3 semantic store. This is the source-of-pollution fix."""
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_MEMORY_PATH", str(tmp_path / "sm.json"))
    monkeypatch.setenv("MEMORY_WRITE_CASE_MATCH_TYPES", "DIRECT")
    from importlib import reload
    import src.config as config_module
    reload(config_module)

    # Patch get_case_based_memory so we can record whether index_patient is called
    calls = []

    class _FakeCaseStore:
        def index_patient(self, **kwargs):
            calls.append(kwargs)
            return True

    import src.agents.memory_consolidator as mc
    monkeypatch.setattr(mc, "get_case_based_memory", lambda: _FakeCaseStore())

    state_miss = {
        "agent_outputs": {
            "evaluation": {"match_type": "MISS", "matched_diagnosis": "NONE"},
            "final_diagnosis": {"primary_diagnosis": "Type 2 diabetes"},
        },
        "patient_context": {"ehr_case": {"patient_uuid": "miss-uuid"},
                            "lab_case": {}},
    }
    mc.memory_consolidation_node(state_miss)
    assert calls == [], f"MISS case should NOT be indexed in Tier-4: {calls}"

    # Now a DIRECT case: should be indexed
    state_direct = {
        "agent_outputs": {
            "evaluation": {"match_type": "DIRECT", "rank": 1,
                           "matched_diagnosis": "Hypertension"},
            "final_diagnosis": {"primary_diagnosis": "Hypertension"},
        },
        "patient_context": {"ehr_case": {"patient_uuid": "direct-uuid"},
                            "lab_case": {}},
    }
    mc.memory_consolidation_node(state_direct)
    assert len(calls) == 1, f"DIRECT case should be indexed: {calls}"
    assert calls[0]["match_type"] == "DIRECT"
    assert calls[0]["canonical_family"] == "HTN"


def test_consolidator_writes_canonical_family_to_qdrant_payload(monkeypatch, tmp_path):
    """The canonical_family field flows from consolidator → index_patient
    → Qdrant payload, so case-based recall results carry the family
    label without re-canonicalising at query time."""
    monkeypatch.setenv("MEMORY_ENABLED", "true")
    monkeypatch.setenv("SEMANTIC_MEMORY_PATH", str(tmp_path / "sm.json"))
    monkeypatch.setenv("MEMORY_WRITE_CASE_MATCH_TYPES", "DIRECT")
    from importlib import reload
    import src.config as config_module
    reload(config_module)

    captured = {}

    class _FakeCaseStore:
        def index_patient(self, **kwargs):
            captured.update(kwargs)
            return True

    import src.agents.memory_consolidator as mc
    monkeypatch.setattr(mc, "get_case_based_memory", lambda: _FakeCaseStore())

    state = {
        "agent_outputs": {
            "evaluation": {"match_type": "DIRECT", "rank": 1,
                           "matched_diagnosis": "Diabetic nephropathy (CKD stage 4)"},
            "final_diagnosis": {
                "primary_diagnosis": "Diabetic nephropathy (CKD stage 4)",
            },
        },
        "patient_context": {"ehr_case": {"patient_uuid": "u-canonical"},
                            "lab_case": {}},
    }
    mc.memory_consolidation_node(state)
    assert captured["canonical_family"] == "CKD"
    assert "Diabetic nephropathy" in captured["matched_diagnosis"]
