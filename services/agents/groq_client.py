"""
Groq Client — Async HTTP wrapper for the Groq Cloud LLM API.

Design:
  - LSP: Implements LLMProvider ABC — fully substitutable with any other provider.
  - SRP: Only handles LLM text generation via Groq. No routing or search.
  - DIP: Callers depend on LLMProvider interface, never on this concrete class.
  - OWASP A02: API key read from settings (env var), never hardcoded.
  - OWASP A09: Errors logged with context, generic messages returned to callers.

Groq uses the OpenAI-compatible REST API:
  POST https://api.groq.com/openai/v1/chat/completions
  Authorization: Bearer {GROQ_API_KEY}

DeepSeek R1 Support:
  DeepSeek reasoning models emit <think>...</think> blocks containing the
  model's internal chain-of-thought. These are logged for debugging but
  stripped from the final answer returned to users.
"""

from __future__ import annotations

import json
import logging
import re
from typing import AsyncGenerator, Optional

import httpx

from config import settings
from llm_interface import LLMProvider

logger = logging.getLogger(__name__)

# Groq OpenAI-compatible endpoint
_GROQ_BASE_URL = "https://api.groq.com"
_CHAT_ENDPOINT = "/openai/v1/chat/completions"

# Regex to strip DeepSeek <think>...</think> reasoning blocks
_THINK_BLOCK_PATTERN = re.compile(r"<think>.*?</think>", re.DOTALL)


