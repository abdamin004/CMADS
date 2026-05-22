"""MongoDB client lifecycle.

Two entry points:
  * Async ``init_db(db)`` — register Beanie models on a Motor database.
    Called from FastAPI lifespan and from script entry points.
  * Sync ``get_sync_db()`` — convenience for the non-async pipeline
    scripts. Spins up its own loop boundary; the caller does not need
    to know it is talking to async code.
"""
from __future__ import annotations
import asyncio
from typing import Any
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from beanie import init_beanie

from src.config import cfg
from src.db.documents import (
    PatientCase,
    AgentRun,
    SemanticMemoryEntry,
    DerivedArtefact,
)

_DOCUMENT_MODELS = [PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact]
_client: AsyncIOMotorClient | None = None


async def init_db(database: AsyncIOMotorDatabase | None = None) -> AsyncIOMotorDatabase:
    """Bind Beanie to ``database``. When ``database`` is None, opens
    the configured ``MONGO_URI`` / ``MONGO_DB`` and binds to that."""
    global _client
    if database is None:
        if _client is None:
            _client = AsyncIOMotorClient(cfg.MONGO_URI)
        database = _client[cfg.MONGO_DB]
    await init_beanie(database=database, document_models=_DOCUMENT_MODELS)
    return database


def get_sync_db() -> Any:
    """Synchronous bootstrap for scripts. Initialises the global client
    and runs ``init_db`` once via ``asyncio.run``. Subsequent calls in
    the same process are idempotent."""
    global _client
    if _client is None:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(init_db())
    return _client[cfg.MONGO_DB]
