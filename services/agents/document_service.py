"""
Document Service — Business logic for document tracking and lifecycle.

Design:
  - SRP: Only handles document CRUD in PostgreSQL. No parsing or embedding.
  - DIP: Depends on database.get_pool() abstraction.
  - OWASP A03: All queries use parameterized statements ($1, $2, ...).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from database import get_pool

logger = logging.getLogger(__name__)

# Map file extensions to human-readable types
_TYPE_MAP = {
    ".pdf": "PDF",
    ".docx": "Word",
    ".doc": "Word",
    ".html": "HTML",
    ".htm": "HTML",
    ".txt": "Text",
}


def _detect_file_type(filename: str) -> str:
    """Detect document type from filename extension."""
    ext = Path(filename).suffix.lower()
    return _TYPE_MAP.get(ext, "Unknown")


async def record_document(
    filename: str,
    chunk_count: int,
    file_size_bytes: int = 0,
) -> Optional[int]:
    """
    Record a newly ingested document in the documents table.

    Uses INSERT ... ON CONFLICT to handle re-uploads gracefully:
    if the same filename already exists, it updates the chunk count.

    Returns:
        The document ID, or None if the database is unavailable.
    """
    pool = get_pool()
    if pool is None:
        logger.warning("DB unavailable — skipping document record for '%s'.", filename)
        return None

    file_type = _detect_file_type(filename)

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO documents (filename, file_type, chunk_count, file_size_bytes, status, created_at)
                VALUES ($1, $2, $3, $4, 'active', $5)
                ON CONFLICT (filename) DO UPDATE
                SET chunk_count = $3, file_size_bytes = $4, status = 'active', created_at = $5
                RETURNING id
                """,
                filename,
                file_type,
                chunk_count,
                file_size_bytes,
                datetime.now(timezone.utc),
            )
            doc_id = row["id"]
            logger.info("Recorded document '%s' (id=%d, type=%s, chunks=%d).", filename, doc_id, file_type, chunk_count)
            return doc_id

    except Exception as exc:
        logger.error("Failed to record document '%s': %s", filename, exc)
        return None


async def list_documents(file_type: Optional[str] = None) -> list[dict]:
    """
    List all active documents, optionally filtered by file_type.

    Returns:
        A list of document dicts with id, filename, file_type, chunk_count, created_at.
    """
    pool = get_pool()
    if pool is None:
        return []

    try:
        async with pool.acquire() as conn:
            if file_type:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, file_type, chunk_count, file_size_bytes, created_at
                    FROM documents
                    WHERE status = 'active' AND file_type = $1
                    ORDER BY created_at DESC
                    """,
                    file_type,
                )
            else:
                rows = await conn.fetch(
                    """
                    SELECT id, filename, file_type, chunk_count, file_size_bytes, created_at
                    FROM documents
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    """
                )

        return [
            {
                "id": row["id"],
                "filename": row["filename"],
                "file_type": row["file_type"],
                "chunk_count": row["chunk_count"],
                "file_size_bytes": row["file_size_bytes"],
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]

    except Exception as exc:
        logger.error("Failed to list documents: %s", exc)
        return []


async def delete_document(doc_id: int) -> Optional[str]:
    """
    Soft-delete a document by marking it as 'deleted'.

    Returns:
        The filename of the deleted document (needed for Qdrant cleanup),
        or None if not found or DB unavailable.
    """
    pool = get_pool()
    if pool is None:
        return None

    try:
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE documents SET status = 'deleted'
                WHERE id = $1 AND status = 'active'
                RETURNING filename
                """,
                doc_id,
            )

            if row:
                logger.info("Marked document id=%d ('%s') as deleted.", doc_id, row["filename"])
                return row["filename"]
            else:
                logger.warning("Document id=%d not found or already deleted.", doc_id)
                return None

    except Exception as exc:
        logger.error("Failed to delete document id=%d: %s", doc_id, exc)
        return None
