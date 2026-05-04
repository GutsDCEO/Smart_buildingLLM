"""
Tests for auth_middleware.py — JWT extraction and role enforcement.

Updated for HTTPBearer-based signature (FastAPI security scheme).
All auth_service calls are mocked.

FIRST Principles:
  - Fast: All DB / service calls mocked. No real JWTs validated against DB.
  - Independent: Each test creates its own credentials object.
  - Repeatable: Deterministic JWT secret and payloads.
  - Self-Validating: Clear assert + pytest.raises.
  - Timely: Written alongside the middleware.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import jwt
import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

# ── Deterministic test config ────────────────────────────────────
TEST_JWT_SECRET = "test-secret-key-for-unit-tests-only-64chars-minimum!!!!!!!!!!!"
TEST_JWT_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Override settings for all tests."""
    monkeypatch.setattr("auth_service.settings.jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr("auth_service.settings.jwt_algorithm", TEST_JWT_ALGORITHM)
    monkeypatch.setattr("auth_service.settings.jwt_access_token_expire_minutes", 30)
    monkeypatch.setattr("auth_service.settings.jwt_refresh_token_expire_days", 7)


def _make_valid_token(user_id=1, username="testuser", role="viewer"):
    """Helper: create a valid JWT for testing."""
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


def _make_expired_token():
    """Helper: create an expired JWT."""
    payload = {
        "sub": "1", "username": "test", "role": "viewer",
        "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        "iat": datetime.now(timezone.utc) - timedelta(hours=2),
        "type": "access",
    }
    return jwt.encode(payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)


def _make_credentials(token: str) -> HTTPAuthorizationCredentials:
    """Helper: wrap a token string in HTTPAuthorizationCredentials."""
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def _make_user_response(user_id=1, username="testuser", role="viewer", is_active=True):
    """Helper: create a mock UserResponse."""
    from auth_models import UserResponse, UserRole
    return UserResponse(
        id=user_id,
        username=username,
        email=f"{username}@test.com",
        role=UserRole(role),
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )


# ══════════════════════════════════════════════════════════════
# get_current_user Tests
# ══════════════════════════════════════════════════════════════

class TestGetCurrentUser:
    """Tests for the get_current_user dependency."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Should return UserResponse for a valid JWT."""
        from auth_middleware import get_current_user

        token = _make_valid_token(user_id=1, username="alice", role="viewer")
        user_mock = _make_user_response(user_id=1, username="alice", role="viewer")
        creds = _make_credentials(token)

        with patch("auth_service.get_user_by_id", new_callable=AsyncMock, return_value=user_mock):
            result = await get_current_user(auth=creds)
            assert result.id == 1
            assert result.username == "alice"

    @pytest.mark.asyncio
    async def test_expired_token_raises_401(self):
        """Should reject expired tokens."""
        from auth_middleware import get_current_user

        token = _make_expired_token()
        creds = _make_credentials(token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(auth=creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_signature_raises_401(self):
        """Should reject tokens signed with wrong secret."""
        from auth_middleware import get_current_user

        payload = {
            "sub": "1", "username": "test", "role": "viewer",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        bad_token = jwt.encode(payload, "wrong-secret", algorithm=TEST_JWT_ALGORITHM)
        creds = _make_credentials(bad_token)

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(auth=creds)
        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_user_not_in_db_raises_401(self):
        """Should reject valid JWT if user no longer exists."""
        from auth_middleware import get_current_user

        token = _make_valid_token(user_id=999)
        creds = _make_credentials(token)

        with patch("auth_service.get_user_by_id", new_callable=AsyncMock, return_value=None):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(auth=creds)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_inactive_user_raises_401(self):
        """Should reject valid JWT if user account is disabled."""
        from auth_middleware import get_current_user

        token = _make_valid_token(user_id=1)
        creds = _make_credentials(token)
        inactive_user = _make_user_response(user_id=1, is_active=False)

        with patch("auth_service.get_user_by_id", new_callable=AsyncMock, return_value=inactive_user):
            with pytest.raises(HTTPException) as exc_info:
                await get_current_user(auth=creds)
            assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_garbage_token_raises_401(self):
        """Should reject completely invalid token strings."""
        from auth_middleware import get_current_user

        creds = _make_credentials("not.a.real.jwt.token")

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(auth=creds)
        assert exc_info.value.status_code == 401


# ══════════════════════════════════════════════════════════════
# require_admin Tests
# ══════════════════════════════════════════════════════════════

class TestRequireAdmin:
    """Tests for the require_admin dependency."""

    @pytest.mark.asyncio
    async def test_admin_user_passes(self):
        """Should return user if role is admin."""
        from auth_middleware import require_admin

        admin_user = _make_user_response(user_id=1, role="admin")

        # require_admin now takes UserResponse from get_current_user (via Depends)
        result = await require_admin(user=admin_user)
        assert result.role.value == "admin"

    @pytest.mark.asyncio
    async def test_viewer_user_raises_403(self):
        """Should raise 403 Forbidden if user is not admin."""
        from auth_middleware import require_admin

        viewer_user = _make_user_response(user_id=2, role="viewer")

        with pytest.raises(HTTPException) as exc_info:
            await require_admin(user=viewer_user)
        assert exc_info.value.status_code == 403


# ══════════════════════════════════════════════════════════════
# optional_user Tests
# ══════════════════════════════════════════════════════════════

class TestOptionalUser:
    """Tests for the optional_user dependency."""

    @pytest.mark.asyncio
    async def test_no_token_returns_none(self):
        """Should return None when no credentials provided."""
        from auth_middleware import optional_user
        result = await optional_user(auth=None)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_token_returns_user(self):
        """Should return user when valid token is present."""
        from auth_middleware import optional_user

        token = _make_valid_token(user_id=1)
        creds = _make_credentials(token)
        user_mock = _make_user_response(user_id=1)

        with patch("auth_service.get_user_by_id", new_callable=AsyncMock, return_value=user_mock):
            result = await optional_user(auth=creds)
            assert result is not None
            assert result.id == 1

    @pytest.mark.asyncio
    async def test_invalid_token_returns_none(self):
        """Should return None (not raise) for invalid tokens."""
        from auth_middleware import optional_user
        creds = _make_credentials("invalid-garbage-token")
        result = await optional_user(auth=creds)
        assert result is None
