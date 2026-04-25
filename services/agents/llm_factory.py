"""
LLM Factory — Returns the correct LLM client based on configuration.

Design:
  - OCP: Adding a new provider requires only one new elif block here.
  - DIP: Returns LLMProvider interface — callers never know the concrete type.
  - Fail-Fast: Misconfiguration raises at startup, not at query time.
  - ISP: Factory only creates clients — no other responsibilities.

Supported providers:
  - "groq"   → GroqClient  (Groq Cloud API — DeepSeek R1, Llama, etc.)
  - "ollama" → OllamaClient (Local LLM engine)

To add a new provider (e.g., OpenAI, Anthropic):
  1. Create a new client class implementing LLMProvider ABC
  2. Add an elif block below
  3. Add config fields to AgentsSettings
  That's it — zero changes to qa_agent, router, or main.py.
"""

import logging

from config import settings
from llm_interface import LLMProvider

logger = logging.getLogger(__name__)


def create_llm_client() -> LLMProvider:
    """
    Instantiate and return the LLM client for the configured provider.

    Returns:
        An LLMProvider implementation matching the LLM_PROVIDER env var.

    Raises:
        RuntimeError: If provider is unknown, or if required credentials
                      are missing (fail-fast at startup).
    """
    provider = settings.llm_provider.strip().lower()

    if provider == "groq":
        # Validate key exists before creating client (Fail-Fast — Quality Rule ④)
        if not settings.groq_api_key:
            raise RuntimeError(
                "LLM_PROVIDER=groq but GROQ_API_KEY is not set. "
                "Add GROQ_API_KEY to your .env file. "
                "Get a free key at https://console.groq.com/keys"
            )
        from groq_client import GroqClient
        logger.info(
            "LLM provider: Groq (model=%s, timeout=%ds)",
            settings.groq_model,
            settings.groq_timeout_seconds,
        )
        return GroqClient()

    elif provider == "ollama":
        from ollama_client import OllamaClient
        logger.info(
            "LLM provider: Ollama (host=%s, model=%s)",
            settings.ollama_host,
            settings.ollama_model,
        )
        return OllamaClient()

    else:
        raise RuntimeError(
            f"Unknown LLM_PROVIDER='{provider}'. "
            "Supported: 'groq', 'ollama'. Check your .env file."
        )
