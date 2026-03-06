"""
Data Transfer Objects (DTOs) for the Ingestion Service.

These Pydantic models define the contracts between layers.
No business logic lives here (Quality Rule ④ — Dumb DTOs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ParsedPage(BaseModel):
    """Output from a parser — one page/section of extracted text."""

    text: str = Field(..., description="Extracted text content")
    page_number: int = Field(..., description="Page number (1-indexed) or paragraph index")
    source_file: str = Field(..., description="Original filename")
    metadata: dict = Field(
        default_factory=dict,
        description="Additional metadata (e.g., author, title)",
    )


class TextChunk(BaseModel):
    """A single chunk of text after splitting."""

    text: str = Field(..., description="Chunk text content")
    chunk_index: int = Field(..., description="Position of chunk in the document (0-indexed)")
    token_count: int = Field(..., description="Number of tokens in this chunk")
    source_file: str = Field(..., description="Original filename")
    page_number: Optional[int] = Field(
        default=None,
        description="Source page number if available",
    )
    start_char: int = Field(..., description="Start character offset in original text")
    end_char: int = Field(..., description="End character offset in original text")


class IngestRequest(BaseModel):
    """Metadata sent alongside a file upload."""

    source_label: Optional[str] = Field(
        default=None,
        description="Optional human-readable label for the document",
    )


class IngestResponse(BaseModel):
    """Response from the /ingest endpoint."""

    source_file: str = Field(..., description="Name of the ingested file")
    total_pages: int = Field(..., description="Total pages/sections extracted")
    total_chunks: int = Field(..., description="Total chunks after splitting")
    chunks: list[TextChunk] = Field(..., description="All text chunks with metadata")
    ingested_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of ingestion",
    )


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = "healthy"
    service: str = "ingestion"
    version: str = "0.1.0"
