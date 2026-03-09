"""
Embedding Service — FastAPI Entry Point.

Thin Controller pattern: this module only handles HTTP concerns.
All business logic is delegated to the embedder, Qdrant store, and DB logger.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from config import settings
from models import EmbedRequest, EmbedResponse, HealthResponse, StoredChunkInfo
from embedder import embedder
from qdrant_store import vector_store
from db import connect_db, disconnect_db, log_ingestion

# ──────────────────────────────────────────────────────────────
# Logging Setup
# ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────────
# Lifespan — load model and connect to stores on startup
# ──────────────────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Load the embedding model and connect to Qdrant/Postgres at startup."""
    logger.info("Starting Embedding Service...")

    # Load the sentence-transformers model
    embedder.load_model()

    # Connect to Qdrant (ensure collection exists)
    try:
        vector_store.connect()
    except Exception as exc:
        logger.warning("Qdrant not available at startup: %s", exc)

    # Connect to PostgreSQL (for metadata logging)
    await connect_db()

    logger.info("Embedding Service ready.")
    yield

    # Shutdown
    await disconnect_db()
    logger.info("Embedding Service shut down.")


# ──────────────────────────────────────────────────────────────
# Application Factory
# ──────────────────────────────────────────────────────────────
app = FastAPI(
    title="Smart Building AI — Embedding Service",
    description="Converts text chunks into vector embeddings and stores them in Qdrant.",
    version="0.1.0",
    lifespan=lifespan,
)


# ──────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health_check() -> HealthResponse:
    """Health check for Docker and load balancers."""
    return HealthResponse(model_loaded=embedder.is_loaded)


@app.post("/embed", response_model=EmbedResponse, tags=["Embedding"])
async def embed_chunks(request: EmbedRequest) -> EmbedResponse:
    """
    Embed a batch of text chunks and store them in Qdrant.

    Flow:
      1. Extract texts from chunks
      2. Generate embeddings via sentence-transformers
      3. Upsert vectors + metadata into Qdrant
      4. Log the batch to PostgreSQL
      5. Return vector IDs

    Raises:
      400: Empty or invalid chunk data.
      503: Qdrant is not connected.
      500: Unexpected error.
    """
    chunks = request.chunks

    if not chunks:
        raise HTTPException(status_code=400, detail="No chunks provided.")

    # --- Step 1: Extract texts ---
    texts = [chunk.text for chunk in chunks]
    source_file = chunks[0].source_file

    # --- Step 2: Generate embeddings ---
    try:
        vectors = embedder.embed(texts)
    except RuntimeError as exc:
        logger.error("Embedding model error: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    # --- Step 3: Store in Qdrant ---
    if not vector_store.is_connected:
        raise HTTPException(
            status_code=503,
            detail="Qdrant is not connected. Start Qdrant and restart the service.",
        )

    try:
        vector_ids = vector_store.upsert_chunks(chunks, vectors)
    except Exception as exc:
        logger.exception("Qdrant upsert failed for '%s'", source_file)
        raise HTTPException(
            status_code=500,
            detail="Failed to store vectors in Qdrant.",
        ) from exc

    # --- Step 4: Log to PostgreSQL (non-blocking, graceful) ---
    await log_ingestion(
        source_file=source_file,
        chunk_count=len(chunks),
        vector_ids=vector_ids,
    )

    # --- Step 5: Build response ---
    stored_chunks = [
        StoredChunkInfo(
            chunk_index=chunk.chunk_index,
            vector_id=vid,
            source_file=chunk.source_file,
        )
        for chunk, vid in zip(chunks, vector_ids)
    ]

    logger.info(
        "Embedding complete: %s → %d chunks stored.",
        source_file,
        len(stored_chunks),
    )

    return EmbedResponse(
        source_file=source_file,
        chunks_stored=len(stored_chunks),
        stored_chunks=stored_chunks,
    )