class GroqClient(LLMProvider):
    """Async HTTP client for Groq's /openai/v1/chat/completions endpoint."""

    def __init__(self) -> None:
        self._model: str = settings.groq_model
        self._timeout: int = settings.groq_timeout_seconds
        self._api_key: str = settings.groq_api_key
        self._headers: dict = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        self._client: httpx.AsyncClient | None = None

    # ── Lifecycle (LLMProvider) ──────────────────────────────

    async def startup(self) -> None:
        """Create a persistent HTTP connection pool. Call once at lifespan startup."""
        self._client = httpx.AsyncClient(
            base_url=_GROQ_BASE_URL,
            headers=self._headers,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )
        logger.info("Groq client pool created (model=%s).", self._model)

    async def shutdown(self) -> None:
        """Close the connection pool. Call at lifespan shutdown."""
        if self._client:
            await self._client.aclose()
            self._client = None
            logger.info("Groq client pool closed.")

    # ── Generation (LLMProvider) ─────────────────────────────

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        enable_thinking: bool = False,
    ) -> str:
        """
        Send a prompt to Groq and return the generated text (non-streaming).

        For DeepSeek R1 / Qwen3 models, strips <think>...</think> reasoning blocks
        from the response. The thinking trace is logged at DEBUG level.

        When enable_thinking=True, passes reasoning_effort='default' to activate
        Qwen3's native Chain-of-Thought mode.

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system instruction.
            temperature: Sampling temperature (lower = more deterministic).
            enable_thinking: If True, activate Qwen3 CoT reasoning (~3x tokens).

        Returns:
            The generated text response (without thinking tokens).

        Raises:
            RuntimeError: If Groq is unreachable, returns an error, or times out.
        """
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
            "stream": False,
        }
        if enable_thinking:
            payload["reasoning_effort"] = "default"
            logger.info("Thinking mode ACTIVE on non-streaming call.")

        logger.info(
            "Calling Groq [%s] with prompt_len=%d",
            self._model,
            len(prompt),
        )

        try:
            client = self._get_client()
            response = await client.post(_CHAT_ENDPOINT, json=payload)
            response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("Cannot reach Groq API: %s", exc)
            raise RuntimeError("LLM service (Groq) is not reachable.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Groq request timed out after %ds", self._timeout)
            raise RuntimeError("LLM request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            await self._handle_http_error(exc)

        data = response.json()
        raw_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not raw_text:
            logger.warning("Groq returned an empty response.")
            raise RuntimeError("LLM returned an empty response.")

        # Strip DeepSeek thinking tokens and return clean answer
        clean_text = self._strip_thinking_tokens(raw_text)

        logger.info("Groq response received (%d chars).", len(clean_text))
        return clean_text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
        enable_thinking: bool = False,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Groq one-by-one (SSE format).

        When enable_thinking=True, Qwen3 activates its internal CoT reasoning
        pass before answering. The <think>...</think> blocks are stripped in
        real-time so the user only sees the clean final answer.

        Note on token cost: thinking mode uses ~2-3x more tokens per request.
        On Groq's free tier (6,000 TPM for qwen3-32b), this can trigger 429s
        for back-to-back questions. The UI shows a persistent warning when active.
        """
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
            "stream": True,
        }
        if enable_thinking:
            payload["reasoning_effort"] = "default"
            logger.info("Thinking mode ACTIVE (reasoning_effort=default) — expect higher token usage.")

        logger.info(
            "Streaming from Groq [%s] prompt_len=%d",
            self._model,
            len(prompt),
        )

        token_count = 0
        in_think_block = False
        think_buffer: list[str] = []

        try:
            client = self._get_client()
            async with client.stream("POST", _CHAT_ENDPOINT, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    raw = line[6:]  # strip "data: " prefix

                    if raw == "[DONE]":
                        break

                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed Groq line: %.80s", line)
                        continue

                    token = (
                        data.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if not token:
                        continue

                    # Real-time <think> block filtering for DeepSeek R1
                    if "<think>" in token:
                        in_think_block = True
                        think_buffer.append(token)
                        continue

                    if in_think_block:
                        think_buffer.append(token)
                        if "</think>" in token:
                            in_think_block = False
                            thinking_trace = "".join(think_buffer)
                            logger.debug(
                                "DeepSeek thinking trace (%d chars): %.200s...",
                                len(thinking_trace),
                                thinking_trace,
                            )
                            think_buffer.clear()
                        continue

                    token_count += 1
                    yield token

        except httpx.ConnectError as exc:
            logger.error("Cannot reach Groq API: %s", exc)
            raise RuntimeError("LLM service (Groq) is not reachable.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Groq stream timed out after %ds", self._timeout)
            raise RuntimeError("LLM request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            await self._handle_http_error(exc)

        if token_count == 0:
            logger.warning("Groq streaming returned zero tokens.")
            raise RuntimeError("LLM returned an empty response.")

        logger.info("Groq stream complete (%d tokens).", token_count)

    # ── Health (LLMProvider) ─────────────────────────────────

    async def is_reachable(self) -> bool:
        """Check if Groq API is reachable (used by /health endpoint)."""
        try:
            client = self._get_client()
            response = await client.get("/openai/v1/models")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return False

    # ── Private Helpers ──────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        """Return the pooled client, or a one-shot fallback for tests."""
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=_GROQ_BASE_URL,
            headers=self._headers,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )

    @staticmethod
    def _build_messages(prompt: str, system_prompt: Optional[str]) -> list[dict]:
        """Build the OpenAI-format messages array."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    @staticmethod
    def _strip_thinking_tokens(text: str) -> str:
        """
        Remove DeepSeek R1 <think>...</think> reasoning blocks from output.

        The thinking trace is valuable for debugging but should never be
        shown to end users. It is logged at DEBUG level before stripping.
        """
        if "<think>" not in text:
            return text

        # Log the thinking trace for debugging
        think_matches = _THINK_BLOCK_PATTERN.findall(text)
        for match in think_matches:
            logger.debug("DeepSeek thinking: %.500s", match)

        clean = _THINK_BLOCK_PATTERN.sub("", text).strip()
        logger.info(
            "Stripped %d thinking block(s) from response.",
            len(think_matches),
        )
        return clean

    @staticmethod
    async def _handle_http_error(exc: httpx.HTTPStatusError) -> None:
        """Centralized HTTP error handling — maps status codes to user-safe messages."""
        status = exc.response.status_code
        try:
            await exc.response.aread()
            error_body = exc.response.text
        except Exception:
            error_body = "<unavailable>"

        if status == 401:
            logger.error("Groq: Invalid API key (401). Body: %s", error_body)
            raise RuntimeError("LLM authentication failed. Check GROQ_API_KEY.") from exc
        elif status == 429:
            logger.error("Groq: Rate limit reached (429). Body: %s", error_body)
            raise RuntimeError("LLM rate limit reached. Try again shortly.") from exc
        else:
            logger.error("Groq HTTP %d Error: %s", status, error_body)
            raise RuntimeError(f"LLM service error (HTTP {status})") from exc


# Singleton instance (used only when LLM_PROVIDER=groq)
groq_client = GroqClient()
