"""
Template Router — FastAPI endpoints for template upload, filling, and download.

Design:
  - Thin Controller: HTTP concerns only. All logic delegated to TemplateService.
  - Auth: All endpoints require get_current_user (available to all authenticated users).
  - A01: Download validates file ownership via user_id prefix in filename.
  - A03: MIME type and file size validated before any processing.
  - A04: Rate limiting applied via existing rate_limiter dependency.

Endpoints:
  POST /templates/analyze       — Upload PDF, extract fillable fields
  POST /templates/fill          — Run RAG fill loop with SSE progress stream
  GET  /templates/download/{id} — Download the completed PDF (ownership-checked)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

from auth_middleware import get_current_user
from auth_models import UserResponse
from config import settings
from models import TemplateAnalyzeResponse, TemplateFillRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/templates", tags=["Templates"])

# Injected by main.py lifespan after TemplateService is constructed
_template_service = None  # type: ignore[assignment]

ALLOWED_MIME_TYPES = {"application/pdf"}
MAX_FILENAME_LEN = 200


def _get_service():
    """Dependency that returns the singleton TemplateService instance."""
    if _template_service is None:
        raise HTTPException(
            status_code=503,
            detail="Template service is not available. Check server logs.",
        )
    return _template_service


def _validate_upload(file: UploadFile, content: bytes) -> None:
    """
    Validate file MIME type and size at the controller boundary (OWASP A03).

    Raises HTTPException 400 for invalid type, 413 for oversized files.
    """
    mime = file.content_type or ""
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{mime}'. Only PDF files are accepted.",
        )

    max_bytes = settings.template_max_upload_mb * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"File too large ({len(content) // 1024 // 1024} MB). "
                f"Maximum allowed: {settings.template_max_upload_mb} MB."
            ),
        )

    if (
        not file.filename
        or not file.filename.strip()
        or len(file.filename) > MAX_FILENAME_LEN
    ):
        raise HTTPException(status_code=400, detail="Invalid or missing filename.")


# ── Endpoints ────────────────────────────────────────────────────────────────


@router.post("/analyze", response_model=TemplateAnalyzeResponse)
async def analyze_template(
    file: UploadFile = File(...),
    user: UserResponse = Depends(get_current_user),
    service=Depends(_get_service),
) -> TemplateAnalyzeResponse:
    """
    Upload a PDF template and extract all fillable fields.

    Returns a file_id for use with /templates/fill, plus a list
    of detected fields (name, type, page number).

    Raises:
      400: Non-PDF file or empty filename.
      413: File exceeds TEMPLATE_MAX_UPLOAD_MB.
      503: Template service unavailable.
    """
    content = await file.read()
    _validate_upload(file, content)

    logger.info(
        "Template analyze request: '%s' (%d bytes) by user=%s",
        file.filename,
        len(content),
        user.username,
    )

    try:
        result = await service.analyze(content, file.filename, user.id)
    except RuntimeError as exc:
        logger.error("Template analyze error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    logger.info(
        "Template analyzed: %d fields in '%s' (file_id=%s, user=%s)",
        result.total_fields,
        result.filename,
        result.file_id,
        user.username,
    )
    return result


@router.post("/fill")
async def fill_template(
    request: TemplateFillRequest,
    user: UserResponse = Depends(get_current_user),
    service=Depends(_get_service),
) -> StreamingResponse:
    """
    Fill template fields using the RAG pipeline. Returns an SSE stream.

    Events emitted:
      - status:   Pipeline stage updates with progress counters
      - field:    Per-field result (status: filled | failed)
      - complete: Final TemplateFillResponse JSON summary
      - done:     Stream terminator

    Raises:
      400: Empty file_id.
      503: Template service unavailable.
    """
    if not request.file_id.strip():
        raise HTTPException(status_code=400, detail="file_id cannot be empty.")

    logger.info(
        "Template fill request: file_id=%s, user=%s", request.file_id, user.username
    )

    return StreamingResponse(
        service.fill_stream(
            file_id=request.file_id,
            user_id=user.id,
            requested_fields=request.fields,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/download/{file_id}")
async def download_filled(
    file_id: str,
    user: UserResponse = Depends(get_current_user),
) -> FileResponse:
    """
    Download the completed PDF template.

    Enforces ownership: only the user who initiated the fill can download
    the result. File is stored as {user_id}_{file_id}_output.pdf,
    so the user_id prefix is validated server-side (OWASP A01).

    Raises:
      403: File does not belong to the requesting user.
      404: File not found (never generated or already deleted).
    """
    output_dir = Path(settings.template_output_dir)

    # Ownership check: file must start with this user's ID prefix
    # Path traversal guard: file_id must not contain path separators
    safe_id = Path(file_id).name  # Strips any ../ or / from the ID
    if safe_id != file_id:
        raise HTTPException(status_code=400, detail="Invalid file_id.")

    expected_path = output_dir / f"{user.id}_{safe_id}_output.pdf"

    if not expected_path.exists():
        # Check if another user owns this file (403 vs 404 distinction)
        any_match = list(output_dir.glob(f"*_{safe_id}_output.pdf"))
        if any_match:
            logger.warning(
                "Ownership violation: user=%s attempted to download file_id=%s owned by another user.",
                user.username,
                file_id,
            )
            raise HTTPException(
                status_code=403,
                detail="Access denied. This file belongs to another user.",
            )
        raise HTTPException(status_code=404, detail="File not found.")

    logger.info("Template download: file_id=%s, user=%s", file_id, user.username)

    return FileResponse(
        path=str(expected_path),
        media_type="application/pdf",
        filename=f"filled_{safe_id}.pdf",
    )


def set_service(service) -> None:
    """Called by main.py lifespan to inject the TemplateService singleton."""
    global _template_service
    _template_service = service
