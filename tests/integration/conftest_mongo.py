"""Per-test MongoDB fixture — connects to MONGO_URI, uses a unique DB name
per test session, drops the DB on teardown so tests are isolated."""
import os, uuid as _uuid
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie

from src.config import cfg
from src.db.documents import PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact

@pytest_asyncio.fixture
async def mongo_db():
    """Spin up a fresh Beanie-bound test database for one test."""
    db_name = f"cmads_test_{_uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(cfg.MONGO_URI)
    await init_beanie(
        database=client[db_name],
        document_models=[PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact],
    )
    yield client[db_name]
    await client.drop_database(db_name)
    client.close()
