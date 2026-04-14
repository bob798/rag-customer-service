"""Tests for DocxParser — mocks python-docx and PaddleOCR, tests extraction and chunk logic."""
import io
import pytest
from unittest.mock import MagicMock, PropertyMock, patch, ANY
from lxml import etree

from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.docx_parser import DocxParser, _NSMAP


DOC_ID = "doc-docx-001"
META = {"source_title": "test.docx", "source_path": "/tmp/test.docx", "file_type": "docx"}


@pytest.fixture
def parser():
    return DocxParser(chunker=SemanticChunker())


@pytest.fixture
def parser_with_mock_ocr():
    """Parser with a mock OCR engine that returns fixed text (PaddleOCR 3.x predict() API)."""
    mock_ocr = MagicMock()
    # predict() returns a generator of OCRResult (dict subclass)
    mock_page_result = {"rec_texts": ["识别的中文文本"], "rec_scores": [0.95]}
    mock_ocr.predict.return_value = [mock_page_result]
    p = DocxParser(chunker=SemanticChunker(), ocr_engine=mock_ocr)
    return p


# =====================================================================
# can_handle
# =====================================================================

class TestCanHandle:
    def test_handles_docx(self, parser):
        assert parser.can_handle("docx") is True

    def test_does_not_handle_pdf(self, parser):
        assert parser.can_handle("pdf") is False

    def test_does_not_handle_txt(self, parser):
        assert parser.can_handle("txt") is False


# =====================================================================
# Table rendering
# =====================================================================

def _mock_cell(text, tc=None):
    """Create a mock table cell with proper _tc.tcPr structure."""
    if tc is None:
        tc = MagicMock()
    tc.tcPr = None  # no special properties (no vMerge)
    cell = MagicMock(text=text, _tc=tc)
    return cell


def _mock_vmerge_continuation_cell(tc=None):
    """Create a mock cell that is a vertical merge continuation (should be skipped)."""
    if tc is None:
        tc = MagicMock()
    v_merge_elem = MagicMock()
    v_merge_elem.get = MagicMock(return_value='')  # no "restart" = continuation
    tc_pr = MagicMock()
    tc_pr.find = MagicMock(return_value=v_merge_elem)
    tc.tcPr = tc_pr
    cell = MagicMock(text="", _tc=tc)
    return cell


class TestRenderTableMarkdown:
    def test_simple_table(self):
        table = MagicMock()
        row1 = MagicMock()
        row1.cells = [_mock_cell("参数"), _mock_cell("值")]
        row2 = MagicMock()
        row2.cells = [_mock_cell("功率"), _mock_cell("50W")]
        table.rows = [row1, row2]

        md = DocxParser._render_table_markdown(table)
        assert "参数" in md
        assert "功率" in md
        assert "50W" in md
        assert "---" in md  # separator

    def test_empty_table(self):
        table = MagicMock()
        table.rows = []
        assert DocxParser._render_table_markdown(table) == ""

    def test_pipe_in_cell_escaped(self):
        table = MagicMock()
        row1 = MagicMock()
        row1.cells = [_mock_cell("A|B"), _mock_cell("C")]
        table.rows = [row1]
        md = DocxParser._render_table_markdown(table)
        assert "A\\|B" in md

    def test_merged_cells_deduplicated(self):
        """Horizontally merged cells should not produce duplicate text."""
        table = MagicMock()
        shared_tc = MagicMock()
        shared_tc.tcPr = None
        cell_a = _mock_cell("Merged", tc=shared_tc)
        cell_b = _mock_cell("Merged", tc=shared_tc)  # same _tc = merged
        cell_c = _mock_cell("Normal")
        row = MagicMock()
        row.cells = [cell_a, cell_b, cell_c]
        table.rows = [row]

        md = DocxParser._render_table_markdown(table)
        assert md.count("Merged") == 1
        assert "Normal" in md

    def test_vertical_merge_continuation_skipped(self):
        """Vertically merged continuation cells should output empty text."""
        table = MagicMock()
        # Row 1: master cell "音频输入"
        row1 = MagicMock()
        row1.cells = [_mock_cell("音频输入"), _mock_cell("AUX")]
        # Row 2: continuation cell (vMerge without restart)
        row2 = MagicMock()
        row2.cells = [_mock_vmerge_continuation_cell(), _mock_cell("USB-C")]
        table.rows = [row1, row2]

        md = DocxParser._render_table_markdown(table)
        assert md.count("音频输入") == 1  # only in row 1, not repeated
        assert "USB-C" in md

    def test_uneven_columns_padded(self):
        table = MagicMock()
        row1 = MagicMock()
        row1.cells = [_mock_cell("A"), _mock_cell("B"), _mock_cell("C")]
        row2 = MagicMock()
        row2.cells = [_mock_cell("1"), _mock_cell("2")]
        table.rows = [row1, row2]
        md = DocxParser._render_table_markdown(table)
        # Should not crash, row2 padded to 3 columns
        lines = md.strip().split("\n")
        assert len(lines) == 3  # header + separator + 1 data row


