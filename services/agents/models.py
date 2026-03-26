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
# Health Check DTO
# ──────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    """Response from the /health endpoint."""

    status: str = "healthy"
    service: str = "agents"
    version: str = "0.1.0"
    ollama_reachable: bool = False
    qdrant_reachable: bool = False
