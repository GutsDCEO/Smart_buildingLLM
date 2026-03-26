"""
Qdrant Search Client — Read-only similarity search for the Q&A Agent.

Design:
  - SRP: Only handles vector search operations. No upserts.
  - Returns structured chunk data with metadata for citation building.
  - Separate from the Embedding Service's VectorStore (write-focused).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from qdrant_client import QdrantClient
from qdrant_client.models import ScoredPoint

from config import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SearchResult:
    """A single search result with chunk data and relevance score."""

    text: str
    source_file: str
    page_number: int | None
    chunk_index: int
    token_count: int
    score: float  # Cosine similarity (0.0–1.0)


class QdrantSearch:
    """Read-only Qdrant client for similarity search."""

    def __init__(self) -> None:
        self._client: QdrantClient | None = None

    @property
    def is_connected(self) -> bool:
        """Check if the client has been initialized."""
        return self._client is not None

    def connect(self) -> None:
        """Initialize the Qdrant client. Call once at startup."""
        logger.info(
            "Connecting to Qdrant (search) at %s:%d",
            settings.qdrant_host,
            settings.qdrant_port,
        )
        self._client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
        )
        logger.info("Qdrant search client connected.")

    def search(
        self,
        query_vector: list[float],
        top_k: int | None = None,
    ) -> list[SearchResult]:
        """
        Find the most similar chunks to the query vector.

        Args:
            query_vector: The embedded query vector.
            top_k: Number of results to return (default: from settings).

        Returns:
            List of SearchResult sorted by relevance (highest first).

        Raises:
            RuntimeError: If the client hasn't been connected.
        """
        if self._client is None:
            raise RuntimeError(
                "Qdrant search client not connected. Call connect() at startup."
            )

        k = top_k or settings.top_k_results

        logger.info(
            "Searching collection '%s' for top-%d results...",
            settings.qdrant_collection_name,
            k,
        )

        scored_points: list[ScoredPoint] = self._client.query_points(
            collection_name=settings.qdrant_collection_name,
            query=query_vector,
            limit=k,
        ).points

        results = [
            SearchResult(
                text=point.payload.get("text", ""),
                source_file=point.payload.get("source_file", "unknown"),
                page_number=point.payload.get("page_number"),
                chunk_index=point.payload.get("chunk_index", 0),
                token_count=point.payload.get("token_count", 0),
                score=point.score,
            )
            for point in scored_points
        ]

        logger.info(
            "Found %d results. Top score: %.4f",
            len(results),
            results[0].score if results else 0.0,
        )

        return results


# Singleton instance
qdrant_search = QdrantSearch()
