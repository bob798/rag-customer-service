"""Tests for PaddleOCRParser — mocks PaddleOCR, tests markdown parsing and chunk logic."""
import pytest
from unittest.mock import patch

from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.paddleocr import PaddleOCRParser


DOC_ID = "doc-paddle-001"
META = {"source_title": "test.pdf", "source_path": "/tmp/test.pdf", "file_type": "pdf"}


@pytest.fixture
def parser():
    return PaddleOCRParser(chunker=SemanticChunker(), use_gpu=False)


# =====================================================================
# can_handle
# =====================================================================

class TestCanHandle:
    def test_handles_pdf(self, parser):
        assert parser.can_handle("pdf") is True

    def test_does_not_handle_txt(self, parser):
        assert parser.can_handle("txt") is False

    def test_does_not_handle_docx(self, parser):
        assert parser.can_handle("docx") is False


# =====================================================================
# Markdown parsing
# =====================================================================

class TestParseMarkdown:
    def test_plain_text(self):
        md = "这是一段普通文本。\n第二行也是文本。"
        segments = PaddleOCRParser._parse_markdown(md)
        assert len(segments) == 1
        assert segments[0]["type"] == "text"
        assert "普通文本" in segments[0]["content"]

    def test_heading(self):
        md = "# 第一章 概述\n\n这是正文。"
        segments = PaddleOCRParser._parse_markdown(md)
        assert segments[0]["type"] == "heading"
        assert segments[0]["level"] == 1
        assert segments[0]["content"] == "第一章 概述"
        assert segments[1]["type"] == "text"

    def test_nested_headings(self):
        md = "# 第一章\n\n## 1.1 概述\n\n正文内容\n\n## 1.2 详情\n\n更多内容"
        segments = PaddleOCRParser._parse_markdown(md)
        headings = [s for s in segments if s["type"] == "heading"]
        assert len(headings) == 3
        assert headings[0]["level"] == 1
        assert headings[1]["level"] == 2
        assert headings[2]["level"] == 2

    def test_markdown_table(self):
        md = "| 参数 | 值 |\n|------|------|\n| 功率 | 50W |"
        segments = PaddleOCRParser._parse_markdown(md)
        assert len(segments) == 1
        assert segments[0]["type"] == "table"
        assert "功率" in segments[0]["content"]

    def test_table_between_text(self):
        md = "前面的文本\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\n后面的文本"
        segments = PaddleOCRParser._parse_markdown(md)
        types = [s["type"] for s in segments]
        assert "text" in types
        assert "table" in types

    def test_image(self):
        md = "![系统架构图](images/arch.png)"
        segments = PaddleOCRParser._parse_markdown(md)
        assert len(segments) == 1
        assert segments[0]["type"] == "image"
        assert segments[0]["content"] == "系统架构图"
        assert segments[0]["image_path"] == "images/arch.png"

    def test_image_no_alt(self):
        md = "![](images/fig.png)"
        segments = PaddleOCRParser._parse_markdown(md)
        assert segments[0]["content"] == "[图片]"

    def test_formula(self):
        md = "$$E = mc^2$$"
        segments = PaddleOCRParser._parse_markdown(md)
        assert len(segments) == 1
        assert segments[0]["type"] == "formula"
        assert "E = mc^2" in segments[0]["content"]

    def test_mixed_content(self):
        md = (
            "# 产品概述\n\n"
            "BLV-D1 是一款蓝牙放大器。\n\n"
            "| 参数 | 值 |\n|---|---|\n| 功率 | 50W |\n\n"
            "![外观](img/photo.jpg)\n\n"
            "$$P = V^2 / R$$\n\n"
            "更多说明文本。"
        )
        segments = PaddleOCRParser._parse_markdown(md)
        types = [s["type"] for s in segments]
        assert "heading" in types
        assert "text" in types
        assert "table" in types
        assert "image" in types
        assert "formula" in types

    def test_empty_input(self):
        segments = PaddleOCRParser._parse_markdown("")
        assert segments == []

    def test_html_table_single_line(self):
        md = "<table><tr><td>A</td></tr></table>"
        segments = PaddleOCRParser._parse_markdown(md)
        assert len(segments) == 1
        assert segments[0]["type"] == "table"


# =====================================================================
# Section paths
# =====================================================================

class TestSectionPaths:
    def test_flat_no_headings(self):
        segments = [{"type": "text", "content": "abc", "level": None}]
        paths = PaddleOCRParser._build_section_paths(segments)
        assert paths == [""]

    def test_single_heading(self):
        segments = [
            {"type": "heading", "content": "第一章", "level": 1},
            {"type": "text", "content": "正文", "level": None},
        ]
        paths = PaddleOCRParser._build_section_paths(segments)
        assert paths[1] == "第一章"

    def test_nested_and_reset(self):
        segments = [
            {"type": "heading", "content": "Ch1", "level": 1},
            {"type": "heading", "content": "1.1", "level": 2},
            {"type": "text", "content": "body", "level": None},
            {"type": "heading", "content": "1.2", "level": 2},
            {"type": "text", "content": "body2", "level": None},
        ]
        paths = PaddleOCRParser._build_section_paths(segments)
        assert paths[2] == "Ch1 > 1.1"
        assert paths[4] == "Ch1 > 1.2"


# =====================================================================
# Segments → chunks
# =====================================================================

class TestSegmentsToChunks:
    def test_text_chunked(self, parser):
        segments = [{"type": "text", "content": "这是一段正文。", "level": None}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "text"

    def test_table_atomic(self, parser):
        segments = [{"type": "table", "content": "| A | B |\n|---|---|\n| 1 | 2 |", "level": None}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "table"
        assert "[表格]" in chunks[0]["content"]

    def test_image_atomic(self, parser):
        segments = [{"type": "image", "content": "架构图", "level": None, "image_path": "img/a.jpg"}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "image"
        assert chunks[0]["metadata"]["image_path"] == "img/a.jpg"

    def test_formula_atomic(self, parser):
        segments = [{"type": "formula", "content": "E=mc^2", "level": None}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "formula"

    def test_heading_not_stored(self, parser):
        segments = [{"type": "heading", "content": "标题", "level": 1}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert len(chunks) == 0

    def test_section_path_propagated(self, parser):
        segments = [
            {"type": "heading", "content": "技术规格", "level": 1},
            {"type": "text", "content": "输出功率 50W", "level": None},
        ]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert chunks[0]["metadata"]["section"] == "技术规格"

    def test_chunk_index_sequential(self, parser):
        segments = [
            {"type": "text", "content": "段落一", "level": None},
            {"type": "table", "content": "| A |\n|---|\n| 1 |", "level": None},
            {"type": "text", "content": "段落二", "level": None},
        ]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_metadata_preserved(self, parser):
        segments = [{"type": "text", "content": "内容", "level": None}]
        paths = PaddleOCRParser._build_section_paths(segments)
        chunks = parser._segments_to_chunks(segments, paths, DOC_ID, META)
        assert chunks[0]["metadata"]["source_title"] == "test.pdf"
        assert chunks[0]["doc_id"] == DOC_ID


# =====================================================================
# is_available
# =====================================================================

class TestIsAvailable:
    @patch.dict("sys.modules", {"paddleocr": type("mock", (), {})()})
    def test_available_when_installed(self):
        assert PaddleOCRParser.is_available() is True

    def test_not_available_when_missing(self):
        # paddleocr may or may not be installed — test the logic
        import importlib
        try:
            importlib.import_module("paddleocr")
            assert PaddleOCRParser.is_available() is True
        except ImportError:
            assert PaddleOCRParser.is_available() is False
