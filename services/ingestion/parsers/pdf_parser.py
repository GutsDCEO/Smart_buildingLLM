"""
PDF Parser — extracts text from PDF files using PyMuPDF (fitz).

Extends BaseParser (OCP). Adding this parser required zero changes
to the existing codebase.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF

from parsers.base_parser import BaseParser
from models import ParsedPage

logger = logging.getLogger(__name__)


class PdfParser(BaseParser):
    """Extracts text content from PDF documents page by page."""

    @property
    def supported_extensions(self) -> tuple[str, ...]:
        return (".pdf",)

    def parse(self, file_path: Path) -> list[ParsedPage]:
        """
        Extract text from each page of a PDF file.

        Args:
            file_path: Path to the PDF file.

        Returns:
            List of ParsedPage, one per page with non-empty text.
        """
        self.validate_file(file_path)

        pages: list[ParsedPage] = []

        try:
            with fitz.open(str(file_path)) as doc:
                logger.info(
                    "Parsing PDF: %s (%d pages)",
                    file_path.name,
                    len(doc),
                )

                for page_num, page in enumerate(doc, start=1):
                    raw_text = page.get_text("text")
                    cleaned = self._clean_text(raw_text)

                    if not cleaned.strip():
                        logger.debug(
                            "Skipping empty page %d in %s",
                            page_num,
                            file_path.name,
                        )
                        continue

                    pages.append(
                        ParsedPage(
                            text=cleaned,
                            page_number=page_num,
                            source_file=file_path.name,
                            metadata={
                                "total_pages": len(doc),
                                "ingestion_date": datetime.now(timezone.utc).isoformat(),
                            },
                        )
                    )

        except fitz.FileDataError as exc:
            logger.error("Corrupted or invalid PDF: %s — %s", file_path.name, exc)
            raise ValueError(f"Cannot parse PDF '{file_path.name}': {exc}") from exc

        logger.info(
            "Extracted %d non-empty pages from %s",
            len(pages),
            file_path.name,
        )
        return pages

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Remove common PDF extraction noise.

        - Collapses excessive whitespace
        - Strips leading/trailing whitespace per line
        """
        lines = text.splitlines()
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return "\n".join(cleaned_lines)
