import pytest
from unittest.mock import AsyncMock, patch, MagicMock
import httpx

from services.agents.ingestion_gateway import ingestion_gateway
from services.agents.models import IngestResponse


@pytest.fixture
def mock_httpx_post():
    """Mock the httpx.AsyncClient.post method to prevent real network calls."""
    # We must patch the context manager too since the code uses async with httpx.AsyncClient() as client.
    # Actually we just patched httpx.AsyncClient.post, which is perfectly valid.
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        yield mock_post


@pytest.mark.asyncio
async def test_successful_ingestion(mock_httpx_post):
    """Test that a file is successfully forwarded to both ingestion and embedding services."""
    # Mock Response 1: Ingestion Service (returns extracted chunks)
    # The response object itself isn't awaited, only the httpx.post call is. 
    # Therefore, we use MagicMock for the response.
    mock_ingestion_response = MagicMock()
    mock_ingestion_response.json.return_value = {
        "filename": "test.pdf",
        "chunks": [{"text": "chunk1"}, {"text": "chunk2"}]
    }
    mock_ingestion_response.raise_for_status = MagicMock()

    # Mock Response 2: Embedding Service (returns stored chunks count)
    mock_embedding_response = MagicMock()
    mock_embedding_response.json.return_value = {
        "chunks_stored": 2,
        "message": "Success"
    }
    mock_embedding_response.raise_for_status = MagicMock()

    # Set the side_effect so the first call gets response 1, second gets response 2
    mock_httpx_post.side_effect = [mock_ingestion_response, mock_embedding_response]

    file_bytes = b"dummy pdf content"
    result = await ingestion_gateway.ingest_file("test.pdf", file_bytes, "application/pdf")

    assert result.filename == "test.pdf"
    assert result.chunks_extracted == 2
    assert result.chunks_stored == 2
    assert result.status == "success"

    # Verify httpx was called exactly twice
    assert mock_httpx_post.call_count == 2


@pytest.mark.asyncio
async def test_empty_chunks_returns_graceful_message(mock_httpx_post):
    """Test that if no text is extracted, it gracefully returns 0 chunks without calling embedding."""
    mock_ingestion_response = MagicMock()
    mock_ingestion_response.json.return_value = {
        "filename": "empty.pdf",
        "chunks": []
    }
    mock_ingestion_response.raise_for_status = MagicMock()

    mock_httpx_post.return_value = mock_ingestion_response

    result = await ingestion_gateway.ingest_file("empty.pdf", b"", "application/pdf")

    assert result.chunks_extracted == 0
    assert result.chunks_stored == 0
    assert result.status == "No readable text found in file."

    # Embedding service should NOT be called
    assert mock_httpx_post.call_count == 1


@pytest.mark.asyncio
async def test_ingestion_service_error_raises_runtime_error(mock_httpx_post):
    """Test that an HTTP error from the downstream service raises a generic RuntimeError."""
    
    # We must patch httpx.HTTPError for it to raise properly inside the test
    mock_httpx_post.side_effect = httpx.HTTPError("500 Internal Server Error")

    with pytest.raises(RuntimeError, match="Failed to extract text: Ingestion service returned"):
        await ingestion_gateway.ingest_file("broken.pdf", b"bad", "application/pdf")
