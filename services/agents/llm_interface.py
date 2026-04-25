"""
LLM Provider Interface — Abstract Base Class for all LLM backends.

Design:
  - DIP: All consumers (QAAgent, RouterAgent) depend on this abstraction,
         never on concrete clients like GroqClient or OllamaClient.
  - LSP: Any class implementing LLMProvider is fully substitutable.
  - OCP: Adding a new provider (OpenAI, Anthropic, Google) requires only
         a new class implementing this interface — zero changes elsewhere.
  - ISP: The interface is minimal — only methods that ALL providers must support.

Usage:
  from llm_interface import LLMProvider

  class MyNewClient(LLMProvider):
      async def generate(...) -> str: ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import AsyncGenerator


class LLMProvider(ABC):
    """
    Contract that every LLM backend must implement.

    Lifecycle:
      1. startup()         — called once at application boot
      2. generate()        — non-streaming text generation
      3. generate_stream() — streaming token generation (SSE)
      4. is_reachable()    — health check for /health endpoint
      5. shutdown()        — called once at application teardown
    """

    # ── Lifecycle ────────────────────────────────────────────

    @abstractmethod
    async def startup(self) -> None:
        """
        Initialize connection pools, load configs, validate credentials.

        Called once during FastAPI lifespan startup.
        Raise RuntimeError if the provider cannot be initialized.
        """

    @abstractmethod
    async def shutdown(self) -> None:
        """
        Close connection pools and release resources.

        Called once during FastAPI lifespan shutdown.
        """

    # ── Generation ───────────────────────────────────────────

    @abstractmethod
    async def generate(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> str:
        """
        Generate a complete text response (non-streaming).

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system-level instruction.
            temperature: Sampling temperature (0.0 = deterministic).

        Returns:
            The generated text response.

        Raises:
            RuntimeError: If the provider is unreachable, rate-limited,
                          or returns an error.
        """

    @abstractmethod
    async def generate_stream(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
    ) -> AsyncGenerator[str, None]:
        """
        Stream tokens one-by-one from the LLM.

        Used by the /chat SSE endpoint for real-time streaming.

        Args:
            prompt: The user/context prompt.
            system_prompt: Optional system-level instruction.
            temperature: Sampling temperature.

        Yields:
            Individual text tokens as strings.

        Raises:
            RuntimeError: If the provider is unreachable or errors mid-stream.
        """
        # This yield is required to make the abstractmethod a valid generator.
        # Concrete implementations will replace this entirely.
        yield ""  # pragma: no cover

    # ── Health ───────────────────────────────────────────────

    @abstractmethod
    async def is_reachable(self) -> bool:
        """
        Check if the LLM backend is reachable and responding.

        Used by the /health endpoint. Must not raise exceptions —
        return False on any failure.
        """
