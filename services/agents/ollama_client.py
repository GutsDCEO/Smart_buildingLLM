"""
Ollama Client — Async HTTP wrapper for the local LLM engine.

Design:
  - SRP: Only handles LLM text generation. No routing or search.
  - DIP: Abstracts the Ollama API behind a clean interface.
  - Resilient: Configurable timeout and structured error handling.
  - OWASP A09: Errors are logged but never expose internals to the user.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)


class OllamaClient:
    """Async HTTP client for Ollama's /api/generate endpoint."""

    def __init__(self) -> None:
        self._base_url: str = settings.ollama_host
        self._model: str = settings.ollama_model
        self._timeout: int = settings.ollama_timeout_seconds

    @property
    def base_url(self) -> str:
        """The Ollama server URL."""
        return self._base_url

    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Send a prompt to Ollama and return the generated text.

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system instruction.
            temperature: Sampling temperature (lower = more deterministic).

        Returns:
            The generated text response.

        Raises:
            RuntimeError: If Ollama is unreachable or returns an error.
        """
        payload: dict = {
            "model": self._model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
            },
        }

        if system_prompt:
            payload["system"] = system_prompt

        logger.info(
            "Calling Ollama [%s] with model=%s, prompt_len=%d",
            self._base_url,
            self._model,
            len(prompt),
        )

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, connect=10.0),
            ) as client:
                response = await client.post(
                    f"{self._base_url}/api/generate",
                    json=payload,
                )
                response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("Cannot reach Ollama at %s: %s", self._base_url, exc)
            raise RuntimeError(
                "LLM service is not reachable. Ensure Ollama is running."
            ) from exc
        except httpx.TimeoutException as exc:
            logger.error("Ollama request timed out after %ds", self._timeout)
            raise RuntimeError(
                "LLM request timed out. The model may be loading or the query is too complex."
            ) from exc
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama returned HTTP %d: %s", exc.response.status_code, exc)
            raise RuntimeError(
                "LLM service returned an error."
            ) from exc

        data = response.json()
        generated_text = data.get("response", "").strip()

        if not generated_text:
            logger.warning("Ollama returned an empty response.")
            raise RuntimeError("LLM returned an empty response.")

        logger.info("Ollama response received (%d chars).", len(generated_text))
        return generated_text

    async def is_reachable(self) -> bool:
        """Check if Ollama is reachable (for health checks)."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{self._base_url}/api/tags")
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


# Singleton instance
ollama_client = OllamaClient()
