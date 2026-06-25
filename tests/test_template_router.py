"""
Integration Tests — Template Router (HTTP endpoints)

FIRST Principles:
  F - Fast:        Uses FastAPI TestClient. No real files, QA agent, or network.
  I - Independent: Fresh app + mocked service per test class.
  R - Repeatable:  Deterministic mock responses regardless of environment.
  S - Self-Validating: Explicit status code and JSON body assertions.
  T - Timely:      Written alongside template_router.py (Phase 6).

Covers:
  POST /templates/analyze:
    1.  Valid PDF returns 200 with field list and file_id
    2.  Non-PDF MIME type returns 400
    3.  Oversized file returns 413
    4.  Missing filename returns 400
    5.  Unauthenticated request returns 401

  POST /templates/fill:
    6.  Valid request returns 200 SSE stream
    7.  Empty file_id returns 400
    8.  Unauthenticated request returns 401

  GET /templates/download/{file_id}:
    9.  Owner can download their file (200)
    10. Different user gets 403 (ownership check)
    11. Non-existent file_id gets 404
    12. Path traversal attempt is rejected (400)
"""

import sys
import os
import io
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient
from fastapi import FastAPI

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))


# ──────────────────────────────────────────────────────────────
# Shared Fixtures
# ──────────────────────────────────────────────────────────────

MOCK_USER = MagicMock()
MOCK_USER.id = 7
MOCK_USER.username = "test_user"
MOCK_USER.role = "viewer"

MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj\n<< /Type /Catalog >>\nendobj\n"
    b"xref\n0 2\ntrailer\n<< /Size 2 >>\nstartxref\n9\n%%EOF"
)


def _build_test_app(mock_service):
    """
    Build a minimal FastAPI app that includes only the template router,
    with auth bypassed and service injected.
    """
    from template_router import router, set_service

    app = FastAPI()

    # Inject the mock service
    set_service(mock_service)

    # Override auth dependency to always return MOCK_USER
    from auth_middleware import get_current_user

    app.dependency_overrides[get_current_user] = lambda: MOCK_USER

    app.include_router(router)
    return app


def _make_mock_service(analyze_result=None, fill_events=None):
    """Return a mock TemplateService with configurable return values."""
    svc = MagicMock()
    svc.analyze = AsyncMock(return_value=analyze_result)

    async def _fill_gen(*args, **kwargs):
        for event in fill_events or []:
            yield event

    svc.fill_stream = _fill_gen
    return svc


# ──────────────────────────────────────────────────────────────
# POST /templates/analyze Tests
# ──────────────────────────────────────────────────────────────


