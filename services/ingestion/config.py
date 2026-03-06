"""
Configuration module for the Ingestion Service.

Reads settings from environment variables using Pydantic BaseSettings.
No magic numbers or hardcoded values (Quality Rule ④).
"""

from pydantic_settings import BaseSettings


class IngestionSettings(BaseSettings):
    """Ingestion service configuration from environment variables."""

    # --- Chunking ---
    chunk_size_tokens: int = 500
    chunk_overlap_tokens: int = 50

    # --- Logging ---
    log_level: str = "INFO"

    # --- Service ---
    ingestion_service_port: int = 8001

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


# Singleton instance — import this, never instantiate directly.
settings = IngestionSettings()
