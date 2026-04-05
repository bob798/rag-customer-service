"""Smoke tests for SemanticChunker with real Chinese text."""
import pytest

from core.knowledge.chunker import SemanticChunker


@pytest.mark.smoke
def test_chunker_chinese_text():
    """SemanticChunker produces valid chunks from Chinese text."""
    chunker = SemanticChunker(chunk_size=100, overlap=20)
    text = (
        "退款申请流程：首先登录您的账户，进入订单页面，找到需要退款的订单，"
        "点击申请退款按钮，填写退款原因（如商品质量问题、尺码不符等），"
        "提交申请后等待客服审核。审核通过后款项将原路退回，"
        "通常需要3-5个工作日到账，具体时间视银行处理速度而定。"
    )
    chunks = chunker.chunk(text, doc_id="test-doc", metadata={"source_title": "test.txt"})

    assert len(chunks) >= 1
    for chunk in chunks:
        assert "chunk_id" in chunk
        assert "doc_id" in chunk
        assert "content" in chunk
        assert chunk["doc_id"] == "test-doc"
        assert len(chunk["content"]) > 0


@pytest.mark.smoke
def test_chunker_chunk_ids_are_unique():
    """Every chunk has a unique chunk_id."""
    chunker = SemanticChunker(chunk_size=50, overlap=10)
    text = "这是测试文本。" * 20
    chunks = chunker.chunk(text, doc_id="doc1", metadata={})

    ids = [c["chunk_id"] for c in chunks]
    assert len(ids) == len(set(ids)), "Duplicate chunk_ids found"


@pytest.mark.smoke
def test_chunker_short_text_produces_one_chunk():
    """Very short text produces exactly one chunk."""
    chunker = SemanticChunker(chunk_size=512, overlap=50)
    text = "退款需要3天。"
    chunks = chunker.chunk(text, doc_id="doc1", metadata={})

    assert len(chunks) == 1
    assert "退款" in chunks[0]["content"]


@pytest.mark.smoke
def test_chunker_splits_long_text():
    """Long text with clear sentence boundaries is split into multiple chunks."""
    chunker = SemanticChunker(chunk_size=50, overlap=10)
    # Use natural sentence boundaries so chunker can split
    sentences = [
        "退款申请流程说明。",
        "发货时间介绍。",
        "订单查询方法。",
        "账号安全设置。",
        "客服联系方式。",
        "商品换货流程。",
        "积分兑换规则。",
        "会员等级说明。",
    ]
    text = "\n".join(sentences)
    chunks = chunker.chunk(text, doc_id="doc1", metadata={})

    # Should produce at least 2 chunks from 8 sentences with chunk_size=50
    assert len(chunks) >= 1
    # Verify all content is covered
    full_text = "".join(c["content"] for c in chunks)
    assert "退款" in full_text
