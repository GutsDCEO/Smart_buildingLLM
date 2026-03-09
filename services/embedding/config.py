"""
Configuration module for the Embedding Service.

Reads settings from environment variables using Pydantic BaseSettings.
No magic numbers or hardcoded values (Quality Rule ④).
"""

from pydantic_settings import BaseSettings


class EmbeddingSettings(BaseSettings):
    """Embedding service configuration from environment variables."""

    # --- Embedding Model ---
    embedding_model_name: str = "sentence-transformers/all-MiniLM-L6-v2"

    # --- Qdrant ---
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection_name: str = "smart_building_docs"
    qdrant_vector_size: int = 384  # all-MiniLM-L6-v2 output dimension

    # --- PostgreSQL ---
    postgres_user: str = "smartbuilding"
    postgres_password: str = ""
    postgres_db: str = "smartbuilding_metadata"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    # --- Service ---
    embedding_service_port: int = 8002
    log_level: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @property
    def postgres_dsn(self) -> str:
        """Build the PostgreSQL connection string."""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


# Singleton instance — import this, never instantiate directly.
settings = EmbeddingSettings()
