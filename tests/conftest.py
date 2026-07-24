"""
conftest.py — Shared pytest fixtures for the Smart Building AI test suite.

Purpose:
  - Mocks all I/O dependencies (PostgreSQL, Qdrant, LLM client) so unit
    tests never require a running service.
  - Overrides the FastAPI lifespan so TestClient doesn't try to connect
    to real infrastructure during collection or test execution.
  - Provides a UserResponse fixture for auth-protected endpoint tests.

FIRST Principles:
  Fast        — No real network calls; all replaced with AsyncMock / MagicMock.
  Independent — Each test starts with fresh overrides via function-scope fixtures.
  Repeatable  — No external state; always produces the same result.
  Self-Validating — Fixtures fail loudly if patched targets are renamed.
  Timely      — Centralised here so every test file stays focused on logic.
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ─── Stub lifespan — replaces the real one so no DB / Qdrant / LLM needed ───

@asynccontextmanager
async def _stub_lifespan(app):
    """No-op lifespan: skips all real infrastructure setup."""
    import main
    # Populate module-level singletons with safe mocks so endpoints work
    main.llm_client = MagicMock()
    main.guardrail_agent = MagicMock()
    main.router_agent = MagicMock()
    main.qa_agent = MagicMock()
    main.template_service = MagicMock()
    yield


@pytest.fixture(autouse=True, scope="session")
def patch_lifespan():
    """
    Session-scoped: replace the app lifespan once for the whole test run.
    Prevents TestClient from calling connect_db / qdrant / mkdir at startup.
    """
    import main
    original = main.app.router.lifespan_context
    main.app.router.lifespan_context = _stub_lifespan
    yield
    main.app.router.lifespan_context = original


# ─── Auth override — provides a real UserResponse so Depends() works ─────────

@pytest.fixture(autouse=True)
def override_auth():
    """
    Function-scoped: override get_current_user for every test so
    auth-protected endpoints return 200 instead of 401.
    """
    from auth_middleware import get_current_user
    from auth_models import UserResponse, UserRole
    import main

    dummy_user = UserResponse(
        id=1,
        username="testuser",
        email="testuser@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )
    main.app.dependency_overrides[get_current_user] = lambda: dummy_user
    yield
    main.app.dependency_overrides.pop(get_current_user, None)
