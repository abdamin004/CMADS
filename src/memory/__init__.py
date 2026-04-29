"""Multi-level memory subsystem (CoALA-inspired).

Four tiers:
  - WorkingMemory      — per-agent ephemeral (Tier 1, in-state)
  - EpisodicMemory     — current session timeline (Tier 2, in-state, persisted)
  - SemanticMemory     — cross-session insights (Tier 3, on disk)
  - ProceduralMemory   — NICE guidelines via Qdrant (Tier 4, static)

Agents access tiers through MemoryManager:

    from src.memory import MemoryManager
    mm = MemoryManager.from_state(state, agent_id=self.agent_id)
    mm.working.put(...)
    mm.episodic.summarize()
    mm.semantic.recall("Hypertension")
    mm.procedural.lookup_disease("Hypertension")
"""

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
    "ProceduralMemory",
    "SessionEvent",
    "ConfidenceCheckpoint",
    "SemanticInsight",
    "EventType",
]
