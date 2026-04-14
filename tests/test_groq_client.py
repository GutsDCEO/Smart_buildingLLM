"""
Unit Tests — GroqClient

FIRST Principles:
  F - Fast:        No real network calls. All HTTP mocked via unittest.mock.
  I - Independent: Each test sets up its own mock, no shared state.
  R - Repeatable:  Same result in any environment (no GROQ_API_KEY needed).
  S - Self-Validating: Clear assert statements, no manual inspection.
  T - Timely:      Written alongside the feature (TDD).

Tests:
  1. test_generate_returns_text        — happy path non-streaming call
  2. test_generate_stream_yields_tokens — happy path streaming tokens
  3. test_generate_raises_on_auth_error — 401 raises RuntimeError
  4. test_generate_raises_on_rate_limit — 429 raises RuntimeError
  5. test_is_reachable_true            — 200 from /models → True
  6. test_is_reachable_false           — ConnectError → False
  7. test_factory_selects_groq         — factory returns GroqClient for LLM_PROVIDER=groq
  8. test_factory_selects_ollama       — factory returns OllamaClient for LLM_PROVIDER=ollama
  9. test_factory_raises_missing_key   — factory raises if GROQ_API_KEY is empty with groq provider
"""

import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

import pytest
import httpx

# ---------------------------------------------------------------------------
# Path fix: tests/ is at project root, agents modules live in services/agents/
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_groq_response(content: str) -> dict:
    """Build a minimal Groq/OpenAI-compatible non-streaming response."""
    return {
        "choices": [{"message": {"content": content}}]
    }


def _make_stream_lines(tokens: list[str]) -> list[str]:
    """Build SSE lines as Groq streams them."""
    lines = []
    for t in tokens:
        chunk = {"choices": [{"delta": {"content": t}}]}
        lines.append(f"data: {json.dumps(chunk)}")
    lines.append("data: [DONE]")
    return lines


# ---------------------------------------------------------------------------
# GroqClient — non-streaming
# ---------------------------------------------------------------------------

class TestGroqClientGenerate:

    @pytest.mark.asyncio
    async def test_generate_returns_text(self) -> None:
        """Happy path: Groq returns 200 with generated text."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = _make_groq_response("HVAC runs 08:00–18:00.")
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_test"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            result = await client.generate("What is the HVAC schedule?")

        assert result == "HVAC runs 08:00–18:00."
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_generate_raises_on_auth_error(self) -> None:
        """401 from Groq raises RuntimeError with a safe message (OWASP A09)."""
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=mock_request, response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_invalid"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            with pytest.raises(RuntimeError, match="authentication failed"):
                await client.generate("What is the HVAC schedule?")

    @pytest.mark.asyncio
    async def test_generate_raises_on_rate_limit(self) -> None:
        """429 from Groq raises RuntimeError mentioning rate limit."""
        mock_request = MagicMock()
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "429", request=mock_request, response=mock_response
        )

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_test"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            with pytest.raises(RuntimeError, match="rate limit"):
                await client.generate("test query")


# ---------------------------------------------------------------------------
# GroqClient — streaming
# ---------------------------------------------------------------------------

class TestGroqClientStream:

    @pytest.mark.asyncio
    async def test_generate_stream_yields_tokens(self) -> None:
        """Happy path: streaming yields individual tokens in order."""
        tokens = ["The ", "HVAC ", "runs ", "all day."]
        sse_lines = _make_stream_lines(tokens)

        # Build a mock async context manager for client.stream()
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_lines():
            for line in sse_lines:
                yield line

        mock_response.aiter_lines = fake_aiter_lines

        mock_stream_ctx = MagicMock()
        mock_stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        mock_stream_ctx.__aexit__ = AsyncMock(return_value=False)

        mock_client = MagicMock()
        mock_client.stream = MagicMock(return_value=mock_stream_ctx)

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_test"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            collected: list[str] = []
            async for token in client.generate_stream("What is the HVAC schedule?"):
                collected.append(token)

        assert collected == tokens


# ---------------------------------------------------------------------------
# GroqClient — health check
# ---------------------------------------------------------------------------

class TestGroqClientHealth:

    @pytest.mark.asyncio
    async def test_is_reachable_true(self) -> None:
        """200 from /openai/v1/models returns True."""
        mock_response = MagicMock()
        mock_response.status_code = 200

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_response)

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_test"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            assert await client.is_reachable() is True

    @pytest.mark.asyncio
    async def test_is_reachable_false_on_connect_error(self) -> None:
        """ConnectError while reaching Groq returns False (graceful degradation)."""
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(side_effect=httpx.ConnectError("unreachable"))

        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30
            mock_settings.groq_api_key = "gsk_test"

            from groq_client import GroqClient
            client = GroqClient()
            client._client = mock_client

            assert await client.is_reachable() is False


# ---------------------------------------------------------------------------
# LLM Factory
# ---------------------------------------------------------------------------

class TestLLMFactory:

    def test_factory_selects_groq(self) -> None:
        """LLM_PROVIDER=groq with a valid key returns a GroqClient."""
        with patch("llm_factory.settings") as mock_settings:
            mock_settings.llm_provider = "groq"
            mock_settings.groq_api_key = "gsk_test"
            mock_settings.groq_model = "llama-3.1-70b-versatile"
            mock_settings.groq_timeout_seconds = 30

            from llm_factory import create_llm_client
            from groq_client import GroqClient

            client = create_llm_client()
            assert isinstance(client, GroqClient)

    def test_factory_selects_ollama(self) -> None:
        """LLM_PROVIDER=ollama returns an OllamaClient."""
        with patch("llm_factory.settings") as mock_settings:
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_host = "http://localhost:11434"
            mock_settings.ollama_model = "llama3.1"

            from llm_factory import create_llm_client
            from ollama_client import OllamaClient

            client = create_llm_client()
            assert isinstance(client, OllamaClient)

    def test_factory_raises_if_groq_key_missing(self) -> None:
        """LLM_PROVIDER=groq with empty GROQ_API_KEY raises RuntimeError at startup."""
        with patch("llm_factory.settings") as mock_settings:
            mock_settings.llm_provider = "groq"
            mock_settings.groq_api_key = ""  # No key set

            from llm_factory import create_llm_client

            with pytest.raises(RuntimeError, match="GROQ_API_KEY"):
                create_llm_client()
