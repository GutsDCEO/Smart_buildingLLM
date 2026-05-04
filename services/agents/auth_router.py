"""
Auth Router — Thin controller for /auth/* endpoints.

Design:
  - SRP: Only handles HTTP concerns (receive request → call service → return response).
         All business logic is in auth_service.py.
  - OWASP A07: Login errors return generic 401, no user enumeration.
  - OWASP A09: Internal errors logged, safe messages returned to client.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status

import auth_service
from auth_middleware import get_current_user, require_admin
from rate_limiter import login_rate_limit
from auth_models import (
    LoginRequest,
    RegisterRequest,
    RefreshRequest,
    TokenResponse,
    UserResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ──────────────────────────────────────────────────────────────
# POST /auth/register — Open registration
# ──────────────────────────────────────────────────────────────

@router.post(
    "/register",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account",
)
async def register(request: RegisterRequest) -> UserResponse:
    """
    Create a new user account.

    First-user-is-admin: the first registered user on a fresh
    deployment automatically receives the 'admin' role.

    Raises:
        409: Username or email already exists.
        503: Database unavailable.
    """
    try:
        return await auth_service.register(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        ) from exc
    except RuntimeError as exc:
        logger.error("Registration service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registration service unavailable. Please try again later.",
        ) from exc


# ──────────────────────────────────────────────────────────────
# POST /auth/login — Authenticate and issue tokens
# ──────────────────────────────────────────────────────────────

@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Login and receive JWT tokens",
)
async def login(
    request: Request,
    body: LoginRequest,
    _: None = Depends(login_rate_limit),
) -> TokenResponse:
    """
    Authenticate with username and password.

    Returns access_token (short-lived JWT) and refresh_token (long-lived).
    Rate limited to 10 attempts per 60 seconds per IP (OWASP A07).

    Raises:
        429: Rate limit exceeded.
        401: Invalid credentials (OWASP A07: generic message).
        503: Database unavailable.
    """
    try:
        return await auth_service.authenticate(body)
    except ValueError as exc:
        # OWASP A07: always return 401, never reveal whether user exists
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except RuntimeError as exc:
        logger.error("Login service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication service unavailable.",
        ) from exc


# ──────────────────────────────────────────────────────────────
# POST /auth/refresh — Token rotation
# ──────────────────────────────────────────────────────────────

@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh expired access token",
)
async def refresh(request: RefreshRequest) -> TokenResponse:
    """
    Exchange a valid refresh token for a new access + refresh token pair.

    The old refresh token is revoked (rotation).

    Raises:
        401: Invalid, expired, or revoked refresh token.
        503: Database unavailable.
    """
    try:
        return await auth_service.refresh_tokens(request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except RuntimeError as exc:
        logger.error("Token refresh service error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Token refresh service unavailable.",
        ) from exc


# ──────────────────────────────────────────────────────────────
# POST /auth/logout — Revoke all refresh tokens
# ──────────────────────────────────────────────────────────────

@router.post(
    "/logout",
    summary="Logout and revoke all refresh tokens",
)
async def logout(
    user: UserResponse = Depends(get_current_user),
) -> dict:
    """
    Revoke all refresh tokens for the current user.

    The access token remains valid until expiry (stateless JWT),
    but no new access tokens can be obtained via refresh.
    """
    count = await auth_service.revoke_all_tokens(user.id)
    return {"status": "logged_out", "tokens_revoked": count}


# ──────────────────────────────────────────────────────────────
# GET /auth/me — Current user info
# ──────────────────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=UserResponse,
    summary="Get current user profile",
)
async def me(
    user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """Return the currently authenticated user's profile."""
    return user


# ──────────────────────────────────────────────────────────────
# GET /auth/users — Admin: list all users
# ──────────────────────────────────────────────────────────────

@router.get(
    "/users",
    response_model=list[UserResponse],
    summary="List all users (admin only)",
)
async def list_users(
    user: UserResponse = Depends(require_admin),
) -> list[UserResponse]:
    """List all registered users. Admin access required."""
    return await auth_service.list_users()


# ──────────────────────────────────────────────────────────────
# PATCH /auth/users/{user_id}/toggle — Admin: enable/disable user
# ──────────────────────────────────────────────────────────────

@router.patch(
    "/users/{user_id}/toggle",
    summary="Enable or disable a user (admin only)",
)
async def toggle_user(
    user_id: int,
    is_active: bool,
    admin: UserResponse = Depends(require_admin),
) -> dict:
    """
    Enable or disable a user account. Admin access required.

    Disabled users cannot log in or refresh tokens.

    Raises:
        404: User not found.
        400: Cannot disable own admin account.
    """
    if user_id == admin.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot disable your own admin account.",
        )

    success = await auth_service.toggle_user_active(user_id, is_active)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found.",
        )

    action = "enabled" if is_active else "disabled"
    return {"status": action, "user_id": user_id}
