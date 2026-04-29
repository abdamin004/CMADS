"""Tier 2 — Episodic Memory.

The current pipeline run's timeline of significant events: decisions, critiques,
confidence checks, conflicts, evidence links. Every agent can append events,
and downstream agents can read the trail.

Lives in PipelineState.session_memory (append-only via reducer) and is saved
to disk at the end of a run as `session_memory.json` for post-hoc analysis.

Distinct from `execution_trace` (which is just status/timing per agent) —
episodic memory captures the *content* of reasoning, not the bookkeeping.
"""

from __future__ import annotations

from typing import Any, Iterable

from src.memory.types import EventType, SessionEvent


class EpisodicMemory:
    """Helper around the session_memory state channel.

    Reads operate on a snapshot list; writes return partial-state dicts that
    LangGraph's append-reducer merges back into the main state.
    """

    def __init__(self, events: list[dict] | None = None):
        self._events = events or []

    # ── Reads ────────────────────────────────────────────────────────────

    @property
    def events(self) -> list[dict]:
        return list(self._events)

    def by_agent(self, agent_id: str) -> list[dict]:
        return [e for e in self._events if e.get("agent_id") == agent_id]

    def by_type(self, event_type: EventType) -> list[dict]:
        return [e for e in self._events if e.get("event_type") == event_type]

    def by_tag(self, tag: str) -> list[dict]:
        return [e for e in self._events if tag in (e.get("tags") or [])]

    def latest(self, n: int = 10) -> list[dict]:
        return self._events[-n:]

    def summarize(self, max_events: int = 30) -> str:
        """Compact human-readable digest for prompt injection.

        Truncates to the last `max_events` to keep prompt cost bounded; the
        Diagnostic Reasoning loop can produce 6+ events alone, so on a full run
        we want the most recent context, not everything.
        """
        if not self._events:
            return "(no prior session events)"
        tail = self._events[-max_events:]
        lines = [f"Session timeline ({len(tail)} of {len(self._events)} events):"]
        for e in tail:
            agent = e.get("agent_id", "?")
            etype = e.get("event_type", "?")
            summary = e.get("summary", "")
            lines.append(f"  - [{agent}] {etype}: {summary}")
        return "\n".join(lines)

    # ── Writes (return a partial state dict) ────────────────────────────

    @staticmethod
    def make_event(
        event_type: EventType,
        agent_id: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        tags: Iterable[str] | None = None,
    ) -> dict:
        """Build a SessionEvent dict (validated via Pydantic)."""
        ev = SessionEvent(
            event_type=event_type,
            agent_id=agent_id,
            summary=summary,
            payload=payload or {},
            tags=list(tags or []),
        )
        return ev.model_dump()

    @classmethod
    def write(
        cls,
        event_type: EventType,
        agent_id: str,
        summary: str,
        payload: dict[str, Any] | None = None,
        tags: Iterable[str] | None = None,
    ) -> dict:
        """Return a partial state dict that LangGraph will append-merge.

        Usage from an agent:
            return {"session_memory": [EpisodicMemory.write("decision", ...)]}
        """
        return cls.make_event(event_type, agent_id, summary, payload, tags)
