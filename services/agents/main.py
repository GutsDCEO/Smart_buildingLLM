"""
Agents Service — FastAPI Entry Point.

Thin Controller pattern: this module only handles HTTP concerns.
All business logic is delegated to:
  - guardrail_agent  (input validation)
  - router_agent     (intent classification)
  - qa_agent         (RAG pipeline)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from config import settings
from models import (
    AskRequest, AskResponse,
    GuardRequest, GuardResponse,
    HealthResponse,
    RouteRequest, RouteResponse,
)
from guardrail_agent import guardrail_agent
from router_agent import router_agent
from qa_agent import qa_agent
from ollama_client import ollama_client
from qdrant_search import qdrant_search

# ──────────────────────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Lifespan — connect to dependencies at startup
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Connect to Qdrant at startup; disconnect at shutdown."""
    logger.info("Starting Agents Service...")

    try:
        qdrant_search.connect()
    except Exception as exc:
        logger.warning("Qdrant not available at startup: %s", exc)

    logger.info("Agents Service ready.")
    yield

    logger.info("Agents Service shut down.")


# ──────────────────────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Smart Building AI — Agents Service",
    description=(
        "Orchestrates the three-agent RAG pipeline: "
        "Guardrail → Router → Q&A with citations."
    ),
    version="0.1.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check: verifies Ollama and Qdrant reachability."""
    ollama_ok = await ollama_client.is_reachable()
    qdrant_ok = qdrant_search.is_connected
    return HealthResponse(
        ollama_reachable=ollama_ok,
        qdrant_reachable=qdrant_ok,
    )


@app.post("/guard", response_model=GuardResponse, tags=["Agents"])
async def guard(request: GuardRequest) -> GuardResponse:
    """
    Validate and sanitize user input.

    Returns:
      - allowed=True + sanitized_question if input is safe.
      - allowed=False + reason if input is blocked.
    """
    result = guardrail_agent.validate(request)
    logger.info("Guard result: allowed=%s", result.allowed)
    return result


@app.post("/route", response_model=RouteResponse, tags=["Agents"])
async def route(request: RouteRequest) -> RouteResponse:
    """
    Classify user question intent via LLM.

    Returns:
      - intent: 'factual_qa' or 'out_of_scope'
      - confidence: 0.0–1.0

    Raises:
      400: Empty question.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    result = await router_agent.classify(request)
    logger.info("Route result: intent=%s (%.2f)", result.intent.value, result.confidence)
    return result


@app.post("/ask", response_model=AskResponse, tags=["Agents"])
async def ask(request: AskRequest) -> AskResponse:
    """
    Full RAG pipeline: embed → search → generate cited answer.

    Flow:
      1. Vectorize question via Embedding Service
      2. Search Qdrant for top-K relevant chunks
      3. Build context prompt with source citations
      4. Generate answer via Ollama

    Raises:
      400: Empty question.
      503: Embedding Service or LLM unavailable.
      500: Unexpected error.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    try:
        result = await qa_agent.answer(request)
    except RuntimeError as exc:
        # Service-level errors (Ollama down, Qdrant disconnected, etc.)
        logger.error("Q&A pipeline error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        # Unexpected errors — log with context, return generic error (OWASP A09)
        logger.exception("Unexpected error in /ask")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please check the server logs.",
        ) from exc

    logger.info(
        "/ask complete: %d citations, answer=%d chars",
        len(result.citations),
        len(result.answer),
    )
    return result
