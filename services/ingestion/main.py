"""
Ingestion Service — FastAPI Entry Point.

Thin Controller pattern: this module only handles HTTP concerns.
All business logic is delegated to parsers and the chunker.
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException

from config import settings
from models import IngestResponse, HealthResponse
from parsers import get_parser, get_supported_extensions
from chunker import chunk_text

# ──────────────────────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Smart Building AI — Ingestion Service",
    description="Extracts text from documents and splits into chunks for RAG.",
    version="0.1.0",
)


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check for Docker and load balancers."""
    return HealthResponse()


@app.get("/formats", tags=["System"])
async def list_formats() -> dict:
    """Return all supported file formats."""
    return {"supported_extensions": get_supported_extensions()}


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest_document(file: UploadFile = File(...)) -> IngestResponse:
    """
    Ingest a document file: parse it and split into chunks.

    Accepts: PDF, DOCX

    Flow:
      1. Save uploaded file to a temporary location
      2. Detect format and select the appropriate parser
      3. Extract text (pages/paragraphs)
      4. Chunk the text using token-based splitting
      5. Return all chunks with metadata

    Raises:
      400: Unsupported file type or corrupted document.
      500: Unexpected server error.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")

    file_path = Path(file.filename)

    # Fail early: check if we have a parser for this format
    try:
        parser = get_parser(file_path)
    except ValueError as exc:
        logger.warning("Unsupported format rejected: %s", file.filename)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Save upload to a temp file for parsing
    try:
        with tempfile.NamedTemporaryFile(
            delete=False,
            suffix=file_path.suffix,
        ) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = Path(tmp.name)

        logger.info("Saved upload to temp file: %s", tmp_path)

        # Parse the document
        pages = parser.parse(tmp_path)

        if not pages:
            raise HTTPException(
                status_code=400,
                detail=f"No text could be extracted from '{file.filename}'.",
            )

        # Chunk each page
        all_chunks = []
        for page in pages:
            page_chunks = chunk_text(
                text=page.text,
                source_file=file.filename,
                page_number=page.page_number,
            )
            all_chunks.extend(page_chunks)

        # Re-index chunks globally across all pages
        for i, chunk in enumerate(all_chunks):
            chunk.chunk_index = i

        logger.info(
            "Ingestion complete: %s → %d pages, %d chunks",
            file.filename,
            len(pages),
            len(all_chunks),
        )

        return IngestResponse(
            source_file=file.filename,
            total_pages=len(pages),
            total_chunks=len(all_chunks),
            chunks=all_chunks,
        )

    except ValueError as exc:
        logger.error("Parse error: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    except Exception as exc:
        # OWASP A09: Log context but don't expose stack traces
        logger.exception("Unexpected error during ingestion of %s", file.filename)
        raise HTTPException(
            status_code=500,
            detail="An internal error occurred during document processing.",
        ) from exc

    finally:
        # Cleanup temp file
        if tmp_path.exists():
            tmp_path.unlink()
            logger.debug("Cleaned up temp file: %s", tmp_path)
