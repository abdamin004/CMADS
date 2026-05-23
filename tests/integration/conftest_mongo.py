"""Per-test MongoDB fixture — connects to MONGO_URI, uses a unique DB name
per test session, drops the DB on teardown so tests are isolated."""
import os, uuid as _uuid
import pytest
import pytest_asyncio
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from fastapi.testclient import TestClient

from src.config import cfg
from src.db.documents import PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact, TestPatient

@pytest_asyncio.fixture
async def mongo_db():
    """Spin up a fresh Beanie-bound test database for one test."""
    db_name = f"cmads_test_{_uuid.uuid4().hex[:8]}"
    client = AsyncIOMotorClient(cfg.MONGO_URI)
    await init_beanie(
        database=client[db_name],
        document_models=[PatientCase, AgentRun, SemanticMemoryEntry, DerivedArtefact, TestPatient],
    )
    yield client[db_name]
    await client.drop_database(db_name)
    client.close()


@pytest.fixture
def mongo_db(monkeypatch):  # noqa: F811 — sync override for non-async tests
    """Sync pymongo fixture for non-async integration tests.

    Spins up a fresh database per test, wires src.db.mongo._sync_client
    to point at it, reloads the app module so every _coll() call in
    the test uses this DB, and drops the DB on teardown.
    """
    from pymongo import MongoClient
    import src.db.mongo as mongo_mod
    import doctor_console.backend.app as app_mod
    from importlib import reload

    db_name = f"cmads_test_{_uuid.uuid4().hex[:8]}"
    sync_client = MongoClient(cfg.MONGO_URI)

    # Point the sync mongo helper at the test DB.
    monkeypatch.setenv("MONGO_DB", db_name)
    monkeypatch.setenv("USE_MONGO", "true")
    mongo_mod._sync_client = sync_client

    # Reset caches and reload so the app's _coll() sees the new MONGO_DB.
    app_mod._vocab_cache = None
    mongo_mod._sync_client = sync_client
    reload(app_mod)

    yield sync_client[db_name]

    sync_client.drop_database(db_name)
    sync_client.close()
    # Restore so subsequent tests get a clean slate.
    mongo_mod._sync_client = None


@pytest.fixture
def client(mongo_db):  # noqa: F811
    """TestClient wired to the reloaded app (same DB as mongo_db fixture)."""
    import doctor_console.backend.app as app_mod
    return TestClient(app_mod.app, raise_server_exceptions=True)
