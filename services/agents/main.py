"""
Agents Service — FastAPI Entry Point.

Thin Controller pattern: this module only handles HTTP concerns.
All business logic is delegated to:
  - guardrail_agent  (input validation)
  - router_agent     (intent classification)
  - qa_agent         (RAG pipeline)
"""

from __future__ import annotations

import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, HTTPException, Query, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse

from config import settings
from models import (
    AskRequest, AskResponse,
    ChatRequest,
    GuardRequest, GuardResponse,
    HealthResponse, IntentType,
    RouteRequest, RouteResponse,
    IngestResponse,
)
from guardrail_agent import GuardrailAgent
from router_agent import RouterAgent
from qa_agent import QAAgent
from domain_config import domain_config
from reranker import reranker
from llm_factory import create_llm_client
from qdrant_search import qdrant_search
from ingestion_gateway import ingestion_gateway
from database import connect_db, disconnect_db
import document_service
import history_service
import sync_service

# Agents and LLM client — resolved at startup by the factory (Groq or Ollama)
# Using module-level variables so the lifespan and endpoints share the same instances.
llm_client = None  # type: ignore[assignment]
guardrail_agent = None  # type: ignore[assignment]
router_agent = None  # type: ignore[assignment]
qa_agent = None  # type: ignore[assignment]

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
    """Connect to Qdrant and LLM pool at startup; disconnect at shutdown."""
    global llm_client, guardrail_agent, router_agent, qa_agent
    logger.info("Starting Agents Service...")

    try:
        qdrant_search.connect()
    except Exception as exc:
        logger.warning("Qdrant not available at startup: %s", exc)

    # Connect to PostgreSQL (persistence layer)
    await connect_db()

    # Resolve and start the correct LLM client (Groq or Ollama)
    llm_client = create_llm_client()
    await llm_client.startup()

    logger.info("LLM Provider Active: %s", settings.llm_provider)
    logger.info("Client Instance: %s", type(llm_client).__name__)

    # Load the re-ranker cross-encoder model
    try:
        reranker.load_model()
    except Exception as exc:
        logger.warning("Reranker not available: %s (will use raw results)", exc)

    # Initialize Agents with the unified LLM client
    guardrail_agent = GuardrailAgent()
    router_agent = RouterAgent(llm_client)
    qa_agent = QAAgent(llm_client)

    logger.info(
        "Agents Service ready. Domain: '%s' v%s",
        domain_config.name,
        domain_config.version,
    )
    yield

    # Shutdown: close connection pools
    await llm_client.shutdown()
    await disconnect_db()
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
    version="0.2.0",
    lifespan=lifespan,
)

# ──────────────────────────────────────────────────────────────
# CORS — Allow Chat UI to call this API (OWASP A01)
# ──────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.chat_ui_cors_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check: verifies Ollama and Qdrant reachability."""
    ollama_ok = await llm_client.is_reachable() if llm_client else False
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


