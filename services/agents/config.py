"""
Configuration module for the Agents Service.

Reads settings from environment variables using Pydantic BaseSettings.
No magic numbers or hardcoded values (Quality Rule ④).
"""

from pydantic_settings import BaseSettings


class AgentsSettings(BaseSettings):
    """Agents service configuration from environment variables."""

    # --- Ollama (LLM) ---
    ollama_host: str = "http://ollama:11434"
    ollama_model: str = "llama3.1"
    ollama_timeout_seconds: int = 120

    # --- Qdrant (Vector Search) ---
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "smart_building_docs"

    # --- Embedding Service (query vectorization) ---
    embedding_service_url: str = "http://embedding:8002"

    # --- RAG Parameters ---
    top_k_results: int = 5

    # --- Guardrail Limits ---
    max_query_length: int = 2000
    min_query_length: int = 3

    # --- Service ---
    agents_service_port: int = 8003
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — import this, never instantiate directly.
settings = AgentsSettings()
