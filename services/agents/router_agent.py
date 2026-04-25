"""
Router Agent — LLM-based intent classification.

Design:
  - SRP: Only classifies intent. No answering or guarding.
  - Uses Ollama to understand natural language intent.
  - MVP categories: factual_qa, out_of_scope.
"""

from __future__ import annotations

import json
import logging

from domain_config import domain_config
from llm_interface import LLMProvider
from models import IntentType, RouteRequest, RouteResponse

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# System Prompt — Intent Classification
# ──────────────────────────────────────────────────────────────

# Router prompt loaded from domain config at runtime.
# Fallback to a sensible default if domain config is not available.
_FALLBACK_ROUTER_PROMPT = """You are an intent classifier.
Classify into: "factual_qa" or "out_of_scope".
Respond with JSON only: {"intent": "...", "confidence": 0.95}
"""


def _get_router_prompt() -> str:
    """Load router prompt from domain config, with fallback."""
    prompt = domain_config.router_system_prompt
    return prompt if prompt else _FALLBACK_ROUTER_PROMPT


class RouterAgent:
    """Classifies user questions into intent categories using an LLM."""

    def __init__(self, llm_client: LLMProvider) -> None:
        self._llm = llm_client

    async def classify(self, request: RouteRequest) -> RouteResponse:
        """
        Classify the intent of a user question.

        Args:
            request: The sanitized question from the Guardrail.

        Returns:
            RouteResponse with intent and confidence.
        """
        prompt = f'Classify this question: "{request.question}"'

        logger.info("Router: Starting classification for question: %.50s...", request.question)
        try:
            raw_response = await self._llm.generate(
                prompt=prompt,
                system_prompt=_get_router_prompt(),
                temperature=0.0,  # Fully deterministic classification
            )
            logger.info("Router: LLM response received.")

            result = self._parse_response(raw_response)
            logger.info(
                "Router classified '%s' as %s (%.2f)",
                request.question[:60],
                result.intent.value,
                result.confidence,
            )
            return result

        except RuntimeError as exc:
            # LLM is unavailable — fail open (assume factual_qa)
            logger.warning(
                "Router LLM unavailable, defaulting to factual_qa: %s", exc
            )
            return RouteResponse(
                intent=IntentType.FACTUAL_QA,
                confidence=0.0,
            )

    @staticmethod
    def _parse_response(raw: str) -> RouteResponse:
        """
        Parse the LLM's JSON response into a RouteResponse.

        Falls back to factual_qa if parsing fails (fail-open strategy).
        """
        try:
            # Handle cases where LLM wraps JSON in markdown code blocks
            cleaned = raw.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned
                cleaned = cleaned.rsplit("```", 1)[0]
                cleaned = cleaned.strip()

            data = json.loads(cleaned)

            intent_str = data.get("intent", "factual_qa").lower()
            confidence = float(data.get("confidence", 0.5))

            # Map to enum (default to factual_qa for unknown intents)
            try:
                intent = IntentType(intent_str)
            except ValueError:
                logger.warning("Unknown intent '%s', defaulting to factual_qa", intent_str)
                intent = IntentType.FACTUAL_QA

            return RouteResponse(intent=intent, confidence=confidence)

        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            logger.warning("Failed to parse router response: %s | raw: %s", exc, raw[:200])
            return RouteResponse(
                intent=IntentType.FACTUAL_QA,
                confidence=0.0,
            )


