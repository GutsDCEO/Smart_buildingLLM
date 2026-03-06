"""
DOCX Parser — extracts text from Word documents using python-docx.

Extends BaseParser (OCP). DOCX files don't have physical "pages,"
so we treat each paragraph as a logical section.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError

from parsers.base_parser import BaseParser
from models import ParsedPage

logger = logging.getLogger(__name__)


class DocxParser(BaseParser):
    """Extracts text content from DOCX documents paragraph by paragraph."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".docx",)

    def parse(self, file_path: Path) -> list[ParsedPage]:
        """
        Extract text from a DOCX file.

        Concatenates all paragraphs into a single ParsedPage per logical
        section. Since DOCX has no page concept, we group all text as
        page_number=1 and let the chunker handle splitting.

        Args:
            file_path: Path to the DOCX file.

        Returns:
            List containing one ParsedPage with all document text.
        """
        self.validate_file(file_path)

        try:
            doc = Document(str(file_path))
        except PackageNotFoundError as exc:
            logger.error("Invalid DOCX file: %s — %s", file_path.name, exc)
            raise ValueError(f"Cannot parse DOCX '{file_path.name}': {exc}") from exc

        paragraphs = [p.text.strip() for p in doc.paragraphs if p.text.strip()]

        if not paragraphs:
            logger.warning("No text found in DOCX: %s", file_path.name)
            return []

        full_text = "\n".join(paragraphs)

        logger.info(
            "Extracted %d paragraphs from %s",
            len(paragraphs),
            file_path.name,
        )

        return [
            ParsedPage(
                text=full_text,
                page_number=1,
                source_file=file_path.name,
                metadata={
                    "paragraph_count": len(paragraphs),
                    "ingestion_date": datetime.now(timezone.utc).isoformat(),
                },
            )
        ]