@app.post("/ingest", response_model=IngestResponse, tags=["Ingestion"])
async def ingest(file: UploadFile = File(...)) -> IngestResponse:
    """
    Unified ingestion endpoint. Receives a file from the UI,
    saves it to the /data/ingest folder (to maintain sync integrity),
    forwards it to the Ingestion Service (:8001), then passes
    the chunks to the Embedding Service (:8002) for vector storage.

    Order of operations:
      1. Save file to /data/ingest FIRST — so Sync never sees it as a ghost.
      2. Send to Ingestion + Embedding services.
      3. Record in PostgreSQL.

    Raises:
      400: If no file is provided.
      503: If downstream microservices fail.
      500: Unexpected errors.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided for upload.")

    try:
        content = await file.read()
        mime_type = file.content_type or "application/octet-stream"

        # ── Step 1: Persist to /data/ingest BEFORE touching the DB ──────────
        # This ensures that any immediately-following /sync call finds the file
        # in the folder and does NOT prune it as a ghost.
        ingest_path = Path(settings.ingest_folder) / file.filename
        try:
            ingest_path.write_bytes(content)
            logger.info("Saved uploaded file to '%s' (%d bytes).", ingest_path, len(content))
        except OSError as save_err:
            # Non-fatal: log and continue — ingestion can still succeed.
            logger.error("Could not save '%s' to ingest folder: %s", file.filename, save_err)

        # ── Step 2: Extract text + embed vectors ─────────────────────────────
        result = await ingestion_gateway.ingest_file(
            filename=file.filename,
            file_contents=content,
            content_type=mime_type,
        )

        # ── Step 3: Record metadata in PostgreSQL ────────────────────────────
        await document_service.record_document(
            filename=file.filename,
            chunk_count=result.chunks_stored,
            file_size_bytes=len(content),
        )

        return result

    except RuntimeError as exc:
        logger.error("Ingestion gateway error: %s", exc)
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Unexpected error in /ingest")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred during ingestion.",
        ) from exc


# ──────────────────────────────────────────────────────────────
# /chat — Unified SSE Pipeline (Phase 3)
#
# Runs the FULL Guard → Route → Q&A pipeline in a single
# streaming connection. Each stage emits SSE events so the
# Chat UI can show real-time pipeline progress + streaming text.
# ──────────────────────────────────────────────────────────────

def _sse_event(event: str, data: dict | list | str) -> str:
    """Format a Server-Sent Event string."""
    payload = json.dumps(data) if not isinstance(data, str) else data
    return f"event: {event}\ndata: {payload}\n\n"


async def _chat_stream(
    question: str,
    session_id: str = "default-session",
    enable_thinking: bool = False,
) -> AsyncGenerator[str, None]:
    """
    The core SSE generator: runs Guard → Route → Q&A pipeline.

    Each pipeline stage emits a `status` event. LLM tokens stream
    via `token` events. Citations and completion are sent at the end.
    This generator never raises — all errors are emitted as SSE
    `error` events so the client always gets a clean close.

    Args:
        question: The user's question.
        session_id: The session ID for history persistence.
        enable_thinking: If True, activates Qwen3 CoT reasoning mode.
    """
    accumulated_answer = ""
    try:
        # ── Stage 1: Guardrail ──
        yield _sse_event("status", {"stage": "guardrail", "message": "Checking input safety..."})

        guard_result = guardrail_agent.validate(GuardRequest(question=question))
        if not guard_result.allowed:
            logger.warning("Chat blocked by guardrail: %s", guard_result.reason)
            yield _sse_event("error", {
                "stage": "guardrail",
                "message": guard_result.reason,
            })
            yield _sse_event("done", {"answered_at": datetime.now(timezone.utc).isoformat()})
            return

        sanitized = guard_result.sanitized_question

        # ── Stage 2: Router ──
        yield _sse_event("status", {"stage": "router", "message": "Classifying intent..."})

        route_result = await router_agent.classify(RouteRequest(question=sanitized))

        if route_result.intent == IntentType.OUT_OF_SCOPE:
            logger.info("Chat out_of_scope: %s", sanitized[:60])
            yield _sse_event("token", {
                "text": domain_config.out_of_scope_message,
            })
            yield _sse_event("done", {
                "answered_at": datetime.now(timezone.utc).isoformat(),
                "intent": "out_of_scope",
            })
            return

        # ── Stage 3: Vector Search + Re-Rank ──
        yield _sse_event("status", {"stage": "retrieval", "message": "Searching documents..."})

        # Embed the question via Embedding Service
        query_vector = await qa_agent._embed_question(sanitized)

        if not qdrant_search.is_connected:
            yield _sse_event("error", {
                "stage": "retrieval",
                "message": "Vector database is not available. Please try again later.",
            })
            yield _sse_event("done", {"answered_at": datetime.now(timezone.utc).isoformat()})
            return

        results = qdrant_search.search(
            query_vector,
            top_k=domain_config.retrieval.top_k_retrieval,
        )

        if not results:
            yield _sse_event("token", {
                "text": "I don't have any relevant documents to answer this question. "
                        "Please ensure documents have been ingested first.",
            })
            yield _sse_event("citations", [])
            yield _sse_event("done", {"answered_at": datetime.now(timezone.utc).isoformat()})
            return

        # Re-rank for precision
        yield _sse_event("status", {"stage": "reranking", "message": "Re-ranking results..."})
        reranked = reranker.rerank(
            question=sanitized,
            results=results,
            top_n=domain_config.retrieval.top_n_reranked,
        )

        # ── Stage 4: Load conversation history ──
        history = await history_service.get_recent_messages(
            session_id,
            limit=domain_config.memory.max_history_turns * 2,
        )
        history_dicts = [
            {"role": msg["role"], "content": msg["content"]}
            for msg in history
        ] if history else None

        # ── Stage 5: Stream LLM Answer ──
        yield _sse_event("status", {"stage": "generating", "message": "Generating answer..."})

        context_prompt = QAAgent._build_context_prompt(
            sanitized, reranked, history=history_dicts,
        )
        citations = [
            {
                "source_file": r.source_file,
                "page_number": r.page_number,
                "chunk_index": r.chunk_index,
                "relevance_score": round(r.score, 4),
            }
            for r in reranked
        ]

        # Stream tokens from LLM (works for both Groq and Ollama)
        async for token in llm_client.generate_stream(
            prompt=context_prompt,
            system_prompt=domain_config.qa_system_prompt,
            temperature=0.2,
            enable_thinking=enable_thinking,
        ):
            accumulated_answer += token
            yield _sse_event("token", {"text": token})

        # Save the assistant's full response to the database
        if accumulated_answer:
            await history_service.save_message(session_id, "assistant", accumulated_answer)

        # Send citations after full answer
        yield _sse_event("citations", citations)
        yield _sse_event("done", {
            "answered_at": datetime.now(timezone.utc).isoformat(),
            "intent": "factual_qa",
        })

        logger.info("/chat complete: %d citations", len(citations))

    except RuntimeError as exc:
        # Service-level errors (Ollama down, Embedding timeout, etc.)
        logger.error("Chat pipeline error: %s", exc)
        yield _sse_event("error", {
            "stage": "error",
            "message": str(exc),
        })
        yield _sse_event("done", {"answered_at": datetime.now(timezone.utc).isoformat()})

    except Exception as exc:
        # Unexpected errors — OWASP A09: log full trace, return safe message
        logger.exception("Unexpected error in /chat stream")
        yield _sse_event("error", {
            "stage": "error",
            "message": "An unexpected error occurred. Please try again.",
        })
        yield _sse_event("done", {"answered_at": datetime.now(timezone.utc).isoformat()})


@app.post("/chat", tags=["Chat"])
async def chat(request: ChatRequest) -> StreamingResponse:
    """
    Unified SSE streaming endpoint for the Chat UI.

    Runs the full pipeline: Guardrail → Router → Q&A with
    token-by-token streaming. Returns SSE events, not JSON.

    Events emitted:
      - status: Pipeline stage updates
      - token: Individual LLM tokens
      - citations: Source documents used
      - error: Pipeline errors (safe messages only)
      - done: Stream completion

    Raises:
      400: Empty question.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    # Save the user message to the database
    session_id = request.session_id or "default-session"
    await history_service.save_message(session_id, "user", request.question)

    return StreamingResponse(
        _chat_stream(request.question, session_id, request.enable_thinking),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        },
    )


