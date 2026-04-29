# Decisions log

One bullet per decision. Date + reason. Tag `#decision`.

- 2026-04-29 — Add **multi-level memory** subsystem (4 tiers: working / episodic / semantic / procedural) on top of the existing LangGraph state. **Why:** supervisor request for shared session context; the previous design exposed only final agent JSONs to downstream agents, hiding the *path* taken to a diagnosis. **Refs:** [`src/memory/`](../src/memory/), [`src/agents/memory_consolidator.py`](../src/agents/memory_consolidator.py), [`tests/test_memory.py`](../tests/test_memory.py); gated by `MEMORY_ENABLED` env var so the before/after experiment is a clean A/B. #decision #thesis
