"""
LLM Factory — returns the correct LLM client based on the LLM_PROVIDER env var.

Design:
  - OCP: Adding a new provider (e.g., OpenAI) requires one new elif here only.
  - DIP: All callers receive a duck-typed object — never a concrete class.
  - Fail-Fast: Misconfiguration (missing API key) raises at startup, not at query time.
"""

import logging

from config import settings

logger = logging.getLogger(__name__)


def create_llm_client():
    """
    Instantiate and return the LLM client for the configured provider.

    Returns:
        An object with the interface: startup(), shutdown(), generate(),
        generate_stream(), is_reachable() — matching both OllamaClient
        and GroqClient.

    Raises:
        RuntimeError: If provider is unknown, or if Groq is selected
                      but GROQ_API_KEY is not set.
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
            "Expected 'ollama' or 'groq'. Check your .env file."
        )
