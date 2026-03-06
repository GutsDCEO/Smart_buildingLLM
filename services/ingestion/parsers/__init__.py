"""
Parser Registry — maps file extensions to their parser implementation.

This module follows OCP: to add a new format, register a new parser here.
No other file needs to change.
"""

from __future__ import annotations

import logging
from pathlib import Path

from parsers.base_parser import BaseParser
from parsers.pdf_parser import PdfParser
from parsers.docx_parser import DocxParser

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Parser Registry — add new parsers here (OCP extension point)
# ──────────────────────────────────────────────────────────────
_PARSERS: list[BaseParser] = [
    PdfParser(),
    DocxParser(),
]

# Build extension → parser lookup map
_EXTENSION_MAP: dict[str, BaseParser] = {}
for parser in _PARSERS:
    for ext in parser.supported_extensions:
        _EXTENSION_MAP[ext] = parser


def get_parser(file_path: Path) -> BaseParser:
    """
    Look up the correct parser for a given file.

    Args:
        file_path: Path to the file (used to detect extension).

    Returns:
        The appropriate BaseParser implementation.

    Raises:
        ValueError: If no parser supports the file extension.
    """
    suffix = file_path.suffix.lower()
    parser = _EXTENSION_MAP.get(suffix)

    if parser is None:
        supported = ", ".join(sorted(_EXTENSION_MAP.keys()))
        raise ValueError(
            f"No parser registered for '{suffix}'. "
            f"Supported formats: {supported}"
        )

    logger.debug("Selected %s for file: %s", parser.__class__.__name__, file_path.name)
    return parser


def get_supported_extensions() -> list[str]:
    """Return all supported file extensions."""
    return sorted(_EXTENSION_MAP.keys())
