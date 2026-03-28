"""PipelineState — LangGraph shared memory implemented as TypedDict channels.

This IS the shared memory store from SDD §4. Each key is a namespace:
  patient_context   — Gold-layer data (written by Orchestrator, read by all)
  agent_outputs     — Per-agent output slots (write-own, read-downstream)
  conflicts         — Contradiction records (written by conflict detector)
  execution_trace   — Invocation logs (written by Orchestrator)
  scratchpad        — Per-agent ephemeral notes

Implements: IF-001–005, MA-005
"""

from __future__ import annotations

import copy
from typing import Annotated, TypedDict
from operator import add


def _merge_agent_outputs(existing: dict, new: dict) -> dict:
    """Reducer: merge new agent output slots into existing dict.

    Each agent writes to its own key (e.g., {"ehr_analyst": {...}}).
    This reducer merges without overwriting other agents' slots.
    """
    merged = copy.copy(existing) if existing else {}
    merged.update(new)
    return merged


class PipelineState(TypedDict, total=False):
    """LangGraph shared memory — proper TypedDict with reducer annotations.

    Using Annotated types with reducer functions for append-only fields.
    LangGraph reads the __annotations__ to build state channels.
    """
    # Gold-layer patient data (set once by orchestrator)
    patient_context: dict

    # Per-agent output slots — merge reducer prevents overwriting
    agent_outputs: Annotated[dict, _merge_agent_outputs]

    # Conflict records — append-only list
    conflicts: Annotated[list, add]

    # Execution trace — append-only list
    execution_trace: Annotated[list, add]

    # Per-agent ephemeral scratchpad
    scratchpad: dict
