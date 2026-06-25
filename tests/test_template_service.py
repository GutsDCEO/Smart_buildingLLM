"""
Unit Tests — Template Service (PlaceholderExtractor + TemplateService)

FIRST Principles:
  F - Fast:        All file I/O, PyMuPDF, and QAAgent calls are mocked. No real PDFs.
  I - Independent: Fresh fixtures per test via pytest fixtures. Zero shared mutable state.
  R - Repeatable:  Deterministic mock responses. No randomness or environment dependence.
  S - Self-Validating: Explicit assertions on field counts, names, types, error flags.
  T - Timely:      Written alongside template_service.py (Phase 6).

Covers:
  PlaceholderExtractor:
    1.  AcroForm widgets extracted correctly
    2.  Bracket placeholders extracted from flat PDF
    3.  Underscore placeholders extracted
    4.  Mustache tags extracted
    5.  AcroForm takes precedence over text patterns when both exist
    6.  Empty PDF returns zero fields
    7.  Duplicate placeholders de-duplicated

  TemplateService:
    8.  analyze() saves file and returns TemplateAnalyzeResponse
    9.  _fill_field() delegates to QAAgent and returns answer + confidence
    10. _fill_field() returns error when QAAgent raises RuntimeError
    11. _fill_field() truncates answer exceeding MAX_ANSWER_CHARS
    12. fill_stream() yields SSE events and produces complete event
    13. fill_stream() reports failed fields without aborting remaining fields
    14. fill_stream() emits error when file not found
"""

import sys
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "services", "agents"))


# ──────────────────────────────────────────────────────────────
# Helpers — build minimal fitz mock objects
# ──────────────────────────────────────────────────────────────


def _make_widget(field_name: str, field_value: str = "") -> MagicMock:
    """Return a minimal mock of a fitz Widget object."""
    w = MagicMock()
    w.field_name = field_name
    w.field_value = field_value
    w.field_type_string = "Text"
    return w


def _make_page(text: str = "", widgets: list = None) -> MagicMock:
    """Return a minimal mock of a fitz Page object."""
    page = MagicMock()
    page.get_text.return_value = text
    page.widgets.return_value = iter(widgets or [])
    page.search_for.return_value = []
    return page


def _make_doc(pages: list) -> MagicMock:
    """Return a minimal mock of a fitz Document object."""
    doc = MagicMock()
    doc.__len__ = MagicMock(return_value=len(pages))
    doc.__iter__ = MagicMock(side_effect=lambda: iter(pages))
    doc.__getitem__ = MagicMock(side_effect=lambda i: pages[i])
    doc.close = MagicMock()
    doc.save = MagicMock()
    return doc


def _make_qa_agent(answer: str = "Test answer", score: float = 0.88) -> AsyncMock:
    """Return a mock QAAgent whose answer() returns a deterministic response."""
    from models import AskResponse, Citation

    agent = AsyncMock()
    response = AskResponse(
        answer=answer,
        citations=[
            Citation(
                source_file="boiler-log.pdf",
                page_number=2,
                chunk_index=0,
                relevance_score=score,
            )
        ],
    )
    agent.answer = AsyncMock(return_value=response)
    return agent


# ──────────────────────────────────────────────────────────────
# PlaceholderExtractor Tests
# ──────────────────────────────────────────────────────────────


