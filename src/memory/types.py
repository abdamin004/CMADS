"""Memory event types — typed records that flow through the multi-level memory system.

Inspired by Cognitive Architectures for Language Agents (CoALA, Sumers et al., 2024):
working / episodic / semantic / case-based memory tiers, each serving a distinct
role in the agent's reasoning loop. NICE guideline retrieval remains external
reference knowledge rather than a learned memory tier.

These Pydantic models give every memory entry a stable schema so downstream
agents (and the evaluator) can introspect what happened during a run.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


EventType = Literal[
    "decision",
    "hypothesis",
    "critique",
    "confidence_check",
    "evidence_link",
    "conflict",
    "memory_recall",
    "agent_start",
    "agent_complete",
]


class SessionEvent(BaseModel):
    """A single typed entry in the episodic memory timeline.

    Every agent appends events that record WHAT decision/observation was made
    and WHY, so downstream agents can read the reasoning trail rather than
    just the final structured output.
    """

    event_type: EventType
    agent_id: str
    timestamp: str = Field(default_factory=_now_iso)
    summary: str  # one-line, human-readable
    payload: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class ConfidenceCheckpoint(BaseModel):
    """A confidence reading at a given reasoning round."""

    agent_id: str
    round_num: int
    confidence: float  # 0–100
    rationale: str = ""
    timestamp: str = Field(default_factory=_now_iso)


class SemanticInsight(BaseModel):
    """A distilled cross-session insight stored in Tier 3 (semantic memory).

    Keyed by disease name. Updated on every run so future runs benefit from
    aggregate observations — e.g. "Hypertension reaches DIRECT match in 55% of
    cases when the differential places it at rank-1 with confidence ≥ 80".

    NOTE: Contains no PHI. Only disease names, evidence patterns (de-identified),
    and aggregate statistics.
    """

    disease: str
    runs_observed: int = 0
    direct_matches: int = 0
    indirect_matches: int = 0
    misses: int = 0
    rank1_when_found: int = 0  # times disease was rank-1 in a found run
    avg_primary_confidence: float = 0.0
    common_evidence_patterns: list[str] = Field(default_factory=list)
    last_updated: str = Field(default_factory=_now_iso)

    @property
    def found_rate(self) -> float:
        if self.runs_observed == 0:
            return 0.0
        return (self.direct_matches + self.indirect_matches) / self.runs_observed

    @property
    def direct_rate(self) -> float:
        if self.runs_observed == 0:
            return 0.0
        return self.direct_matches / self.runs_observed