# =====================================================================
# Image extraction
# =====================================================================

class TestExtractImages:
    def _make_paragraph_with_image(self, embed_id="rId5", alt="测试图片"):
        """Build a mock paragraph element with an embedded image."""
        xml = f"""
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
             xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
             xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
             xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
             xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
          <w:r>
            <w:drawing>
              <wp:inline>
                <wp:docPr id="1" name="Picture 1" descr="{alt}"/>
                <a:graphic>
                  <a:graphicData>
                    <pic:pic>
                      <pic:blipFill>
                        <a:blip r:embed="{embed_id}"/>
                      </pic:blipFill>
                    </pic:pic>
                  </a:graphicData>
                </a:graphic>
              </wp:inline>
            </w:drawing>
          </w:r>
        </w:p>
        """
        return etree.fromstring(xml)

    def test_extract_inline_image(self):
        elem = self._make_paragraph_with_image(embed_id="rId5", alt="设备照片")

        # Mock paragraph and doc
        para = MagicMock()
        para._element = elem

        mock_image = MagicMock()
        mock_image.image.blob = b"fake-png-bytes"
        doc = MagicMock()
        doc.part.related_parts = {"rId5": mock_image}

        images = DocxParser._extract_images_from_paragraph(para, doc)
        assert len(images) == 1
        blob, alt = images[0]
        assert blob == b"fake-png-bytes"
        assert "设备照片" in alt

    def test_no_images_in_text_paragraph(self):
        xml = """
        <w:p xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
          <w:r><w:t>纯文本段落</w:t></w:r>
        </w:p>
        """
        elem = etree.fromstring(xml)
        para = MagicMock()
        para._element = elem
        doc = MagicMock()

        images = DocxParser._extract_images_from_paragraph(para, doc)
        assert len(images) == 0

    def test_missing_related_part_skipped(self):
        elem = self._make_paragraph_with_image(embed_id="rId99")
        para = MagicMock()
        para._element = elem
        doc = MagicMock()
        doc.part.related_parts = {}  # no rId99

        images = DocxParser._extract_images_from_paragraph(para, doc)
        assert len(images) == 0


# =====================================================================
# OCR
# =====================================================================

class TestOcrImage:
    def test_ocr_returns_text(self, parser_with_mock_ocr):
        # Create a minimal valid PNG image
        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 30), color="white").save(buf, format="PNG")
        blob = buf.getvalue()

        result = parser_with_mock_ocr._ocr_image(blob)
        assert "识别的中文文本" in result

    def test_ocr_engine_not_available(self, parser):
        # Force OCR engine to be unavailable
        parser._ocr_engine = False  # sentinel
        result = parser._ocr_image(b"fake-blob")
        assert result == ""

    def test_ocr_empty_result(self):
        mock_ocr = MagicMock()
        mock_ocr.predict.return_value = [{"rec_texts": []}]
        p = DocxParser(chunker=SemanticChunker(), ocr_engine=mock_ocr)

        from PIL import Image
        buf = io.BytesIO()
        Image.new("RGB", (100, 30)).save(buf, format="PNG")

        result = p._ocr_image(buf.getvalue())
        assert result == ""


# =====================================================================
# walk_body + elements_to_chunks (integration-level with mocks)
# =====================================================================

