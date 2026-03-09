"""
Embedding Engine — converts text chunks into vector embeddings.

Uses sentence-transformers (all-MiniLM-L6-v2) locally on CPU.
The model is loaded once at startup (singleton) for efficiency.

Design:
  - SRP: Only handles text → vector conversion.
  - No storage logic — that belongs to qdrant_client.py.
"""

from __future__ import annotations

import logging

from sentence_transformers import SentenceTransformer

from config import settings

logger = logging.getLogger(__name__)


class Embedder:
    """Singleton wrapper around the sentence-transformers model."""

    def __init__(self) -> None:
        self._model: SentenceTransformer | None = None

    @property
    def is_loaded(self) -> bool:
        """Check if the model has been loaded."""
        return self._model is not None

    def load_model(self) -> None:
        """
        Load the embedding model into memory.

        Call this once at application startup (lifespan event).
        """
        if self._model is not None:
            logger.info("Model already loaded, skipping.")
            return

        logger.info("Loading embedding model: %s", settings.embedding_model_name)
        self._model = SentenceTransformer(settings.embedding_model_name)
        logger.info(
            "Model loaded. Vector dimension: %d",
            self._model.get_sentence_embedding_dimension(),
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        """
        Convert a batch of texts into vector embeddings.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of float vectors, one per input text.

        Raises:
            RuntimeError: If the model hasn't been loaded yet.
        """
        if self._model is None:
            raise RuntimeError(
                "Embedding model not loaded. Call load_model() at startup."
            )

        if not texts:
            logger.warning("Empty text list provided for embedding.")
            return []

        logger.info("Embedding %d text(s)...", len(texts))
        embeddings = self._model.encode(
            texts,
            batch_size=32,
            show_progress_bar=False,
            normalize_embeddings=True,
        )

        # Convert numpy arrays to plain Python lists for JSON serialization
        result = [vec.tolist() for vec in embeddings]
        logger.info("Embedding complete. Generated %d vectors.", len(result))
        return result


# Singleton instance — import this across the application.
embedder = Embedder()
