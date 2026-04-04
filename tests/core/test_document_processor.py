"""Tests for FAQParser, DefaultParser, and ParserRegistry."""
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.default import DefaultParser
from core.knowledge.parsers.faq import FAQParser
from core.knowledge.parsers.registry import ParserRegistry


DOC_ID = "doc-001"
BASE_METADATA = {"source": "test"}

FAQ_CONTENT = """\
Q: What is your return policy?
A: You can return items within 30 days of purchase.

Q: How do I track my order?
A: Log in to your account and visit the Orders section.

Q: Do you offer free shipping?
A: Yes, on orders over $50.
"""


# ---------------------------------------------------------------------------
# FAQParser tests
# ---------------------------------------------------------------------------


class TestFAQParser:
    @pytest.fixture
    def parser(self):
        return FAQParser()

    def test_faq_parser_can_handle_faq_txt(self, parser):
        assert parser.can_handle("txt", "faq document") is True

    def test_faq_parser_can_handle_explicit_faq_type(self, parser):
        """file_type='faq' must match even with an empty content_hint."""
        assert parser.can_handle("faq") is True
        assert parser.can_handle("faq", "") is True
        assert parser.can_handle("faq", "faq content") is True

    def test_faq_parser_cannot_handle_pdf(self, parser):
        assert parser.can_handle("pdf") is False

    def test_faq_parser_cannot_handle_txt_without_hint(self, parser):
        """Plain txt without faq hint should not be handled by FAQParser."""
        assert parser.can_handle("txt", "product manual") is False

    def test_faq_parser_extracts_qa_pairs(self, parser):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(FAQ_CONTENT)
            tmp_path = f.name
        try:
            chunks = parser.parse(tmp_path, DOC_ID, BASE_METADATA)
            assert len(chunks) == 3
        finally:
            os.unlink(tmp_path)

    def test_faq_parser_qa_content_format(self, parser):
        """Each chunk content should follow 'Q: ...\\nA: ...' format."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(FAQ_CONTENT)
            tmp_path = f.name
        try:
            chunks = parser.parse(tmp_path, DOC_ID, BASE_METADATA)
            for chunk in chunks:
                lines = chunk["content"].split("\n")
                assert lines[0].startswith("Q: ")
                assert lines[1].startswith("A: ")
        finally:
            os.unlink(tmp_path)

    def test_faq_parser_chunk_structure(self, parser):
        """Every chunk must have required keys and correct doc_id."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(FAQ_CONTENT)
            tmp_path = f.name
        try:
            chunks = parser.parse(tmp_path, DOC_ID, BASE_METADATA)
            for chunk in chunks:
                assert "chunk_id" in chunk
                assert chunk["doc_id"] == DOC_ID
                assert "content" in chunk
                assert "metadata" in chunk
                assert chunk["metadata"]["type"] == "faq"
                assert "question" in chunk["metadata"]
        finally:
            os.unlink(tmp_path)

    def test_faq_parser_correct_questions_extracted(self, parser):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(FAQ_CONTENT)
            tmp_path = f.name
        try:
            chunks = parser.parse(tmp_path, DOC_ID, BASE_METADATA)
            questions = [c["metadata"]["question"] for c in chunks]
            assert "What is your return policy?" in questions
            assert "How do I track my order?" in questions
            assert "Do you offer free shipping?" in questions
        finally:
            os.unlink(tmp_path)


# ---------------------------------------------------------------------------
# ParserRegistry tests
# ---------------------------------------------------------------------------


