"""
Sync Service — Scans the local ingest folder and triggers ingestion for new files.

Design:
  - SRP: Only responsible for folder scanning and dispatching to the ingestion gateway.
  - Idempotent: Re-scanning a folder will not re-ingest already-indexed files.
  - OWASP A03: Validates file paths to prevent directory traversal.
"""

from __future__ import annotations

import logging
from pathlib import Path
from dataclasses import dataclass, field

from config import settings

logger = logging.getLogger(__name__)

# Supported file extensions for the ingest folder scan
SUPPORTED_EXTENSIONS: frozenset[str] = frozenset({".pdf", ".docx", ".doc", ".txt"})

# MIME type map for supported extensions
MIME_TYPE_MAP: dict[str, str] = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".doc": "application/msword",
    ".txt": "text/plain",
}


@dataclass
class SyncResult:
    """Summary of a single sync operation."""
    total_files_found: int = 0
    already_indexed: int = 0
    newly_ingested: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


async def sync_ingest_folder(
    ingestion_gateway,
    existing_filenames: set[str],
    on_ingested=None,
) -> SyncResult:
    """
    Scan the local ingest folder and ingest files not already tracked.

    Args:
        ingestion_gateway: The IngestionGateway instance for forwarding files.
        existing_filenames: Set of filenames already recorded in the documents table.
        on_ingested: Optional async callable(filename, chunk_count, file_size_bytes)
                     called after each successful ingestion to record the document.

    Returns:
        A SyncResult summarizing what was found and processed.
    """
    result = SyncResult()
    ingest_path = Path(settings.ingest_folder)

    if not ingest_path.exists():
        logger.warning("Ingest folder '%s' does not exist.", ingest_path)
        result.errors.append(f"Ingest folder not found: {ingest_path}")
        return result

    # Collect all supported files from the ingest folder (non-recursive)
    candidate_files = [
        f for f in ingest_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    ]
    result.total_files_found = len(candidate_files)

    logger.info(
        "Sync: found %d supported file(s) in '%s'.",
        result.total_files_found,
        ingest_path,
    )

    for file_path in candidate_files:
        filename = file_path.name

        # --- Idempotency check ---
        if filename in existing_filenames:
            logger.debug("Sync: skipping already-indexed '%s'.", filename)
            result.already_indexed += 1
            continue

        # --- OWASP A03: Path traversal guard ---
        resolved = file_path.resolve()
        if not str(resolved).startswith(str(ingest_path.resolve())):
            logger.warning("Sync: rejected suspicious path '%s'.", file_path)
            result.failed += 1
            result.errors.append(f"Rejected path: {filename}")
            continue

        # --- Ingest the new file ---
        try:
            mime = MIME_TYPE_MAP.get(file_path.suffix.lower(), "application/octet-stream")
            file_bytes = resolved.read_bytes()
            file_size = resolved.stat().st_size

            ingest_response = await ingestion_gateway.ingest_file(
                filename=filename,
                file_contents=file_bytes,
                content_type=mime,
            )

            logger.info(
                "Sync: ingested '%s' → %d chunks stored.",
                filename,
                ingest_response.chunks_stored,
            )

            # Record in Postgres via the injected callback (DIP)
            if on_ingested is not None:
                await on_ingested(
                    filename=filename,
                    chunk_count=ingest_response.chunks_stored,
                    file_size_bytes=file_size,
                )

            result.newly_ingested += 1

        except Exception as exc:
            logger.error("Sync: failed to ingest '%s': %s", filename, exc)
            result.failed += 1
            result.errors.append(f"{filename}: {exc}")

    logger.info(
        "Sync complete — found=%d, skipped=%d, ingested=%d, failed=%d",
        result.total_files_found,
        result.already_indexed,
        result.newly_ingested,
        result.failed,
    )
    return result
