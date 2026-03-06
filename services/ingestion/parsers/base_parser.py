"""
Abstract Base Parser — defines the contract all document parsers must follow.

Design Principles:
  - DIP: Consumers depend on BaseParser, never on PdfParser/DocxParser directly.
  - OCP: Adding a new parser (HTML, CSV) = new file, zero changes to existing code.
  - ISP: Single method interface — parsers only implement `parse()`.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path

from models import ParsedPage

logger = logging.getLogger(__name__)


class BaseParser(ABC):
    """Abstract base class for all document parsers."""

    @property
    @abstractmethod
    def supported_extensions(self) -> tuple[str, ...]:
        """File extensions this parser can handle (e.g., ('.pdf',))."""
        ...

    @abstractmethod
    def parse(self, file_path: Path) -> list[ParsedPage]:
        """
        Extract text from a document file.

        Args:
            file_path: Path to the document file.

        Returns:
            A list of ParsedPage objects, one per page/section.

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file type is not supported by this parser.
        """
        ...

    def validate_file(self, file_path: Path) -> None:
        """
        Common pre-parse validation. Fail early at the boundary (Quality Rule ④).

        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the extension is not supported.
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix not in self.supported_extensions:
            raise ValueError(
                f"Unsupported file type '{suffix}' for {self.__class__.__name__}. "
                f"Supported: {self.supported_extensions}"
            )

        logger.info(
            "Validated file for parsing: %s (%s)",
            file_path.name,
            suffix,
        )
