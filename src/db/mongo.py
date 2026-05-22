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


async def ensure_db_initialized() -> None:
    """Initialize Beanie only when it has not been initialized yet.

    This is the safe entry point for helper functions that may be called from
    both production code (where nothing is set up yet) and from tests (where
    the conftest has already called init_beanie on a test database). Re-calling
    init_db in tests would re-bind document models to a new Motor client whose
    event loop is the one from the previous test, causing 'Event loop is closed'
    errors on subsequent test runs.
    """
    from beanie.exceptions import CollectionWasNotInitialized
    try:
        # If any document model has its Motor collection bound, Beanie is up.
        AgentRun.get_motor_collection()
    except CollectionWasNotInitialized:
        await init_db()


def get_sync_db() -> Any:
    """Synchronous bootstrap for scripts. Initialises the global client
    and runs ``init_db`` once via ``asyncio.run``. Subsequent calls in
    the same process are idempotent."""
    global _client
    if _client is None:
        asyncio.get_event_loop_policy().new_event_loop().run_until_complete(init_db())
    return _client[cfg.MONGO_DB]
