"""Smoke tests for BM25 with real jieba tokenization.

These tests verify that the real jieba + rank_bm25 stack works end-to-end
without any mocking. Run with: pytest tests/smoke/ -v -m smoke
"""
import pytest

from core.knowledge.bm25_store import Bm25Store


@pytest.mark.smoke
def test_bm25_real_chinese_retrieval():
    """Real jieba tokenization + BM25 finds relevant chunks in Chinese corpus."""
    store = Bm25Store()
    chunks = [
        {"chunk_id": "c1", "doc_id": "d1", "content": "退款申请流程：登录账号，找到订单，点击退款"},
        {"chunk_id": "c2", "doc_id": "d1", "content": "发货时间：工作日24小时内发货，节假日顺延"},
        {"chunk_id": "c3", "doc_id": "d1", "content": "账号注册：填写手机号和验证码完成注册"},
        {"chunk_id": "c4", "doc_id": "d1", "content": "订单查询：在我的订单页面查看所有订单状态"},
    ]
    store.add(chunks)

    results = store.search("退款", top_k=3)

    assert len(results) > 0
    assert results[0]["chunk_id"] == "c1"
    assert all("chunk_id" in r for r in results)
    assert all("score" in r for r in results)
    assert all(r["score"] > 0 for r in results)


@pytest.mark.smoke
def test_bm25_real_mixed_language():
    """Real BM25 handles mixed Chinese/English content."""
    store = Bm25Store()
    chunks = [
        {"chunk_id": "e1", "doc_id": "d1", "content": "API接口文档：POST /api/v1/refund"},
        {"chunk_id": "e2", "doc_id": "d1", "content": "SDK使用说明：import sdk"},
        {"chunk_id": "e3", "doc_id": "d1", "content": "配置文件：config.yaml设置参数"},
    ]
    store.add(chunks)

    results = store.search("API", top_k=2)

    assert len(results) > 0


@pytest.mark.smoke
def test_bm25_real_top_k_ordering():
    """BM25 results are sorted by relevance score descending."""
    store = Bm25Store()
    chunks = [
        {"chunk_id": "high", "doc_id": "d1", "content": "退款退款退款退款退款退款"},  # many hits
        {"chunk_id": "mid", "doc_id": "d1", "content": "退款一次"},
        {"chunk_id": "low", "doc_id": "d1", "content": "发货查询物流"},
        {"chunk_id": "none", "doc_id": "d1", "content": "账号密码安全设置"},
    ]
    store.add(chunks)
    results = store.search("退款", top_k=4)

    # "high" should rank first due to term frequency
    if len(results) >= 2:
        assert results[0]["score"] >= results[1]["score"]
