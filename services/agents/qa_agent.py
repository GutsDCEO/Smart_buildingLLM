"""
Q&A Agent — The core RAG pipeline that answers user questions with citations.

Design:
  - SRP: Only handles question → answer flow. No validation or routing.
  - Reuses Embedding Service /vectorize via HTTP (DIP: no local model).
  - Builds context-stuffed prompts with source metadata for citations.
  - OWASP A09: All errors are logged but never leak internals to the caller.
"""

from __future__ import annotations

import logging

import httpx

from typing import Any
from config import settings
from models import AskRequest, AskResponse, Citation
from qdrant_search import qdrant_search, SearchResult

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# System Prompt — Citation-Aware Answering
# ──────────────────────────────────────────────────────────────

_QA_SYSTEM_PROMPT = """You are a Smart Building AI assistant. Your job is to answer questions \
about buildings, HVAC systems, maintenance, equipment, facilities management, and related topics.

CRITICAL RULES:
1. ONLY use the provided context to answer. Do NOT use general knowledge.
2. If the context does not contain enough information, say exactly:
   "I don't have enough information in the available documents to answer this question."
3. ALWAYS cite your sources using the format: [Source: filename, Page X]
4. Be precise and technical. Building professionals rely on your accuracy.
5. If multiple sources agree, cite the most relevant one.
6. Keep answers concise but complete."""


class QAAgent:
    """Answers user questions using RAG: vectorize → search → generate."""

    def __init__(self, llm_client: Any):
        self.llm_client = llm_client

    async def answer(self, request: AskRequest) -> AskResponse:
        """
        Full RAG pipeline:
          1. Vectorize the user question via Embedding Service /vectorize
          2. Search Qdrant for the top-K most relevant chunks
          3. Build a context-stuffed prompt
          4. Call Ollama to generate a cited answer
          5. Return AskResponse with answer and citations

        Raises:
            RuntimeError: If the Embedding Service or Ollama is unreachable.
            HTTPException (503): If Qdrant has no results.
        """
        question = request.question

        # --- Step 1: Vectorize via Embedding Service ---
        query_vector = await self._embed_question(question)

        # --- Step 2: Search Qdrant ---
        if not qdrant_search.is_connected:
            raise RuntimeError("Qdrant search client is not connected.")

        results = qdrant_search.search(query_vector)

        if not results:
            logger.warning("No search results for: %.80s", question)
            return AskResponse(
                answer=(
                    "I don't have any relevant documents to answer this question. "
                    "Please ensure documents have been ingested first."
                ),
                citations=[],
            )

        # --- Step 3: Build context prompt ---
        context_prompt = self._build_context_prompt(question, results)

        # --- Step 4: Generate answer via injected LLM client ---
        raw_answer = await self.llm_client.generate(
            prompt=context_prompt,
            system_prompt=_QA_SYSTEM_PROMPT,
            temperature=0.2,  # Low = factual, deterministic
        )

        # --- Step 5: Build citations ---
        citations = self._build_citations(results)

        logger.info(
            "Q&A complete for '%s' — %d citations, answer=%d chars",
            question[:60],
            len(citations),
            len(raw_answer),
        )

        return AskResponse(answer=raw_answer, citations=citations)

    async def _embed_question(self, question: str) -> list[float]:
        """
        Call the Embedding Service /vectorize to get a query vector.

        This endpoint returns a raw float vector without storing anything
        in Qdrant or Postgres — pure in-memory conversion.
        """
        vectorize_url = f"{settings.embedding_service_url}/vectorize"

        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(30.0)) as client:
                response = await client.post(
                    vectorize_url,
                    json={"text": question},
                )
                response.raise_for_status()
        except httpx.ConnectError as exc:
            logger.error("Cannot reach Embedding Service at %s: %s", vectorize_url, exc)
            raise RuntimeError("Embedding Service is not reachable.") from exc
        except httpx.TimeoutException as exc:
            logger.error("Embedding Service timed out.")
            raise RuntimeError("Embedding Service timed out.") from exc
        except httpx.HTTPStatusError as exc:
            logger.error("Embedding Service HTTP %d", exc.response.status_code)
            raise RuntimeError("Embedding Service returned an error.") from exc

        data = response.json()
        vector: list[float] = data["vector"]
        logger.info("Got query vector (dim=%d).", data.get("dimension", len(vector)))
        return vector

    @staticmethod
    def _build_context_prompt(question: str, results: list[SearchResult]) -> str:
        """
        Build a context-stuffed prompt from Qdrant search results.

        Format example:
          [Source: HVAC_Manual.pdf, Page 3] (Relevance: 0.89)
          <chunk text>
          ---
          Question: ...
          Answer:
        """
        parts: list[str] = []

        for result in results:
            page_info = f", Page {result.page_number}" if result.page_number else ""
            header = f"[Source: {result.source_file}{page_info}] (Relevance: {result.score:.2f})"
            parts.append(f"{header}\n{result.text}")

        context_block = "\n---\n".join(parts)

        return (
            f"Context from documents:\n\n{context_block}\n\n"
            f"---\n\n"
            f"Question: {question}\n\n"
            f"Answer:"
        )

    @staticmethod
    def _build_citations(results: list[SearchResult]) -> list[Citation]:
        """Convert search results into structured Citation objects."""
        return [
            Citation(
                source_file=r.source_file,
                page_number=r.page_number,
                chunk_index=r.chunk_index,
                relevance_score=round(r.score, 4),
            )
            for r in results
        ]


