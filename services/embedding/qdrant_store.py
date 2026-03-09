"""
Qdrant Vector Storage Client — manages collection lifecycle and vector upserts.

Design:
  - SRP: Only handles Qdrant operations.
  - Fail early: validates connection at startup.
  - No business logic — just storage I/O.
"""

from __future__ import annotations

import logging
import uuid

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    PointStruct,
    VectorParams,
)

from config import settings
from models import ChunkInput

logger = logging.getLogger(__name__)


class VectorStore:
    """Client wrapper for Qdrant vector database operations."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None

    @property
    def is_connected(self) -> bool:
        """Check if the client has been initialized."""
        return self._client is not None

    def connect(self) -> None:
        """
        Initialize the Qdrant client and ensure the collection exists.

        Call this once at application startup (lifespan event).
        """
        logger.info(
            "Connecting to Qdrant at %s:%d",
            settings.qdrant_host,
            settings.qdrant_port,
        )

        self._client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )

        self._ensure_collection()
        logger.info("Qdrant connection established.")

    def _ensure_collection(self) -> None:
        """Create the vector collection if it doesn't already exist."""
        collection_name = settings.qdrant_collection_name

        existing = [c.name for c in self._client.get_collections().collections]

        if collection_name in existing:
            logger.info("Collection '%s' already exists.", collection_name)
            return

        logger.info("Creating collection '%s'...", collection_name)
        self._client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(
                size=settings.qdrant_vector_size,
                distance=Distance.COSINE,
            ),
        )
        logger.info("Collection '%s' created.", collection_name)

    def upsert_chunks(
        self,
        chunks: list[ChunkInput],
        vectors: list[list[float]],
    ) -> list[str]:
        """
        Store chunk vectors and metadata in Qdrant.

        Args:
            chunks: The text chunk metadata.
            vectors: The corresponding embedding vectors.

        Returns:
            List of generated point IDs (UUIDs).

        Raises:
            RuntimeError: If the client hasn't been connected yet.
            ValueError: If chunks and vectors have mismatched lengths.
        """
        if self._client is None:
            raise RuntimeError(
                "Qdrant client not connected. Call connect() at startup."
            )

        if len(chunks) != len(vectors):
            raise ValueError(
                f"Chunk count ({len(chunks)}) does not match "
                f"vector count ({len(vectors)})"
            )

        points: list[PointStruct] = []
        point_ids: list[str] = []

        for chunk, vector in zip(chunks, vectors):
            point_id = str(uuid.uuid4())
            point_ids.append(point_id)

            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "text": chunk.text,
                        "source_file": chunk.source_file,
                        "page_number": chunk.page_number,
                        "chunk_index": chunk.chunk_index,
                        "token_count": chunk.token_count,
                        "start_char": chunk.start_char,
                        "end_char": chunk.end_char,
                    },
                )
            )

        self._client.upsert(
            collection_name=settings.qdrant_collection_name,
            points=points,
        )

        logger.info(
            "Upserted %d vectors to collection '%s'.",
            len(points),
            settings.qdrant_collection_name,
        )

        return point_ids


# Singleton instance — import this across the application.
vector_store = VectorStore()
