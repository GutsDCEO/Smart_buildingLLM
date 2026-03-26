"""
Guardrail Agent — Rule-based input validation and sanitization.

Design:
  - SRP: Only validates user input. No routing or answering.
  - Rule-based (no LLM): Fast, deterministic, zero latency.
  - OWASP A03: Sanitizes all input before downstream processing.
"""

from __future__ import annotations

import logging
import re

from config import settings
from models import GuardRequest, GuardResponse

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Constants — Named patterns (no magic strings, Quality Rule ④)
# ──────────────────────────────────────────────────────────────

# Common prompt injection patterns (OWASP LLM01)
_INJECTION_PATTERNS: list[re.Pattern] = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions|prompts)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"<\s*(script|img|iframe|svg|object)", re.IGNORECASE),
    re.compile(r"(DROP\s+TABLE|DELETE\s+FROM|INSERT\s+INTO|UPDATE\s+\w+\s+SET)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|the)\s+(rules|instructions)", re.IGNORECASE),
    re.compile(r"pretend\s+(you\s+are|to\s+be)", re.IGNORECASE),
    re.compile(r"reveal\s+(your|the|hidden|system|secret|\s)+\s+(prompt|instructions)", re.IGNORECASE),
    re.compile(r"(expose|show|reveal|print|output)\s+(your|the|all)?\s*(api\s*tokens?|keys?|passwords?|credentials?|secrets?)", re.IGNORECASE),
    re.compile(r"(what\s+is|tell\s+me)\s+(your|the)\s+(api\s*tokens?|keys?|passwords?|credentials?|secrets?)", re.IGNORECASE),
]

# Abusive / off-topic patterns
_ABUSE_PATTERNS: list[re.Pattern] = [
    re.compile(r"\b(hack|exploit|bypass|jailbreak)\b", re.IGNORECASE),
]


class GuardrailAgent:
    """Validates and sanitizes user questions before processing."""

    def validate(self, request: GuardRequest) -> GuardResponse:
        """
        Run the validation pipeline on user input.

        Checks (in order):
          1. Empty/whitespace-only input
          2. Length limits (min/max)
          3. Prompt injection patterns
          4. Abuse/off-topic patterns
          5. Sanitize surviving input

        Returns:
            GuardResponse with allowed=True and sanitized question, or
            allowed=False with the rejection reason.
        """
        question = request.question.strip()

        # --- Check 1: Empty input ---
        if not question:
            logger.warning("Blocked: empty question")
            return GuardResponse(allowed=False, reason="Question cannot be empty.")

        # --- Check 2: Length limits ---
        if len(question) < settings.min_query_length:
            logger.warning("Blocked: question too short (%d chars)", len(question))
            return GuardResponse(
                allowed=False,
                reason=f"Question must be at least {settings.min_query_length} characters.",
            )

        if len(question) > settings.max_query_length:
            logger.warning("Blocked: question too long (%d chars)", len(question))
            return GuardResponse(
                allowed=False,
                reason=f"Question exceeds maximum length of {settings.max_query_length} characters.",
            )

        # --- Check 3: Prompt injection ---
        for pattern in _INJECTION_PATTERNS:
            if pattern.search(question):
                logger.warning("Blocked: prompt injection detected: %s", pattern.pattern)
                return GuardResponse(
                    allowed=False,
                    reason="Your question contains disallowed patterns.",
                )

        # --- Check 4: Abuse patterns ---
        for pattern in _ABUSE_PATTERNS:
            if pattern.search(question):
                logger.warning("Blocked: abuse pattern detected: %s", pattern.pattern)
                return GuardResponse(
                    allowed=False,
                    reason="Your question contains disallowed content.",
                )

        # --- Check 5: Sanitize ---
        sanitized = self._sanitize(question)

        logger.info("Guardrail PASSED for question: %.80s...", sanitized)
        return GuardResponse(
            allowed=True,
            reason="OK",
            sanitized_question=sanitized,
        )

    @staticmethod
    def _sanitize(text: str) -> str:
        """
        Clean the text for downstream processing.

        - Strip control characters
        - Collapse excessive whitespace
        - Remove null bytes
        """
        # Remove null bytes and control chars (except newline/tab)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()
        return text


# Singleton instance
guardrail_agent = GuardrailAgent()
