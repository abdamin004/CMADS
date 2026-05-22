"""Mongo-backed write path for Tier-3 semantic memory.

This module holds only the async helper that performs atomic $inc updates on
SemanticMemoryEntry documents. The existing filesystem-backed SemanticMemory
class in semantic_memory.py is unchanged — this is a purely additive module.

The memory consolidator dispatches here when USE_MONGO=true; the filesystem
path remains the default until the cutover flag is flipped.
"""

from __future__ import annotations


async def consolidate_to_mongo(
    disease: str, *, match_type: str, at_rank_1: bool,
) -> None:
    """Atomic per-disease increment. Replaces the previous read-modify-write
    on semantic_memory.json (which was unsafe under parallel consolidation)."""
    from datetime import datetime
    from src.db.mongo import ensure_db_initialized
    from src.db.documents import SemanticMemoryEntry

    await ensure_db_initialized()
    field = {"DIRECT": "direct", "INDIRECT": "indirect", "MISS": "miss"}.get(match_type, "miss")
    inc: dict[str, int] = {f"counts.{field}": 1}
    if at_rank_1 and match_type in ("DIRECT", "INDIRECT"):
        inc["rank1_when_found"] = 1
    await SemanticMemoryEntry.find_one(SemanticMemoryEntry.id == disease).upsert(
        {"$inc": inc, "$set": {"updated_at": datetime.utcnow()}},
        on_insert=SemanticMemoryEntry(id=disease, counts={field: 1},
                                      rank1_when_found=(1 if at_rank_1 and match_type != "MISS" else 0),
                                      updated_at=datetime.utcnow()),
    )
