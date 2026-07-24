"""
TDD Tests — Router Agent

Follows FIRST principles:
  Fast        — Mocks the LLM client. No real LLM calls.
  Independent — Each test sets up its own mock. No shared state.
  Repeatable  — Deterministic mock responses. Same result everywhere.
  Self-Validating — Clear assertions on intent and confidence.
  Timely      — Written alongside the feature.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from router_agent import RouterAgent
from models import IntentType, RouteRequest


@pytest.fixture
def agent() -> RouterAgent:
    """Provide a fresh RouterAgent for every test."""
    mock_llm = MagicMock()
    return RouterAgent(llm_client=mock_llm)


# ──────────────────────────────────────────────────────────────
# Happy Path — factual_qa classification
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_building_question_classified_as_factual_qa(agent):
    """Building questions should be classified as factual_qa."""
    raw = json.dumps({"intent": "factual_qa", "confidence": 0.97})
    agent._llm.generate = AsyncMock(return_value=raw)
    result = await agent.classify(RouteRequest(question="What is the HVAC schedule?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.97, abs=0.01)


@pytest.mark.asyncio
async def test_maintenance_question_classified_as_factual_qa(agent):
    """Maintenance-related questions should be classified as factual_qa."""
    raw = json.dumps({"intent": "factual_qa", "confidence": 0.92})
    agent._llm.generate = AsyncMock(return_value=raw)
    result = await agent.classify(RouteRequest(question="When was the last fire alarm test?"))

    assert result.intent == IntentType.FACTUAL_QA


# ──────────────────────────────────────────────────────────────
# Happy Path — out_of_scope classification
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_off_topic_question_classified_as_out_of_scope(agent):
    """Completely unrelated questions should be classified as out_of_scope."""
    raw = json.dumps({"intent": "out_of_scope", "confidence": 0.99})
    agent._llm.generate = AsyncMock(return_value=raw)
    result = await agent.classify(RouteRequest(question="What is the best recipe for pasta?"))

    assert result.intent == IntentType.OUT_OF_SCOPE
    assert result.confidence == pytest.approx(0.99, abs=0.01)


# ──────────────────────────────────────────────────────────────
# Resilience — LLM returns malformed JSON
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_defaults_to_factual_qa(agent):
    """If the LLM returns garbage, router should fail-open to factual_qa."""
    agent._llm.generate = AsyncMock(return_value="Sorry, I cannot classify this.")
    result = await agent.classify(RouteRequest(question="What time is it?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_markdown_wrapped_json_is_parsed(agent):
    """The LLM sometimes wraps responses in ```json ... ``` — must be handled."""
    raw = "```json\n{\"intent\": \"factual_qa\", \"confidence\": 0.88}\n```"
    agent._llm.generate = AsyncMock(return_value=raw)
    result = await agent.classify(RouteRequest(question="What is the energy report?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.88, abs=0.01)


@pytest.mark.asyncio
async def test_unknown_intent_defaults_to_factual_qa(agent):
    """An unrecognized intent string should map to factual_qa (fail-open)."""
    raw = json.dumps({"intent": "general_chat", "confidence": 0.5})
    agent._llm.generate = AsyncMock(return_value=raw)
    result = await agent.classify(RouteRequest(question="Hello!"))

    assert result.intent == IntentType.FACTUAL_QA


# ──────────────────────────────────────────────────────────────
# Resilience — LLM is down
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_unreachable_defaults_to_factual_qa(agent):
    """If the LLM is down, router should fail-open to factual_qa (not crash)."""
    agent._llm.generate = AsyncMock(side_effect=RuntimeError("LLM service is not reachable."))
    result = await agent.classify(RouteRequest(question="What is the HVAC filter interval?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.0, abs=0.01)
