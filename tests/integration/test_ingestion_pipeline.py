"""Integration tests for document ingestion pipeline.

Tests real parsers + chunker + BM25 without mocking core logic.
"""
import uuid
from pathlib import Path

import pytest

from core.knowledge.bm25_store import Bm25Store
from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.faq import FAQParser


@pytest.mark.asyncio
async def test_faq_txt_end_to_end(sample_faq_file: Path, real_bm25_store: Bm25Store):
    """FAQParser → chunks → BM25 add → search returns relevant result."""
    parser = FAQParser()
    content = sample_faq_file.read_text(encoding="utf-8")

    assert parser.can_handle("faq", content)

    doc_id = str(uuid.uuid4())
    # parse() takes file_path, doc_id, metadata
    chunks = parser.parse(str(sample_faq_file), doc_id=doc_id, metadata={"source_title": "faq.txt"})

    assert len(chunks) >= 3, f"Expected at least 3 FAQ chunks, got {len(chunks)}"

    real_bm25_store.add(chunks)
    results = real_bm25_store.search("退款", top_k=5)

    assert len(results) > 0
    top_content = results[0]["content"]
    assert "退款" in top_content


@pytest.mark.asyncio
async def test_txt_chunking_via_semantic_chunker(
    real_chunker: SemanticChunker, real_bm25_store: Bm25Store
):
    """SemanticChunker.chunk() produces chunks that BM25 can search.

    Uses 3 distinct text blocks to ensure BM25Okapi IDF > 0 (requires N >= 3
    or term in < N/2 docs).
    """
    # Three distinct blocks so BM25 has enough docs for IDF > 0
    blocks = [
        "退款申请流程：首先登录您的账户，进入订单页面，找到需要退款的订单，"
        "点击申请退款按钮，填写退款原因，提交申请。客服审核通过后将原路退款至您账户。",
        "订单查询方法：在首页点击我的订单，可以查看所有历史订单和当前订单状态。"
        "包括待支付、已支付、已发货、已完成等各种状态信息详情。",
        "账户安全设置：定期修改密码，开启双重验证，不要泄露个人账号信息给他人。"
        "如发现异常登录请立即联系客服处理相关安全问题。",
    ]
    doc_id = str(uuid.uuid4())
    all_chunks = []
    for i, text in enumerate(blocks):
        chunks = real_chunker.chunk(text, doc_id=doc_id, metadata={"source_title": f"block{i}.txt"})
        all_chunks.extend(chunks)

    assert len(all_chunks) >= 3, f"Expected >= 3 chunks, got {len(all_chunks)}"
    real_bm25_store.add(all_chunks)

    results = real_bm25_store.search("退款申请", top_k=3)
    assert len(results) > 0


def test_chunk_structure_consistency(real_chunker: SemanticChunker):
    """All chunks produced by chunker have required fields."""
    text = "客服系统提供退款、换货、投诉等多种服务。" * 5
    doc_id = str(uuid.uuid4())
    chunks = real_chunker.chunk(text, doc_id=doc_id, metadata={"source_title": "test.txt"})

    assert len(chunks) > 0
    for chunk in chunks:
        assert "chunk_id" in chunk, f"Missing chunk_id in {chunk}"
        assert "doc_id" in chunk, f"Missing doc_id in {chunk}"
        assert "content" in chunk, f"Missing content in {chunk}"
        assert "metadata" in chunk, f"Missing metadata in {chunk}"
        assert chunk["content"].strip(), "Empty chunk content"
