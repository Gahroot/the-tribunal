"""Tests for knowledge-document text extraction.

Verifies format detection (by filename + MIME), the plain-text / CSV / DOCX happy
paths, and that malformed or unsupported inputs raise :class:`TextExtractionError`
(so the ingest flow rolls back instead of leaking a parser stack trace).
"""

from __future__ import annotations

import io

import pytest

from app.services.knowledge.text_extraction import (
    TextExtractionError,
    extract_text,
    normalize_extension,
)


class TestNormalizeExtension:
    def test_resolves_by_filename(self) -> None:
        assert normalize_extension(filename="notes.MD", content_type=None) == "md"
        assert normalize_extension(filename="a.markdown", content_type=None) == "md"
        assert normalize_extension(filename="data.csv", content_type=None) == "csv"

    def test_falls_back_to_content_type(self) -> None:
        assert normalize_extension(filename=None, content_type="application/pdf") == "pdf"
        assert normalize_extension(filename="x.unknown", content_type="text/csv") == "csv"

    def test_unknown_returns_none(self) -> None:
        assert normalize_extension(filename="image.png", content_type=None) is None
        assert normalize_extension(filename=None, content_type=None) is None


class TestExtract:
    def test_txt_and_md_decode_plain(self) -> None:
        assert extract_text(b"  hello world  ", filename="a.txt") == "hello world"
        assert extract_text(b"# Title\n\nBody", filename="a.md") == "# Title\n\nBody"

    def test_csv_flattens_rows(self) -> None:
        data = b"name,role\nAda,eng\nGrace,admiral\n"
        out = extract_text(data, filename="people.csv")
        assert out == "name, role\nAda, eng\nGrace, admiral"

    def test_docx_extracts_paragraphs(self) -> None:
        docx = pytest.importorskip("docx")
        document = docx.Document()
        document.add_paragraph("First paragraph.")
        document.add_paragraph("Second paragraph.")
        buf = io.BytesIO()
        document.save(buf)

        out = extract_text(
            buf.getvalue(),
            content_type=(
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            ),
        )
        assert "First paragraph." in out
        assert "Second paragraph." in out

    def test_unsupported_type_raises(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"\x89PNG", filename="logo.png")

    def test_malformed_pdf_raises(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"not really a pdf", filename="broken.pdf")

    def test_malformed_docx_raises(self) -> None:
        with pytest.raises(TextExtractionError):
            extract_text(b"not really a docx", filename="broken.docx")
