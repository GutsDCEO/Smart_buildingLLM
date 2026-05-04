"""
Rate Limiter — In-memory sliding window for auth endpoint protection.

Design:
  - SRP: Only handles rate limiting. No auth or business logic.
  - OWASP A04/A07: Prevents brute-force attacks on /auth/login.
  - OCP: New limiters can be created with different windows/limits
         without modifying this module.

Implementation:
  - Uses a sliding window counter per client IP.
  - Falls back gracefully if headers are missing (never blocks legitimate traffic).
  - No external dependency (Redis) required for single-instance deployment.
    For multi-instance, swap _store for a Redis-backed implementation.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict, deque
from typing import Deque

from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

# ── Constants ─────────────────────────────────────────────────────
# These are intentionally conservative for a local Mac Mini deployment.
# Adjust for production traffic patterns.
LOGIN_MAX_ATTEMPTS: int = 10        # Max attempts per window
LOGIN_WINDOW_SECONDS: int = 60      # Sliding window duration (1 minute)
LOGIN_BLOCK_MESSAGE: str = (
    "Too many login attempts. Please wait before trying again."
)

# ── In-memory store (IP → timestamps of recent attempts) ─────────
# deque(maxlen=LOGIN_MAX_ATTEMPTS) ensures O(1) insertions with
# automatic eviction of the oldest entry when full.
_store: dict[str, Deque[float]] = defaultdict(
    lambda: deque(maxlen=LOGIN_MAX_ATTEMPTS)
)


def _get_client_ip(request: Request) -> str:
    """
    Extract the real client IP from the request.

    Checks X-Forwarded-For first (for reverse proxy / Docker setups),
    falls back to the direct connection IP.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "unknown"


def _is_rate_limited(ip: str) -> bool:
    """
    Sliding window check: return True if the IP has exceeded the limit.

    Evicts timestamps older than LOGIN_WINDOW_SECONDS, then checks
    if the remaining count exceeds LOGIN_MAX_ATTEMPTS.
    """
    now = time.monotonic()
    window_start = now - LOGIN_WINDOW_SECONDS
    timestamps = _store[ip]

    # Evict expired timestamps from the left of the deque
    while timestamps and timestamps[0] < window_start:
        timestamps.popleft()

    return len(timestamps) >= LOGIN_MAX_ATTEMPTS


def _record_attempt(ip: str) -> None:
    """Record a new attempt timestamp for the given IP."""
    _store[ip].append(time.monotonic())


# ── FastAPI Dependency ────────────────────────────────────────────

async def login_rate_limit(request: Request) -> None:
    """
    FastAPI dependency for rate limiting the /auth/login endpoint.

    Usage:
        @router.post("/login")
        async def login(
            request: LoginRequest,
            _: None = Depends(login_rate_limit),
        ):

    Raises:
        HTTPException 429: Too Many Requests when limit is exceeded.
    """
    ip = _get_client_ip(request)

    if _is_rate_limited(ip):
        logger.warning("Rate limit exceeded for IP: %s", ip)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=LOGIN_BLOCK_MESSAGE,
            headers={"Retry-After": str(LOGIN_WINDOW_SECONDS)},
        )

    _record_attempt(ip)
