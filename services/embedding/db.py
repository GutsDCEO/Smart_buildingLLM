"""
PostgreSQL Metadata Logger — logs ingestion events for auditing.

Design:
  - SRP: Only handles metadata logging.
  - Async: Uses asyncpg for non-blocking DB operations.
  - Graceful degradation: If DB is unavailable, logs a warning but
    does NOT block the embedding pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

import asyncpg

from config import settings

logger = logging.getLogger(__name__)

# Module-level connection pool (initialized at startup)
_pool: asyncpg.Pool | None = None

# SQL for creating the metadata table on first run
_CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingestion_log (
    id              SERIAL PRIMARY KEY,
    source_file     TEXT NOT NULL,
    chunk_count     INTEGER NOT NULL,
    vector_ids      TEXT[] NOT NULL,
    ingested_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
"""


async def connect_db() -> None:
    """
    Initialize the connection pool and create the table if needed.

    Call this once at application startup (lifespan event).
    """
    global _pool

    try:
        _pool = await asyncpg.create_pool(
            dsn=settings.postgres_dsn,
            min_size=1,
            max_size=5,
        )

        async with _pool.acquire() as conn:
            await conn.execute(_CREATE_TABLE_SQL)

        logger.info("PostgreSQL connected and ingestion_log table ensured.")

    except (asyncpg.PostgresError, OSError) as exc:
        logger.warning(
            "PostgreSQL unavailable (%s). Metadata logging will be skipped. "
            "The embedding pipeline will continue without audit logging.",
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


async def log_ingestion(
    source_file: str,
    chunk_count: int,
    vector_ids: list[str],
) -> None:
    """
    Log an ingestion batch to PostgreSQL.

    If the DB is unavailable, this logs a warning and returns without
    blocking. The embedding pipeline should not fail because of logging.

    Args:
        source_file: Name of the source document.
        chunk_count: Number of chunks that were embedded.
        vector_ids: List of Qdrant point IDs.
    """
    if _pool is None:
        logger.warning(
            "Skipping metadata log for '%s' — PostgreSQL not connected.",
            source_file,
        )
        return

    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO ingestion_log (source_file, chunk_count, vector_ids, ingested_at)
                VALUES ($1, $2, $3, $4)
                """,
                source_file,
                chunk_count,
                vector_ids,
                datetime.now(timezone.utc),
            )
        logger.info(
            "Logged ingestion: %s (%d chunks) to PostgreSQL.",
            source_file,
            chunk_count,
        )

    except asyncpg.PostgresError as exc:
        # OWASP A09: Log with context, don't expose internals
        logger.error(
            "Failed to log ingestion for '%s': %s",
            source_file,
            exc,
        )
