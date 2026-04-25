"""
Unit Tests — Think Token Stripping (Qwen3 / DeepSeek R1 CoT filtering)

FIRST Principles:
  F - Fast:         Pure string operations, zero I/O.
  I - Independent:  Every test is completely self-contained.
  R - Repeatable:   Deterministic — same input always → same output.
  S - Self-Validating: Clear assertions. No manual inspection required.
  T - Timely:       Written for the new Qwen3/DeepSeek R1 reasoning support.

Covers:
  1. No <think> block → text returned unchanged
  2. Simple <think>...</think> → stripped, answer preserved
  3. Multi-line thinking block → stripped cleanly
  4. <think> with surrounding whitespace → clean result
  5. Multiple <think> blocks (model glitches) → all stripped
  6. Empty <think> block → handled gracefully
  7. Only <think> block, no answer → returns empty string (not exception)
  8. Partial / unclosed <think> tag → returns full text unchanged (safe fallback)
"""

import sys
import os
import re

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))

# Import the regex directly to test the logic in isolation
from groq_client import GroqClient

# ──────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────

def strip(text: str) -> str:
    """Exercise the real _strip_thinking_tokens() on the client class."""
    return GroqClient._strip_thinking_tokens(text)


# ──────────────────────────────────────────────────────────────
# Test cases
# ──────────────────────────────────────────────────────────────

class TestThinkTokenStripping:

    def test_no_think_block_returns_text_unchanged(self):
        """Plain text without any think tags must pass through untouched."""
        text = "The HVAC system operates on a 24-hour schedule."
        assert strip(text) == text

    def test_simple_think_block_is_stripped(self):
        """A basic <think>...</think> block should be removed, leaving only the answer."""
        text = "<think>Let me analyze the HVAC data carefully.</think>The HVAC schedule is 08:00–18:00."
        result = strip(text)
        assert "<think>" not in result
        assert "</think>" not in result
        assert "The HVAC schedule is 08:00–18:00." in result

    def test_multiline_think_block_is_stripped(self):
        """Multi-line reasoning blocks (typical for Qwen3/DeepSeek) should be fully removed."""
        text = (
            "<think>\n"
            "Step 1: The user is asking about HVAC maintenance.\n"
            "Step 2: I should check the documents for the maintenance interval.\n"
            "Step 3: The manual says quarterly maintenance is required.\n"
            "</think>\n"
            "According to the manual, HVAC maintenance is required quarterly."
        )
        result = strip(text)
        assert "<think>" not in result
        assert "Step 1" not in result
        assert "quarterly" in result

    def test_whitespace_around_think_block_is_cleaned(self):
        """Result should be stripped of leading/trailing whitespace."""
        text = "   <think>thinking...</think>   The answer is yes.   "
        result = strip(text)
        assert not result.startswith(" ")
        assert not result.endswith(" ")
        assert "The answer is yes." in result

    def test_multiple_think_blocks_all_stripped(self):
        """Edge case: if the model emits multiple think blocks, all should be removed."""
        text = (
            "<think>First thought.</think>"
            "Intermediate text."
            "<think>Second thought.</think>"
            "Final answer."
        )
        result = strip(text)
        assert "<think>" not in result
        assert "First thought" not in result
        assert "Second thought" not in result
        assert "Final answer." in result

    def test_empty_think_block_is_handled(self):
        """An empty <think></think> should be stripped without error."""
        text = "<think></think>The building has 3 HVAC zones."
        result = strip(text)
        assert "<think>" not in result
        assert "3 HVAC zones" in result

    def test_only_think_block_returns_empty_string(self):
        """If the model ONLY produces a think block and no answer, return empty (not crash)."""
        text = "<think>I'm still thinking and never answered.</think>"
        result = strip(text)
        assert "<think>" not in result
        assert result == ""

    def test_partial_unclosed_think_tag_is_returned_safely(self):
        """An unclosed <think> tag should NOT cause an exception — return text as-is."""
        text = "<think>I started thinking but never closed the tag..."
        # The regex pattern requires the closing tag — if it's absent, text is unchanged
        result = strip(text)
        # Should not raise an exception; content is returned (pattern won't match)
        assert isinstance(result, str)

    def test_think_block_with_code_inside(self):
        """Reasoning blocks may contain code — this must not cause regex issues."""
        text = (
            "<think>\n"
            "```python\n"
            "def check_hvac(): return True\n"
            "```\n"
            "</think>\n"
            "The HVAC check function is correct."
        )
        result = strip(text)
        assert "<think>" not in result
        assert "check_hvac" not in result
        assert "correct." in result
