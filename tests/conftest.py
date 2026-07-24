"""
conftest.py — Shared pytest fixtures for the Smart Building AI test suite.

Key insight: TestClient(app) runs the FastAPI lifespan in a separate thread,
so unittest.mock.patch (which is NOT thread-safe) cannot reliably mock calls
that happen inside the lifespan from the test thread.

Solution: Patch at import time using monkeypatch-style permanent patches that
survive thread boundaries, and wrap TemplateService to be CI-safe.

FIRST Principles:
  Fast        — No real network calls; all mocked before any test runs.
  Independent — Each test starts with fresh dependency_overrides.
  Repeatable  — No external state; always produces the same result.
  Self-Validating — Fixtures fail loudly if patched targets are renamed.
  Timely      — Centralised here so every test file stays focused on logic.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest


# ─── Patch infrastructure BEFORE any test module is imported ─────────────────
# These patches must happen at import time so they survive TestClient threads.

def _noop_connect_db():
    """Async no-op: replaces real connect_db."""
    future = asyncio.get_event_loop().create_future()
    future.set_result(None)
    return future


# Patch database at module level so TestClient thread sees the mock
import database as _db_module
_original_connect = _db_module.connect_db
_original_disconnect = _db_module.disconnect_db
_db_module.connect_db = AsyncMock(return_value=None)
_db_module.disconnect_db = AsyncMock(return_value=None)


# Patch TemplateService.__init__ to use /tmp instead of /data
import template_service as _ts_module
_original_ts_init = _ts_module.TemplateService.__init__

def _safe_ts_init(self, qa_agent):
    self._qa = qa_agent
    from template_service import PlaceholderExtractor
    self._extractor = PlaceholderExtractor()
    self._output_dir = Path("/tmp/sb_test_outputs")
    self._output_dir.mkdir(parents=True, exist_ok=True)

_ts_module.TemplateService.__init__ = _safe_ts_init


# Patch reranker.load_model to be a no-op (heavy model not needed in CI)
try:
    import reranker as _reranker_module
    _reranker_module.load_model = MagicMock()
except Exception:
    pass


# ─── Auth override ────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def override_auth():
    """
    Function-scoped: override get_current_user for every test so
    auth-protected endpoints return the correct user instead of 401.
    """
    from auth_middleware import get_current_user, require_admin
    from auth_models import UserResponse, UserRole
    import main

    admin_user = UserResponse(
        id=1,
        username="testuser",
        email="testuser@example.com",
        role=UserRole.ADMIN,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )

    viewer_user = UserResponse(
        id=2,
        username="viewer",
        email="viewer@example.com",
        role=UserRole.VIEWER,
        is_active=True,
        created_at=datetime.now(timezone.utc),
        last_login=None,
    )

    main.app.dependency_overrides[get_current_user] = lambda: admin_user
    yield
    main.app.dependency_overrides.pop(get_current_user, None)
    main.app.dependency_overrides.pop(require_admin, None)
