"""Multi-level memory subsystem (CoALA-inspired).

Four tiers:
  - WorkingMemory       — per-agent ephemeral (Tier 1, in-state)
  - EpisodicMemory      — current session timeline (Tier 2, in-state, persisted)
  - SemanticMemory      — cross-session disease stats (Tier 3, on disk)
  - CaseBasedMemory     — past patient cases via Qdrant (Tier 4, vector recall)

NICE clinical guidelines remain accessible through ProceduralMemory but they
are *external reference knowledge*, not part of the memory hierarchy — Tier 4
was redesigned to hold the actually-useful patient context that benefits from
vector similarity (case-based recall).

Agents access tiers through MemoryManager:

    from src.memory import MemoryManager
    mm = MemoryManager.from_state(state, agent_id=self.agent_id)
    mm.working.put(...)
    mm.episodic.summarize()
    mm.semantic.recall("Hypertension")
    mm.case_based.recall(patient_context, top_k=5)
    mm.knowledge_base.lookup_disease("Hypertension")  # NICE guidelines
"""

from src.memory.case_based_memory import (
    CaseBasedMemory,
    build_case_text,
    get_case_based_memory,
)
from src.memory.episodic_memory import EpisodicMemory
from src.memory.manager import MemoryManager
from src.memory.procedural_memory import ProceduralMemory
from src.memory.semantic_memory import SemanticMemory
from src.memory.types import (
    ConfidenceCheckpoint,
    EventType,
    SemanticInsight,
    SessionEvent,
)
from src.memory.working_memory import WorkingMemory

__all__ = [
    "MemoryManager",
    "WorkingMemory",
    "EpisodicMemory",
    "SemanticMemory",
    "CaseBasedMemory",
    "ProceduralMemory",
    "SessionEvent",
    "ConfidenceCheckpoint",
    "SemanticInsight",
    "EventType",
    "build_case_text",
    "get_case_based_memory",
]
