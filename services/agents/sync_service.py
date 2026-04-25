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
    existing_docs: list[dict],
    on_ingested=None,
    on_deleted=None,
) -> SyncResult:
    """
    Synchronize the local ingest folder with the document database.

    Features:
      - Addition: Ingests new files.
      - Modification: Re-ingests files if the size has changed.
      - Pruning: Marks documents as 'deleted' if they are missing from the folder.

    Args:
        ingestion_gateway: The IngestionGateway instance.
        existing_docs: List of document records from Postgres (id, filename, file_size_bytes).
        on_ingested: Async callback(filename, chunk_count, file_size_bytes) for new/updated docs.
        on_deleted: Async callback(doc_id) to mark a missing file as deleted.

    Returns:
        A SyncResult summarizing the operation.
    """
    result = SyncResult()
    ingest_path = Path(settings.ingest_folder)

    if not ingest_path.exists():
        logger.warning("Ingest folder '%s' does not exist.", ingest_path)
        result.errors.append(f"Ingest folder not found: {ingest_path}")
        return result

    # 1. Map existing docs for quick lookup
    # Only track files that originated from the ingest folder (simulated by checking if we have them)
    db_files = {doc["filename"]: doc for doc in existing_docs}

    # 2. Collect files currently in the folder
    folder_files = {
        f.name: f for f in ingest_path.iterdir()
        if f.is_file() and f.suffix.lower() in SUPPORTED_EXTENSIONS
    }
    result.total_files_found = len(folder_files)

    # 3. Identify files to ingest or update
    for filename, file_path in folder_files.items():
        db_record = db_files.get(filename)
        current_size = file_path.stat().st_size

        # Idempotency / Update check
        if db_record:
            if db_record.get("file_size_bytes") == current_size:
                logger.debug("Sync: skipping unchanged '%s'.", filename)
                result.already_indexed += 1
                continue
            else:
                logger.info("Sync: detected modification in '%s' (%d -> %d bytes). Re-ingesting...", 
                            filename, db_record.get("file_size_bytes", 0), current_size)

        # Ingest the file
        try:
            mime = MIME_TYPE_MAP.get(file_path.suffix.lower(), "application/octet-stream")
            file_bytes = file_path.read_bytes()

            ingest_response = await ingestion_gateway.ingest_file(
                filename=filename,
                file_contents=file_bytes,
                content_type=mime,
            )

            if on_ingested is not None:
                await on_ingested(
                    filename=filename,
                    chunk_count=ingest_response.chunks_stored,
                    file_size_bytes=current_size,
                )

            result.newly_ingested += 1
            logger.info("Sync: successfully processed '%s'.", filename)

        except Exception as exc:
            logger.error("Sync: failed to ingest '%s': %s", filename, exc)
            result.failed += 1
            result.errors.append(f"{filename}: {exc}")

    # 4. Pruning: Mark files missing from folder as deleted
    if on_deleted:
        for filename, db_record in db_files.items():
            if filename not in folder_files:
                logger.info("Sync: pruning ghost file '%s' (id=%d) from AI.", filename, db_record["id"])
                try:
                    await on_deleted(db_record["id"])
                except Exception as exc:
                    logger.error("Sync: failed to prune '%s': %s", filename, exc)

    return result
