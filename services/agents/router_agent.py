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

from models import IntentType, RouteRequest, RouteResponse
from ollama_client import ollama_client

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# System Prompt — Intent Classification
# ──────────────────────────────────────────────────────────────

_ROUTER_SYSTEM_PROMPT = """You are an intent classifier for a Smart Building AI assistant.

Your ONLY job is to classify a user's question into one of these categories:
- "factual_qa": The question is about buildings, HVAC, maintenance, equipment, facilities, energy, safety, regulations, construction, or any Smart Building topic.
- "out_of_scope": The question is completely unrelated to buildings or facilities management (e.g., cooking recipes, sports scores, personal advice).

IMPORTANT RULES:
1. When in doubt, classify as "factual_qa" — it is better to attempt an answer than to reject a valid question.
2. Questions about general engineering, sustainability, or workplace safety ARE in scope.
3. Respond ONLY with valid JSON. No explanation, no markdown, no extra text.

Response format:
{"intent": "factual_qa", "confidence": 0.95}
"""


class RouterAgent:
    """Classifies user questions into intent categories using an LLM."""

    async def classify(self, request: RouteRequest) -> RouteResponse:
        """
        Classify the intent of a user question.

        Args:
            request: The sanitized question from the Guardrail.

        Returns:
            RouteResponse with intent and confidence.
        """
        prompt = f'Classify this question: "{request.question}"'

        try:
            raw_response = await ollama_client.generate(
                prompt=prompt,
                system_prompt=_ROUTER_SYSTEM_PROMPT,
                temperature=0.0,  # Fully deterministic classification
            )

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


# Singleton instance
router_agent = RouterAgent()
