"""Integration tests for HybridRetriever with real BM25 and deterministic embedder.

Uses a fake ChromaVectorStore (deterministic embedder + in-memory Chroma).
"""
import sys
import types
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from core.knowledge.bm25_store import Bm25Store
from core.rag.retriever import HybridRetriever


def make_vector_store_mock(results_by_query: dict = None):
    """Build a mock vector store that returns preset results."""
    store = MagicMock()
    results_by_query = results_by_query or {}

    async def query(vec, top_k=20):
        # Return preset results or empty list
        return results_by_query.get("_default", [])

    store.query = query
    return store


def make_chunk(chunk_id: str, doc_id: str, content: str) -> dict:
    return {"chunk_id": chunk_id, "doc_id": doc_id, "content": content, "metadata": {}}


@pytest.mark.asyncio
async def test_rrf_combines_both_sources():
    """When both vector and BM25 have results, RRF fuses them."""
    bm25 = Bm25Store()
    bm25.add([
        make_chunk("bm25_1", "d1", "退款申请退款退款"),  # high BM25 for 退款
        make_chunk("bm25_2", "d1", "订单查询状态"),
        make_chunk("shared", "d1", "退款流程退款退款退款"),
    ])

    vector_results = [
        {**make_chunk("vector_1", "d2", "语义相关内容"), "score": 0.9},
        {**make_chunk("shared", "d1", "退款流程退款退款退款"), "score": 0.85},
    ]
    vector_store = make_vector_store_mock({"_default": vector_results})

    retriever = HybridRetriever(vector_store, bm25)
    results = await retriever.retrieve([0.1] * 64, "退款", top_k=5)

    chunk_ids = {r["chunk_id"] for r in results}
    # "shared" appears in both → should be in results
    assert "shared" in chunk_ids
    assert len(results) > 0


@pytest.mark.asyncio
async def test_vector_only_when_bm25_empty():
    """When BM25 has no matching results, vector results come through."""
    bm25 = Bm25Store()
    bm25.add([make_chunk("c1", "d1", "无关内容无关无关")])

    vector_results = [
        {**make_chunk("v1", "d2", "退款语义内容"), "score": 0.9},
        {**make_chunk("v2", "d2", "退款相关内容"), "score": 0.8},
    ]
    vector_store = make_vector_store_mock({"_default": vector_results})

    retriever = HybridRetriever(vector_store, bm25)
    results = await retriever.retrieve([0.1] * 64, "退款申请查询", top_k=3)

    chunk_ids = {r["chunk_id"] for r in results}
    assert "v1" in chunk_ids or "v2" in chunk_ids


@pytest.mark.asyncio
async def test_bm25_surfaces_keyword_match():
    """BM25 result for exact keyword appears even if vector has no match.

    Note: BM25Okapi IDF=0 when term appears in exactly N/2 docs (N=even).
    Add 3+ docs so that IDF > 0 for the target term.
    """
    bm25 = Bm25Store()
    bm25.add([
        make_chunk("bm1", "d1", "退款退款退款退款退款"),  # many matches
        make_chunk("bm2", "d1", "订单发货查询物流"),
        make_chunk("bm3", "d1", "账号密码登录注册"),  # 3rd doc ensures IDF > 0
    ])

    vector_store = make_vector_store_mock({"_default": []})  # no vector results

    retriever = HybridRetriever(vector_store, bm25)
    results = await retriever.retrieve([0.1] * 64, "退款", top_k=3)

    chunk_ids = {r["chunk_id"] for r in results}
    assert "bm1" in chunk_ids


@pytest.mark.asyncio
async def test_top_k_limit_respected():
    """Final result count never exceeds top_k."""
    bm25 = Bm25Store()
    bm25.add([make_chunk(f"b{i}", "d1", f"退款内容{i}退款退款") for i in range(10)])

    vector_results = [
        {**make_chunk(f"v{i}", "d2", f"content{i}"), "score": 0.9 - i * 0.05}
        for i in range(10)
    ]
    vector_store = make_vector_store_mock({"_default": vector_results})

    retriever = HybridRetriever(vector_store, bm25)
    results = await retriever.retrieve([0.1] * 64, "退款", top_k=4)

    assert len(results) <= 4
