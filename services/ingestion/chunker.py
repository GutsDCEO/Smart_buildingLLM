"""
Text Chunker — splits extracted text into token-based chunks with overlap.

Uses tiktoken (cl100k_base) for accurate token counting that matches
the embedding model's tokenization behavior.

Design:
  - Splits on sentence boundaries when possible
  - Guarantees overlap between consecutive chunks for context continuity
  - No business logic beyond splitting — SRP compliant
"""

from __future__ import annotations

import logging
import re
from typing import Optional

import tiktoken

from config import settings
from models import TextChunk

logger = logging.getLogger(__name__)

# Use the same encoding as OpenAI / most modern models
_ENCODING = tiktoken.get_encoding("cl100k_base")

# Sentence boundary regex — splits on period, exclamation, or question mark
# followed by whitespace. Avoids splitting on abbreviations like "Dr." loosely.
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[.!?])\s+")


def chunk_text(
    text: str,
    source_file: str,
    page_number: Optional[int] = None,
    chunk_size: Optional[int] = None,
    overlap: Optional[int] = None,
) -> list[TextChunk]:
    """
    Split text into token-based chunks with overlap.

    Args:
        text: The full text to split.
        source_file: Name of the source document.
        page_number: Optional page number for metadata.
        chunk_size: Max tokens per chunk (default from config).
        overlap: Overlap tokens between chunks (default from config).

    Returns:
        List of TextChunk objects.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for chunking from %s", source_file)
        return []

    chunk_size = chunk_size or settings.chunk_size_tokens
    overlap = overlap or settings.chunk_overlap_tokens

    if overlap >= chunk_size:
        raise ValueError(
            f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        )

    sentences = _split_into_sentences(text)
    chunks = _assemble_chunks(
        sentences=sentences,
        source_file=source_file,
        page_number=page_number,
        chunk_size=chunk_size,
        overlap=overlap,
        original_text=text,
    )

    logger.info(
        "Chunked %s (page %s): %d chunks from %d sentences",
        source_file,
        page_number or "N/A",
        len(chunks),
        len(sentences),
    )

    return chunks


def _split_into_sentences(text: str) -> list[str]:
    """Split text into sentences using boundary detection."""
    sentences = _SENTENCE_SPLIT_PATTERN.split(text.strip())
    return [s.strip() for s in sentences if s.strip()]


def _count_tokens(text: str) -> int:
    """Count tokens using tiktoken."""
    return len(_ENCODING.encode(text))


def _assemble_chunks(
    sentences: list[str],
    source_file: str,
    page_number: Optional[int],
    chunk_size: int,
    overlap: int,
    original_text: str,
) -> list[TextChunk]:
    """
    Build chunks from sentences respecting token limits and overlap.

    Strategy:
      1. Accumulate sentences until the token limit is reached.
      2. Emit a chunk.
      3. Rewind by `overlap` tokens worth of sentences.
      4. Repeat until all sentences are consumed.
    """
    chunks: list[TextChunk] = []
    current_sentences: list[str] = []
    current_tokens = 0
    chunk_index = 0

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        sentence_tokens = _count_tokens(sentence)

        # If a single sentence exceeds chunk_size, include it as its own chunk
        if sentence_tokens > chunk_size:
            # Flush any accumulated sentences first
            if current_sentences:
                chunks.append(
                    _build_chunk(
                        current_sentences, chunk_index, source_file,
                        page_number, original_text,
                    )
                )
                chunk_index += 1
                current_sentences = []
                current_tokens = 0

            # Emit the oversized sentence as a single chunk
            chunks.append(
                _build_chunk(
                    [sentence], chunk_index, source_file,
                    page_number, original_text,
                )
            )
            chunk_index += 1
            i += 1
            continue

        # If adding this sentence would exceed the limit, emit current chunk
        if current_tokens + sentence_tokens > chunk_size and current_sentences:
            chunks.append(
                _build_chunk(
                    current_sentences, chunk_index, source_file,
                    page_number, original_text,
                )
            )
            chunk_index += 1

            # Rewind for overlap: keep trailing sentences up to `overlap` tokens
            overlap_sentences: list[str] = []
            overlap_tokens = 0
            for s in reversed(current_sentences):
                s_tokens = _count_tokens(s)
                if overlap_tokens + s_tokens > overlap:
                    break
                overlap_sentences.insert(0, s)
                overlap_tokens += s_tokens

            current_sentences = overlap_sentences
            current_tokens = overlap_tokens
            continue  # Re-evaluate the current sentence with the new state

        current_sentences.append(sentence)
        current_tokens += sentence_tokens
        i += 1

    # Flush remaining sentences
    if current_sentences:
        chunks.append(
            _build_chunk(
                current_sentences, chunk_index, source_file,
                page_number, original_text,
            )
        )

    return chunks


def _build_chunk(
    sentences: list[str],
    chunk_index: int,
    source_file: str,
    page_number: Optional[int],
    original_text: str,
) -> TextChunk:
    """Create a TextChunk from a list of sentences."""
    text = " ".join(sentences)
    token_count = _count_tokens(text)

    # Find character offsets in the original text
    start_char = original_text.find(sentences[0])
    last_sentence = sentences[-1]
    end_char_search = original_text.find(last_sentence)
    end_char = end_char_search + len(last_sentence) if end_char_search != -1 else -1

    return TextChunk(
        text=text,
        chunk_index=chunk_index,
        token_count=token_count,
        source_file=source_file,
        page_number=page_number,
        start_char=max(start_char, 0),
        end_char=max(end_char, 0),
    )
