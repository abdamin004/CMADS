"""Tier 1 — Working Memory.

Per-agent ephemeral scratch space, scoped to a single agent invocation.
Lives in PipelineState.scratchpad[agent_id] (a previously-unused channel).

Use case: multi-round agents (e.g. Diagnostic Reasoning's critique loop) need
to track intermediate reasoning across LLM calls within ONE __call__. Without
this, the only way to pass context between rounds is via free-text concatenation.

Working memory is NOT persisted to disk and NOT visible to downstream agents
(use Episodic memory for that).
"""

from __future__ import annotations

from typing import Any


class WorkingMemory:
    """Thin wrapper over PipelineState.scratchpad for a single agent.

    Usage in an agent:
        wm = WorkingMemory(state, self.agent_id)
        wm.put("round_1_critique", "...")
        prior = wm.get("round_1_critique")
        wm.append_to("hypotheses", "diabetes type 2")
    """

    def __init__(self, state: dict, agent_id: str):
        self._state = state
        self._agent_id = agent_id
        self._state.setdefault("scratchpad", {})
        self._state["scratchpad"].setdefault(agent_id, {})

    @property
    def slot(self) -> dict[str, Any]:
        return self._state["scratchpad"][self._agent_id]

    def put(self, key: str, value: Any) -> None:
        self.slot[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self.slot.get(key, default)

    def append_to(self, key: str, item: Any) -> None:
        bucket = self.slot.setdefault(key, [])
        if not isinstance(bucket, list):
            raise TypeError(f"working_memory[{key!r}] is not a list")
        bucket.append(item)

    def merge(self, updates: dict[str, Any]) -> None:
        self.slot.update(updates)

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of the current working memory."""
        return dict(self.slot)
