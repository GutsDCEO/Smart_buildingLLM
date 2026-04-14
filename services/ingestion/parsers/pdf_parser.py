"""
PDF Parser — extracts text from PDF files using PyMuPDF (fitz).

Two-pass strategy (SRP: parsing lives here, OCR is just a detail):
  Pass 1: Native text extraction via PyMuPDF (fast, lossless).
  Pass 2: If a page returns no text (scanned/image PDF), render it
          as an image and run pytesseract OCR on it (slower but 
          handles 100% scanned documents).

Extends BaseParser (OCP). Adding this parser required zero changes
to the existing codebase.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

import fitz  # PyMuPDF
import pytesseract
from PIL import Image, ImageOps, ImageFilter

from parsers.base_parser import BaseParser
from models import ParsedPage

logger = logging.getLogger(__name__)

# Minimum character count before we consider a page "empty" and run OCR.
# Increased to 200 to ensure pages with only headers/metadata still trigger OCR.
_OCR_THRESHOLD: int = 200

# DPI for rendering pages to images for OCR. Higher = more accurate but slower.
# 400 DPI is excellent for dense technical checklists/tables.
_OCR_DPI: int = 400


class PdfParser(BaseParser):
    """
    Extracts text content from PDF documents page by page.

    Automatically falls back to OCR (via Tesseract) for pages
    that contain only scanned images with no extractable text layer.
    """

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
        ocr_pages: int = 0

        try:
            with fitz.open(str(file_path)) as doc:
                total_pages = len(doc)
                logger.info(
                    "Parsing PDF: %s (%d pages)",
                    file_path.name,
                    total_pages,
                )

                for page_num, page in enumerate(doc, start=1):
                    # --- Pass 1: Native text extraction ---
                    raw_text = page.get_text("text")
                    cleaned = self._clean_text(raw_text)

                    # --- Pass 2: OCR Fallback ---
                    # Calculate punctuation density (periods, ! or ?)
                    punct_count = sum(cleaned.count(p) for p in ".!?")
                    
                    # Trigger OCR if:
                    # 1. Text is too short
                    # 2. Density is < 1 mark per 500 chars (likely bad native layer/metadata)
                    is_too_short = len(cleaned) < _OCR_THRESHOLD
                    is_low_density = len(cleaned) > 20 and (punct_count / len(cleaned)) < 0.002
                    
                    if is_too_short or is_low_density:
                        reason = "short text" if is_too_short else f"low punct density ({punct_count} total)"
                        logger.info(
                            "Triggering OCR for page %d/%d (reason: %s)",
                            page_num, total_pages, reason
                        )
                        ocr_text = self._ocr_page(page, file_path.name, page_num)
                        
                        # Only use OCR text if it's materially different/longer
                        if len(ocr_text) > (len(cleaned) * 1.1):
                            cleaned = ocr_text
                            ocr_pages += 1

                    if not cleaned.strip():
                        logger.debug(
                            "Skipping empty page %d in %s (even after OCR)",
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
                                "total_pages": total_pages,
                                "ingestion_date": datetime.now(timezone.utc).isoformat(),
                                "ocr_used": ocr_pages > 0,
                            },
                        )
                    )

        except fitz.FileDataError as exc:
            logger.error("Corrupted or invalid PDF: %s — %s", file_path.name, exc)
            raise ValueError(f"Cannot parse PDF '{file_path.name}': {exc}") from exc

        if ocr_pages > 0:
            logger.info(
                "Extracted %d non-empty pages from %s (%d via OCR).",
                len(pages),
                file_path.name,
                ocr_pages,
            )
        else:
            logger.info(
                "Extracted %d non-empty pages from %s",
                len(pages),
                file_path.name,
            )

        return pages

    @staticmethod
    def _ocr_page(page: fitz.Page, filename: str, page_num: int) -> str:
        """
        Render a PDF page as a raster image and run Tesseract OCR on it.
        Includes pre-processing filters to improve accuracy on tables/grids.

        Args:
            page: The PyMuPDF page object.
            filename: Source filename for logging.
            page_num: 1-indexed page number for logging.

        Returns:
            Cleaned extracted text, or an empty string on failure.
        """
        try:
            # 1. Render at high resolution (400 DPI)
            mat = fitz.Matrix(_OCR_DPI / 72, _OCR_DPI / 72)
            pix = page.get_pixmap(matrix=mat, colorspace=fitz.csRGB)

            # 2. Convert to Pillow Image
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

            # 3. Vision Upgrade: Aggressive Binarization
            # - Convert to Grayscale
            img = ImageOps.grayscale(img)
            
            # - Thresholding: Everything darker than 180 becomes black (0), else white (255)
            # This erases light gray grid lines and background noise
            img = img.point(lambda x: 0 if x < 180 else 255, '1')
            
            # - Sharpen the resulting image
            img = img.filter(ImageFilter.SHARPEN)
            
            # 4. Run Tesseract with optimized configuration:
            # --psm 1: Automatic page segmentation with OSD (best for complex form layouts)
            # --oem 1: Use LSTM engine only (more modern/accurate)
            custom_config = r'--oem 1 --psm 1'
            text: str = pytesseract.image_to_string(img, lang="eng", config=custom_config)
            
            cleaned = PdfParser._clean_text(text)

            logger.info(
                "OCR on page %d of '%s' yielded %d chars. Sample: %s",
                page_num,
                filename,
                len(cleaned),
                cleaned[:200].replace("\n", " ") + "..." if len(cleaned) > 0 else "EMPTY"
            )
            return cleaned

        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "Tesseract not found — OCR skipped for page %d of '%s'. "
                "Install tesseract-ocr to enable OCR support.",
                page_num,
                filename,
            )
            return ""

        except Exception as exc:
            logger.error(
                "OCR failed for page %d of '%s': %s",
                page_num,
                filename,
                exc,
            )
            return ""

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