class TestPlaceholderExtractor:
    """Tests for the multi-format placeholder extraction strategy chain."""

    def setup_method(self):
        from template_service import PlaceholderExtractor

        self.extractor = PlaceholderExtractor()

    # ── Test 1: AcroForm widgets ──────────────────────────────

    def test_extracts_acroform_widgets(self):
        """Should extract AcroForm widget names when interactive fields exist."""
        widgets = [
            _make_widget("Inspector Name", ""),
            _make_widget("Date of Inspection", "2026-01-01"),
            _make_widget("Building ID", ""),
        ]
        pages = [_make_page(widgets=widgets)]
        doc = _make_doc(pages)

        fields = self.extractor.extract(doc)

        assert len(fields) == 3
        names = [f.field_name for f in fields]
        assert "Inspector Name" in names
        assert "Date of Inspection" in names
        assert all(f.field_type == "acroform" for f in fields)

    def test_acroform_preserves_existing_value(self):
        """AcroForm fields with existing values should record current_value."""
        widgets = [_make_widget("Date", "2026-06-01")]
        doc = _make_doc([_make_page(widgets=widgets)])

        fields = self.extractor.extract(doc)

        assert fields[0].current_value == "2026-06-01"

    # ── Test 2: Bracket placeholders ─────────────────────────

    def test_extracts_bracket_placeholders(self):
        """Should detect [Field Name] style placeholders in flat PDF text."""
        text = "Building name: [Building Name]\nLocation: [City, Country]\n"
        doc = _make_doc([_make_page(text=text)])

        fields = self.extractor.extract(doc)

        names = [f.field_name for f in fields]
        assert "Building Name" in names
        assert "City, Country" in names
        assert all(f.field_type == "bracket" for f in fields)

    # ── Test 3: Underscore placeholders ──────────────────────

    def test_extracts_underscore_placeholders(self):
        """Should detect 'Label: ____' patterns."""
        text = "Inspector: ___________\nDate: __________\n"
        doc = _make_doc([_make_page(text=text)])

        fields = self.extractor.extract(doc)

        assert len(fields) >= 1
        assert any(f.field_type == "underscore" for f in fields)

    # ── Test 4: Mustache tags ─────────────────────────────────

    def test_extracts_mustache_tags(self):
        """Should detect {{field_name}} style mustache placeholders."""
        text = "Building: {{building_name}}\nStatus: {{compliance_status}}\n"
        doc = _make_doc([_make_page(text=text)])

        fields = self.extractor.extract(doc)

        names = [f.field_name for f in fields]
        assert "building_name" in names
        assert "compliance_status" in names
        assert all(f.field_type == "mustache" for f in fields)

    # ── Test 5: AcroForm takes precedence ────────────────────

    def test_acroform_takes_priority_over_text_patterns(self):
        """When AcroForm widgets exist, text-pattern scan must be skipped."""
        widgets = [_make_widget("Inspector")]
        # Page also has bracket text — should be ignored
        page = _make_page(text="Building: [Building Name]", widgets=widgets)
        doc = _make_doc([page])

        fields = self.extractor.extract(doc)

        # Only the AcroForm widget, not the bracket
        assert all(f.field_type == "acroform" for f in fields)
        assert len(fields) == 1

    # ── Test 6: Empty PDF ─────────────────────────────────────

    def test_empty_pdf_returns_no_fields(self):
        """An empty PDF with no text or widgets returns an empty list."""
        doc = _make_doc([_make_page(text="")])

        fields = self.extractor.extract(doc)

        assert fields == []

    # ── Test 7: Deduplication ─────────────────────────────────

    def test_duplicate_placeholders_deduplicated(self):
        """The same placeholder appearing on multiple pages is extracted only once."""
        text = "[Building Name]"
        pages = [_make_page(text=text), _make_page(text=text)]
        doc = _make_doc(pages)

        fields = self.extractor.extract(doc)

        names = [f.field_name for f in fields]
        assert names.count("Building Name") == 1


# ──────────────────────────────────────────────────────────────
# TemplateService Tests
# ──────────────────────────────────────────────────────────────


