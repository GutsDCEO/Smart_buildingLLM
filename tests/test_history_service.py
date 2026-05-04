"""
Tests for history_service.py — Chat message persistence with user_id isolation.

Covers:
  - save_message (with and without user_id)
  - get_history (with user isolation, backward compat)
  - clear_history (with user isolation)
  - list_sessions (with user isolation)
  - get_recent_messages

FIRST Principles:
  - Fast: All asyncpg pool calls mocked via AsyncMock.
  - Independent: Each test builds its own mock pool.
  - Repeatable: Fixed datetimes used in mock rows.
  - Self-Validating: Clear asserts on SQL args and return values.
  - Timely: Written alongside the user_id refactor.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest


# ── Pool factory helper ───────────────────────────────────────────

def _make_pool(fetchrow_return=None, fetch_return=None, execute_return=None, fetchval_return=None):
    """Create a mock asyncpg pool with configurable per-method returns."""
    conn = AsyncMock()
    conn.fetchrow = AsyncMock(return_value=fetchrow_return)
    conn.fetch = AsyncMock(return_value=fetch_return or [])
    conn.execute = AsyncMock(return_value=execute_return or "DELETE 0")
    conn.fetchval = AsyncMock(return_value=fetchval_return or 0)

    pool = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


def _make_message_row(msg_id=1, role="user", content="Hello", offset_seconds=0):
    """Create a fake asyncpg message row."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": msg_id,
        "role": role,
        "content": content,
        "created_at": datetime(2025, 1, 1, 12, 0, offset_seconds, tzinfo=timezone.utc),
    }[key]
    return row


def _make_session_row(session_id="sess-1", message_count=4):
    """Create a fake asyncpg session row."""
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "session_id": session_id,
        "last_active": datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        "message_count": message_count,
    }[key]
    return row


# ══════════════════════════════════════════════════════════════
# save_message Tests
# ══════════════════════════════════════════════════════════════