class TestWalkBodyAndChunks:
    def _build_mock_doc(self, body_elements):
        """Build a mock Document with given body child elements."""
        doc = MagicMock()
        body = MagicMock()
        body.__iter__ = MagicMock(return_value=iter(body_elements))
        doc.element.body = body
        doc.part.related_parts = {}
        return doc

    def _make_text_element(self, text, style_name=None):
        """Create a mock paragraph XML element."""
        child = MagicMock()
        child.tag = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p"

        # We need to patch Paragraph creation, so we'll use a different approach
        return ("p", text, style_name)

    def test_text_only_document(self, parser):
        """Test parsing a document with only text paragraphs."""
        elements = [
            {"type": "text", "content": "第一段文本", "section": ""},
            {"type": "text", "content": "第二段文本", "section": ""},
        ]

        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        assert len(chunks) >= 1
        combined = " ".join(c["content"] for c in chunks)
        assert "第一段" in combined
        assert "第二段" in combined
        assert all(c["metadata"]["content_type"] == "text" for c in chunks)

    def test_table_becomes_atomic_chunk(self, parser):
        elements = [
            {"type": "table", "content": "| A | B |\n|---|---|\n| 1 | 2 |", "section": ""},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "table"
        assert "[表格]" in chunks[0]["content"]

    def test_image_becomes_atomic_chunk(self, parser):
        elements = [
            {"type": "image", "content": "OCR识别文本", "section": "技术规格", "alt": "图1"},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        assert len(chunks) == 1
        assert chunks[0]["metadata"]["content_type"] == "image"
        assert "[图片]" in chunks[0]["content"]
        assert "OCR识别文本" in chunks[0]["content"]
        assert chunks[0]["metadata"]["section"] == "技术规格"

    def test_mixed_content_preserves_order(self, parser):
        elements = [
            {"type": "heading", "content": "概述", "section": "概述"},
            {"type": "text", "content": "产品介绍文本", "section": "概述"},
            {"type": "table", "content": "| 参数 | 值 |\n|---|---|\n| 功率 | 50W |", "section": "概述"},
            {"type": "image", "content": "面板图中文字", "section": "概述", "alt": "面板"},
            {"type": "text", "content": "更多说明", "section": "概述"},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        types = [c["metadata"]["content_type"] for c in chunks]
        # text, table, image, text — heading not stored
        assert types == ["text", "table", "image", "text"]

    def test_section_propagated_to_chunks(self, parser):
        elements = [
            {"type": "heading", "content": "安装步骤", "section": "安装步骤"},
            {"type": "text", "content": "步骤一：打开包装", "section": "安装步骤"},
            {"type": "image", "content": "安装示意图文字", "section": "安装步骤", "alt": ""},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        for chunk in chunks:
            assert chunk["metadata"]["section"] == "安装步骤"

    def test_chunk_index_sequential(self, parser):
        elements = [
            {"type": "text", "content": "段落一", "section": ""},
            {"type": "table", "content": "| A |\n|---|\n| 1 |", "section": ""},
            {"type": "text", "content": "段落二", "section": ""},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        indices = [c["metadata"]["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_metadata_preserved(self, parser):
        elements = [{"type": "text", "content": "内容", "section": ""}]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        assert chunks[0]["metadata"]["source_title"] == "test.docx"
        assert chunks[0]["doc_id"] == DOC_ID

    def test_heading_not_stored_as_chunk(self, parser):
        elements = [
            {"type": "heading", "content": "标题", "section": "标题"},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        assert len(chunks) == 0

    def test_consecutive_text_merged_before_chunking(self, parser):
        elements = [
            {"type": "text", "content": "第一段", "section": "章节A"},
            {"type": "text", "content": "第二段", "section": "章节A"},
            {"type": "text", "content": "第三段", "section": "章节A"},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        # Short texts should be merged into fewer chunks
        combined = " ".join(c["content"] for c in chunks)
        assert "第一段" in combined
        assert "第三段" in combined

    def test_section_change_flushes_text_buffer(self, parser):
        elements = [
            {"type": "heading", "content": "章节A", "section": "章节A"},
            {"type": "text", "content": "A的内容", "section": "章节A"},
            {"type": "heading", "content": "章节B", "section": "章节B"},
            {"type": "text", "content": "B的内容", "section": "章节B"},
        ]
        chunks = parser._elements_to_chunks(elements, DOC_ID, META)
        # Should have at least 2 chunks (one per section)
        sections = [c["metadata"]["section"] for c in chunks]
        assert "章节A" in sections
        assert "章节B" in sections


# =====================================================================
# Full parse with mocked Document
# =====================================================================

class TestFullParse:
    @patch("core.knowledge.parsers.docx_parser.DocxParser._walk_body")
    @patch("docx.Document")
    def test_parse_delegates_to_walk_body(self, mock_doc_cls, mock_walk, parser):
        mock_walk.return_value = [
            {"type": "text", "content": "测试文本", "section": ""},
        ]
        mock_doc_cls.return_value = MagicMock()

        chunks = parser.parse("/fake/test.docx", DOC_ID, META)

        assert len(chunks) == 1
        assert "测试文本" in chunks[0]["content"]
        mock_walk.assert_called_once()
