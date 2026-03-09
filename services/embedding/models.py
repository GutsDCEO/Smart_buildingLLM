"""
Data Transfer Objects (DTOs) for the Embedding Service.

These Pydantic models define the contracts between layers.
No business logic lives here (Quality Rule ④ — Dumb DTOs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class ChunkInput(BaseModel):
    """A single chunk to be embedded — mirrors the Ingestion Service output."""

    text: str = Field(..., description="Chunk text content")
    chunk_index: int = Field(..., description="Position in the document (0-indexed)")
    token_count: int = Field(..., description="Number of tokens in this chunk")
    source_file: str = Field(..., description="Original filename")
    page_number: Optional[int] = Field(
        default=None,
        description="Source page number if available",
    )
    start_char: int = Field(default=0, description="Start character offset")
    end_char: int = Field(default=0, description="End character offset")


class EmbedRequest(BaseModel):
    """Request body for the /embed endpoint."""

    chunks: list[ChunkInput] = Field(
        ...,
        description="List of text chunks to embed and store",
        min_length=1,
    )


class StoredChunkInfo(BaseModel):
    """Information about a successfully stored chunk."""

    chunk_index: int
    vector_id: str
    source_file: str


class EmbedResponse(BaseModel):
    """Response from the /embed endpoint."""

    source_file: str = Field(..., description="Name of the source file")
    chunks_stored: int = Field(..., description="Number of chunks embedded and stored")
    stored_chunks: list[StoredChunkInfo] = Field(
        ...,
        description="Details of each stored chunk",
    )
    embedded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of embedding",
    )


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = "healthy"
    service: str = "embedding"
    version: str = "0.1.0"
    model_loaded: bool = False
