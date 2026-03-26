"""
TDD Tests — Router Agent

Follows FIRST principles:
  Fast        — Mocks the Ollama HTTP client. No real LLM calls.
  Independent — Each test sets up its own mock. No shared state.
  Repeatable  — Deterministic mock responses. Same result everywhere.
  Self-Validating — Clear assertions on intent and confidence.
  Timely      — Written alongside the feature.
"""
import json
import pytest
from unittest.mock import AsyncMock, patch

from router_agent import RouterAgent
from models import IntentType, RouteRequest


@pytest.fixture
def agent() -> RouterAgent:
    """Provide a fresh RouterAgent for every test."""
    return RouterAgent()


def _mock_ollama(raw_response: str):
    """Helper: patch ollama_client.generate with a fixed string response."""
    return patch(
        "router_agent.ollama_client.generate",
        new_callable=AsyncMock,
        return_value=raw_response,
    )


# ──────────────────────────────────────────────────────────────
# Happy Path — factual_qa classification
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_building_question_classified_as_factual_qa(agent):
    """Building questions should be classified as factual_qa."""
    raw = json.dumps({"intent": "factual_qa", "confidence": 0.97})

    with _mock_ollama(raw):
        result = await agent.classify(RouteRequest(question="What is the HVAC schedule?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.97, abs=0.01)


@pytest.mark.asyncio
async def test_maintenance_question_classified_as_factual_qa(agent):
    """Maintenance-related questions should be classified as factual_qa."""
    raw = json.dumps({"intent": "factual_qa", "confidence": 0.92})

    with _mock_ollama(raw):
        result = await agent.classify(RouteRequest(question="When was the last fire alarm test?"))

    assert result.intent == IntentType.FACTUAL_QA


# ──────────────────────────────────────────────────────────────
# Happy Path — out_of_scope classification
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_off_topic_question_classified_as_out_of_scope(agent):
    """Completely unrelated questions should be classified as out_of_scope."""
    raw = json.dumps({"intent": "out_of_scope", "confidence": 0.99})

    with _mock_ollama(raw):
        result = await agent.classify(RouteRequest(question="What is the best recipe for pasta?"))

    assert result.intent == IntentType.OUT_OF_SCOPE
    assert result.confidence == pytest.approx(0.99, abs=0.01)


# ──────────────────────────────────────────────────────────────
# Resilience — LLM returns malformed JSON
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_malformed_json_defaults_to_factual_qa(agent):
    """If the LLM returns garbage, router should fail-open to factual_qa."""
    with _mock_ollama("Sorry, I cannot classify this."):
        result = await agent.classify(RouteRequest(question="What time is it?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.0, abs=0.01)


@pytest.mark.asyncio
async def test_markdown_wrapped_json_is_parsed(agent):
    """The LLM sometimes wraps responses in ```json ... ``` — must be handled."""
    raw = "```json\n{\"intent\": \"factual_qa\", \"confidence\": 0.88}\n```"

    with _mock_ollama(raw):
        result = await agent.classify(RouteRequest(question="What is the energy report?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.88, abs=0.01)


@pytest.mark.asyncio
async def test_unknown_intent_defaults_to_factual_qa(agent):
    """An unrecognized intent string should map to factual_qa (fail-open)."""
    raw = json.dumps({"intent": "general_chat", "confidence": 0.5})

    with _mock_ollama(raw):
        result = await agent.classify(RouteRequest(question="Hello!"))

    assert result.intent == IntentType.FACTUAL_QA


# ──────────────────────────────────────────────────────────────
# Resilience — LLM is down
# ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ollama_unreachable_defaults_to_factual_qa(agent):
    """If Ollama is down, router should fail-open to factual_qa (not crash)."""
    with patch(
        "router_agent.ollama_client.generate",
        new_callable=AsyncMock,
        side_effect=RuntimeError("LLM service is not reachable."),
    ):
        result = await agent.classify(RouteRequest(question="What is the HVAC filter interval?"))

    assert result.intent == IntentType.FACTUAL_QA
    assert result.confidence == pytest.approx(0.0, abs=0.01)
