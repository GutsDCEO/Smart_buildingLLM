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
    ollama_timeout_seconds: int = 1200

    # --- LLM Provider ("ollama" or "groq") ---
    llm_provider: str = "ollama"

    # --- Groq Cloud (OWASP A02: secret from env only, never hardcoded) ---
    groq_api_key: str = ""
    groq_model: str = "deepseek-r1-distill-llama-70b"
    groq_timeout_seconds: int = 60

    # --- Qdrant (Vector Search) ---
    qdrant_host: str = "qdrant"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "smart_building_docs"

    # --- Upstream Services ---
    embedding_service_url: str = "http://embedding:8002"
    ingestion_service_url: str = "http://ingestion:8001"

    # --- RAG Parameters ---
    top_k_results: int = 15  # Over-retrieve for re-ranking

    # --- Re-Ranker ---
    reranker_model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranked_top_n: int = 5  # Keep top-N after re-ranking

    # --- Guardrail Limits ---
    max_query_length: int = 2000
    min_query_length: int = 3

    # --- Service ---
    agents_service_port: int = 8003
    log_level: str = "INFO"

    # --- PostgreSQL (Persistence) ---
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_user: str = "smartbuilding"
    postgres_password: str = ""
    postgres_db: str = "smartbuilding_metadata"

    # --- Local Ingest Folder (mounted from host) ---
    ingest_folder: str = "/data/ingest"

    # --- Domain Configuration ---
    domain_config: str = "smart_building"

    # --- Chat UI CORS ---
    chat_ui_cors_origin: str = "http://localhost:3000"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — import this, never instantiate directly.
settings = AgentsSettings()
