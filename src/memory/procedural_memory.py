"""Tier 4 — Procedural Memory.

Long-term, static knowledge: the NICE clinical guidelines already loaded into
Qdrant. This module is a thin uniform wrapper so agents access procedural
memory the same way they access the other tiers, instead of importing the
vector-DB module directly.

Why a wrapper? Two reasons:
1. Symmetry — every memory tier exposes a `recall(query)` method.
2. Graceful degradation — if Qdrant is unreachable (no QDRANT_URL set, network
   down), the wrapper returns an empty result instead of crashing the pipeline.
"""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


class ProceduralMemory:
    """Read-only access to NICE guidelines via Qdrant.

    The Treatment agent already uses query_guidelines.search_guidelines()
    directly; this wrapper preserves backwards compatibility while giving the
    Diagnostic and Reviewer agents a unified entry point.
    """

    def recall(self, query: str, top_k: int = 3) -> list[dict]:
        """Return top-k matching NICE guidelines for a disease/symptom query.

        Returns an empty list on failure (Qdrant down, no QDRANT_URL).
        """
        try:
            from src.vectordb.query_guidelines import search_guidelines
            return search_guidelines(query, top_k=top_k) or []
        except Exception as e:  # noqa: BLE001 — vector DB failures shouldn't break the run
            logger.warning(
                "procedural_memory_recall_failed",
                query=query[:60],
                error=str(e)[:120],
            )
            return []

    def lookup_disease(self, disease: str) -> dict | None:
        """Return the single best-matching guideline for a disease, or None."""
        results = self.recall(disease, top_k=1)
        if not results:
            return None
        return results[0]
