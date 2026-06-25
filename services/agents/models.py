"""
Data Transfer Objects (DTOs) for the Agents Service.

These Pydantic models define the contracts between layers.
No business logic lives here (Quality Rule ④ — Dumb DTOs).
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# ──────────────────────────────────────────────────────────────
# Guardrail Agent DTOs
# ──────────────────────────────────────────────────────────────


class GuardRequest(BaseModel):
    """Input to the Guardrail Agent."""

    question: str = Field(..., description="The raw user question to validate")


class GuardResponse(BaseModel):
    """Output from the Guardrail Agent."""

    allowed: bool = Field(..., description="Whether the question passed validation")
    reason: str = Field(
        default="OK",
        description="Why the question was blocked (or 'OK' if allowed)",
    )
    sanitized_question: str = Field(
        default="",
        description="Cleaned version of the question (if allowed)",
    )


# ──────────────────────────────────────────────────────────────
# Router Agent DTOs
# ──────────────────────────────────────────────────────────────


class IntentType(str, Enum):
    """Supported intent categories for the MVP Router."""

    FACTUAL_QA = "factual_qa"
    OUT_OF_SCOPE = "out_of_scope"


class RouteRequest(BaseModel):
    """Input to the Router Agent."""

    question: str = Field(..., description="The sanitized user question")


class RouteResponse(BaseModel):
    """Output from the Router Agent."""

    intent: IntentType = Field(..., description="Classified intent")
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Classification confidence (0.0–1.0)",
    )


# ──────────────────────────────────────────────────────────────
# Q&A Agent DTOs
# ──────────────────────────────────────────────────────────────


class Citation(BaseModel):
    """A source citation for a chunk used in the answer."""

    source_file: str = Field(..., description="Original document filename")
    page_number: Optional[int] = Field(
        default=None,
        description="Page number in the source document",
    )
    chunk_index: int = Field(..., description="Chunk position in the document")
    relevance_score: float = Field(
        default=0.0,
        description="Cosine similarity score (0.0–1.0)",
    )


class AskRequest(BaseModel):
    """Input to the Q&A Agent."""

    question: str = Field(..., description="The user's question")


class ChatRequest(BaseModel):
    """Input to the unified /chat SSE endpoint."""

    question: str = Field(..., description="The user's question")
    session_id: Optional[str] = Field(
        default=None,
        description="Optional session ID for conversation history",
    )
    enable_thinking: bool = Field(
        default=False,
        description="Enable Qwen3 Chain-of-Thought reasoning mode (~3x token cost)",
    )


class AskResponse(BaseModel):
    """Output from the Q&A Agent — the core product."""

    answer: str = Field(..., description="The LLM-generated answer")
    citations: list[Citation] = Field(
        default_factory=list,
        description="Source documents used to build the answer",
    )
    intent: str = Field(
        default="factual_qa",
        description="The classified intent of the question",
    )
    answered_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of when the answer was generated",
    )


# ──────────────────────────────────────────────────────────────
# Ingestion Gateway DTO
# ──────────────────────────────────────────────────────────────


class IngestResponse(BaseModel):
    """Response returned after successfully ingesting a document via the Gateway."""

    filename: str = Field(..., description="Name of the ingested file")
    chunks_extracted: int = Field(..., description="Number of text chunks extracted")
    chunks_stored: int = Field(..., description="Number of vectors stored in Qdrant")
    status: str = Field(default="success", description="Status message")


# ──────────────────────────────────────────────────────────────
# Health Check DTO
# ──────────────────────────────────────────────────────────────


class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = "healthy"
    service: str = "agents"
    version: str = "0.1.0"
    ollama_reachable: bool = False
    qdrant_reachable: bool = False


# ──────────────────────────────────────────────────────────────
# Template Filling DTOs (Phase 6)
# ──────────────────────────────────────────────────────────────


class TemplateField(BaseModel):
    """A single extractable field from a template document."""

    field_name: str = Field(..., description="The placeholder label or widget name")
    field_type: str = Field(
        ...,
        description="Detection method: acroform | bracket | underscore | mustache",
    )
    page_number: int = Field(..., description="1-indexed page where the field appears")
    current_value: Optional[str] = Field(
        default=None, description="Pre-existing value if any"
    )
    generated_value: Optional[str] = Field(
        default=None, description="RAG-generated answer after filling"
    )
    confidence: float = Field(
        default=0.0, description="Best citation relevance score (0.0–1.0)"
    )
    error: Optional[str] = Field(
        default=None, description="Error message if filling failed for this field"
    )


class TemplateAnalyzeResponse(BaseModel):
    """Response from POST /templates/analyze."""

    file_id: str = Field(..., description="Temporary file ID for subsequent /fill call")
    filename: str = Field(..., description="Original uploaded filename")
    total_fields: int = Field(..., description="Number of fillable fields detected")
    fields: list[TemplateField] = Field(
        default_factory=list, description="All detected fields with metadata"
    )


class TemplateFillRequest(BaseModel):
    """Request body for POST /templates/fill."""

    file_id: str = Field(..., description="ID returned from /templates/analyze")
    fields: Optional[list[str]] = Field(
        default=None,
        description="Subset of field names to fill. None = fill all fields.",
    )


class TemplateFillError(BaseModel):
    """Details about a single field that failed to fill."""

    field_name: str = Field(..., description="Name of the field that failed")
    reason: str = Field(..., description="Human-readable error reason")


class TemplateFillResponse(BaseModel):
    """Final summary returned as the last SSE event from POST /templates/fill."""

    file_id: str = Field(..., description="ID of the generated output file")
    filename: str = Field(..., description="Output filename")
    fields_filled: int = Field(..., description="Number of successfully filled fields")
    fields_failed: int = Field(
        ..., description="Number of fields that could not be filled"
    )
    field_errors: list[TemplateFillError] = Field(
        default_factory=list, description="Per-field error details"
    )
    download_url: str = Field(
        ..., description="Relative URL to download the output file"
    )
    status: str = Field(
        default="completed",
        description="'completed' or 'completed_with_errors'",
    )
