"""
Ingestion Gateway — Proxy to handle unified file ingestion from the UI.

Design:
  - SRP: Acts strictly as an orchestrator. Does not extract or embed directly.
  - Passes valid files to Ingestion Service (:8001).
  - Passes extracted chunks to Embedding Service (:8002).
  - Handles HTTP connection scoping natively via httpx.
"""

import logging
from typing import BinaryIO

import httpx

from config import settings
from models import IngestResponse

logger = logging.getLogger(__name__)


class IngestionGateway:
    """Orchestrates document ingestion across external microservices."""

    def __init__(self) -> None:
        self.ingestion_url = f"{settings.ingestion_service_url}/ingest"
        self.embedding_url = f"{settings.embedding_service_url}/embed"

    async def ingest_file(self, filename: str, file_contents: bytes, content_type: str) -> IngestResponse:
        """
        Coordinates the ingestion of a file by sending it to the
        Ingestion Service, mapping the output, and forwarding
        chunks to the Embedding Service.

        Args:
            filename: The original name of the uploaded document.
            file_contents: The raw bytes of the file.
            content_type: MIME type of the file.

        Returns:
            IngestResponse with chunk counts.

        Raises:
            RuntimeError: If either downstream service errors out or times out.
        """
        logger.info("Gateway received file '%s' (%d bytes) for ingestion.", filename, len(file_contents))

        # 1. Forward file to Ingestion Service (Port 8001)
        extracted_data = await self._call_ingestion_service(filename, file_contents, content_type)
        chunks = extracted_data.get("chunks", [])

        if not chunks:
            logger.warning("No text chunks extracted from '%s'.", filename)
            return IngestResponse(
                filename=filename,
                chunks_extracted=0,
                chunks_stored=0,
                status="No readable text found in file."
            )

        # 2. Forward generated chunks to Embedding Service (Port 8002)
        embed_data = await self._call_embedding_service(chunks)
        chunks_stored = embed_data.get("chunks_stored", 0)

        logger.info(
            "Gateway successfully ingested '%s': %d chunks extracted, %d stored.",
            filename,
            len(chunks),
            chunks_stored,
        )

        return IngestResponse(
            filename=filename,
            chunks_extracted=len(chunks),
            chunks_stored=chunks_stored,
            status="success"
        )

    async def _call_ingestion_service(self, filename: str, file_contents: bytes, content_type: str) -> dict:
        """Sends the raw file to the Ingestion Service."""
        try:
            files = {
                "file": (filename, file_contents, content_type)
            }
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(self.ingestion_url, files=files)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("Ingestion Service error: %s", exc)
            raise RuntimeError(f"Failed to extract text: Ingestion service returned {exc}") from exc

    async def _call_embedding_service(self, chunks: list[dict]) -> dict:
        """Sends the extracted chunks to the Embedding Service for storage."""
        try:
            payload = {"chunks": chunks}
            # High timeout since embeddings can take a long time on CPU
            async with httpx.AsyncClient(timeout=300.0) as client:
                response = await client.post(self.embedding_url, json=payload)
                response.raise_for_status()
                return response.json()
        except httpx.HTTPError as exc:
            logger.error("Embedding Service error: %s", exc)
            raise RuntimeError(f"Failed to vectorize chunks: Embedding service returned {exc}") from exc


# Singleton instance
ingestion_gateway = IngestionGateway()
