"""MemoryManager — unified facade over all four memory tiers.

Agents should generally not instantiate the per-tier classes directly; they
go through MemoryManager so the wiring stays in one place.

    mm = MemoryManager.from_state(state, agent_id=self.agent_id)
    mm.working.put("hypotheses", [...])
    mm.episodic.summarize()
    mm.semantic.recall("Hypertension")
    mm.procedural.lookup_disease("Hypertension")
    return {"session_memory": [mm.episodic.write("decision", ...)], ...}

The manager intentionally has no LLM coupling: recall is rule-based, fast,
and deterministic. This keeps the multi-level memory feature within scope
for a thesis project and gives reproducible behavior for evaluation.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

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
        self.procedural = ProceduralMemory()

    # ── Convenience constructors ────────────────────────────────────────

    @classmethod
    def from_state(cls, state: dict, agent_id: str) -> "MemoryManager":
        return cls(state=state, agent_id=agent_id)

    # ── Helpers used by agents ──────────────────────────────────────────

    def context_block(
        self,
        diseases_for_semantic: list[str] | None = None,
        max_episodic: int = 30,
    ) -> str:
        """Build a single human-readable context block for prompt injection.

        Combines the most recent episodic events and any cross-session insights
        relevant to the given differential diseases. Designed to be concise so
        adding it to a prompt doesn't blow up token cost.
        """
        parts: list[str] = []
        episodic_summary = self.episodic.summarize(max_events=max_episodic)
        parts.append("### Episodic memory (current session)")
        parts.append(episodic_summary)
        if diseases_for_semantic:
            parts.append("")
            parts.append("### Semantic memory (prior runs)")
            parts.append(self.semantic.summarize_for_diseases(diseases_for_semantic))
        return "\n".join(parts)


def _default_semantic_path() -> Path:
    """Default location for the cross-session semantic memory store."""
    from src.config import cfg
    base = Path(cfg.MAS_RESULTS_DIR).parent
    return base / "memory" / "semantic_memory.json"
