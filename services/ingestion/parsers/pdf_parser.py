"""
PDF Parser — extracts text from PDF files.

Three-pass strategy (SRP: parsing lives here, OCR/AI are details):
  Pass 1: Native text extraction via PyMuPDF (fast, lossless).
           Ideal for digital/text-layer PDFs.
  Pass 2: IBM Docling deep-learning layout engine (TableFormer ACCURATE).
           Handles scanned PDFs with complex tables, checklists, grids.
  Pass 3: Tesseract OCR safety net — only if Docling also fails or produces
           insufficient text. Ensures no page is ever left empty.

Extends BaseParser (OCP). Adding this parser required zero changes
to the existing codebase (main.py, chunker.py, etc.).
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

# Minimum character count before we consider a page "empty" and escalate.
# Increased to 200 to catch pages with only headers/metadata.
_OCR_THRESHOLD: int = 200

# DPI for Tesseract rendering (Pass 3 safety net only).
_TESSERACT_DPI: int = 400


class PdfParser(BaseParser):
    """
    Extracts text content from PDF documents page by page.

    Cascade strategy:
      1. PyMuPDF native — fast path for digital PDFs
      2. IBM Docling (TableFormer ACCURATE) — deep-learning for scanned/table PDFs
      3. Tesseract OCR — safety net if Docling is unavailable or insufficient
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
        docling_pages: int = 0
        tesseract_pages: int = 0
        needs_fallback: list[int] = []  # 1-indexed page numbers needing Pass 2+

        # ── Pass 1: PyMuPDF native text extraction ──────────────────────────
        try:
            with fitz.open(str(file_path)) as doc:
                total_pages = len(doc)
                logger.info(
                    "Parsing PDF: %s (%d pages)",
                    file_path.name,
                    total_pages,
                )

                pymupdf_texts: dict[int, str] = {}
                fitz_pages: dict[int, fitz.Page] = {}

                for page_num, page in enumerate(doc, start=1):
                    raw_text = page.get_text("text")
                    cleaned = self._clean_text(raw_text)

                    # Quality gate: too short or low punctuation density
                    punct_count = sum(cleaned.count(p) for p in ".!?")
                    is_too_short = len(cleaned) < _OCR_THRESHOLD
                    is_low_density = (
                        len(cleaned) > 20
                        and (punct_count / len(cleaned)) < 0.002
                    )

                    if is_too_short or is_low_density:
                        reason = (
                            "short text"
                            if is_too_short
                            else f"low punct density ({punct_count} marks)"
                        )
                        logger.info(
                            "Page %d/%d needs fallback (reason: %s)",
                            page_num, total_pages, reason,
                        )
                        needs_fallback.append(page_num)

                    pymupdf_texts[page_num] = cleaned

                # Keep page objects accessible for Tesseract (Pass 3)
                # We re-open the doc below so pages are still valid
                fitz_page_data: dict[int, bytes] = {}
                if needs_fallback:
                    for page_num, page in enumerate(doc, start=1):
                        if page_num in needs_fallback:
                            mat = fitz.Matrix(
                                _TESSERACT_DPI / 72, _TESSERACT_DPI / 72
                            )
                            pix = page.get_pixmap(
                                matrix=mat, colorspace=fitz.csRGB
                            )
                            fitz_page_data[page_num] = (
                                pix.width, pix.height, pix.samples
                            )

        except fitz.FileDataError as exc:
            logger.error(
                "Corrupted or invalid PDF: %s — %s", file_path.name, exc
            )
            raise ValueError(
                f"Cannot parse PDF '{file_path.name}': {exc}"
            ) from exc

        # ── Pass 2: Docling deep-learning fallback ───────────────────────────
        docling_texts: dict[int, str] = {}
        if needs_fallback:
            logger.info(
                "Running Docling on %s for %d pages: %s",
                file_path.name, len(needs_fallback), needs_fallback,
            )
            docling_texts = self._docling_convert(file_path, needs_fallback)

        # ── Pass 3: Tesseract safety net for pages Docling couldn't cover ────
        tesseract_texts: dict[int, str] = {}
        still_needs_fallback = [
            p for p in needs_fallback
            if not docling_texts.get(p)
            or len(docling_texts.get(p, "")) <= (
                len(pymupdf_texts.get(p, "")) * 1.1
            )
        ]
        if still_needs_fallback:
            logger.info(
                "Tesseract safety net for %d pages: %s",
                len(still_needs_fallback), still_needs_fallback,
            )
            for page_num in still_needs_fallback:
                if page_num in fitz_page_data:
                    w, h, samples = fitz_page_data[page_num]
                    tesseract_texts[page_num] = self._tesseract_page(
                        w, h, samples, file_path.name, page_num
                    )

        # ── Assemble final pages from best available text ────────────────────
        for page_num in range(1, total_pages + 1):
            pymupdf_text = pymupdf_texts.get(page_num, "")
            docling_text = docling_texts.get(page_num, "")
            tesseract_text = tesseract_texts.get(page_num, "")

            # Cascade: prefer Docling over Tesseract over PyMuPDF
            if page_num in needs_fallback:
                if len(docling_text) > (len(pymupdf_text) * 1.1):
                    text = docling_text
                    docling_pages += 1
                    source = "docling"
                elif len(tesseract_text) > (len(pymupdf_text) * 1.1):
                    text = tesseract_text
                    tesseract_pages += 1
                    source = "tesseract"
                else:
                    text = pymupdf_text
                    source = "pymupdf"
            else:
                text = pymupdf_text
                source = "pymupdf"

            if not text.strip():
                logger.debug(
                    "Skipping empty page %d in %s (even after all passes)",
                    page_num,
                    file_path.name,
                )
                continue

            pages.append(
                ParsedPage(
                    text=text,
                    page_number=page_num,
                    source_file=file_path.name,
                    metadata={
                        "total_pages": total_pages,
                        "ingestion_date": datetime.now(timezone.utc).isoformat(),
                        "extraction_source": source,
                        "docling_used": source == "docling",
                        "ocr_used": source in ("docling", "tesseract"),
                    },
                )
            )

        # ── Summary logging ──────────────────────────────────────────────────
        total = len(pages)
        pymupdf_count = total - docling_pages - tesseract_pages
        logger.info(
            "Extracted %d pages from %s: %d PyMuPDF | %d Docling | %d Tesseract",
            total, file_path.name, pymupdf_count, docling_pages, tesseract_pages,
        )

        return pages

    # ── Pass 2: IBM Docling ──────────────────────────────────────────────────

    @staticmethod
    def _docling_convert(
        file_path: Path,
        page_numbers: list[int],
    ) -> dict[int, str]:
        """
        Run IBM Docling (TableFormer ACCURATE) on specific pages of a PDF.

        To save memory and avoid OOM crashes on large documents, we extract
        the target pages into a temporary PDF before processing.

        Args:
            file_path: Path to the original PDF.
            page_numbers: List of 1-indexed page numbers to process.

        Returns:
            Dict mapping original 1-indexed page number → extracted text.
        """
        if not page_numbers:
            return {}

        try:
            from docling.document_converter import (          # noqa: PLC0415
                DocumentConverter,
                PdfFormatOption,
            )
            from docling.datamodel.base_models import InputFormat  # noqa: PLC0415
            from docling.datamodel.pipeline_options import (       # noqa: PLC0415
                PdfPipelineOptions,
                TableStructureOptions,
                TableFormerMode,
            )
        except ImportError:
            logger.warning("Docling not installed — skippingPass 2.")
            return {}

        import tempfile  # noqa: PLC0415
        temp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
        temp_pdf_path = Path(temp_pdf.name)
        temp_pdf.close()

        try:
            # 1. Extract specific pages using PyMuPDF to a temp file
            with fitz.open(str(file_path)) as src:
                dst = fitz.open()
                for p in page_numbers:
                    dst.insert_pdf(src, from_page=p - 1, to_page=p - 1)
                dst.save(str(temp_pdf_path))
                dst.close()

            # 2. Configure Docling
            pipeline_opts = PdfPipelineOptions()
            pipeline_opts.do_table_structure = True
            pipeline_opts.table_structure_options = TableStructureOptions(
                mode=TableFormerMode.ACCURATE
            )

            converter = DocumentConverter(
                format_options={
                    InputFormat.PDF: PdfFormatOption(
                        pipeline_options=pipeline_opts
                    )
                }
            )

            logger.info(
                "Docling: processing %d pages from %s",
                len(page_numbers), file_path.name
            )
            result = converter.convert(str(temp_pdf_path))

            # 3. Export markdown and map back to original page numbers
            page_texts: dict[int, str] = {}
            for i, original_page_no in enumerate(page_numbers, start=1):
                try:
                    # Docling result indices for the temp PDF (1-indexed)
                    md = result.document.export_to_markdown(page_no=i)
                    cleaned = PdfParser._clean_text(md)
                    if cleaned:
                        page_texts[original_page_no] = cleaned
                except Exception as page_exc:
                    logger.warning(
                        "Docling: failed to export page %d: %s",
                        original_page_no, page_exc,
                    )

            return page_texts

        except Exception as exc:
            logger.error("Docling failed: %s", exc)
            return {}
        finally:
            if temp_pdf_path.exists():
                temp_pdf_path.unlink()

    # ── Pass 3: Tesseract safety net ────────────────────────────────────────

    @staticmethod
    def _tesseract_page(
        width: int,
        height: int,
        samples: bytes,
        filename: str,
        page_num: int,
    ) -> str:
        """
        Run Tesseract OCR on a pre-rendered page image (safety net).

        Includes aggressive binarization pre-processing to handle grid lines
        and table backgrounds common in HVAC checklists.

        Args:
            width: Pixel width of the rendered image.
            height: Pixel height of the rendered image.
            samples: Raw RGB pixel bytes from PyMuPDF.
            filename: Source filename for logging.
            page_num: 1-indexed page number for logging.

        Returns:
            Cleaned extracted text, or empty string on failure.
        """
        try:
            img = Image.frombytes("RGB", [width, height], samples)

            # Pre-processing: grayscale → threshold → sharpen
            img = ImageOps.grayscale(img)
            img = img.point(lambda x: 0 if x < 180 else 255, "1")
            img = img.filter(ImageFilter.SHARPEN)

            # LSTM engine, automatic page segmentation with OSD
            custom_config = r"--oem 1 --psm 1"
            text: str = pytesseract.image_to_string(
                img, lang="eng", config=custom_config
            )
            cleaned = PdfParser._clean_text(text)

            logger.info(
                "Tesseract (safety net) page %d of '%s': %d chars. "
                "Sample: %s",
                page_num,
                filename,
                len(cleaned),
                (cleaned[:200].replace("\n", " ") + "...")
                if cleaned
                else "EMPTY",
            )
            return cleaned

        except pytesseract.TesseractNotFoundError:
            logger.warning(
                "Tesseract not found — safety net skipped for page %d of '%s'.",
                page_num, filename,
            )
            return ""

        except Exception as exc:
            logger.error(
                "Tesseract failed for page %d of '%s': %s",
                page_num, filename, exc,
            )
            return ""

    # ── Shared utilities ─────────────────────────────────────────────────────

    @staticmethod
    def _clean_text(text: str) -> str:
        """
        Remove common PDF/OCR extraction noise.

        - Collapses excessive whitespace
        - Strips leading/trailing whitespace per line
        """
        lines = text.splitlines()
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return "\n".join(cleaned_lines)