class TestTemplateService:
    """Tests for the TemplateService orchestration layer."""

    def setup_method(self):
        """Fresh service instance with mocked QAAgent and output dir."""
        self._qa = _make_qa_agent()

    def _make_service(self, tmp_path: Path):
        from template_service import TemplateService

        with patch("template_service.settings") as mock_settings:
            mock_settings.template_output_dir = str(tmp_path)
            mock_settings.template_max_upload_mb = 25
            svc = TemplateService(self._qa)
            svc._output_dir = tmp_path
        return svc

    # ── Test 8: analyze() ────────────────────────────────────

    @pytest.mark.asyncio
    async def test_analyze_saves_file_and_returns_response(self, tmp_path):
        """analyze() should persist the PDF and return detected fields."""
        from template_service import PlaceholderExtractor
        from models import TemplateField

        svc = self._make_service(tmp_path)
        fake_fields = [
            TemplateField(field_name="Inspector", field_type="bracket", page_number=1),
            TemplateField(field_name="Date", field_type="bracket", page_number=1),
        ]
        fake_bytes = b"%PDF-1.4 fake content"

        with (
            patch("template_service.fitz.open") as mock_fitz,
            patch.object(PlaceholderExtractor, "extract", return_value=fake_fields),
        ):
            mock_doc = MagicMock()
            mock_doc.close = MagicMock()
            mock_fitz.return_value = mock_doc

            result = await svc.analyze(fake_bytes, "checklist.pdf", user_id=42)

        assert result.total_fields == 2
        assert result.filename == "checklist.pdf"
        assert result.file_id  # Non-empty UUID
        # File should be persisted
        saved_files = list(tmp_path.glob("42_*_input.pdf"))
        assert len(saved_files) == 1

    # ── Test 9: _fill_field() happy path ─────────────────────

    @pytest.mark.asyncio
    async def test_fill_field_returns_answer_and_confidence(self, tmp_path):
        """_fill_field() should call QAAgent and return the answer with confidence."""

        svc = self._make_service(tmp_path)
        answer, confidence, error = await svc._fill_field("Inspector Name")

        assert answer == "Test answer"
        assert confidence == pytest.approx(0.88, abs=0.001)
        assert error is None
        self._qa.answer.assert_called_once()

    # ── Test 10: _fill_field() error path ────────────────────

    @pytest.mark.asyncio
    async def test_fill_field_returns_error_on_runtime_error(self, tmp_path):
        """When QAAgent raises RuntimeError, _fill_field returns an error string."""

        svc = self._make_service(tmp_path)
        self._qa.answer = AsyncMock(side_effect=RuntimeError("Qdrant not connected"))

        answer, confidence, error = await svc._fill_field("Building Name")

        assert answer == ""
        assert error == "Qdrant not connected"

    # ── Test 11: _fill_field() truncation ────────────────────

    @pytest.mark.asyncio
    async def test_fill_field_truncates_long_answer(self, tmp_path):
        """Answers exceeding MAX_ANSWER_CHARS should be truncated with ellipsis."""
        from template_service import MAX_ANSWER_CHARS

        long_answer = "A" * (MAX_ANSWER_CHARS + 50)
        self._qa = _make_qa_agent(answer=long_answer)
        svc = self._make_service(tmp_path)

        answer, _, error = await svc._fill_field("Some Field")

        assert error is None
        assert len(answer) == MAX_ANSWER_CHARS + 1  # +1 for the ellipsis char
        assert answer.endswith("…")

    # ── Test 12: fill_stream() happy path ────────────────────

    @pytest.mark.asyncio
    async def test_fill_stream_yields_complete_event(self, tmp_path):
        """fill_stream() must yield a 'complete' SSE event with correct counts."""
        from template_service import PlaceholderExtractor
        from models import TemplateField

        svc = self._make_service(tmp_path)
        file_id = "test-uuid-1234"

        # Create fake input file
        input_file = tmp_path / f"42_{file_id}_input.pdf"
        input_file.write_bytes(b"%PDF-1.4 fake")

        fake_fields = [
            TemplateField(field_name="Inspector", field_type="bracket", page_number=1),
            TemplateField(field_name="Date", field_type="bracket", page_number=1),
        ]

        chunks = []
        events = []
        with (
            patch("template_service.fitz.open") as mock_fitz,
            patch.object(PlaceholderExtractor, "extract", return_value=fake_fields),
        ):
            mock_doc = _make_doc([_make_page(text="[Inspector]\n[Date]")])
            mock_fitz.return_value = mock_doc

            async for chunk in svc.fill_stream(file_id=file_id, user_id=42):
                chunks.append(chunk)
                # Parse each SSE event line
                for line in chunk.strip().split("\n"):
                    if line.startswith("event: "):
                        events.append(line.replace("event: ", ""))

        assert "complete" in events
        assert "done" in events
        assert len(events) > 0
        all_text = "".join(chunks)
        assert "event: complete" in all_text

    # ── Test 13: fill_stream() partial failure ────────────────

    @pytest.mark.asyncio
    async def test_fill_stream_continues_after_field_failure(self, tmp_path):
        """A failing field should not stop the fill loop for remaining fields."""
        from template_service import PlaceholderExtractor
        from models import TemplateField

        svc = self._make_service(tmp_path)
        file_id = "test-uuid-fail"

        input_file = tmp_path / f"42_{file_id}_input.pdf"
        input_file.write_bytes(b"%PDF-1.4 fake")

        fake_fields = [
            TemplateField(field_name="FailField", field_type="bracket", page_number=1),
            TemplateField(field_name="OkField", field_type="bracket", page_number=1),
        ]

        call_count = 0

        async def _side_effect(request):
            nonlocal call_count
            call_count += 1
            if "FailField" in request.question:
                raise RuntimeError("No RAG results")
            from models import AskResponse

            return AskResponse(answer="OK answer", citations=[])

        svc._qa.answer = _side_effect

        events = []
        with (
            patch("template_service.fitz.open") as mock_fitz,
            patch.object(PlaceholderExtractor, "extract", return_value=fake_fields),
        ):
            mock_doc = _make_doc([_make_page()])
            mock_fitz.return_value = mock_doc

            async for chunk in svc.fill_stream(file_id=file_id, user_id=42):
                events.append(chunk)

        # Both fields were attempted (call_count == 2)
        assert call_count == 2

        all_text = "".join(events)
        assert "failed" in all_text
        assert "filled" in all_text

    # ── Test 14: fill_stream() file not found ─────────────────

    @pytest.mark.asyncio
    async def test_fill_stream_emits_error_for_missing_file(self, tmp_path):
        """fill_stream() must emit an error SSE event when the file_id is unknown."""

        svc = self._make_service(tmp_path)

        events = []
        async for chunk in svc.fill_stream(file_id="nonexistent-id", user_id=99):
            events.append(chunk)

        all_text = "".join(events)
        assert "event: error" in all_text
        assert "event: done" in all_text

    # ── Test 15: fill_stream() rate limit retry ─────────────────

    @pytest.mark.asyncio
    async def test_fill_stream_retries_on_rate_limit(self, tmp_path):
        """fill_stream() must retry when hitting a rate limit error."""
        from template_service import PlaceholderExtractor
        from models import TemplateField

        svc = self._make_service(tmp_path)
        file_id = "test-uuid-retry"

        input_file = tmp_path / f"42_{file_id}_input.pdf"
        input_file.write_bytes(b"%PDF-1.4 fake")

        fake_fields = [
            TemplateField(field_name="Inspector", field_type="bracket", page_number=1),
        ]

        call_count = 0

        async def _side_effect(request):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("LLM rate limit reached. Try again shortly.")
            from models import AskResponse

            return AskResponse(answer="Success after retry", citations=[])

        svc._qa.answer = _side_effect

        events = []
        with (
            patch("template_service.fitz.open") as mock_fitz,
            patch.object(PlaceholderExtractor, "extract", return_value=fake_fields),
            patch(
                "template_service.asyncio.sleep", new_callable=AsyncMock
            ) as mock_sleep,
        ):
            mock_doc = _make_doc([_make_page()])
            mock_fitz.return_value = mock_doc

            async for chunk in svc.fill_stream(file_id=file_id, user_id=42):
                events.append(chunk)

        assert call_count == 2
        mock_sleep.assert_called_once_with(5.0)

        all_text = "".join(events)
        assert "Success after retry" in all_text
        assert "Rate limit hit" in all_text
