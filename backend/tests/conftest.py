"""Test setup: real Postgres `cogniflow_test` DB, real Alembic migration.

Decision (Phase 1, user-approved): tests run against the dockerized
pgvector Postgres, not SQLite, so the actual migration (incl. the pgvector
extension) is exercised. DATABASE_URL is pointed at the test database
BEFORE any app import, so the app engine and alembic both use it.

Requires `docker compose up -d` (postgres healthy) before `uv run pytest`.
"""

import asyncio
import os
from pathlib import Path

import asyncpg
import pytest
from alembic.config import Config
from sqlalchemy import text

from alembic import command

BACKEND_DIR = Path(__file__).resolve().parent.parent
TEST_DB_NAME = "cogniflow_test"
ADMIN_DB_URL = "postgresql://cogniflow:devpassword@localhost:5432/postgres"
TEST_DATABASE_URL = f"postgresql+asyncpg://cogniflow:devpassword@localhost:5432/{TEST_DB_NAME}"

# Must happen before any `app.*` import (settings/engine read these at import).
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("MONGO_DB", "test")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


async def _ensure_database() -> None:
    conn = await asyncpg.connect(ADMIN_DB_URL)
    try:
        exists = await conn.fetchval("SELECT 1 FROM pg_database WHERE datname = $1", TEST_DB_NAME)
        if not exists:
            await conn.execute(f'CREATE DATABASE "{TEST_DB_NAME}"')
    finally:
        await conn.close()


async def _truncate_all() -> None:
    from app.db.postgres import engine

    async with engine.begin() as conn:
        await conn.execute(
            text(
                "TRUNCATE users, organizations, memberships, workspaces, agents, llm_calls CASCADE"
            )
        )
    # Connections are bound to the event loop that created them; tests use
    # fresh asyncio.run() loops, so never leave pooled connections behind.
    await engine.dispose()


@pytest.fixture(scope="session", autouse=True)
def test_database():
    """Create the test DB and apply the real migrations once per session."""
    asyncio.run(_ensure_database())

    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_tables():
    """Every test starts with empty tables (and leave them empty behind)."""
    asyncio.run(_truncate_all())
    yield
    asyncio.run(_truncate_all())


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
