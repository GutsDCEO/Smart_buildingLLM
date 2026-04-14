"""
TDD Tests — OllamaClient.generate_stream() (token streaming).

Follows FIRST principles:
  Fast        — Mocks httpx entirely. No real network calls.
  Independent — Fresh OllamaClient instance per test.
  Repeatable  — Deterministic mock line sequences.
  Self-Validating — Asserts exact token order and error types.
  Timely      — Written alongside the feature.
"""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from ollama_client import OllamaClient


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _make_stream_lines(*tokens: str, done_at_end: bool = True) -> list[bytes]:
    """Build the list of NDJSON lines that Ollama would stream."""
    lines = [json.dumps({"response": tok, "done": False}).encode() for tok in tokens]
    if done_at_end:
        lines.append(json.dumps({"response": "", "done": True}).encode())
    return lines


async def _async_line_iter(lines: list[bytes]):
    """Simulate httpx's aiter_lines() as an async generator."""
    for line in lines:
        yield line.decode()


# ─── Happy Path ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_stream_yields_tokens_in_order():
    """Tokens must arrive in exact order from the mocked stream."""
    client = OllamaClient()
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = lambda: _async_line_iter(
        _make_stream_lines("The", " HVAC", " schedule", ".")
    )
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_http = MagicMock()
    mock_http.stream = MagicMock(return_value=mock_response)
    mock_http.__aenter__ = AsyncMock(return_value=mock_http)
    mock_http.__aexit__ = AsyncMock(return_value=False)

    with patch.object(client, "_get_client", return_value=mock_http):
        tokens = []
        async for tok in client.generate_stream("Test prompt"):
            tokens.append(tok)

    assert tokens == ["The", " HVAC", " schedule", "."]


@pytest.mark.asyncio
async def test_generate_stream_skips_empty_tokens():
    """Empty response tokens (intermediate Ollama keep-alives) must be skipped."""
    client = OllamaClient()

    lines = [
        json.dumps({"response": "Hello", "done": False}).encode(),
        json.dumps({"response": "",      "done": False}).encode(),  # ← empty, skip
        json.dumps({"response": " World", "done": False}).encode(),
        json.dumps({"response": "",      "done": True}).encode(),
    ]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = lambda: _async_line_iter(lines)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_http = MagicMock()
    mock_http.stream = MagicMock(return_value=mock_response)

    with patch.object(client, "_get_client", return_value=mock_http):
        tokens = []
        async for tok in client.generate_stream("Test"):
            tokens.append(tok)

    assert tokens == ["Hello", " World"]


# ─── Error Cases ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_generate_stream_raises_on_connect_error():
    """ConnectError from httpx must surface as RuntimeError (OWASP A09)."""
    import httpx
    client = OllamaClient()
    mock_http = MagicMock()
    mock_http.stream = MagicMock(side_effect=httpx.ConnectError("refused"))

    with patch.object(client, "_get_client", return_value=mock_http):
        with pytest.raises(RuntimeError, match="not reachable"):
            async for _ in client.generate_stream("Test"):
                pass


@pytest.mark.asyncio
async def test_generate_stream_raises_on_timeout():
    """TimeoutException from httpx must surface as RuntimeError."""
    import httpx
    client = OllamaClient()
    mock_http = MagicMock()
    mock_http.stream = MagicMock(side_effect=httpx.TimeoutException("timeout"))

    with patch.object(client, "_get_client", return_value=mock_http):
        with pytest.raises(RuntimeError, match="timed out"):
            async for _ in client.generate_stream("Test"):
                pass


@pytest.mark.asyncio
async def test_generate_stream_raises_on_zero_tokens():
    """A stream that emits only done=True (no tokens) must raise RuntimeError."""
    client = OllamaClient()
    lines = [json.dumps({"response": "", "done": True}).encode()]

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.aiter_lines = lambda: _async_line_iter(lines)
    mock_response.__aenter__ = AsyncMock(return_value=mock_response)
    mock_response.__aexit__ = AsyncMock(return_value=False)

    mock_http = MagicMock()
    mock_http.stream = MagicMock(return_value=mock_response)

    with patch.object(client, "_get_client", return_value=mock_http):
        with pytest.raises(RuntimeError, match="empty"):
            async for _ in client.generate_stream("Test"):
                pass


# ─── Connection Pool ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_startup_creates_client_pool():
    """startup() must create an httpx.AsyncClient available via _get_client."""
    import httpx
    client = OllamaClient()
    assert client._client is None  # not created yet

    await client.startup()
    assert isinstance(client._client, httpx.AsyncClient)

    await client.shutdown()
    assert client._client is None  # properly closed


def test_get_client_fallback_without_startup():
    """_get_client() must return a fresh client even without startup() (test safety)."""
    import httpx
    client = OllamaClient()
    assert client._client is None
    fallback = client._get_client()
    assert isinstance(fallback, httpx.AsyncClient)
