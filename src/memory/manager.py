"""MemoryManager — unified facade over all four memory tiers.

Agents should generally not instantiate the per-tier classes directly; they
go through MemoryManager so the wiring stays in one place.

    mm = MemoryManager.from_state(state, agent_id=self.agent_id)
    mm.working.put("hypotheses", [...])
    mm.episodic.summarize()
    mm.semantic.recall("Hypertension")
    mm.case_based.recall(state.get("patient_context"), top_k=5)
    mm.knowledge_base.lookup_disease("Hypertension")  # NICE guidelines
    return {"session_memory": [mm.episodic.write("decision", ...)], ...}

Tiers 1–3 have no LLM coupling: recall is rule-based, fast, deterministic.
Tier 4 (case-based) uses the same BioLORD embedding model as the existing
NICE-guidelines store but a separate Qdrant collection (`patient_cases`).

NICE clinical guidelines remain accessible through `knowledge_base` (a
`ProceduralMemory` instance, kept for the Treatment agent) — they are
external reference knowledge, not part of the memory hierarchy.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.memory.case_based_memory import CaseBasedMemory, get_case_based_memory
from src.memory.episodic_memory import EpisodicMemory
from src.memory.procedural_memory import ProceduralMemory
from src.memory.semantic_memory import SemanticMemory
from src.memory.working_memory import WorkingMemory


class MemoryManager:
    """Bundle the four memory tiers around a single PipelineState dict.

    Construction is per-agent (each agent gets its own working-memory slot).
    """

    def __init__(
        self,
        state: dict,
        agent_id: str,
        semantic_path: Optional[Path] = None,
    ):
        self.state = state
        self.agent_id = agent_id

        self.working = WorkingMemory(state, agent_id)
        self.episodic = EpisodicMemory(state.get("session_memory") or [])
        self.semantic = SemanticMemory(
            semantic_path or _default_semantic_path()
        )
        # Tier 4 — past patient cases in Qdrant (case-based recall).
        self.case_based: CaseBasedMemory = get_case_based_memory()
        # NICE guidelines stay accessible as an external knowledge base —
        # the Treatment agent still needs them — but they live outside the
        # memory hierarchy. Exposed via knowledge_base for clarity; the
        # `procedural` alias is kept so older agent code keeps working.
        self.knowledge_base = ProceduralMemory()
        self.procedural = self.knowledge_base

    # ── Convenience constructors ────────────────────────────────────────

    @classmethod
    def from_state(cls, state: dict, agent_id: str) -> "MemoryManager":
        return cls(state=state, agent_id=agent_id)

    # ── Helpers used by agents ──────────────────────────────────────────

    def context_block(
        self,
        diseases_for_semantic: list[str] | None = None,
        case_based_recall: list[dict] | None = None,
        max_episodic: int = 30,
    ) -> str:
        """Build a single human-readable context block for prompt injection.

        Combines the most recent episodic events, cross-session disease
        insights for the given differential, and (optionally) the top-K
        similar past patients from case-based memory.
        """
        parts: list[str] = []
        episodic_summary = self.episodic.summarize(max_events=max_episodic)
        parts.append("### Episodic memory (current session)")
        parts.append(episodic_summary)
        if diseases_for_semantic:
            parts.append("")
            parts.append("### Semantic memory (prior runs)")
            parts.append(self.semantic.summarize_for_diseases(diseases_for_semantic))
        if case_based_recall:
            parts.append("")
            parts.append("### Case-based memory (similar past patients)")
            parts.append(CaseBasedMemory.summarize_for_prompt(case_based_recall))
        return "\n".join(parts)


def _default_semantic_path() -> Path:
    """Default location for the cross-session semantic memory store."""
    from src.config import cfg
    base = Path(cfg.MAS_RESULTS_DIR).parent
    return base / "memory" / "semantic_memory.json"
