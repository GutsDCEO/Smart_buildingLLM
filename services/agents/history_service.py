"""
History Service — Chat message persistence for conversation replay.

Design:
  - SRP: Only handles message CRUD. No streaming or LLM logic.
  - DIP: Depends on database.get_pool() abstraction.
  - OWASP A03: All queries use parameterized statements.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from database import get_pool

logger = logging.getLogger(__name__)


async def save_message(
    session_id: str,
    role: str,
    content: str,
) -> Optional[int]:
    """
    Persist a single chat message to PostgreSQL.

    Args:
        session_id: Client-generated session identifier.
        role: Either 'user' or 'assistant'.
        content: The message text.

    Returns:
        The message ID, or None if the database is unavailable.
    """
    pool = get_pool()
    if pool is None:
        logger.debug("DB unavailable — skipping message save.")
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO messages (session_id, role, content, created_at)
                VALUES ($1, $2, $3, $4)
                RETURNING id
                """,
                session_id,
                role,
                content,
                datetime.now(timezone.utc),
            )
            return row["id"]

    except Exception as exc:
        logger.error("Failed to save message: %s", exc)
        return None


async def get_history(session_id: str, limit: int = 50) -> list[dict]:
    """
    Retrieve chat history for a session, ordered chronologically.

    Args:
        session_id: The session to retrieve messages for.
        limit: Maximum number of messages to return.

    Returns:
        A list of message dicts with id, role, content, created_at.
    """
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, role, content, created_at
                FROM messages
                WHERE session_id = $1
                ORDER BY created_at ASC
                LIMIT $2
                """,
                session_id,
                limit,
            )

        return [
            {
                "id": row["id"],
                "role": row["role"],
                "content": row["content"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    except Exception as exc:
        logger.error("Failed to fetch history for session '%s': %s", session_id, exc)
        return []


async def clear_history(session_id: str) -> int:
    """
    Delete all messages for a given session.

    Returns:
        Number of messages deleted.
    """
    pool = get_pool()
    if pool is None:
        return 0

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "DELETE FROM messages WHERE session_id = $1",
                session_id,
            )
            count = int(result.split()[-1])
            logger.info("Cleared %d messages for session '%s'.", count, session_id)
            return count

    except Exception as exc:
        logger.error("Failed to clear history for session '%s': %s", session_id, exc)
        return 0
