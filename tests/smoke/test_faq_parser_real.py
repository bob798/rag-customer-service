"""Smoke tests for FAQParser with real Chinese Q&A files."""
import tempfile
from pathlib import Path

import pytest

from core.knowledge.parsers.faq import FAQParser


@pytest.mark.smoke
def test_faq_parser_chinese_qa():
    """FAQParser extracts Q&A pairs from Chinese FAQ file."""
    content = """问：如何申请退款？
答：您可以在订单页面点击"申请退款"，填写退款原因后提交申请。

问：退款多久到账？
答：审核通过后3-5个工作日原路退回。

问：如何联系客服？
答：通过页面右下角在线客服按钮联系我们。
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", encoding="utf-8", delete=False) as f:
        f.write(content)
        tmp_path = f.name

    parser = FAQParser()
    chunks = parser.parse(tmp_path, doc_id="test-doc", metadata={"source_title": "faq.txt"})

    assert len(chunks) == 3
    for chunk in chunks:
        assert "chunk_id" in chunk
        assert "doc_id" in chunk
        assert chunk["doc_id"] == "test-doc"
        assert "Q:" in chunk["content"] or "问" in chunk["content"]
        assert "A:" in chunk["content"] or "答" in chunk["content"]


@pytest.mark.smoke
def test_faq_can_handle_detection():
    """FAQParser correctly identifies FAQ content."""
    parser = FAQParser()

    # Explicit faq type
    assert parser.can_handle("faq", "any content")

    # Chinese Q&A pattern detection
    assert parser.can_handle("txt", "问：退款如何操作？\n答：...")

    # Non-FAQ content
    assert not parser.can_handle("pdf", "random content")
    assert not parser.can_handle("txt", "no qa patterns here just text")