# ──────────────────────────────────────────────────────────────
# /documents — Knowledge Base Management (Phase 4)
# ──────────────────────────────────────────────────────────────

@app.get("/documents", tags=["Knowledge Base"])
async def list_documents(file_type: Optional[str] = Query(None, description="Filter by file type: PDF, Word, HTML, Text")):
    """
    List all ingested documents with optional type filtering.

    Returns:
      A list of document metadata (id, filename, type, chunk count, date).
    """
    docs = await document_service.list_documents(file_type=file_type)
    return {"documents": docs, "total": len(docs)}


@app.delete("/documents/{doc_id}", tags=["Knowledge Base"])
async def delete_document(doc_id: int):
    """
    Delete a document and all its associated chunks from Qdrant.

    This is a cascading delete:
      1. Mark the document as 'deleted' in PostgreSQL.
      2. Remove all vectors with matching source_file from Qdrant.

    Raises:
      404: Document not found or already deleted.
      503: Qdrant unavailable for cleanup.
    """
    filename = await document_service.delete_document(doc_id)
    if not filename:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Cascade: remove vectors from Qdrant
    try:
        if qdrant_search.is_connected and qdrant_search._client:
            from qdrant_client.models import Filter, FieldCondition, MatchValue
            qdrant_search._client.delete(
                collection_name=settings.qdrant_collection_name,
                points_selector=Filter(
                    must=[
                        FieldCondition(
                            key="source_file",
                            match=MatchValue(value=filename),
                        )
                    ]
                ),
            )
            logger.info("Deleted Qdrant vectors for '%s'.", filename)
    except Exception as exc:
        logger.error("Failed to delete Qdrant vectors for '%s': %s", filename, exc)
        # Don't fail — the DB record is already soft-deleted

    return {"status": "deleted", "filename": filename}


