"""
Database Module — Async PostgreSQL connection pool and schema management.

Design:
  - SRP: Only handles database connections and schema. No business logic.
  - DIP: Callers depend on this abstraction, never on raw asyncpg.
  - Graceful degradation: If Postgres is unavailable, logs a warning
    but does NOT block the agent pipeline.
  - OWASP A03: All queries use parameterized statements.
  - OWASP A02: DSN built from env vars, never hardcoded.
"""

from __future__ import annotations

import logging

import asyncpg

from config import settings

logger = logging.getLogger(__name__)

# Module-level connection pool (initialized at startup)
_pool: asyncpg.Pool | None = None

# ──────────────────────────────────────────────────────────────
# Schema Definitions
# ──────────────────────────────────────────────────────────────

_CREATE_DOCUMENTS_TABLE = """
CREATE TABLE IF NOT EXISTS documents (
    id              SERIAL PRIMARY KEY,
    filename        TEXT NOT NULL UNIQUE,
    file_type       TEXT NOT NULL,
    chunk_count     INTEGER NOT NULL DEFAULT 0,
    file_size_bytes INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'active',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""

_CREATE_MESSAGES_TABLE = """
CREATE TABLE IF NOT EXISTS messages (
    id              SERIAL PRIMARY KEY,
    session_id      TEXT NOT NULL,
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_messages_session_id ON messages (session_id);
"""


# ──────────────────────────────────────────────────────────────
# Connection Lifecycle
# ──────────────────────────────────────────────────────────────

async def connect_db() -> None:
    """
    Initialize the connection pool and ensure tables exist.

    Call once at application startup (lifespan event).
    """
    global _pool

    dsn = (
        f"postgresql://{settings.postgres_user}:{settings.postgres_password}"
        f"@{settings.postgres_host}:{settings.postgres_port}"
        f"/{settings.postgres_db}"
    )

    try:
        _pool = await asyncpg.create_pool(dsn=dsn, min_size=1, max_size=5)

        async with _pool.acquire() as conn:
            await conn.execute(_CREATE_DOCUMENTS_TABLE)
            await conn.execute(_CREATE_MESSAGES_TABLE)

        logger.info("PostgreSQL connected. 'documents' and 'messages' tables ensured.")

    except (asyncpg.PostgresError, OSError) as exc:
        logger.warning(
            "PostgreSQL unavailable (%s). Persistence features will be disabled.",
            exc,
        )
        _pool = None


async def disconnect_db() -> None:
    """Close the connection pool. Call at application shutdown."""
    global _pool

    if _pool is not None:
        await _pool.close()
        _pool = None
        logger.info("PostgreSQL connection pool closed.")


def get_pool() -> asyncpg.Pool | None:
    """Return the connection pool (or None if Postgres is unavailable)."""
    return _pool
