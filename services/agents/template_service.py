"""
Template Service — Multi-Format PDF Field Extraction and RAG-Based Filling.

Design:
  - SRP: Only handles template parsing and RAG-filling orchestration.
  - DIP: Depends on QAAgent abstraction, not on concrete LLM clients.
  - OCP: New placeholder formats added by extending PLACEHOLDER_PATTERNS list only.
  - Strategy Pattern: PlaceholderExtractor tries detection strategies in priority order.

Pipeline:
  1. Upload PDF → extract fillable fields (AcroForm → bracket → underscore → mustache)
  2. Store uploaded file in /data/outputs/{file_id}_input.pdf
  3. For each field, call QAAgent.answer() to get a RAG-generated value
  4. Write values back into a copy of the PDF
  5. Save output to /data/outputs/{user_id}_{file_id}.pdf
  6. Yield SSE progress events throughout

OWASP:
  - A01: All output files namespaced by user_id to prevent horizontal access
  - A03: MIME type and size validated at router layer before reaching this service
  - A04: Answer length capped to prevent layout-breaking overlays
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from pathlib import Path
from typing import AsyncGenerator, Optional

import fitz  # PyMuPDF

from config import settings
from models import (
    AskRequest,
    TemplateAnalyzeResponse,
    TemplateFillError,
    TemplateFillResponse,
    TemplateField,
)
from qa_agent import QAAgent

logger = logging.getLogger(__name__)

# ── Placeholder Detection Patterns ──────────────────────────────────────────
# Ordered by specificity. AcroForm is handled separately via fitz widgets API.
# Each tuple: (compiled_regex, field_type_label)
PLACEHOLDER_PATTERNS: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\[([^\]]{3,150})\]"), "bracket"),
    (re.compile(r"([\w][^\n:]{2,60}):\s*_{4,}"), "underscore"),
    (re.compile(r"\{\{([^}]{1,100})\}\}"), "mustache"),
]

# Maximum characters written into a flat-PDF placeholder rectangle.
# Prevents text overflow that would corrupt the document layout.
MAX_ANSWER_CHARS = 300


# ── Placeholder Extractor ────────────────────────────────────────────────────


class PlaceholderExtractor:
    """
    Detects fillable fields from a PDF using a strategy chain.

    Strategy priority:
      1. AcroForm widgets (interactive PDF forms) — cleanest fill path
      2. Bracket placeholders  [Field Name]
      3. Underscore placeholders  Label: _______
      4. Mustache tags  {{field_name}}
    """

    def extract(self, doc: fitz.Document) -> list[TemplateField]:
        """Return all detected fields across all pages."""
        fields = self._extract_acroform(doc)
        if fields:
            logger.info(
                "AcroForm widgets found (%d). Skipping text-pattern scan.", len(fields)
            )
            return fields

        logger.info("No AcroForm widgets. Running text-pattern extraction.")
        return self._extract_text_patterns(doc)

    # ── Private Strategies ───────────────────────────────────────────────────

    def _extract_acroform(self, doc: fitz.Document) -> list[TemplateField]:
        fields: list[TemplateField] = []
        for page_num, page in enumerate(doc, start=1):
            for widget in page.widgets():
                name = (widget.field_name or "").strip()
                if not name:
                    continue
                fields.append(
                    TemplateField(
                        field_name=name,
                        field_type="acroform",
                        page_number=page_num,
                        current_value=str(widget.field_value or "").strip() or None,
                    )
                )
        return fields

    def _extract_text_patterns(self, doc: fitz.Document) -> list[TemplateField]:
        fields: list[TemplateField] = []
        seen: set[str] = set()  # De-duplicate identical placeholders across pages

        for page_num, page in enumerate(doc, start=1):
            text = page.get_text()
            for pattern, ptype in PLACEHOLDER_PATTERNS:
                for match in pattern.finditer(text):
                    raw = match.group(1).strip()
                    key = raw.lower()
                    if not raw or key in seen:
                        continue
                    seen.add(key)
                    fields.append(
                        TemplateField(
                            field_name=raw,
                            field_type=ptype,
                            page_number=page_num,
                        )
                    )

        return fields


# ── Template Service ─────────────────────────────────────────────────────────


class TemplateService:
    """
    Orchestrates the full template-filling pipeline.

    Injected QAAgent means this service reuses the entire existing
    embed → search → rerank → LLM generation stack without duplication.
    """

    def __init__(self, qa_agent: QAAgent) -> None:
        self._qa = qa_agent
        self._extractor = PlaceholderExtractor()
        self._output_dir = Path(settings.template_output_dir)
        self._output_dir.mkdir(parents=True, exist_ok=True)

    # ── Public API ───────────────────────────────────────────────────────────

    async def analyze(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: int,
    ) -> TemplateAnalyzeResponse:
        """
        Extract fillable fields from an uploaded PDF.

        Saves the uploaded file to disk so that a subsequent /fill call
        can open it by file_id without re-uploading.

        Returns:
            TemplateAnalyzeResponse with detected fields and a file_id.
        """
        file_id = str(uuid.uuid4())
        safe_name = Path(filename).stem  # Strip path separators — path traversal guard
        input_path = self._output_dir / f"{user_id}_{file_id}_input.pdf"

        try:
            input_path.write_bytes(file_bytes)
            logger.info("Template saved: %s (%d bytes)", input_path, len(file_bytes))
        except OSError as exc:
            raise RuntimeError(f"Could not save template file: {exc}") from exc

        doc = fitz.open(stream=file_bytes, filetype="pdf")
        try:
            fields = self._extractor.extract(doc)
        finally:
            doc.close()

        logger.info(
            "Analyzed '%s': %d fields detected (file_id=%s)",
            filename,
            len(fields),
            file_id,
        )
        return TemplateAnalyzeResponse(
            file_id=file_id,
            filename=safe_name + ".pdf",
            total_fields=len(fields),
            fields=fields,
        )

    async def fill_stream(
        self,
        file_id: str,
        user_id: int,
        requested_fields: Optional[list[str]] = None,
    ) -> AsyncGenerator[str, None]:
        """
        Fill template fields using RAG. Yields SSE events throughout.

        Yields events:
          - status: pipeline stage updates
          - field: per-field fill result (filled or failed)
          - complete: final TemplateFillResponse summary
          - done: stream terminator

        Never raises — all errors are emitted as SSE events.
        """
        input_path = self._output_dir / f"{user_id}_{file_id}_input.pdf"

        if not input_path.exists():
            yield _sse(
                "error", {"message": "Template file not found. Please re-upload."}
            )
            yield _sse("done", {})
            return

        yield _sse("status", {"stage": "opening", "message": "Opening template..."})

        try:
            doc = fitz.open(str(input_path))
        except Exception as exc:
            logger.error("Cannot open template %s: %s", input_path, exc)
            yield _sse("error", {"message": "Could not open the template PDF."})
            yield _sse("done", {})
            return

        try:
            # ── 1. Extract fields ────────────────────────────────────────────
            yield _sse(
                "status", {"stage": "analyzing", "message": "Extracting fields..."}
            )
            fields = self._extractor.extract(doc)

            if requested_fields:
                req_lower = {f.lower() for f in requested_fields}
                fields = [f for f in fields if f.field_name.lower() in req_lower]

            total = len(fields)
            if total == 0:
                yield _sse(
                    "error",
                    {"message": "No fillable fields detected in this template."},
                )
                yield _sse("done", {})
                return

            # ── 2. RAG fill loop ─────────────────────────────────────────────
            filled_count = 0
            errors: list[TemplateFillError] = []

            for idx, field in enumerate(fields, start=1):
                yield _sse(
                    "status",
                    {
                        "stage": "filling",
                        "message": f"Filling field {idx} of {total}: {field.field_name}",
                        "progress": idx,
                        "total": total,
                    },
                )

                # Retry on rate limits (Resilient RAG filling)
                retries = 3
                for attempt in range(retries):
                    answer, confidence, err = await self._fill_field(field.field_name)
                    if err and "rate limit" in err.lower() and attempt < retries - 1:
                        # Extract requested wait time from LLM provider error if available (self-healing)
                        wait_time = (attempt + 1) * 5.0
                        match = re.search(r"try again in (\d+(?:\.\d+)?)s", err)
                        if match:
                            wait_time = float(match.group(1)) + 1.5

                        yield _sse(
                            "status",
                            {
                                "stage": "filling",
                                "message": f"Rate limit hit. Waiting {round(wait_time, 1)}s to retry field: {field.field_name}",
                                "progress": idx,
                                "total": total,
                            },
                        )
                        logger.warning(
                            "Rate limit hit for field '%s'. Retrying in %.1fs (attempt %d/%d)...",
                            field.field_name,
                            wait_time,
                            attempt + 1,
                            retries,
                        )
                        await asyncio.sleep(wait_time)
                        continue
                    break

                if err:
                    errors.append(
                        TemplateFillError(field_name=field.field_name, reason=err)
                    )
                    yield _sse(
                        "field",
                        {
                            "field_name": field.field_name,
                            "status": "failed",
                            "error": err,
                        },
                    )
                    logger.warning("Field '%s' failed: %s", field.field_name, err)
                    continue

                # Write into the document
                self._write_field(doc, field, answer)
                filled_count += 1
                yield _sse(
                    "field",
                    {
                        "field_name": field.field_name,
                        "status": "filled",
                        "value": answer[:120],  # Preview only in SSE
                        "confidence": round(confidence, 3),
                    },
                )

            # ── 3. Save output PDF ───────────────────────────────────────────
            yield _sse(
                "status", {"stage": "writing", "message": "Saving filled PDF..."}
            )

            output_path = self._output_dir / f"{user_id}_{file_id}_output.pdf"
            try:
                doc.save(str(output_path))
                logger.info("Output saved: %s", output_path)
            except OSError as exc:
                yield _sse("error", {"message": f"Could not save output PDF: {exc}"})
                yield _sse("done", {})
                return

            # ── 4. Final summary ─────────────────────────────────────────────
            status = "completed" if not errors else "completed_with_errors"
            summary = TemplateFillResponse(
                file_id=file_id,
                filename=output_path.name,
                fields_filled=filled_count,
                fields_failed=len(errors),
                field_errors=errors,
                download_url=f"/templates/download/{file_id}",
                status=status,
            )
            yield _sse("complete", summary.model_dump())
            yield _sse("done", {})

            logger.info(
                "Template fill complete: %d filled, %d failed (file_id=%s)",
                filled_count,
                len(errors),
                file_id,
            )

        finally:
            doc.close()

    # ── Private Helpers ──────────────────────────────────────────────────────

    async def _fill_field(self, field_name: str) -> tuple[str, float, Optional[str]]:
        """
        Call QAAgent to get a RAG answer for one field.

        Returns:
            (answer, confidence, error_reason)
            error_reason is None on success, a human-readable string on failure.
        """
        try:
            question = f"What is the value for: {field_name}"
            request = AskRequest(question=question)
            response = await self._qa.answer(request)

            if not response.answer.strip():
                return "", 0.0, "LLM returned an empty answer."

            confidence = max(
                (c.relevance_score for c in response.citations), default=0.0
            )

            # Truncate to prevent layout-breaking overflow
            answer = response.answer.strip()
            if len(answer) > MAX_ANSWER_CHARS:
                logger.warning(
                    "Answer for '%s' truncated (%d → %d chars)",
                    field_name,
                    len(answer),
                    MAX_ANSWER_CHARS,
                )
                answer = answer[:MAX_ANSWER_CHARS] + "…"

            return answer, confidence, None

        except RuntimeError as exc:
            return "", 0.0, str(exc)
        except Exception:  # noqa: BLE001
            logger.exception("Unexpected error filling field '%s'", field_name)
            return "", 0.0, "Unexpected error — see server logs."

    def _write_field(
        self, doc: fitz.Document, field: TemplateField, answer: str
    ) -> None:
        """Write a generated answer into the appropriate location in the PDF."""
        if field.field_type == "acroform":
            self._write_acroform(doc, field.field_name, answer)
        else:
            self._write_text_overlay(doc, field, answer)

    def _write_acroform(self, doc: fitz.Document, field_name: str, answer: str) -> None:
        """Direct AcroForm widget fill — clean, layout-safe."""
        for page in doc:
            for widget in page.widgets():
                if widget.field_name == field_name:
                    widget.field_value = answer
                    widget.update()
                    return
        logger.warning("AcroForm widget '%s' not found in doc.", field_name)

    def _write_text_overlay(
        self, doc: fitz.Document, field: TemplateField, answer: str
    ) -> None:
        """
        Redact the original placeholder text and overlay the answer.

        Works for bracket, underscore, and mustache placeholder types.
        Uses fitz redaction to cleanly erase the original text first,
        then inserts the answer at the same coordinates.
        """
        # Build the search string based on field type
        if field.field_type == "bracket":
            search_str = f"[{field.field_name}]"
        elif field.field_type == "mustache":
            search_str = "{{" + field.field_name + "}}"
        else:
            # underscore: the label is already printed, only erase the underscores
            search_str = "_" * 6  # Match the first run of underscores after label

        page_idx = field.page_number - 1
        if page_idx >= len(doc):
            return

        page = doc[page_idx]
        instances = page.search_for(search_str)
        if not instances:
            logger.debug(
                "Placeholder text '%s' not found on page %d.",
                search_str,
                field.page_number,
            )
            return

        rect = instances[0]  # Use first occurrence only (de-duped at extraction)

        # Redact the placeholder text
        page.add_redact_annot(rect, fill=(1, 1, 1))  # white fill
        page.apply_redactions()

        # Insert the answer at the same position with matching font size
        page.insert_text(
            rect.tl,
            answer,
            fontsize=9,
            color=(0, 0, 0),
        )


# ── SSE Helper ───────────────────────────────────────────────────────────────


def _sse(event: str, data: dict) -> str:
    """Format a Server-Sent Event string."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"
