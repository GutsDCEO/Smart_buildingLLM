"""
Auth Service — Authentication business logic.

Design:
  - SRP: Only handles user lifecycle and token management.
         No HTTP concerns, no streaming, no LLM logic.
  - DIP: Depends on database.get_pool() abstraction, never on raw asyncpg.
  - OCP: New auth providers (OAuth2, LDAP) can extend via new modules
         without modifying this service.
  - OWASP A02: JWT secret from settings, never hardcoded.
  - OWASP A03: Passwords hashed with bcrypt (work factor ≥ 12).
  - OWASP A07: Login returns generic errors — no user enumeration.
  - OWASP A09: Exceptions logged with context, never exposed to client.
"""

from __future__ import annotations

import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt

from auth_models import (
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
    UserRole,
)
from config import settings
from database import get_pool

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Constants — No magic numbers (Quality Rule ④)
# ──────────────────────────────────────────────────────────────

BCRYPT_WORK_FACTOR = 12
REFRESH_TOKEN_BYTES = 32  # 256-bit entropy for refresh tokens

# Generic error message — prevents user enumeration (OWASP A07)
_INVALID_CREDENTIALS_MSG = "Invalid username or password."
_ACCOUNT_DISABLED_MSG = "Account is disabled. Contact an administrator."


# ──────────────────────────────────────────────────────────────
# Password Hashing — bcrypt (OWASP A03)
# ──────────────────────────────────────────────────────────────

def _hash_password(plain_password: str) -> str:
    """Hash a plaintext password using bcrypt with work factor ≥ 12."""
    salt = bcrypt.gensalt(rounds=BCRYPT_WORK_FACTOR)
    return bcrypt.hashpw(plain_password.encode("utf-8"), salt).decode("utf-8")