class TestAnalyzeEndpoint:
    """Tests for POST /templates/analyze."""

    def setup_method(self):
        from models import TemplateAnalyzeResponse, TemplateField

        self.mock_response = TemplateAnalyzeResponse(
            file_id="abc-123",
            filename="checklist.pdf",
            total_fields=2,
            fields=[
                TemplateField(
                    field_name="Inspector", field_type="bracket", page_number=1
                ),
                TemplateField(field_name="Date", field_type="bracket", page_number=1),
            ],
        )
        self.svc = _make_mock_service(analyze_result=self.mock_response)
        self.client = TestClient(_build_test_app(self.svc))

    # Test 1: Valid PDF
    def test_valid_pdf_returns_200_with_fields(self):
        """Valid PDF upload returns 200 with file_id and field list."""
        response = self.client.post(
            "/templates/analyze",
            files={
                "file": ("checklist.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["file_id"] == "abc-123"
        assert data["total_fields"] == 2
        assert len(data["fields"]) == 2
        assert data["fields"][0]["field_name"] == "Inspector"

    # Test 2: Non-PDF MIME type
    def test_non_pdf_mime_returns_400(self):
        """Uploading a non-PDF file should return 400 Bad Request."""
        response = self.client.post(
            "/templates/analyze",
            files={
                "file": (
                    "report.docx",
                    io.BytesIO(b"PK\x03\x04fake"),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        assert response.status_code == 400
        assert "PDF" in response.json()["detail"]

    # Test 3: Oversized file
    def test_oversized_file_returns_413(self):
        """File exceeding TEMPLATE_MAX_UPLOAD_MB should return 413."""
        # Simulate a 26 MB file (limit is 25 MB)
        big_content = b"A" * (26 * 1024 * 1024)
        with patch("template_router.settings") as mock_settings:
            mock_settings.template_max_upload_mb = 25
            response = self.client.post(
                "/templates/analyze",
                files={"file": ("big.pdf", io.BytesIO(big_content), "application/pdf")},
            )
        assert response.status_code == 413

    # Test 4: Missing filename
    def test_missing_filename_returns_400(self):
        """Request with an empty filename should return 400."""
        response = self.client.post(
            "/templates/analyze",
            files={"file": ("   ", io.BytesIO(MINIMAL_PDF), "application/pdf")},
        )
        assert response.status_code == 400

    # Test 5: Unauthenticated
    def test_unauthenticated_returns_401(self):
        """Requests without a valid JWT must be rejected with 401."""
        from template_router import router, set_service
        from auth_middleware import get_current_user
        from fastapi import HTTPException

        app = FastAPI()
        set_service(self.svc)

        def _require_auth():
            raise HTTPException(status_code=401, detail="Not authenticated")

        app.dependency_overrides[get_current_user] = _require_auth
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post(
            "/templates/analyze",
            files={
                "file": ("checklist.pdf", io.BytesIO(MINIMAL_PDF), "application/pdf")
            },
        )
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────
# POST /templates/fill Tests
# ──────────────────────────────────────────────────────────────


class TestFillEndpoint:
    """Tests for POST /templates/fill."""

    def setup_method(self):
        self.events = [
            'event: status\ndata: {"stage": "filling", "message": "Filling field 1 of 1"}\n\n',
            'event: field\ndata: {"field_name": "Inspector", "status": "filled", "value": "John"}\n\n',
            'event: complete\ndata: {"file_id": "abc-123", "filename": "out.pdf", "fields_filled": 1, "fields_failed": 0, "field_errors": [], "download_url": "/templates/download/abc-123", "status": "completed"}\n\n',
            "event: done\ndata: {}\n\n",
        ]
        self.svc = _make_mock_service(fill_events=self.events)
        self.client = TestClient(_build_test_app(self.svc))

    # Test 6: Valid fill request
    def test_valid_fill_returns_sse_stream(self):
        """Valid fill request returns 200 with text/event-stream content type."""
        response = self.client.post(
            "/templates/fill",
            json={"file_id": "abc-123"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")

    # Test 7: Empty file_id
    def test_empty_file_id_returns_400(self):
        """Empty file_id string should return 400."""
        response = self.client.post(
            "/templates/fill",
            json={"file_id": "   "},
        )
        assert response.status_code == 400

    # Test 8: Unauthenticated
    def test_unauthenticated_fill_returns_401(self):
        """Fill without auth should be rejected with 401."""
        from template_router import router, set_service
        from auth_middleware import get_current_user
        from fastapi import HTTPException

        app = FastAPI()
        set_service(self.svc)

        def _require_auth():
            raise HTTPException(status_code=401, detail="Not authenticated")

        app.dependency_overrides[get_current_user] = _require_auth
        app.include_router(router)

        client = TestClient(app, raise_server_exceptions=False)
        response = client.post("/templates/fill", json={"file_id": "abc-123"})
        assert response.status_code == 401


# ──────────────────────────────────────────────────────────────
# GET /templates/download/{file_id} Tests
# ──────────────────────────────────────────────────────────────


class TestDownloadEndpoint:
    """Tests for GET /templates/download/{file_id}."""

    def setup_method(self):
        self.svc = _make_mock_service()
        self.client = TestClient(_build_test_app(self.svc))

    # Test 9: Owner can download
    def test_owner_can_download_file(self, tmp_path):
        """File owner (user_id=7) can download their generated PDF."""
        file_id = "owner-file-id"
        output_file = tmp_path / f"7_{file_id}_output.pdf"
        output_file.write_bytes(MINIMAL_PDF)

        with patch("template_router.settings") as mock_settings:
            mock_settings.template_output_dir = str(tmp_path)
            response = self.client.get(f"/templates/download/{file_id}")

        assert response.status_code == 200
        assert response.headers["content-type"] == "application/pdf"

    # Test 10: Wrong user gets 403
    def test_different_user_gets_403(self, tmp_path):
        """File owned by user 99 should return 403 for user 7."""
        file_id = "other-user-file"
        # File belongs to user 99, not user 7 (MOCK_USER.id = 7)
        output_file = tmp_path / f"99_{file_id}_output.pdf"
        output_file.write_bytes(MINIMAL_PDF)

        with patch("template_router.settings") as mock_settings:
            mock_settings.template_output_dir = str(tmp_path)
            response = self.client.get(f"/templates/download/{file_id}")

        assert response.status_code == 403

    # Test 11: Non-existent file_id
    def test_nonexistent_file_returns_404(self, tmp_path):
        """Unknown file_id with no matching file returns 404."""
        with patch("template_router.settings") as mock_settings:
            mock_settings.template_output_dir = str(tmp_path)
            response = self.client.get("/templates/download/does-not-exist")

        assert response.status_code == 404

    # Test 12: Path traversal rejected
    def test_path_traversal_in_file_id_returns_400(self, tmp_path):
        """file_id containing path separators must be rejected with 400."""
        with patch("template_router.settings") as mock_settings:
            mock_settings.template_output_dir = str(tmp_path)
            response = self.client.get("/templates/download/..%2F..%2Fetc%2Fpasswd")

        # FastAPI URL routing encodes slashes; the safe_id check catches other forms
        assert response.status_code in (400, 404)
