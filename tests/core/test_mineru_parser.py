"""Tests for MinerUParser — mocks MinerU CLI, tests content_list processing."""
import json
import pytest
from unittest.mock import patch, MagicMock

from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.mineru import MinerUParser


DOC_ID = "doc-mineru-001"
BASE_METADATA = {"source_title": "test.pdf", "source_path": "/tmp/test.pdf", "file_type": "pdf"}


@pytest.fixture
def chunker():
    return SemanticChunker(chunk_size=500, overlap=50)


@pytest.fixture
def parser(chunker):
    return MinerUParser(chunker=chunker, output_dir="/tmp/mineru_test")


# --- Helpers ---

def make_content_list(*items):
    """Build a content_list from simplified item dicts."""
    return list(items)


def text_item(text, level=0, page=0):
    return {"type": "text", "text": text, "text_level": level, "page_idx": page, "bbox": [0, 0, 100, 20]}


def table_item(html, caption=None, footnote=None, page=0):
    return {
        "type": "table",
        "table_body": html,
        "table_caption": [caption] if caption else [],
        "table_footnote": [footnote] if footnote else [],
        "page_idx": page,
        "bbox": [0, 50, 100, 200],
    }


def image_item(path, caption=None, page=0):
    return {
        "type": "image",
        "img_path": path,
        "image_caption": [caption] if caption else [],
        "image_footnote": [],
        "page_idx": page,
        "bbox": [0, 50, 100, 200],
    }


def equation_item(latex, page=0):
    return {
        "type": "equation",
        "text": latex,
        "text_format": "latex",
        "page_idx": page,
        "bbox": [50, 100, 200, 120],
    }


def code_item(body, caption=None, page=0):
    return {
        "type": "code",
        "code_body": body,
        "code_caption": [caption] if caption else [],
        "page_idx": page,
        "bbox": [0, 0, 100, 50],
    }


# =====================================================================
# can_handle tests
# =====================================================================

class TestCanHandle:
    def test_handles_pdf(self, parser):
        assert parser.can_handle("pdf") is True

    def test_does_not_handle_docx(self, parser):
        assert parser.can_handle("docx") is False

    def test_does_not_handle_txt(self, parser):
        assert parser.can_handle("txt") is False


# =====================================================================
# Section path tests
# =====================================================================

class TestSectionPaths:
    def test_flat_text_no_headings(self):
        cl = [text_item("paragraph 1"), text_item("paragraph 2")]
        paths = MinerUParser._build_section_paths(cl)
        assert paths == ["", ""]

    def test_single_heading(self):
        cl = [
            text_item("Chapter 1", level=1),
            text_item("Some body text"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        assert paths[0] == "Chapter 1"
        assert paths[1] == "Chapter 1"

    def test_nested_headings(self):
        cl = [
            text_item("第一章", level=1),
            text_item("1.1 概述", level=2),
            text_item("正文内容"),
            text_item("1.2 详情", level=2),
            text_item("更多内容"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        assert paths[2] == "第一章 > 1.1 概述"
        assert paths[4] == "第一章 > 1.2 详情"

    def test_heading_level_reset(self):
        cl = [
            text_item("Ch1", level=1),
            text_item("1.1", level=2),
            text_item("Ch2", level=1),  # should reset
            text_item("body"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        assert paths[3] == "Ch2"


# =====================================================================
# Content list → chunks tests
# =====================================================================

class TestContentListToChunks:
    def test_text_produces_chunks(self, parser):
        cl = [text_item("这是一段正文内容，用于测试文本分块功能。")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "text"
        assert "正文内容" in chunks[0]["content"]

    def test_heading_not_stored_as_chunk(self, parser):
        cl = [text_item("第一章 标题", level=1)]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 0

    def test_table_as_atomic_chunk(self, parser):
        html = "<table><tr><td>A</td><td>B</td></tr></table>"
        cl = [table_item(html, caption="表1：对比")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "table"
        assert "[表格]" in chunks[0]["content"]
        assert html in chunks[0]["content"]
        assert "表1：对比" in chunks[0]["content"]

    def test_table_with_footnote(self, parser):
        cl = [table_item("<table></table>", caption="表2", footnote="数据来源：内部")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert "注：数据来源：内部" in chunks[0]["content"]

    def test_image_as_atomic_chunk(self, parser):
        cl = [image_item("images/arch.jpg", caption="图1：系统架构")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "image"
        assert "[图片]" in chunks[0]["content"]
        assert "图1：系统架构" in chunks[0]["content"]
        assert chunks[0]["metadata"]["image_path"] == "images/arch.jpg"

    def test_equation_as_atomic_chunk(self, parser):
        cl = [equation_item("E = mc^2")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "formula"
        assert "E = mc^2" in chunks[0]["content"]

    def test_code_as_atomic_chunk(self, parser):
        cl = [code_item("print('hello')", caption="示例代码")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "code"
        assert "print('hello')" in chunks[0]["content"]

    def test_mixed_content_types(self, parser):
        cl = [
            text_item("第一章", level=1),
            text_item("这是正文。"),
            table_item("<table><tr><td>1</td></tr></table>", caption="表1"),
            image_item("img/fig1.jpg", caption="图1"),
            text_item("更多正文。"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)

        types = [c["metadata"]["content_type"] for c in chunks]
        assert "text" in types
        assert "table" in types
        assert "image" in types

    def test_page_idx_propagated(self, parser):
        cl = [text_item("页面3的内容", page=3)]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert chunks[0]["metadata"]["page"] == 3

    def test_section_path_propagated(self, parser):
        cl = [
            text_item("产品概述", level=1),
            text_item("这里是产品描述。"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert chunks[0]["metadata"]["section"] == "产品概述"

    def test_metadata_preserved(self, parser):
        cl = [text_item("内容")]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert chunks[0]["metadata"]["source_title"] == "test.pdf"
        assert chunks[0]["doc_id"] == DOC_ID

    def test_chunk_index_sequential(self, parser):
        cl = [
            text_item("段落一"),
            table_item("<table></table>", caption="表"),
            text_item("段落二"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_discarded_types_ignored(self, parser):
        cl = [
            {"type": "header", "text": "Company Logo", "page_idx": 0},
            {"type": "footer", "text": "Page 1", "page_idx": 0},
            {"type": "page_number", "text": "1", "page_idx": 0},
            text_item("实际内容"),
        ]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, DOC_ID, BASE_METADATA)
        assert len(chunks) == 1
        assert "实际内容" in chunks[0]["content"]


# =====================================================================
# is_available tests
# =====================================================================

class TestIsAvailable:
    @patch("shutil.which", return_value="/usr/local/bin/mineru")
    def test_available_when_installed(self, mock_which):
        assert MinerUParser.is_available() is True

    @patch("shutil.which", return_value=None)
    def test_not_available_when_missing(self, mock_which):
        assert MinerUParser.is_available() is False
