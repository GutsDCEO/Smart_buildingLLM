"""
Re-Ranker — Cross-encoder precision filter for RAG retrieval.

Design:
  - SRP: Only re-scores and filters search results. No search or generation.
  - DIP: Depends on SearchResult dataclass, not on Qdrant internals.
  - Resource-aware: Uses cross-encoder/ms-marco-MiniLM-L-6-v2 (22M params)
    which runs comfortably on Mac Mini i5 6-core / 16GB RAM.

How it works:
  1. QA Agent over-retrieves top-15 from Qdrant (fast, approximate).
  2. This re-ranker scores each chunk against the original question using
     a cross-encoder (slow but precise — processes question+chunk jointly).
  3. Returns only the top-N most relevant chunks, filtering out noise.

Why this matters:
  Vector search finds "topically similar" chunks but can't judge if a chunk
  actually *answers* the question. A cross-encoder can — it sees both the
  question and the chunk together, producing a much more accurate relevance score.
"""

from __future__ import annotations

import logging
from typing import Optional

from sentence_transformers import CrossEncoder

from config import settings
from qdrant_search import SearchResult

logger = logging.getLogger(__name__)


class Reranker:
    """
    Cross-encoder re-ranker for precision filtering of RAG results.

    Loaded once at startup as a singleton. Thread-safe for read-only inference.
    """

    def __init__(self) -> None:
        self._model: CrossEncoder | None = None
        self._model_name: str = settings.reranker_model_name

    @property
    def is_loaded(self) -> bool:
        """Check if the cross-encoder model has been loaded."""
        return self._model is not None

    def load_model(self) -> None:
        """
        Load the cross-encoder model into memory.

        Call once at application startup. On Mac Mini i5 (16GB RAM),
        ms-marco-MiniLM-L-6-v2 uses ~100MB and loads in <2 seconds.
        """
        if self._model is not None:
            logger.info("Reranker model already loaded, skipping.")
            return

        logger.info("Loading reranker model: %s", self._model_name)
        self._model = CrossEncoder(self._model_name)
        logger.info("Reranker model loaded successfully.")

    def rerank(
        self,
        question: str,
        results: list[SearchResult],
        top_n: Optional[int] = None,
    ) -> list[SearchResult]:
        """
        Re-score search results using the cross-encoder and return the top-N.

        Args:
            question: The original user question.
            results: Raw search results from Qdrant (over-retrieved).
            top_n: Number of results to keep after re-ranking.
                   Defaults to settings.reranked_top_n.

        Returns:
            The top-N results, sorted by cross-encoder score (highest first).
            If the model is not loaded, returns the original results truncated
            to top_n (graceful degradation).
        """
        top_n = top_n or settings.reranked_top_n

        if not results:
            return []

        if self._model is None:
            logger.warning(
                "Reranker not loaded — returning raw results (top-%d).",
                top_n,
            )
            return results[:top_n]

        # Build question-chunk pairs for the cross-encoder
        pairs = [(question, r.text) for r in results]

        logger.info(
            "Re-ranking %d results down to top-%d...",
            len(results),
            top_n,
        )

        scores = self._model.predict(pairs)

        # Pair results with scores and sort by cross-encoder score
        scored_results = sorted(
            zip(results, scores),
            key=lambda x: x[1],
            reverse=True,
        )

        # Log the score distribution for diagnostics
        if scored_results:
            top_score = scored_results[0][1]
            bottom_score = scored_results[-1][1]
            logger.info(
                "Re-rank complete. Score range: %.4f → %.4f. Keeping top-%d.",
                top_score,
                bottom_score,
                top_n,
            )

        return [result for result, _score in scored_results[:top_n]]


# Singleton instance — loaded once at startup
reranker = Reranker()
