"""
Unit Tests — LLMProvider Interface Compliance (SOLID LSP + DIP)

FIRST Principles:
  F - Fast:         No real network calls. Inspects class structure only.
  I - Independent:  Each assertion is self-contained.
  R - Repeatable:   Pure static analysis — always deterministic.
  S - Self-Validating: Pass/fail without manual inspection.
  T - Timely:       Written to enforce the Layer 0 SOLID contract.

Covers:
  1. LLMProvider is a proper ABC with abstract methods
  2. GroqClient declares all required abstract methods
  3. OllamaClient declares all required abstract methods
  4. A class missing any method cannot be instantiated
  5. Both clients are substitutable for LLMProvider (Liskov Substitution)
  6. llm_factory returns an LLMProvider instance (Dependency Inversion)
"""

import sys
import os
import inspect
from unittest.mock import patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))


# ──────────────────────────────────────────────────────────────
# Required interface contract
# ──────────────────────────────────────────────────────────────

REQUIRED_METHODS = {"startup", "shutdown", "generate", "generate_stream", "is_reachable"}


class TestLLMProviderABC:

    def test_llm_provider_is_abstract(self):
        """LLMProvider must be an ABC — cannot be directly instantiated."""
        from llm_interface import LLMProvider
        with pytest.raises(TypeError):
            LLMProvider()  # type: ignore[abstract]

    def test_llm_provider_has_all_required_abstract_methods(self):
        """LLMProvider must declare all methods that clients are expected to implement."""
        from llm_interface import LLMProvider
        abstract_methods = LLMProvider.__abstractmethods__
        for method in REQUIRED_METHODS:
            assert method in abstract_methods, (
                f"LLMProvider is missing abstract method: {method}"
            )


class TestGroqClientCompliance:

    def test_groq_client_implements_llm_provider(self):
        """GroqClient must be a subclass of LLMProvider (LSP compliance)."""
        from llm_interface import LLMProvider
        from groq_client import GroqClient
        assert issubclass(GroqClient, LLMProvider)

    def test_groq_client_implements_all_abstract_methods(self):
        """GroqClient must implement every method defined in LLMProvider."""
        from groq_client import GroqClient
        for method in REQUIRED_METHODS:
            assert hasattr(GroqClient, method), (
                f"GroqClient is missing method: {method}"
            )
            assert callable(getattr(GroqClient, method)), (
                f"GroqClient.{method} is not callable"
            )

    def test_groq_client_can_be_instantiated(self):
        """GroqClient must be instantiable (all abstract methods implemented)."""
        with patch("groq_client.settings") as mock_settings:
            mock_settings.groq_api_key = "gsk_test"
            mock_settings.groq_model = "qwen/qwen3-32b"
            mock_settings.groq_timeout_seconds = 60

            from groq_client import GroqClient
            client = GroqClient()
            assert client is not None

    def test_groq_client_generate_is_coroutine(self):
        """generate() must be declared as async (coroutine function)."""
        from groq_client import GroqClient
        assert inspect.iscoroutinefunction(GroqClient.generate)

    def test_groq_client_generate_stream_is_async_generator(self):
        """generate_stream() must be declared as an async generator function."""
        from groq_client import GroqClient
        assert inspect.isasyncgenfunction(GroqClient.generate_stream)


class TestOllamaClientCompliance:

    def test_ollama_client_implements_llm_provider(self):
        """OllamaClient must be a subclass of LLMProvider (LSP compliance)."""
        from llm_interface import LLMProvider
        from ollama_client import OllamaClient
        assert issubclass(OllamaClient, LLMProvider)

    def test_ollama_client_implements_all_abstract_methods(self):
        """OllamaClient must implement every method defined in LLMProvider."""
        from ollama_client import OllamaClient
        for method in REQUIRED_METHODS:
            assert hasattr(OllamaClient, method), (
                f"OllamaClient is missing method: {method}"
            )

    def test_ollama_client_generate_is_coroutine(self):
        """generate() must be declared as async on OllamaClient."""
        from ollama_client import OllamaClient
        assert inspect.iscoroutinefunction(OllamaClient.generate)


class TestBrokenImplementationCannotInstantiate:

    def test_incomplete_llm_provider_cannot_be_instantiated(self):
        """A class that skips any abstract method must raise TypeError on instantiation."""
        from llm_interface import LLMProvider

        class IncompleteProvider(LLMProvider):
            # Missing: startup, shutdown, generate_stream, is_reachable
            async def generate(self, prompt, system_prompt=None, temperature=0.1):
                return "partial"

        with pytest.raises(TypeError):
            IncompleteProvider()


class TestLLMFactoryDIP:

    def test_factory_returns_llm_provider_instance_for_groq(self):
        """Factory must return an LLMProvider (DIP: depend on abstraction, not concrete)."""
        with patch("llm_factory.settings") as mock_settings:
            mock_settings.llm_provider = "groq"
            mock_settings.groq_api_key = "gsk_test"
            mock_settings.groq_model = "qwen/qwen3-32b"
            mock_settings.groq_timeout_seconds = 60

            from llm_factory import create_llm_client
            from llm_interface import LLMProvider

            client = create_llm_client()
            assert isinstance(client, LLMProvider)

    def test_factory_returns_llm_provider_instance_for_ollama(self):
        """Factory must also return an LLMProvider for Ollama (DIP compliance)."""
        with patch("llm_factory.settings") as mock_settings:
            mock_settings.llm_provider = "ollama"
            mock_settings.ollama_host = "http://localhost:11434"
            mock_settings.ollama_model = "qwen3:8b"

            from llm_factory import create_llm_client
            from llm_interface import LLMProvider

            client = create_llm_client()
            assert isinstance(client, LLMProvider)
