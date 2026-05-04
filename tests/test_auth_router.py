"""
Tests for auth_router.py — HTTP controller layer (FastAPI endpoints).

Uses TestClient to test the full request/response cycle without
a real server or database. All auth_service calls are mocked.

FIRST Principles:
  - Fast: auth_service mocked via patch — no DB, no real JWTs issued.
  - Independent: Each test patches what it needs; no shared state.
  - Repeatable: Deterministic responses from mocks.
  - Self-Validating: Assert status codes AND response body fields.
  - Timely: Written alongside the router.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

# ── App import ────────────────────────────────────────────────────
# Import the FastAPI app so TestClient can call routes end-to-end
from main import app

# ── Shared test fixtures ──────────────────────────────────────────

def _admin_user():
    """Return a mock admin UserResponse dict."""
    from auth_models import UserResponse, UserRole
    return UserResponse(
        id=1,
        username="admin",
        email="admin@test.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )

def _viewer_user():
    """Return a mock viewer UserResponse dict."""
    from auth_models import UserResponse, UserRole
    return UserResponse(
        id=2,
        username="viewer",
        email="viewer@test.com",
        role=UserRole.VIEWER,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )

def _token_response():
    """Return a mock TokenResponse dict."""
    from auth_models import TokenResponse
    return TokenResponse(
        access_token="mock-access-token",
        refresh_token="mock-refresh-token",
        token_type="bearer",
        expires_in=1800,
    )


# ══════════════════════════════════════════════════════════════
# POST /auth/register
# ══════════════════════════════════════════════════════════════

class TestRegisterEndpoint:
    """Tests for POST /auth/register."""

    def test_register_success_returns_201(self):
        """Should return 201 with user data on successful registration."""
        with patch("auth_service.register", new_callable=AsyncMock, return_value=_admin_user()):
            with TestClient(app) as client:
                res = client.post("/auth/register", json={
                    "username": "admin",
                    "email": "admin@test.com",
                    "password": "SecurePass123!",
                })
        assert res.status_code == 201
        body = res.json()
        assert body["username"] == "admin"
        assert body["role"] == "admin"
        assert "password" not in body  # Never expose password (OWASP A02)

    def test_register_duplicate_username_returns_409(self):
        """Should return 409 Conflict for duplicate username."""
        with patch(
            "auth_service.register",
            new_callable=AsyncMock,
            side_effect=ValueError("Username already taken."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/register", json={
                    "username": "existing",
                    "email": "new@test.com",
                    "password": "SecurePass123!",
                })
        assert res.status_code == 409
        assert "already taken" in res.json()["detail"]

    def test_register_db_unavailable_returns_503(self):
        """Should return 503 when database is down."""
        with patch(
            "auth_service.register",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB down"),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/register", json={
                    "username": "test",
                    "email": "t@t.com",
                    "password": "SecurePass123!",
                })
        assert res.status_code == 503

    def test_register_missing_field_returns_422(self):
        """Should return 422 Unprocessable Entity for missing required field."""
        with TestClient(app) as client:
            res = client.post("/auth/register", json={
                "username": "test",
                # missing email and password
            })
        assert res.status_code == 422

    def test_register_response_has_no_password_hash(self):
        """Password hash must never appear in any response field (OWASP A02)."""
        with patch("auth_service.register", new_callable=AsyncMock, return_value=_viewer_user()):
            with TestClient(app) as client:
                res = client.post("/auth/register", json={
                    "username": "viewer",
                    "email": "v@t.com",
                    "password": "SecurePass123!",
                })
        body = res.json()
        assert "password_hash" not in body
        assert "password" not in body


# ══════════════════════════════════════════════════════════════
# POST /auth/login
# ══════════════════════════════════════════════════════════════

class TestLoginEndpoint:
    """Tests for POST /auth/login."""

    def test_login_success_returns_tokens(self):
        """Should return access_token and refresh_token on success."""
        with patch("auth_service.authenticate", new_callable=AsyncMock, return_value=_token_response()):
            with TestClient(app) as client:
                res = client.post("/auth/login", json={
                    "username": "admin",
                    "password": "correctpass",
                })
        assert res.status_code == 200
        body = res.json()
        assert "access_token" in body
        assert "refresh_token" in body
        assert body["token_type"] == "bearer"
        assert body["expires_in"] == 1800

    def test_login_wrong_password_returns_401(self):
        """Should return 401 for wrong password — generic message (OWASP A07)."""
        with patch(
            "auth_service.authenticate",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid username or password."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/login", json={
                    "username": "admin",
                    "password": "wrongpass",
                })
        assert res.status_code == 401
        # Must be generic — no hint about whether user exists
        assert "Invalid username or password" in res.json()["detail"]

    def test_login_nonexistent_user_same_401(self):
        """Should return same 401 for non-existent user (no enumeration, OWASP A07)."""
        with patch(
            "auth_service.authenticate",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid username or password."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/login", json={
                    "username": "ghost_user_xyz",
                    "password": "anything",
                })
        assert res.status_code == 401
        # EXACT same message as wrong password — no enumeration
        assert res.json()["detail"] == "Invalid username or password."

    def test_login_db_unavailable_returns_503(self):
        """Should return 503 when auth service is unavailable."""
        with patch(
            "auth_service.authenticate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("DB down"),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/login", json={
                    "username": "test",
                    "password": "test",
                })
        assert res.status_code == 503

    def test_login_returns_www_authenticate_header(self):
        """Should include WWW-Authenticate: Bearer on 401 (RFC 6750)."""
        with patch(
            "auth_service.authenticate",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid username or password."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/login", json={
                    "username": "test",
                    "password": "wrong",
                })
        assert res.status_code == 401
        assert "WWW-Authenticate" in res.headers


# ══════════════════════════════════════════════════════════════
# POST /auth/refresh
# ══════════════════════════════════════════════════════════════

class TestRefreshEndpoint:
    """Tests for POST /auth/refresh."""

    def test_refresh_valid_token_returns_new_tokens(self):
        """Should return new token pair for a valid refresh token."""
        with patch("auth_service.refresh_tokens", new_callable=AsyncMock, return_value=_token_response()):
            with TestClient(app) as client:
                res = client.post("/auth/refresh", json={"refresh_token": "valid-token"})
        assert res.status_code == 200
        assert "access_token" in res.json()
        assert "refresh_token" in res.json()

    def test_refresh_invalid_token_returns_401(self):
        """Should return 401 for invalid or expired refresh token."""
        with patch(
            "auth_service.refresh_tokens",
            new_callable=AsyncMock,
            side_effect=ValueError("Invalid refresh token."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/refresh", json={"refresh_token": "bad-token"})
        assert res.status_code == 401

    def test_refresh_revoked_token_returns_401(self):
        """Should return 401 when reusing a revoked token."""
        with patch(
            "auth_service.refresh_tokens",
            new_callable=AsyncMock,
            side_effect=ValueError("Refresh token has been revoked. Please log in again."),
        ):
            with TestClient(app) as client:
                res = client.post("/auth/refresh", json={"refresh_token": "revoked-token"})
        assert res.status_code == 401
        assert "revoked" in res.json()["detail"]


# ══════════════════════════════════════════════════════════════
# GET /auth/me
# ══════════════════════════════════════════════════════════════

class TestMeEndpoint:
    """Tests for GET /auth/me."""

    def test_me_authenticated_returns_user(self):
        """Should return current user profile when authenticated."""
        admin = _admin_user()
        with patch("auth_middleware.get_current_user", return_value=admin):
            with TestClient(app) as client:
                res = client.get(
                    "/auth/me",
                    headers={"Authorization": "Bearer mock-token"},
                )
        assert res.status_code == 200
        assert res.json()["username"] == "admin"

    def test_me_unauthenticated_returns_401(self):
        """Should return 401 when no token is provided."""
        with TestClient(app) as client:
            res = client.get("/auth/me")
        assert res.status_code == 401


# ══════════════════════════════════════════════════════════════
# GET /auth/users (admin only)
# ══════════════════════════════════════════════════════════════

class TestListUsersEndpoint:
    """Tests for GET /auth/users — admin only."""

    def test_admin_can_list_users(self):
        """Admin should receive full user list."""
        admin = _admin_user()
        users = [admin, _viewer_user()]
        with patch("auth_middleware.get_current_user", return_value=admin):
            with patch("auth_service.list_users", new_callable=AsyncMock, return_value=users):
                with TestClient(app) as client:
                    res = client.get(
                        "/auth/users",
                        headers={"Authorization": "Bearer admin-token"},
                    )
        assert res.status_code == 200
        assert len(res.json()) == 2

    def test_viewer_cannot_list_users(self):
        """Viewer should receive 403 Forbidden (OWASP A01)."""
        viewer = _viewer_user()
        with patch("auth_middleware.get_current_user", return_value=viewer):
            with TestClient(app) as client:
                res = client.get(
                    "/auth/users",
                    headers={"Authorization": "Bearer viewer-token"},
                )
        assert res.status_code == 403


# ══════════════════════════════════════════════════════════════
# POST /auth/logout
# ══════════════════════════════════════════════════════════════

class TestLogoutEndpoint:
    """Tests for POST /auth/logout."""

    def test_logout_revokes_tokens(self):
        """Should return success and token count on logout."""
        admin = _admin_user()
        with patch("auth_middleware.get_current_user", return_value=admin):
            with patch("auth_service.revoke_all_tokens", new_callable=AsyncMock, return_value=3):
                with TestClient(app) as client:
                    res = client.post(
                        "/auth/logout",
                        headers={"Authorization": "Bearer mock-token"},
                    )
        assert res.status_code == 200
        body = res.json()
        assert body["status"] == "logged_out"
        assert body["tokens_revoked"] == 3

    def test_logout_unauthenticated_returns_401(self):
        """Should reject logout without a token."""
        with TestClient(app) as client:
            res = client.post("/auth/logout")
        assert res.status_code == 401


# ══════════════════════════════════════════════════════════════
# PATCH /auth/users/{id}/toggle (admin only)
# ══════════════════════════════════════════════════════════════

class TestToggleUserEndpoint:
    """Tests for PATCH /auth/users/{id}/toggle."""

    def test_admin_can_disable_other_user(self):
        """Admin should be able to disable another user."""
        admin = _admin_user()
        with patch("auth_middleware.get_current_user", return_value=admin):
            with patch("auth_service.toggle_user_active", new_callable=AsyncMock, return_value=True):
                with TestClient(app) as client:
                    res = client.patch(
                        "/auth/users/2/toggle?is_active=false",
                        headers={"Authorization": "Bearer admin-token"},
                    )
        assert res.status_code == 200
        assert res.json()["status"] == "disabled"

    def test_admin_cannot_disable_own_account(self):
        """Admin disabling themselves should return 400 (OWASP A01)."""
        admin = _admin_user()  # id=1
        with patch("auth_middleware.get_current_user", return_value=admin):
            with TestClient(app) as client:
                # Target user_id=1 = same as admin.id
                res = client.patch(
                    "/auth/users/1/toggle?is_active=false",
                    headers={"Authorization": "Bearer admin-token"},
                )
        assert res.status_code == 400
        assert "own" in res.json()["detail"].lower()

    def test_toggle_nonexistent_user_returns_404(self):
        """Should return 404 if user_id does not exist."""
        admin = _admin_user()
        with patch("auth_middleware.get_current_user", return_value=admin):
            with patch("auth_service.toggle_user_active", new_callable=AsyncMock, return_value=False):
                with TestClient(app) as client:
                    res = client.patch(
                        "/auth/users/999/toggle?is_active=true",
                        headers={"Authorization": "Bearer admin-token"},
                    )
        assert res.status_code == 404

    def test_viewer_cannot_toggle_users(self):
        """Viewer should receive 403 when attempting to toggle (OWASP A01)."""
        viewer = _viewer_user()
        with patch("auth_middleware.get_current_user", return_value=viewer):
            with TestClient(app) as client:
                res = client.patch(
                    "/auth/users/3/toggle?is_active=false",
                    headers={"Authorization": "Bearer viewer-token"},
                )
        assert res.status_code == 403
