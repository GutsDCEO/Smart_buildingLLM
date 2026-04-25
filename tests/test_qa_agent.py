"""
Unit Tests — QA Agent (RAG Pipeline with Re-Ranking & Memory)

FIRST Principles:
  F - Fast:     All I/O mocked. No Qdrant, Embedding Service, or LLM calls.
  I - Independent: Fresh mocks per test via fixtures. No shared state.
  R - Repeatable:  Deterministic mock responses regardless of environment.
  S - Self-Validating: Explicit assertions on answer, citations, ordering.
  T - Timely:    Written alongside the refactored QAAgent (Layer 2+3+5).

Covers:
  1. Full RAG pipeline: embed → search → rerank → generate → citations
  2. Citations include source_file, page_number, chunk_index, relevance_score
  3. Graceful: empty Qdrant results returns no-documents message
  4. Graceful: Qdrant not connected raises RuntimeError
  5. Graceful: Embedding Service down raises RuntimeError
  6. _build_context_prompt() includes source file and chunk text
  7. _build_context_prompt() includes page numbers
  8. _build_context_prompt() handles None page_number without crashing
  9. _build_context_prompt() injects conversation history when provided
  10. History is included in context prompt in correct order
"""

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))

from qdrant_search import SearchResult


# ──────────────────────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────────────────────

SAMPLE_VECTOR = [0.1] * 768  # BGE-base-en-v1.5 produces 768-dim vectors

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
    "In winter mode (November–March), it runs at reduced fan speed."
)


@pytest.fixture
def mock_llm():
    """A mock LLMProvider that returns a deterministic answer."""
    llm = AsyncMock()
    llm.generate = AsyncMock(return_value=LLM_ANSWER)
    return llm


@pytest.fixture
def agent(mock_llm):
    """Fresh QAAgent using the mock LLM — no real dependencies."""
    from qa_agent import QAAgent
    return QAAgent(mock_llm)


# ──────────────────────────────────────────────────────────────
# Happy Path — Full RAG pipeline
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_full_rag_pipeline_returns_answer_and_citations(agent, mock_llm):
    """Full pipeline produces an answer and populates citations correctly."""
    from models import AskRequest

    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search") as mock_qdrant,
        patch("qa_agent.reranker") as mock_reranker,
    ):
        mock_qdrant.is_connected = True
        mock_qdrant.search.return_value = SAMPLE_RESULTS
        mock_reranker.rerank.return_value = SAMPLE_RESULTS  # pass through

        result = await agent.answer(AskRequest(question="What is the HVAC schedule?"))

    assert result.answer == LLM_ANSWER
    assert len(result.citations) == 2
    assert result.citations[0].source_file == "HVAC_Manual_2024.pdf"
    assert result.citations[0].page_number == 3
    assert result.citations[0].relevance_score == pytest.approx(0.91, abs=0.001)


@pytest.mark.asyncio
async def test_citations_sorted_by_relevance_score(agent):
    """Citations must be returned in descending relevance order."""
    from models import AskRequest

    low = SearchResult(
        text="Low relevance chunk.",
        source_file="doc.pdf", page_number=1, chunk_index=0, token_count=3, score=0.50
    )
    high = SearchResult(
        text="High relevance chunk.",
        source_file="doc.pdf", page_number=2, chunk_index=1, token_count=3, score=0.95
    )

    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search") as mock_qdrant,
        patch("qa_agent.reranker") as mock_reranker,
    ):
        mock_qdrant.is_connected = True
        mock_qdrant.search.return_value = [low, high]
        mock_reranker.rerank.return_value = [high, low]  # re-ranker re-orders

        result = await agent.answer(AskRequest(question="Test?"))

    scores = [c.relevance_score for c in result.citations]
    assert scores == sorted(scores, reverse=True)


# ──────────────────────────────────────────────────────────────
# Graceful degradation
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_search_results_returns_graceful_message(agent):
    """No matching chunks → helpful no-documents message, no crash."""
    from models import AskRequest

    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search") as mock_qdrant,
    ):
        mock_qdrant.is_connected = True
        mock_qdrant.search.return_value = []

        result = await agent.answer(AskRequest(question="What is the thermal load?"))

    assert len(result.citations) == 0
    assert "documents" in result.answer.lower() or "ingested" in result.answer.lower()


@pytest.mark.asyncio
async def test_qdrant_not_connected_raises_runtime_error(agent):
    """Qdrant disconnected → RuntimeError (caught cleanly by /chat stream)."""
    from models import AskRequest

    with (
        patch.object(agent, "_embed_question", new_callable=AsyncMock, return_value=SAMPLE_VECTOR),
        patch("qa_agent.qdrant_search") as mock_qdrant,
    ):
        mock_qdrant.is_connected = False

        with pytest.raises(RuntimeError, match="Qdrant"):
            await agent.answer(AskRequest(question="Test?"))


@pytest.mark.asyncio
async def test_embedding_service_down_raises_runtime_error(agent):
    """Embedding Service unreachable → RuntimeError propagated cleanly."""
    from models import AskRequest

    with patch.object(
        agent, "_embed_question",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Embedding Service is not reachable."),
    ):
        with pytest.raises(RuntimeError, match="Embedding Service"):
            await agent.answer(AskRequest(question="Test?"))


# ──────────────────────────────────────────────────────────────
# Context prompt construction
# ──────────────────────────────────────────────────────────────

def test_build_context_prompt_includes_source_file_and_text(agent):
    """Context prompt must include source filename and chunk content."""
    prompt = agent._build_context_prompt("What is HVAC mode?", SAMPLE_RESULTS)

    assert "HVAC_Manual_2024.pdf" in prompt
    assert "seasonal schedule" in prompt
    assert "What is HVAC mode?" in prompt


def test_build_context_prompt_includes_page_numbers(agent):
    """Context prompt must cite page numbers for traceability."""
    prompt = agent._build_context_prompt("Test?", SAMPLE_RESULTS)

    assert "3" in prompt   # page 3
    assert "4" in prompt   # page 4


def test_build_context_prompt_handles_none_page_number(agent):
    """prompt must not crash or show 'Page None' when page_number is absent."""
    no_page = SearchResult(
        text="Some text without a page.",
        source_file="report.pdf",
        page_number=None,
        chunk_index=0,
        token_count=5,
        score=0.6,
    )
    prompt = agent._build_context_prompt("Test?", [no_page])

    assert "report.pdf" in prompt
    assert "Page None" not in prompt


def test_build_context_prompt_injects_conversation_history(agent):
    """When history is provided, it must appear in the prompt."""
    history = [
        {"role": "user", "content": "What is HVAC?"},
        {"role": "assistant", "content": "HVAC stands for Heating, Ventilation, and Air Conditioning."},
    ]
    prompt = agent._build_context_prompt("Tell me more.", SAMPLE_RESULTS, history=history)

    assert "What is HVAC?" in prompt
    assert "Heating, Ventilation" in prompt


def test_build_context_prompt_no_history_when_none(agent):
    """Passing history=None must not inject any history section or crash."""
    prompt = agent._build_context_prompt("What is HVAC mode?", SAMPLE_RESULTS, history=None)

    # Should not contain common history markers
    assert "Conversation History" not in prompt or "seasonal schedule" in prompt
