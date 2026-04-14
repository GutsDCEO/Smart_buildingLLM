"""
TDD Tests — Q&A Agent

Follows FIRST principles:
  Fast        — Mocks all I/O (Embedding Service, Qdrant, Ollama). No network.
  Independent — Fresh mocks per test. No shared state between tests.
  Repeatable  — Deterministic mock responses.
  Self-Validating — Explicit assertions on answer text, citation count, fields.
  Timely      — Written alongside the feature.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from qa_agent import QAAgent
from models import AskRequest
from qdrant_search import SearchResult

# ─── Shared test fixtures ───────────────────────────────────────────────────

SAMPLE_VECTOR = [0.1] * 384  # Simulated 384-dim all-MiniLM vector

SAMPLE_RESULTS = [
    SearchResult(
        text="The HVAC unit in Building A operates on a seasonal schedule.",
        source_file="HVAC_Manual_2024.pdf",
        page_number=3,
        chunk_index=0,
        token_count=15,
        score=0.91,
    ),
    SearchResult(
        text="Winter mode runs from November to March at reduced fan speed.",
        source_file="HVAC_Manual_2024.pdf",
        page_number=4,
        chunk_index=1,
        token_count=13,
        score=0.85,
    ),
]

LLM_ANSWER = (
    "The HVAC unit operates on a seasonal schedule. "
    "In winter mode (November–March), it runs at reduced fan speed. "
    "[Source: HVAC_Manual_2024.pdf, Page 3]"
)


@pytest.fixture
def agent() -> QAAgent:
    """Provide a fresh QAAgent for every test."""
    return QAAgent()


# ──────────────────────────────────────────────────────────────
# Happy Path — Full RAG pipeline
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_rag_pipeline_returns_answer_with_citations(agent):
    """Full pipeline: vectorize → search → generate should produce answer + citations."""
    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search._client", new=MagicMock()),  # truthy → is_connected=True
        patch("qa_agent.qdrant_search.search", return_value=SAMPLE_RESULTS),
        patch("qa_agent.ollama_client.generate", new_callable=AsyncMock, return_value=LLM_ANSWER),
    ):
        result = await agent.answer(AskRequest(question="What is the HVAC schedule?"))

    assert result.answer == LLM_ANSWER
    assert len(result.citations) == 2
    assert result.citations[0].source_file == "HVAC_Manual_2024.pdf"
    assert result.citations[0].page_number == 3
    assert result.citations[0].relevance_score == pytest.approx(0.91, abs=0.001)


@pytest.mark.asyncio
async def test_citations_are_sorted_by_relevance(agent):
    """Citations should preserve the search-result relevance order (highest first)."""
    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search._client", new=MagicMock()),  # truthy → is_connected=True
        patch("qa_agent.qdrant_search.search", return_value=SAMPLE_RESULTS),
        patch("qa_agent.ollama_client.generate", new_callable=AsyncMock, return_value=LLM_ANSWER),
    ):
        result = await agent.answer(AskRequest(question="Tell me about HVAC modes."))

    scores = [c.relevance_score for c in result.citations]
    assert scores == sorted(scores, reverse=True), "Citations should be in descending relevance order"


# ──────────────────────────────────────────────────────────────
# No search results
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_search_results_returns_graceful_message(agent):
    """When Qdrant has no matching chunks, should return a helpful no-data message."""
    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search._client", new=MagicMock()),  # truthy → is_connected=True
        patch("qa_agent.qdrant_search.search", return_value=[]),
    ):
        result = await agent.answer(AskRequest(question="What is the certified capacity?"))

    assert len(result.citations) == 0
    assert "documents" in result.answer.lower() or "ingested" in result.answer.lower()


# ──────────────────────────────────────────────────────────────
# Context prompt construction
# ──────────────────────────────────────────────────────────────

def test_build_context_prompt_contains_source_and_text(agent):
    """Context prompt must include source file name and chunk text."""
    prompt = agent._build_context_prompt("What is HVAC mode?", SAMPLE_RESULTS)

    assert "HVAC_Manual_2024.pdf" in prompt
    assert "seasonal schedule" in prompt
    assert "Question: What is HVAC mode?" in prompt
    assert "Answer:" in prompt


def test_build_context_prompt_includes_page_number(agent):
    """Context prompt should include page number when available."""
    prompt = agent._build_context_prompt("Test question?", SAMPLE_RESULTS)

    assert "Page 3" in prompt
    assert "Page 4" in prompt


def test_build_context_prompt_handles_missing_page(agent):
    """Prompt should not crash when page_number is None."""
    result_no_page = SearchResult(
        text="Some text without a page number.",
        source_file="general.pdf",
        page_number=None,
        chunk_index=0,
        token_count=7,
        score=0.7,
    )
    prompt = agent._build_context_prompt("Test?", [result_no_page])
    assert "general.pdf" in prompt
    assert "Page None" not in prompt


# ──────────────────────────────────────────────────────────────
# Resilience — Embedding Service down
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_embedding_service_down_raises_runtime_error(agent):
    """If the Embedding Service is unreachable, should raise RuntimeError (caught by controller)."""
    with patch.object(
        agent,
        "_embed_question",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Embedding Service is not reachable."),
    ):
        with pytest.raises(RuntimeError, match="Embedding Service"):
            await agent.answer(AskRequest(question="What is the energy consumption?"))


# ──────────────────────────────────────────────────────────────
# Resilience — Qdrant disconnected
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_qdrant_not_connected_raises_runtime_error(agent):
    """If Qdrant is not connected, should raise RuntimeError (caught by controller)."""
    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search._client", new=None),  # None → is_connected=False
    ):
        with pytest.raises(RuntimeError, match="Qdrant"):
            await agent.answer(AskRequest(question="What is the fire safety plan?"))