class TestParserRegistry:
    def test_registry_returns_correct_parser(self):
        registry = ParserRegistry()
        faq_parser = FAQParser()
        mock_chunker = MagicMock()
        mock_chunker.chunk.return_value = []
        default_parser = DefaultParser(chunker=mock_chunker)

        registry.register(faq_parser)
        registry.register(default_parser)

        # FAQ hint → FAQParser
        assert registry.get_parser("txt", "faq guide") is faq_parser
        # Plain txt without hint → DefaultParser (FAQParser returns False)
        assert registry.get_parser("txt", "manual") is default_parser
        # PDF → DefaultParser
        assert registry.get_parser("pdf") is default_parser

    def test_registry_raises_for_unknown_type(self):
        registry = ParserRegistry()
        registry.register(FAQParser())
        with pytest.raises(ValueError, match="No parser registered"):
            registry.get_parser("xlsx")

    def test_registry_first_match_wins(self):
        """When two parsers both can_handle, the first registered wins."""
        registry = ParserRegistry()
        mock_chunker = MagicMock()
        mock_chunker.chunk.return_value = []
        parser_a = DefaultParser(chunker=mock_chunker)
        parser_b = DefaultParser(chunker=mock_chunker)
        registry.register(parser_a)
        registry.register(parser_b)
        assert registry.get_parser("txt") is parser_a

    def test_registry_empty_raises(self):
        registry = ParserRegistry()
        with pytest.raises(ValueError):
            registry.get_parser("pdf")


# ---------------------------------------------------------------------------
# DefaultParser tests
# ---------------------------------------------------------------------------


class TestDefaultParser:
    @pytest.fixture
    def mock_chunker(self):
        chunker = MagicMock()
        chunker.chunk.return_value = [
            {
                "chunk_id": "c1",
                "doc_id": DOC_ID,
                "content": "mocked chunk",
                "metadata": {"chunk_index": 0},
            }
        ]
        return chunker

    @pytest.fixture
    def parser(self, mock_chunker):
        return DefaultParser(chunker=mock_chunker)

    def test_default_parser_can_handle_types(self, parser):
        assert parser.can_handle("pdf") is True
        assert parser.can_handle("docx") is True
        assert parser.can_handle("txt") is True
        assert parser.can_handle("text") is False  # no real .text extension

    def test_default_parser_cannot_handle_faq(self, parser):
        assert parser.can_handle("faq") is False

    def test_default_parser_txt_file(self, parser, mock_chunker):
        """DefaultParser reads a .txt file and delegates to the chunker."""
        content = "Hello world.\n\nThis is a test document."
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write(content)
            tmp_path = f.name
        try:
            result = parser.parse(tmp_path, DOC_ID, BASE_METADATA)
            # The chunker should have been called with the file content
            mock_chunker.chunk.assert_called_once_with(content, DOC_ID, BASE_METADATA)
            assert result == mock_chunker.chunk.return_value
        finally:
            os.unlink(tmp_path)

    def test_default_parser_pdf_uses_fitz(self, mock_chunker):
        """DefaultParser._extract_pdf should use fitz (PyMuPDF) lazily."""
        parser = DefaultParser(chunker=mock_chunker)

        # Create a fake fitz module
        fake_page = MagicMock()
        fake_page.get_text.return_value = "page text"
        fake_doc = MagicMock()
        fake_doc.__iter__ = MagicMock(return_value=iter([fake_page]))
        fake_fitz = MagicMock()
        fake_fitz.open.return_value = fake_doc

        with patch.dict("sys.modules", {"fitz": fake_fitz}):
            text = parser._extract_pdf("/fake/path/doc.pdf")

        fake_fitz.open.assert_called_once_with("/fake/path/doc.pdf")
        assert "page text" in text

    def test_default_parser_docx_uses_python_docx(self, mock_chunker):
        """DefaultParser._extract_docx should use python-docx lazily."""
        parser = DefaultParser(chunker=mock_chunker)

        para1 = MagicMock()
        para1.text = "First paragraph"
        para2 = MagicMock()
        para2.text = ""  # empty — should be filtered
        para3 = MagicMock()
        para3.text = "Third paragraph"

        fake_doc = MagicMock()
        fake_doc.paragraphs = [para1, para2, para3]
        fake_document_cls = MagicMock(return_value=fake_doc)
        fake_docx = MagicMock()
        fake_docx.Document = fake_document_cls

        with patch.dict("sys.modules", {"docx": fake_docx}):
            text = parser._extract_docx("/fake/path/doc.docx")

        assert "First paragraph" in text
        assert "Third paragraph" in text
        # Empty paragraph should have been filtered out
        assert text == "First paragraph\n\nThird paragraph"