def _verify_password(plain_password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a bcrypt hash."""
    return bcrypt.checkpw(
        plain_password.encode("utf-8"),
        password_hash.encode("utf-8"),
    )


# ──────────────────────────────────────────────────────────────
# JWT Token Generation — (OWASP A02)
# ──────────────────────────────────────────────────────────────

def _create_access_token(user_id: int, username: str, role: str) -> tuple[str, int]:
    """
    Create a short-lived JWT access token.

    Returns:
        (token_string, expires_in_seconds)
    """
    expires_in = settings.jwt_access_token_expire_minutes * 60
    payload = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(seconds=expires_in),
        "iat": datetime.now(timezone.utc),
        "type": "access",
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def _create_refresh_token() -> str:
    """Generate a cryptographically secure random refresh token."""
    return secrets.token_urlsafe(REFRESH_TOKEN_BYTES)


def _hash_refresh_token(token: str) -> str:
    """Hash a refresh token for safe storage (SHA-256, not reversible)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def decode_access_token(token: str) -> dict:
    """
    Decode and verify a JWT access token.

    Raises:
        jwt.ExpiredSignatureError: Token has expired.
        jwt.InvalidTokenError: Token is invalid or tampered.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )


# ──────────────────────────────────────────────────────────────
# User Registration
# ──────────────────────────────────────────────────────────────

async def register(request: RegisterRequest) -> UserResponse:
    """
    Register a new user.

    First-user-is-admin: if the users table is empty, the first
    registered user receives the 'admin' role automatically.
    All subsequent users get the 'viewer' role.

    Raises:
        ValueError: Username or email already exists.
        RuntimeError: Database unavailable.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database unavailable. Cannot register user.")

    password_hash = _hash_password(request.password)

    try:
        async with pool.acquire() as conn:
            # Determine role: first user = admin, rest = viewer
            user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            role = UserRole.ADMIN.value if user_count == 0 else UserRole.VIEWER.value

            row = await conn.fetchrow(
                """
                INSERT INTO users (username, email, password_hash, role)
                VALUES ($1, $2, $3, $4)
                RETURNING id, username, email, role, is_active, created_at, last_login
                """,
                request.username.strip().lower(),
                request.email.strip().lower(),
                password_hash,
                role,
            )

        logger.info(
            "User registered: '%s' (role=%s, id=%d)",
            row["username"], row["role"], row["id"],
        )

        return UserResponse(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            role=UserRole(row["role"]),
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    except Exception as exc:
        error_msg = str(exc).lower()
        if "unique" in error_msg and "username" in error_msg:
            raise ValueError("Username already taken.") from exc
        if "unique" in error_msg and "email" in error_msg:
            raise ValueError("Email already registered.") from exc
        if "unique" in error_msg:
            raise ValueError("Username or email already exists.") from exc
        logger.error("Registration failed: %s", exc)
        raise RuntimeError("Registration failed. Please try again.") from exc


# ──────────────────────────────────────────────────────────────
# User Authentication (Login)
# ──────────────────────────────────────────────────────────────

async def authenticate(request: LoginRequest) -> TokenResponse:
    """
    Authenticate a user and issue JWT + refresh tokens.

    OWASP A07: Returns generic error message for both wrong username
    and wrong password to prevent user enumeration.

    Raises:
        ValueError: Invalid credentials (generic message).
        RuntimeError: Database unavailable.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database unavailable. Cannot authenticate.")

    try:
        async with pool.acquire() as conn:
            # Fetch user by username (case-insensitive)
            row = await conn.fetchrow(
                "SELECT id, username, email, password_hash, role, is_active FROM users WHERE username = $1",
                request.username.strip().lower(),
            )

            if row is None:
                # OWASP A07: Don't reveal that the user doesn't exist
                logger.warning("Login attempt for non-existent user: '%s'", request.username)
                raise ValueError(_INVALID_CREDENTIALS_MSG)

            if not row["is_active"]:
                logger.warning("Login attempt for disabled user: '%s'", request.username)
                raise ValueError(_ACCOUNT_DISABLED_MSG)

            if not _verify_password(request.password, row["password_hash"]):
                logger.warning("Failed login (wrong password) for user: '%s'", request.username)
                raise ValueError(_INVALID_CREDENTIALS_MSG)

            # Generate tokens
            access_token, expires_in = _create_access_token(
                user_id=row["id"],
                username=row["username"],
                role=row["role"],
            )
            refresh_token = _create_refresh_token()
            refresh_hash = _hash_refresh_token(refresh_token)

            # Store refresh token hash in DB
            refresh_expires = datetime.now(timezone.utc) + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )
            await conn.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                row["id"],
                refresh_hash,
                refresh_expires,
            )

            # Update last_login timestamp
            await conn.execute(
                "UPDATE users SET last_login = $1 WHERE id = $2",
                datetime.now(timezone.utc),
                row["id"],
            )

        logger.info("User authenticated: '%s' (id=%d)", row["username"], row["id"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            expires_in=expires_in,
        )

    except ValueError:
        raise  # Re-raise validation errors (already safe messages)
    except Exception as exc:
        logger.error("Authentication error: %s", exc)
        raise RuntimeError("Authentication failed. Please try again.") from exc


# ──────────────────────────────────────────────────────────────
# Token Refresh
# ──────────────────────────────────────────────────────────────

async def refresh_tokens(request: RefreshRequest) -> TokenResponse:
    """
    Exchange a valid refresh token for new access + refresh tokens.

    Implements refresh token rotation: the old token is revoked
    and a new pair is issued.

    Raises:
        ValueError: Token invalid, expired, or already revoked.
        RuntimeError: Database unavailable.
    """
    pool = get_pool()
    if pool is None:
        raise RuntimeError("Database unavailable.")

    incoming_hash = _hash_refresh_token(request.refresh_token)

    try:
        async with pool.acquire() as conn:
            # Find the refresh token record
            token_row = await conn.fetchrow(
                """
                SELECT rt.id, rt.user_id, rt.expires_at, rt.revoked,
                       u.username, u.role, u.is_active
                FROM refresh_tokens rt
                JOIN users u ON u.id = rt.user_id
                WHERE rt.token_hash = $1
                """,
                incoming_hash,
            )

            if token_row is None:
                raise ValueError("Invalid refresh token.")

            if token_row["revoked"]:
                # Possible token reuse attack — revoke ALL tokens for this user
                await conn.execute(
                    "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1",
                    token_row["user_id"],
                )
                logger.warning(
                    "Refresh token reuse detected for user_id=%d. All tokens revoked.",
                    token_row["user_id"],
                )
                raise ValueError("Refresh token has been revoked. Please log in again.")

            if token_row["expires_at"] < datetime.now(timezone.utc):
                raise ValueError("Refresh token has expired. Please log in again.")

            if not token_row["is_active"]:
                raise ValueError(_ACCOUNT_DISABLED_MSG)

            # Revoke the old refresh token (rotation)
            await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE id = $1",
                token_row["id"],
            )

            # Issue new tokens
            access_token, expires_in = _create_access_token(
                user_id=token_row["user_id"],
                username=token_row["username"],
                role=token_row["role"],
            )
            new_refresh = _create_refresh_token()
            new_refresh_hash = _hash_refresh_token(new_refresh)
            refresh_expires = datetime.now(timezone.utc) + timedelta(
                days=settings.jwt_refresh_token_expire_days
            )

            await conn.execute(
                """
                INSERT INTO refresh_tokens (user_id, token_hash, expires_at)
                VALUES ($1, $2, $3)
                """,
                token_row["user_id"],
                new_refresh_hash,
                refresh_expires,
            )

        logger.info("Token refreshed for user: '%s'", token_row["username"])

        return TokenResponse(
            access_token=access_token,
            refresh_token=new_refresh,
            token_type="bearer",
            expires_in=expires_in,
        )

    except ValueError:
        raise
    except Exception as exc:
        logger.error("Token refresh error: %s", exc)
        raise RuntimeError("Token refresh failed.") from exc


# ──────────────────────────────────────────────────────────────
# Token Revocation (Logout)
# ──────────────────────────────────────────────────────────────

async def revoke_all_tokens(user_id: int) -> int:
    """
    Revoke all refresh tokens for a user (logout everywhere).

    Returns:
        Number of tokens revoked.
    """
    pool = get_pool()
    if pool is None:
        return 0

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = $1 AND revoked = FALSE",
                user_id,
            )
            count = int(result.split()[-1])
            logger.info("Revoked %d refresh tokens for user_id=%d.", count, user_id)
            return count

    except Exception as exc:
        logger.error("Failed to revoke tokens for user_id=%d: %s", user_id, exc)
        return 0


# ──────────────────────────────────────────────────────────────
# Current User Lookup
# ──────────────────────────────────────────────────────────────

async def get_user_by_id(user_id: int) -> Optional[UserResponse]:
    """
    Fetch a user by ID from the database.

    Returns:
        UserResponse or None if not found.
    """
    pool = get_pool()
    if pool is None:
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT id, username, email, role, is_active, created_at, last_login
                FROM users WHERE id = $1
                """,
                user_id,
            )

        if row is None:
            return None

        return UserResponse(
            id=row["id"],
            username=row["username"],
            email=row["email"],
            role=UserRole(row["role"]),
            is_active=row["is_active"],
            created_at=row["created_at"],
            last_login=row["last_login"],
        )

    except Exception as exc:
        logger.error("Failed to fetch user_id=%d: %s", user_id, exc)
        return None


# ──────────────────────────────────────────────────────────────
# Admin User Management
# ──────────────────────────────────────────────────────────────

async def list_users() -> list[UserResponse]:
    """List all users (admin only). No password hashes returned."""
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, username, email, role, is_active, created_at, last_login
                FROM users ORDER BY created_at ASC
                """
            )

        return [
            UserResponse(
                id=row["id"],
                username=row["username"],
                email=row["email"],
                role=UserRole(row["role"]),
                is_active=row["is_active"],
                created_at=row["created_at"],
                last_login=row["last_login"],
            )
            for row in rows
        ]

    except Exception as exc:
        logger.error("Failed to list users: %s", exc)
        return []


async def toggle_user_active(user_id: int, is_active: bool) -> bool:
    """Enable or disable a user account. Returns True on success."""
    pool = get_pool()
    if pool is None:
        return False

    try:
        async with pool.acquire() as conn:
            result = await conn.execute(
                "UPDATE users SET is_active = $1 WHERE id = $2",
                is_active,
                user_id,
            )
            updated = int(result.split()[-1]) > 0
            if updated:
                logger.info("User id=%d active status set to %s.", user_id, is_active)
            return updated

    except Exception as exc:
        logger.error("Failed to toggle user_id=%d: %s", user_id, exc)
        return False
