"""
Unit Tests — Reranker (Cross-Encoder Precision Filter)

FIRST Principles:
  F - Fast:         CrossEncoder.predict() is mocked — no model download or inference.
  I - Independent:  Each test constructs its own SearchResult fixtures.
  R - Repeatable:   Mocked scores are deterministic.
  S - Self-Validating: Asserts on order, count, and graceful degradation.
  T - Timely:       Written alongside the Layer 3 re-ranker implementation.

Covers:
  1. rerank() sorts results by cross-encoder score descending
  2. rerank() returns only top_n results
  3. rerank() degrades gracefully when model not loaded (returns raw top-n)
  4. rerank() on empty input returns empty list
  5. rerank() with top_n > len(results) returns all results
  6. Reranker.is_loaded reflects model load state
  7. Reranker.load_model() is idempotent (calling twice doesn't double-load)
"""

import sys
import os
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))

from qdrant_search import SearchResult


def _make_result(text: str, score: float = 0.5) -> SearchResult:
    """Helper: build a SearchResult with minimal required fields."""
    return SearchResult(
        text=text,
        source_file="test.pdf",
        page_number=1,
        chunk_index=0,
        token_count=len(text.split()),
        score=score,
    )


# ──────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────

class TestRerankerSorting:

    def _make_reranker_with_mock_model(self):
        """Produce a Reranker whose CrossEncoder.predict() returns controlled scores."""
        with patch("reranker.settings") as mock_settings:
            mock_settings.reranker_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_settings.reranked_top_n = 5
            from reranker import Reranker
            r = Reranker()

        mock_model = MagicMock()
        r._model = mock_model
        return r, mock_model

    def test_rerank_sorts_by_cross_encoder_score_descending(self):
        """Results must be returned highest-score first, not by vector similarity order."""
        r, mock_model = self._make_reranker_with_mock_model()

        results = [
            _make_result("Chunk A — low relevance", score=0.9),
            _make_result("Chunk B — high relevance", score=0.7),
            _make_result("Chunk C — medium relevance", score=0.8),
        ]
        # Cross-encoder disagrees with vector scores: B is actually most relevant
        mock_model.predict.return_value = [0.1, 0.95, 0.5]

        reranked = r.rerank("What is the HVAC schedule?", results, top_n=3)

        assert reranked[0].text == "Chunk B — high relevance"
        assert reranked[1].text == "Chunk C — medium relevance"
        assert reranked[2].text == "Chunk A — low relevance"

    def test_rerank_returns_only_top_n(self):
        """rerank() must truncate to top_n results."""
        r, mock_model = self._make_reranker_with_mock_model()

        results = [_make_result(f"Chunk {i}") for i in range(10)]
        mock_model.predict.return_value = list(range(10, 0, -1))  # 10,9,8,...

        reranked = r.rerank("query", results, top_n=3)

        assert len(reranked) == 3

    def test_rerank_gracefully_degrades_when_model_not_loaded(self):
        """If the model hasn't loaded (permission error etc.), return raw results[:top_n]."""
        with patch("reranker.settings") as mock_settings:
            mock_settings.reranker_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_settings.reranked_top_n = 5
            from reranker import Reranker
            r = Reranker()
        # _model is None (not loaded)

        results = [_make_result(f"Chunk {i}", score=float(i)) for i in range(8)]
        reranked = r.rerank("query", results, top_n=3)

        assert len(reranked) == 3
        assert reranked[0].text == "Chunk 0"  # Original order preserved

    def test_rerank_empty_input_returns_empty_list(self):
        """Empty results list must not raise — return empty list."""
        r, _ = self._make_reranker_with_mock_model()

        reranked = r.rerank("query", [], top_n=5)
        assert reranked == []

    def test_rerank_top_n_larger_than_results_returns_all(self):
        """When top_n > len(results), all results should be returned."""
        r, mock_model = self._make_reranker_with_mock_model()

        results = [_make_result(f"Chunk {i}") for i in range(3)]
        mock_model.predict.return_value = [0.9, 0.8, 0.7]

        reranked = r.rerank("query", results, top_n=10)

        assert len(reranked) == 3


class TestRerankerLifecycle:

    def test_is_loaded_false_before_load(self):
        """Freshly constructed Reranker.is_loaded must be False."""
        with patch("reranker.settings") as mock_settings:
            mock_settings.reranker_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_settings.reranked_top_n = 5
            from reranker import Reranker
            r = Reranker()

        assert r.is_loaded is False

    def test_is_loaded_true_after_load(self):
        """After load_model(), is_loaded must be True."""
        with (
            patch("reranker.settings") as mock_settings,
            patch("reranker.CrossEncoder") as mock_cross_encoder,
        ):
            mock_settings.reranker_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_settings.reranked_top_n = 5
            from reranker import Reranker
            r = Reranker()
            r.load_model()

        assert r.is_loaded is True

    def test_load_model_is_idempotent(self):
        """Calling load_model() twice must not trigger CrossEncoder() twice."""
        with (
            patch("reranker.settings") as mock_settings,
            patch("reranker.CrossEncoder") as mock_cross_encoder,
        ):
            mock_settings.reranker_model_name = "cross-encoder/ms-marco-MiniLM-L-6-v2"
            mock_settings.reranked_top_n = 5
            from reranker import Reranker
            r = Reranker()
            r.load_model()
            r.load_model()  # second call should be a no-op

        mock_cross_encoder.assert_called_once()
