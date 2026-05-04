"""
History Service — Chat message persistence for conversation replay.

Design:
  - SRP: Only handles message CRUD. No streaming or LLM logic.
  - DIP: Depends on database.get_pool() abstraction.
  - OWASP A01: Session isolation — users can only see their own messages.
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
    user_id: Optional[int] = None,
) -> Optional[int]:
    """
    Persist a single chat message to PostgreSQL.

    Args:
        session_id: Client-generated session identifier.
        role: Either 'user' or 'assistant'.
        content: The message text.
        user_id: The authenticated user's ID (for session isolation).

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
                INSERT INTO messages (session_id, role, content, user_id, created_at)
                VALUES ($1, $2, $3, $4, $5)
                RETURNING id
                """,
                session_id,
                role,
                content,
                user_id,
                datetime.now(timezone.utc),
            )
            return row["id"]

    except Exception as exc:
        logger.error("Failed to save message: %s", exc)
        return None


async def get_history(
    session_id: str,
    limit: int = 50,
    user_id: Optional[int] = None,
) -> list[dict]:
    """
    Retrieve chat history for a session, ordered chronologically.

    Args:
        session_id: The session to retrieve messages for.
        limit: Maximum number of messages to return.
        user_id: If provided, only return messages belonging to this user
                 (OWASP A01: session isolation).

    Returns:
        A list of message dicts with id, role, content, created_at.
    """
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            if user_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT id, role, content, created_at
                    FROM messages
                    WHERE session_id = $1 AND user_id = $2
                    ORDER BY created_at ASC
                    LIMIT $3
                    """,
                    session_id,
                    user_id,
                    limit,
                )
            else:
                # Backward compatibility: if no user_id, return all messages
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


async def clear_history(
    session_id: str,
    user_id: Optional[int] = None,
) -> int:
    """
    Delete all messages for a given session.

    Args:
        session_id: The session to clear.
        user_id: If provided, only delete messages belonging to this user
                 (OWASP A01: prevents cross-user deletion).

    Returns:
        Number of messages deleted.
    """
    pool = get_pool()
    if pool is None:
        return 0

    try:
        async with pool.acquire() as conn:
            if user_id is not None:
                result = await conn.execute(
                    "DELETE FROM messages WHERE session_id = $1 AND user_id = $2",
                    session_id,
                    user_id,
                )
            else:
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


async def get_recent_messages(session_id: str, limit: int = 10) -> list[dict]:
    """
    Retrieve the most recent messages for conversation memory.

    Returns the last `limit` messages in chronological order, suitable
    for injecting into the QA agent prompt as conversation history.

    Args:
        session_id: The session to retrieve messages for.
        limit: Maximum number of messages to return.

    Returns:
        A list of message dicts with role and content.
    """
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT role, content FROM (
                    SELECT role, content, created_at
                    FROM messages
                    WHERE session_id = $1
                    ORDER BY created_at DESC
                    LIMIT $2
                ) sub
                ORDER BY created_at ASC
                """,
                session_id,
                limit,
            )

        return [
            {"role": row["role"], "content": row["content"]}
            for row in rows
        ]

    except Exception as exc:
        logger.error("Failed to fetch recent messages for '%s': %s", session_id, exc)
        return []


async def list_sessions(user_id: Optional[int] = None) -> list[dict]:
    """
    List distinct chat sessions with auto-numbered titles and last activity.

    Args:
        user_id: If provided, only return sessions belonging to this user
                 (OWASP A01: session isolation).

    Sessions are ordered by last activity (most recent first).
    Title is auto-generated as 'Chat N' where N is the reverse chronological
    order index.

    Returns:
        A list of session dicts: {session_id, title, last_active, message_count}
    """
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            if user_id is not None:
                rows = await conn.fetch(
                    """
                    SELECT
                        session_id,
                        MAX(created_at) AS last_active,
                        COUNT(*) AS message_count
                    FROM messages
                    WHERE user_id = $1
                    GROUP BY session_id
                    ORDER BY MAX(created_at) DESC
                    """,
                    user_id,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT
                        session_id,
                        MAX(created_at) AS last_active,
                        COUNT(*) AS message_count
                    FROM messages
                    GROUP BY session_id
                    ORDER BY MAX(created_at) DESC
                    """
                )

        # Auto-number sessions: most recent = Chat 1, second = Chat 2, etc.
        return [
            {
                "session_id": row["session_id"],
                "title": f"Chat {i + 1}",
                "last_active": row["last_active"].isoformat(),
                "message_count": row["message_count"],
            }
            for i, row in enumerate(rows)
        ]

    except Exception as exc:
        logger.error("Failed to list sessions: %s", exc)
        return []
