"""
Authentication DTOs — Request/Response models for the Auth system.

Design:
  - SRP: Pure data contracts only. Zero business logic (Quality Rule ④).
  - Fail early: Pydantic validates at the boundary (Quality Rule ④).
  - OWASP A03: Input constraints enforced via Field validators.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# Constants — No magic strings (Quality Rule ④)
# ──────────────────────────────────────────────────────────────

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 128
EMAIL_MAX_LENGTH = 255


# ──────────────────────────────────────────────────────────────
# Role Enum
# ──────────────────────────────────────────────────────────────

class UserRole(str, Enum):
    """Supported user roles."""

    ADMIN = "admin"
    VIEWER = "viewer"


# ──────────────────────────────────────────────────────────────
# Registration DTOs
# ──────────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    """Input for user registration."""

    username: str = Field(
        ...,
        min_length=USERNAME_MIN_LENGTH,
        max_length=USERNAME_MAX_LENGTH,
        description="Unique username (3-50 chars)",
    )
    email: str = Field(
        ...,
        max_length=EMAIL_MAX_LENGTH,
        description="Valid email address",
    )
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
        description="Password (8-128 chars)",
    )


# ──────────────────────────────────────────────────────────────
# Login DTOs
# ──────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    """Input for user login."""

    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")


# ──────────────────────────────────────────────────────────────
# Token DTOs
# ──────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    """Returned on successful login or token refresh."""

    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="Opaque refresh token")
    token_type: str = Field(default="bearer", description="Token type (always 'bearer')")
    expires_in: int = Field(..., description="Access token TTL in seconds")


class RefreshRequest(BaseModel):
    """Input for token refresh."""

    refresh_token: str = Field(..., description="The refresh token to exchange")


# ──────────────────────────────────────────────────────────────
# User DTOs
# ──────────────────────────────────────────────────────────────

class UserResponse(BaseModel):
    """Public user information (never includes password hash)."""

    id: int = Field(..., description="User ID")
    username: str = Field(..., description="Username")
    email: str = Field(..., description="Email address")
    role: UserRole = Field(..., description="User role (admin or viewer)")
    is_active: bool = Field(..., description="Whether the account is active")
    created_at: datetime = Field(..., description="Account creation timestamp")
    last_login: Optional[datetime] = Field(
        default=None,
        description="Last successful login timestamp",
    )
