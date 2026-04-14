"""
Groq Client — Async HTTP wrapper for the Groq Cloud LLM API.

Design:
  - SRP: Only handles LLM text generation via Groq. No routing or search.
  - DIP: Implements the same duck-typed interface as OllamaClient,
         so callers (qa_agent, router_agent) require zero changes.
  - OWASP A02: API key read from settings (env var), never hardcoded.
  - OWASP A09: Errors logged with context, generic messages returned to callers.

Groq uses the OpenAI-compatible REST API:
  POST https://api.groq.com/openai/v1/chat/completions
  Authorization: Bearer {GROQ_API_KEY}

No extra SDK needed — httpx is already in requirements.txt.
"""

from __future__ import annotations

import json
import logging
from typing import AsyncGenerator, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

# Groq OpenAI-compatible endpoint
_GROQ_BASE_URL = "https://api.groq.com"
_CHAT_ENDPOINT = "/openai/v1/chat/completions"


class GroqClient:
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

    def _get_client(self) -> httpx.AsyncClient:
        """Return the pooled client, or a one-shot fallback for tests."""
        if self._client is not None:
            return self._client
        return httpx.AsyncClient(
            base_url=_GROQ_BASE_URL,
            headers=self._headers,
            timeout=httpx.Timeout(self._timeout, connect=10.0),
        )

    def _build_messages(self, prompt: str, system_prompt: Optional[str]) -> list[dict]:
        """Build the OpenAI-format messages array."""
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        return messages

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Send a prompt to Groq and return the generated text (non-streaming).

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system instruction.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            The generated text response.

        Raises:
            RuntimeError: If Groq is unreachable, returns an error, or times out.
        """
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
            "stream": False,
        }

        logger.info(
            "Calling Groq [%s] with prompt_len=%d",
            self._model,
            len(prompt),
        )

        logger.debug(
            "Groq API Request: %s %s | Model: %s",
            _GROQ_BASE_URL, _CHAT_ENDPOINT, self._model
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
            # Capture the exact error body from Groq (Quality Rule ⑦)
            status = exc.response.status_code
            error_body = exc.response.text
            
            if status == 401:
                logger.error("Groq: Invalid API key (401). Body: %s", error_body)
                raise RuntimeError("LLM authentication failed. Check GROQ_API_KEY.") from exc
            elif status == 429:
                logger.error("Groq: Rate limit reached (429). Body: %s", error_body)
                raise RuntimeError("LLM rate limit reached. Try again shortly.") from exc
            else:
                logger.error("Groq HTTP %d Error: %s", status, error_body)
                raise RuntimeError(f"LLM service error (HTTP {status})") from exc

        data = response.json()
        generated_text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )

        if not generated_text:
            logger.warning("Groq returned an empty response.")
            raise RuntimeError("LLM returned an empty response.")

        logger.info("Groq response received (%d chars).", len(generated_text))
        return generated_text

    async def generate_stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens from Groq one-by-one (SSE format).

        Yields individual tokens as they arrive, compatible with the /chat
        SSE endpoint that streams responses to the Chat UI.

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system instruction.
            temperature: Sampling temperature.

        Yields:
            Individual text tokens as strings.

        Raises:
            RuntimeError: If Groq is unreachable or returns an error.
        """
        payload = {
            "model": self._model,
            "messages": self._build_messages(prompt, system_prompt),
            "temperature": temperature,
            "stream": True,
        }

        logger.info(
            "Streaming from Groq [%s] prompt_len=%d",
            self._model,
            len(prompt),
        )

        url = _CHAT_ENDPOINT
        token_count = 0

        try:
            client = self._get_client()
            async with client.stream("POST", url, json=payload) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or not line.startswith("data: "):
                        continue

                    raw = line[6:]  # strip "data: " prefix

                    # Groq sends "data: [DONE]" to signal stream end
                    if raw == "[DONE]":
                        break

                    try:
                        data = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Skipping malformed Groq line: %.80s", line)
                        continue

                    # OpenAI-compatible delta format
                    token = (
                        data.get("choices", [{}])[0]
                        .get("delta", {})
                        .get("content", "")
                    )
                    if token:
                        token_count += 1
                        yield token

        except httpx.ConnectError as exc:
            logger.error("Cannot reach Groq API: %s", exc)
            raise RuntimeError("LLM service (Groq) is not reachable.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Groq stream timed out after %ds", self._timeout)
            raise RuntimeError("LLM request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            error_body = exc.response.text
            
            if status == 401:
                logger.error("Groq: Invalid API key (401). Body: %s", error_body)
                raise RuntimeError("LLM authentication failed.") from exc
            elif status == 429:
                logger.error("Groq: Rate limit (429). Body: %s", error_body)
                raise RuntimeError("LLM rate limit reached.") from exc
            else:
                logger.error("Groq HTTP %d Stream Error: %s", status, error_body)
                raise RuntimeError(f"LLM stream error (HTTP {status})") from exc

        if token_count == 0:
            logger.warning("Groq streaming returned zero tokens.")
            raise RuntimeError("LLM returned an empty response.")

        logger.info("Groq stream complete (%d tokens).", token_count)

    async def is_reachable(self) -> bool:
        """Check if Groq API is reachable (used by /health endpoint)."""
        try:
            client = self._get_client()
            # Groq has a models endpoint compatible with OpenAI
            response = await client.get("/openai/v1/models")
            return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError):
            return False


# Singleton instance (used only when LLM_PROVIDER=groq)
groq_client = GroqClient()
