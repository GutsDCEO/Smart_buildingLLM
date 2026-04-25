"""
Q&A Agent — The core RAG pipeline that answers user questions with citations.

Design:
  - SRP: Only handles question → answer flow. No validation or routing.
  - DIP: Depends on LLMProvider interface and domain_config abstraction.
  - OCP: New retrieval strategies (hybrid search, etc.) can be added
         without modifying existing code paths.

Pipeline:
  1. Embed the user question via Embedding Service /vectorize
  2. Over-retrieve top-K chunks from Qdrant (K=15)
  3. Re-rank with cross-encoder to keep top-N (N=5)
  4. Build a context-stuffed prompt with conversation history
  5. Generate a cited answer via the LLM provider
  6. Return AskResponse with answer and citations
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings
from domain_config import domain_config
from llm_interface import LLMProvider
from models import AskRequest, AskResponse, Citation
from qdrant_search import qdrant_search, SearchResult
from reranker import reranker

logger = logging.getLogger(__name__)


class QAAgent:
    """Answers user questions using RAG: embed → search → rerank → generate."""

    def __init__(self, llm_client: LLMProvider) -> None:
        self._llm = llm_client

    async def answer(
        self,
        request: AskRequest,
        conversation_history: Optional[list[dict]] = None,
    ) -> AskResponse:
        """
        Full RAG pipeline with re-ranking and conversation memory.

        Args:
            request: The user question.
            conversation_history: Optional list of previous messages
                                  [{"role": "user"|"assistant", "content": "..."}]

        Returns:
            AskResponse with answer and citations.

        Raises:
            RuntimeError: If Embedding Service or LLM is unreachable.
        """
        question = request.question

        # --- Step 1: Vectorize via Embedding Service ---
        query_vector = await self._embed_question(question)

        # --- Step 2: Over-retrieve from Qdrant ---
        if not qdrant_search.is_connected:
            raise RuntimeError("Qdrant search client is not connected.")

        results = qdrant_search.search(
            query_vector,
            top_k=domain_config.retrieval.top_k_retrieval,
        )

        if not results:
            logger.warning("No search results for: %.80s", question)
            return AskResponse(
                answer=(
                    "I don't have any relevant documents to answer this question. "
                    "Please ensure documents have been ingested first."
                ),
                citations=[],
            )

        # --- Step 3: Re-rank for precision ---
        reranked_results = reranker.rerank(
            question=question,
            results=results,
            top_n=domain_config.retrieval.top_n_reranked,
        )

        # --- Step 4: Build context prompt with history ---
        context_prompt = self._build_context_prompt(
            question=question,
            results=reranked_results,
            history=conversation_history,
        )

        # --- Step 5: Generate answer via LLM ---
        raw_answer = await self._llm.generate(
            prompt=context_prompt,
            system_prompt=domain_config.qa_system_prompt,
            temperature=0.2,  # Low = factual, deterministic
        )

        # --- Step 6: Build citations ---
        citations = self._build_citations(reranked_results)

        logger.info(
            "Q&A complete for '%s' — %d citations, answer=%d chars",
            question[:60],
            len(citations),
            len(raw_answer),
        )

        return AskResponse(answer=raw_answer, citations=citations)

    async def answer_stream(
        self,
        request: AskRequest,
        conversation_history: Optional[list[dict]] = None,
    ):
        """
        Streaming version of the RAG pipeline. Yields tokens for SSE.

        Returns a tuple of (token_generator, citations) so the caller
        can emit citations after the stream completes.
        """
        question = request.question

        # Steps 1-3: same as non-streaming
        query_vector = await self._embed_question(question)

        if not qdrant_search.is_connected:
            raise RuntimeError("Qdrant search client is not connected.")

        results = qdrant_search.search(
            query_vector,
            top_k=domain_config.retrieval.top_k_retrieval,
        )

        if not results:
            return None, []

        reranked_results = reranker.rerank(
            question=question,
            results=results,
            top_n=domain_config.retrieval.top_n_reranked,
        )

        context_prompt = self._build_context_prompt(
            question=question,
            results=reranked_results,
            history=conversation_history,
        )

        citations = self._build_citations(reranked_results)

        token_generator = self._llm.generate_stream(
            prompt=context_prompt,
            system_prompt=domain_config.qa_system_prompt,
            temperature=0.2,
        )

        return token_generator, citations

    # ── Private Helpers ──────────────────────────────────────

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
    def _build_context_prompt(
        question: str,
        results: list[SearchResult],
        history: Optional[list[dict]] = None,
    ) -> str:
        """
        Build a context-stuffed prompt from re-ranked search results
        and optional conversation history.

        Format:
          [Conversation History]
          User: ...
          Assistant: ...
          ---
          [Source: file.pdf, Page 3] (Relevance: 0.89)
          <chunk text>
          ---
          Question: ...
          Answer:
        """
        parts: list[str] = []

        # Include conversation history for multi-turn context
        if history:
            max_turns = domain_config.memory.max_history_turns
            recent = history[-max_turns * 2:]  # Each turn = user + assistant
            history_lines = []
            for msg in recent:
                role = msg.get("role", "user").capitalize()
                content = msg.get("content", "")
                history_lines.append(f"{role}: {content}")

            if history_lines:
                parts.append(
                    "Previous conversation:\n" + "\n".join(history_lines)
                )
                parts.append("---")

        # Add document context
        parts.append("Context from documents:\n")
        for result in results:
            page_info = f", Page {result.page_number}" if result.page_number else ""
            header = f"[Source: {result.source_file}{page_info}] (Relevance: {result.score:.2f})"
            parts.append(f"{header}\n{result.text}")

        context_block = "\n---\n".join(parts)

        return (
            f"{context_block}\n\n"
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