class TestSaveMessage:

    @pytest.mark.asyncio
    async def test_save_with_user_id_returns_message_id(self):
        """Should persist message with user_id and return its DB id."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: 42 if key == "id" else None
        pool, conn = _make_pool(fetchrow_return=mock_row)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import save_message
            result = await save_message("sess-1", "user", "Hello!", user_id=7)

        assert result == 42
        # Verify user_id was passed as 4th positional arg
        args = conn.fetchrow.call_args[0]
        assert args[1] == "sess-1"
        assert args[2] == "user"
        assert args[3] == "Hello!"
        assert args[4] == 7  # user_id

    @pytest.mark.asyncio
    async def test_save_without_user_id_uses_none(self):
        """Should pass None user_id for backward compatibility."""
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, key: 1 if key == "id" else None
        pool, conn = _make_pool(fetchrow_return=mock_row)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import save_message
            result = await save_message("sess-1", "assistant", "Hi!")

        assert result == 1
        args = conn.fetchrow.call_args[0]
        assert args[4] is None  # user_id is None

    @pytest.mark.asyncio
    async def test_save_db_unavailable_returns_none(self):
        """Should return None gracefully when DB pool is None."""
        with patch("history_service.get_pool", return_value=None):
            from history_service import save_message
            result = await save_message("sess-1", "user", "Hello!")
        assert result is None

    @pytest.mark.asyncio
    async def test_save_db_exception_returns_none(self):
        """Should return None and log error on DB exception."""
        pool, conn = _make_pool()
        conn.fetchrow = AsyncMock(side_effect=Exception("DB error"))

        with patch("history_service.get_pool", return_value=pool):
            from history_service import save_message
            result = await save_message("sess-1", "user", "Hello!", user_id=1)

        assert result is None  # No exception bubbles up


# ══════════════════════════════════════════════════════════════
# get_history Tests
# ══════════════════════════════════════════════════════════════

class TestGetHistory:

    @pytest.mark.asyncio
    async def test_get_history_with_user_id_filters_by_user(self):
        """Should include user_id=$2 in the WHERE clause (OWASP A01)."""
        rows = [
            _make_message_row(1, "user", "Hello", 0),
            _make_message_row(2, "assistant", "Hi!", 1),
        ]
        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import get_history
            result = await get_history("sess-1", user_id=5)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "Hello"
        # Verify user_id was passed as second param to scoped query
        call_args = conn.fetch.call_args[0]
        assert 5 in call_args  # user_id=5 in query params

    @pytest.mark.asyncio
    async def test_get_history_without_user_id_backward_compat(self):
        """Should use the non-scoped query when user_id is None."""
        rows = [_make_message_row(1, "user", "Old msg")]
        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import get_history
            result = await get_history("sess-old")

        assert len(result) == 1
        # Verify only session_id and limit were passed (no user_id)
        call_args = conn.fetch.call_args[0]
        assert "sess-old" in call_args
        assert 5 not in call_args  # No user_id in args

    @pytest.mark.asyncio
    async def test_get_history_db_unavailable_returns_empty(self):
        """Should return empty list when DB is unavailable."""
        with patch("history_service.get_pool", return_value=None):
            from history_service import get_history
            result = await get_history("sess-1", user_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_db_exception_returns_empty(self):
        """Should return empty list and not raise on DB exception."""
        pool, conn = _make_pool()
        conn.fetch = AsyncMock(side_effect=Exception("DB error"))

        with patch("history_service.get_pool", return_value=pool):
            from history_service import get_history
            result = await get_history("sess-1", user_id=1)

        assert result == []

    @pytest.mark.asyncio
    async def test_get_history_user_isolation_different_users(self):
        """User A's query must not return User B's messages (OWASP A01)."""
        pool_a, conn_a = _make_pool(fetch_return=[_make_message_row(1, "user", "User A msg")])
        pool_b, conn_b = _make_pool(fetch_return=[])  # User B sees nothing in this session

        from history_service import get_history

        with patch("history_service.get_pool", return_value=pool_a):
            result_a = await get_history("shared-sess", user_id=1)
        with patch("history_service.get_pool", return_value=pool_b):
            result_b = await get_history("shared-sess", user_id=2)

        assert len(result_a) == 1  # User A sees their message
        assert len(result_b) == 0  # User B sees nothing


# ══════════════════════════════════════════════════════════════
# clear_history Tests
# ══════════════════════════════════════════════════════════════

class TestClearHistory:

    @pytest.mark.asyncio
    async def test_clear_with_user_id_uses_scoped_delete(self):
        """Should include user_id in DELETE WHERE clause (OWASP A01)."""
        pool, conn = _make_pool(execute_return="DELETE 3")

        with patch("history_service.get_pool", return_value=pool):
            from history_service import clear_history
            count = await clear_history("sess-1", user_id=7)

        assert count == 3
        # Check that user_id=7 was in the DELETE call
        call_args = conn.execute.call_args[0]
        assert 7 in call_args

    @pytest.mark.asyncio
    async def test_clear_without_user_id_deletes_all_in_session(self):
        """Should delete without user filter when user_id is None."""
        pool, conn = _make_pool(execute_return="DELETE 5")

        with patch("history_service.get_pool", return_value=pool):
            from history_service import clear_history
            count = await clear_history("sess-1")

        assert count == 5
        call_args = conn.execute.call_args[0]
        assert 7 not in call_args  # No user_id in args

    @pytest.mark.asyncio
    async def test_clear_db_unavailable_returns_zero(self):
        """Should return 0 when DB is unavailable."""
        with patch("history_service.get_pool", return_value=None):
            from history_service import clear_history
            count = await clear_history("sess-1", user_id=1)
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_db_exception_returns_zero(self):
        """Should return 0 and not raise on DB exception."""
        pool, conn = _make_pool()
        conn.execute = AsyncMock(side_effect=Exception("DB error"))

        with patch("history_service.get_pool", return_value=pool):
            from history_service import clear_history
            count = await clear_history("sess-1", user_id=1)

        assert count == 0


# ══════════════════════════════════════════════════════════════
# list_sessions Tests
# ══════════════════════════════════════════════════════════════

class TestListSessions:

    @pytest.mark.asyncio
    async def test_list_sessions_with_user_id_filters(self):
        """Should scope sessions to specific user (OWASP A01)."""
        rows = [
            _make_session_row("sess-1", 4),
            _make_session_row("sess-2", 2),
        ]
        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import list_sessions
            result = await list_sessions(user_id=3)

        assert len(result) == 2
        assert result[0]["title"] == "Chat 1"
        assert result[1]["title"] == "Chat 2"
        # Verify user_id=3 was in WHERE clause
        call_args = conn.fetch.call_args[0]
        assert 3 in call_args

    @pytest.mark.asyncio
    async def test_list_sessions_without_user_id_returns_all(self):
        """Should return all sessions when no user_id (admin/backward compat)."""
        rows = [_make_session_row("sess-1", 6)]
        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import list_sessions
            result = await list_sessions()

        assert len(result) == 1
        assert result[0]["session_id"] == "sess-1"
        # No user_id param in the unscoped query
        call_args = conn.fetch.call_args[0]
        assert 3 not in call_args

    @pytest.mark.asyncio
    async def test_list_sessions_db_unavailable_returns_empty(self):
        """Should return empty list when DB is unavailable."""
        with patch("history_service.get_pool", return_value=None):
            from history_service import list_sessions
            result = await list_sessions(user_id=1)
        assert result == []

    @pytest.mark.asyncio
    async def test_list_sessions_auto_numbers_titles(self):
        """Most recent session should be Chat 1."""
        rows = [
            _make_session_row("newest", 4),
            _make_session_row("middle", 2),
            _make_session_row("oldest", 6),
        ]
        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import list_sessions
            result = await list_sessions(user_id=1)

        assert result[0]["title"] == "Chat 1"  # Most recent
        assert result[1]["title"] == "Chat 2"
        assert result[2]["title"] == "Chat 3"


# ══════════════════════════════════════════════════════════════
# get_recent_messages Tests
# ══════════════════════════════════════════════════════════════

class TestGetRecentMessages:

    @pytest.mark.asyncio
    async def test_returns_recent_messages_in_chrono_order(self):
        """Should return messages in chronological order for context injection."""
        rows = []
        for i, (role, content) in enumerate([("user", "First"), ("assistant", "Second")]):
            row = MagicMock()
            row.__getitem__ = lambda self, key, r=role, c=content: {"role": r, "content": c}[key]
            rows.append(row)

        pool, conn = _make_pool(fetch_return=rows)

        with patch("history_service.get_pool", return_value=pool):
            from history_service import get_recent_messages
            result = await get_recent_messages("sess-1", limit=10)

        assert len(result) == 2
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "First"

    @pytest.mark.asyncio
    async def test_returns_empty_when_db_unavailable(self):
        """Should return [] when DB pool is None."""
        with patch("history_service.get_pool", return_value=None):
            from history_service import get_recent_messages
            result = await get_recent_messages("sess-1")
        assert result == []
