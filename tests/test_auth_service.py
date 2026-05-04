"""
Tests for auth_service.py — Core authentication business logic.

FIRST Principles:
  - Fast: All DB calls mocked via AsyncMock. No real connections.
  - Independent: Each test creates its own fixtures in setup_method.
  - Repeatable: Deterministic JWT secret and timestamps.
  - Self-Validating: Clear assert statements, no manual inspection.
  - Timely: Written alongside the feature (TDD).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import bcrypt
import jwt
import pytest

# ── Deterministic test config ────────────────────────────────────
TEST_JWT_SECRET = "test-secret-key-for-unit-tests-only-64chars-minimum!!!!!!!!!!!"
TEST_JWT_ALGORITHM = "HS256"
TEST_ACCESS_EXPIRE_MINUTES = 30
TEST_REFRESH_EXPIRE_DAYS = 7


@pytest.fixture(autouse=True)
def mock_settings(monkeypatch):
    """Override settings for all tests — no real env vars needed."""
    monkeypatch.setattr("auth_service.settings.jwt_secret_key", TEST_JWT_SECRET)
    monkeypatch.setattr("auth_service.settings.jwt_algorithm", TEST_JWT_ALGORITHM)
    monkeypatch.setattr("auth_service.settings.jwt_access_token_expire_minutes", TEST_ACCESS_EXPIRE_MINUTES)
    monkeypatch.setattr("auth_service.settings.jwt_refresh_token_expire_days", TEST_REFRESH_EXPIRE_DAYS)


# ══════════════════════════════════════════════════════════════
# Password Hashing Tests
# ══════════════════════════════════════════════════════════════

class TestPasswordHashing:
    """Tests for bcrypt password hashing functions."""

    def test_hash_password_returns_bcrypt_hash(self):
        """Should return a valid bcrypt hash, not the plaintext password."""
        from auth_service import _hash_password
        result = _hash_password("mypassword123")
        assert result != "mypassword123"
        assert result.startswith("$2b$")

    def test_verify_password_correct(self):
        """Should return True for matching password + hash."""
        from auth_service import _hash_password, _verify_password
        hashed = _hash_password("correctpassword")
        assert _verify_password("correctpassword", hashed) is True

    def test_verify_password_incorrect(self):
        """Should return False for wrong password."""
        from auth_service import _hash_password, _verify_password
        hashed = _hash_password("correctpassword")
        assert _verify_password("wrongpassword", hashed) is False

    def test_hash_uses_sufficient_work_factor(self):
        """Should use bcrypt work factor >= 12 (OWASP A03)."""
        from auth_service import _hash_password, BCRYPT_WORK_FACTOR
        assert BCRYPT_WORK_FACTOR >= 12
        hashed = _hash_password("test")
        # bcrypt format: $2b$<rounds>$<salt+hash>
        rounds = int(hashed.split("$")[2])
        assert rounds >= 12


# ══════════════════════════════════════════════════════════════
# JWT Token Tests
# ══════════════════════════════════════════════════════════════

class TestJWTTokens:
    """Tests for JWT creation and decoding."""

    def test_create_access_token_valid(self):
        """Should create a decodable JWT with correct claims."""
        from auth_service import _create_access_token
        token, expires_in = _create_access_token(
            user_id=1, username="testuser", role="admin",
        )
        assert expires_in == TEST_ACCESS_EXPIRE_MINUTES * 60

        payload = jwt.decode(token, TEST_JWT_SECRET, algorithms=[TEST_JWT_ALGORITHM])
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
        assert payload["role"] == "admin"
        assert payload["type"] == "access"

    def test_decode_access_token_valid(self):
        """Should decode a valid token without errors."""
        from auth_service import _create_access_token, decode_access_token
        token, _ = _create_access_token(user_id=42, username="alice", role="viewer")
        payload = decode_access_token(token)
        assert payload["sub"] == "42"
        assert payload["username"] == "alice"

    def test_decode_access_token_expired(self):
        """Should raise ExpiredSignatureError for expired token."""
        from auth_service import decode_access_token
        expired_payload = {
            "sub": "1",
            "username": "test",
            "role": "viewer",
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "type": "access",
        }
        token = jwt.encode(expired_payload, TEST_JWT_SECRET, algorithm=TEST_JWT_ALGORITHM)
        with pytest.raises(jwt.ExpiredSignatureError):
            decode_access_token(token)

    def test_decode_access_token_invalid_secret(self):
        """Should raise InvalidSignatureError for wrong secret."""
        from auth_service import decode_access_token
        payload = {
            "sub": "1", "username": "test", "role": "viewer",
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
            "type": "access",
        }
        token = jwt.encode(payload, "wrong-secret", algorithm=TEST_JWT_ALGORITHM)
        with pytest.raises(jwt.InvalidSignatureError):
            decode_access_token(token)

    def test_create_refresh_token_is_random(self):
        """Should generate unique tokens each call."""
        from auth_service import _create_refresh_token
        t1 = _create_refresh_token()
        t2 = _create_refresh_token()
        assert t1 != t2
        assert len(t1) > 20  # Minimum entropy check

    def test_hash_refresh_token_deterministic(self):
        """Should produce the same SHA-256 hash for the same input."""
        from auth_service import _hash_refresh_token
        h1 = _hash_refresh_token("test-token")
        h2 = _hash_refresh_token("test-token")
        assert h1 == h2
        assert h1 == hashlib.sha256(b"test-token").hexdigest()


# ══════════════════════════════════════════════════════════════
# Registration Tests
# ══════════════════════════════════════════════════════════════

class TestRegister:
    """Tests for user registration."""

    def _mock_pool(self, user_count=0, returned_row=None):
        """Create a mock asyncpg pool with configurable behavior."""
        conn = AsyncMock()
        conn.fetchval = AsyncMock(return_value=user_count)
        conn.fetchrow = AsyncMock(return_value=returned_row or {
            "id": 1,
            "username": "testuser",
            "email": "test@example.com",
            "role": "admin" if user_count == 0 else "viewer",
            "is_active": True,
            "created_at": datetime.now(timezone.utc),
            "last_login": None,
        })
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return pool, conn

    @pytest.mark.asyncio
    async def test_first_user_gets_admin_role(self):
        """Should assign 'admin' role to the first registered user."""
        from auth_service import register
        from auth_models import RegisterRequest

        pool, conn = self._mock_pool(user_count=0)
        with patch("auth_service.get_pool", return_value=pool):
            request = RegisterRequest(
                username="admin1", email="admin@test.com", password="securepass123",
            )
            result = await register(request)
            assert result.role.value == "admin"

    @pytest.mark.asyncio
    async def test_second_user_gets_viewer_role(self):
        """Should assign 'viewer' role to all users after the first."""
        from auth_service import register
        from auth_models import RegisterRequest

        pool, conn = self._mock_pool(user_count=1)
        conn.fetchrow = AsyncMock(return_value={
            "id": 2, "username": "viewer1", "email": "viewer@test.com",
            "role": "viewer", "is_active": True,
            "created_at": datetime.now(timezone.utc), "last_login": None,
        })
        with patch("auth_service.get_pool", return_value=pool):
            request = RegisterRequest(
                username="viewer1", email="viewer@test.com", password="securepass123",
            )
            result = await register(request)
            assert result.role.value == "viewer"

    @pytest.mark.asyncio
    async def test_register_duplicate_username_raises_value_error(self):
        """Should raise ValueError when username is already taken."""
        from auth_service import register
        from auth_models import RegisterRequest

        pool, conn = self._mock_pool(user_count=1)
        conn.fetchrow = AsyncMock(
            side_effect=Exception("duplicate key value violates unique constraint \"users_username_key\"")
        )
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Username already taken"):
                await register(RegisterRequest(
                    username="existing", email="new@test.com", password="securepass123",
                ))

    @pytest.mark.asyncio
    async def test_register_duplicate_email_raises_value_error(self):
        """Should raise ValueError when email is already registered."""
        from auth_service import register
        from auth_models import RegisterRequest

        pool, conn = self._mock_pool(user_count=1)
        conn.fetchrow = AsyncMock(
            side_effect=Exception("duplicate key value violates unique constraint \"users_email_key\"")
        )
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Email already registered"):
                await register(RegisterRequest(
                    username="newuser", email="existing@test.com", password="securepass123",
                ))

    @pytest.mark.asyncio
    async def test_register_db_unavailable_raises_runtime_error(self):
        """Should raise RuntimeError when DB pool is None."""
        from auth_service import register
        from auth_models import RegisterRequest

        with patch("auth_service.get_pool", return_value=None):
            with pytest.raises(RuntimeError, match="Database unavailable"):
                await register(RegisterRequest(
                    username="test", email="t@t.com", password="securepass123",
                ))

    @pytest.mark.asyncio
    async def test_password_never_stored_plaintext(self):
        """Should hash the password before inserting (OWASP A03)."""
        from auth_service import register
        from auth_models import RegisterRequest

        pool, conn = self._mock_pool(user_count=0)
        with patch("auth_service.get_pool", return_value=pool):
            await register(RegisterRequest(
                username="test", email="t@t.com", password="mysecretpass",
            ))
            # Check the INSERT call's 3rd argument (password_hash)
            insert_call = conn.fetchrow.call_args
            stored_hash = insert_call[0][3]  # 4th positional arg
            assert stored_hash != "mysecretpass"
            assert stored_hash.startswith("$2b$")


# ══════════════════════════════════════════════════════════════
# Authentication (Login) Tests
# ══════════════════════════════════════════════════════════════

class TestAuthenticate:
    """Tests for user login."""

    def _make_user_row(self, password="correctpass", is_active=True):
        """Create a fake DB user row with a bcrypt hash."""
        salt = bcrypt.gensalt(rounds=4)  # Low rounds for test speed
        pw_hash = bcrypt.hashpw(password.encode(), salt).decode()
        return {
            "id": 1, "username": "testuser", "email": "t@t.com",
            "password_hash": pw_hash, "role": "admin", "is_active": is_active,
        }

    def _mock_auth_pool(self, user_row=None):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=user_row)
        conn.execute = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return pool

    @pytest.mark.asyncio
    async def test_login_success(self):
        """Should return tokens on correct credentials."""
        from auth_service import authenticate
        from auth_models import LoginRequest

        row = self._make_user_row(password="correctpass")
        pool = self._mock_auth_pool(user_row=row)
        with patch("auth_service.get_pool", return_value=pool):
            result = await authenticate(LoginRequest(username="testuser", password="correctpass"))
            assert result.access_token
            assert result.refresh_token
            assert result.token_type == "bearer"
            assert result.expires_in == TEST_ACCESS_EXPIRE_MINUTES * 60

    @pytest.mark.asyncio
    async def test_login_wrong_password_generic_error(self):
        """Should return generic error for wrong password (OWASP A07)."""
        from auth_service import authenticate
        from auth_models import LoginRequest

        row = self._make_user_row(password="correctpass")
        pool = self._mock_auth_pool(user_row=row)
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Invalid username or password"):
                await authenticate(LoginRequest(username="testuser", password="wrongpass"))

    @pytest.mark.asyncio
    async def test_login_nonexistent_user_same_generic_error(self):
        """Should return SAME generic error for non-existent user (no enumeration)."""
        from auth_service import authenticate
        from auth_models import LoginRequest

        pool = self._mock_auth_pool(user_row=None)  # No user found
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Invalid username or password"):
                await authenticate(LoginRequest(username="ghost", password="anything"))

    @pytest.mark.asyncio
    async def test_login_disabled_account(self):
        """Should reject login for disabled accounts."""
        from auth_service import authenticate
        from auth_models import LoginRequest

        row = self._make_user_row(password="correctpass", is_active=False)
        pool = self._mock_auth_pool(user_row=row)
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Account is disabled"):
                await authenticate(LoginRequest(username="testuser", password="correctpass"))

    @pytest.mark.asyncio
    async def test_login_db_unavailable(self):
        """Should raise RuntimeError when DB is down."""
        from auth_service import authenticate
        from auth_models import LoginRequest

        with patch("auth_service.get_pool", return_value=None):
            with pytest.raises(RuntimeError, match="Database unavailable"):
                await authenticate(LoginRequest(username="test", password="test"))


# ══════════════════════════════════════════════════════════════
# Token Refresh Tests
# ══════════════════════════════════════════════════════════════

class TestRefreshTokens:
    """Tests for token rotation."""

    def _mock_refresh_pool(self, token_row=None):
        conn = AsyncMock()
        conn.fetchrow = AsyncMock(return_value=token_row)
        conn.execute = AsyncMock()
        pool = MagicMock()
        pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
        pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
        return pool, conn

    @pytest.mark.asyncio
    async def test_refresh_valid_token(self):
        """Should issue new tokens and revoke old one."""
        from auth_service import refresh_tokens, _hash_refresh_token
        from auth_models import RefreshRequest

        token_row = {
            "id": 1, "user_id": 1,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "revoked": False,
            "username": "testuser", "role": "admin", "is_active": True,
        }
        pool, conn = self._mock_refresh_pool(token_row=token_row)
        with patch("auth_service.get_pool", return_value=pool):
            result = await refresh_tokens(RefreshRequest(refresh_token="valid-token"))
            assert result.access_token
            assert result.refresh_token
            # Old token should be revoked
            conn.execute.assert_any_call(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE id = $1", 1
            )

    @pytest.mark.asyncio
    async def test_refresh_revoked_token_revokes_all(self):
        """Should revoke ALL tokens for user on reuse detection."""
        from auth_service import refresh_tokens
        from auth_models import RefreshRequest

        token_row = {
            "id": 1, "user_id": 1,
            "expires_at": datetime.now(timezone.utc) + timedelta(days=7),
            "revoked": True,  # Already revoked = reuse attack
            "username": "testuser", "role": "admin", "is_active": True,
        }
        pool, conn = self._mock_refresh_pool(token_row=token_row)
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="revoked"):
                await refresh_tokens(RefreshRequest(refresh_token="reused-token"))
            # Should revoke ALL tokens for this user
            conn.execute.assert_called_with(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1", 1
            )

    @pytest.mark.asyncio
    async def test_refresh_expired_token(self):
        """Should reject expired refresh tokens."""
        from auth_service import refresh_tokens
        from auth_models import RefreshRequest

        token_row = {
            "id": 1, "user_id": 1,
            "expires_at": datetime.now(timezone.utc) - timedelta(days=1),  # Expired
            "revoked": False,
            "username": "testuser", "role": "admin", "is_active": True,
        }
        pool, _ = self._mock_refresh_pool(token_row=token_row)
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="expired"):
                await refresh_tokens(RefreshRequest(refresh_token="expired-token"))

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self):
        """Should reject tokens not found in DB."""
        from auth_service import refresh_tokens
        from auth_models import RefreshRequest

        pool, _ = self._mock_refresh_pool(token_row=None)
        with patch("auth_service.get_pool", return_value=pool):
            with pytest.raises(ValueError, match="Invalid refresh token"):
                await refresh_tokens(RefreshRequest(refresh_token="nonexistent"))
