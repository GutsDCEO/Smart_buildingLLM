"""
Auth Middleware — FastAPI dependency injection for JWT authentication.

Design:
  - SRP: Only extracts and validates tokens from HTTP headers.
         No user CRUD, no token generation.
  - DIP: Endpoints depend on these abstractions, not on JWT internals.
  - OWASP A01: Role-based access control enforced per-endpoint.
  - OWASP A07: Generic error messages — no information leakage.
  - OWASP A09: Detailed errors logged server-side, safe messages returned.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

import auth_service
from auth_models import UserResponse

logger = logging.getLogger(__name__)

# ── Security Scheme — Triggers the "Authorize" button in Swagger ──
security = HTTPBearer()

# ──────────────────────────────────────────────────────────────
# Constants — Safe error messages (OWASP A09)
# ──────────────────────────────────────────────────────────────

_MISSING_TOKEN_MSG = "Authentication required. Please log in."
_INVALID_TOKEN_MSG = "Invalid or expired token. Please log in again."
_INACTIVE_USER_MSG = "Account is disabled. Contact an administrator."
_INSUFFICIENT_ROLE_MSG = "Insufficient permissions. Admin access required."
_BEARER_PREFIX = "Bearer "


# ──────────────────────────────────────────────────────────────
# Token Extraction Helper
# ──────────────────────────────────────────────────────────────

def _extract_bearer_token(authorization: str) -> str:
    """
    Extract the JWT from a 'Bearer <token>' header value.

    Raises:
        HTTPException 401: If the header format is invalid.
    """
    if not authorization.startswith(_BEARER_PREFIX):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )
    return authorization[len(_BEARER_PREFIX):]


# ──────────────────────────────────────────────────────────────
# Dependencies — Use in endpoint signatures via Depends()
# ──────────────────────────────────────────────────────────────

async def get_current_user(
    auth: HTTPAuthorizationCredentials = Depends(security),
) -> UserResponse:
    """
    FastAPI dependency: extract Bearer token, decode JWT, return user.
    """
    token = auth.credentials

    try:
        payload = auth_service.decode_access_token(token)
    except Exception as exc:
        logger.debug("JWT decode failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    user_id = int(payload.get("sub", 0))
    if user_id == 0:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify user still exists and is active in DB
    user = await auth_service.get_user_by_id(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INVALID_TOKEN_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=_INACTIVE_USER_MSG,
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def require_admin(
    user: UserResponse = Depends(get_current_user),
) -> UserResponse:
    """
    FastAPI dependency: same as get_current_user, but requires admin role.
    """
    if user.role.value != "admin":
        logger.warning(
            "Non-admin user '%s' (id=%d) attempted admin action.",
            user.username, user.id,
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=_INSUFFICIENT_ROLE_MSG,
        )

    return user


async def optional_user(
    auth: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[UserResponse]:
    """
    FastAPI dependency: returns user if token is present, None otherwise.
    """
    if auth is None:
        return None

    try:
        payload = auth_service.decode_access_token(auth.credentials)
        user = await auth_service.get_user_by_id(int(payload.get("sub", 0)))
        return user if user and user.is_active else None
    except Exception:
        return None