# ──────────────────────────────────────────────────────────────
# /sessions — Multi-Conversation Management (Phase 5)
# ──────────────────────────────────────────────────────────────

@app.get("/sessions", tags=["Chat"])
async def list_sessions():
    """
    List all chat sessions with their auto-numbered titles and last activity.

    Returns:
      A list of sessions: [{session_id, title, last_active, message_count}]
    """
    sessions = await history_service.list_sessions()
    return {"sessions": sessions}


@app.delete("/sessions/{session_id}", tags=["Chat"])
async def delete_session(session_id: str):
    """
    Delete a conversation and all its messages permanently.

    Returns:
      Number of messages deleted.
    """
    count = await history_service.clear_history(session_id)
    return {"session_id": session_id, "messages_deleted": count}


# ──────────────────────────────────────────────────────────────
# /history — Chat History Persistence (Phase 4)
# ──────────────────────────────────────────────────────────────

@app.get("/history/{session_id}", tags=["Chat"])
async def get_history(session_id: str):
    """
    Retrieve chat history for a given session.

    Returns:
      A list of messages with role, content, and timestamp.
    """
    messages = await history_service.get_history(session_id)
    return {"session_id": session_id, "messages": messages}


# ──────────────────────────────────────────────────────────────
# /sync — Local Folder Sync (Phase 4)
# Scans the /data/ingest mount and ingests any new files.
# ──────────────────────────────────────────────────────────────

@app.post("/sync", tags=["Knowledge Base"])
async def sync_folder():
    """
    Synchronize the local /data/ingest folder with the AI's Knowledge Base.

    This operation is intelligent:
      - Adds new files.
      - Updates existing files if their size changed.
      - Removes files from the AI if they were deleted from the folder.

    Returns:
      A summary with counts of files found, skipped, ingested, and failed.
    """
    # Fetch all existing documents (active ones)
    existing_docs = await document_service.list_documents()

    result = await sync_service.sync_ingest_folder(
        ingestion_gateway=ingestion_gateway,
        existing_docs=existing_docs,
        on_ingested=document_service.record_document,
        on_deleted=delete_document,  # Use the local delete_document logic for Qdrant cleanup
    )

    return {
        "status": "ok",
        "total_files_found": result.total_files_found,
        "already_indexed": result.already_indexed,
        "newly_ingested": result.newly_ingested,
        "failed": result.failed,
        "errors": result.errors,
    }
