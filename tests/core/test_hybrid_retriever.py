"""Tests for HybridRetriever RRF fusion logic."""
import sys
import types
import numpy as np
import pytest
from unittest.mock import AsyncMock, MagicMock

# Install jieba and rank_bm25 stubs BEFORE any project imports so that
# bm25_store.py binds to the stub BM25Okapi (not the real one whose IDF=0
# for small corpora). This must mirror the stubs in test_retriever.py.
if "jieba" not in sys.modules:
    _jieba_stub = types.ModuleType("jieba")
    _jieba_stub.cut = list  # character-level split
    sys.modules["jieba"] = _jieba_stub

if "rank_bm25" not in sys.modules:
    _bm25_stub = types.ModuleType("rank_bm25")

    class _BM25Okapi:
        def __init__(self, corpus):
            self._corpus = corpus

        def get_scores(self, query_tokens):
            query_set = set(query_tokens)
            return np.array([float(len(query_set & set(doc))) for doc in self._corpus])

    _bm25_stub.BM25Okapi = _BM25Okapi
    sys.modules["rank_bm25"] = _bm25_stub

from core.rag.retriever import HybridRetriever  # noqa: E402


def make_doc(chunk_id: str, score: float = 0.5) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc1",
        "content": f"content of {chunk_id}",
        "score": score,
        "metadata": {},
    }


@pytest.fixture
def mock_vector_store():
    store = MagicMock()
    store.query = AsyncMock()
    return store


@pytest.fixture
def mock_bm25_store():
    store = MagicMock()
    store.search = MagicMock()
    return store


@pytest.fixture
def retriever(mock_vector_store, mock_bm25_store):
    return HybridRetriever(mock_vector_store, mock_bm25_store)


@pytest.mark.asyncio
async def test_rrf_combines_both_sources(retriever, mock_vector_store, mock_bm25_store):
    """Chunk appearing in both sources gets higher RRF score."""
    mock_vector_store.query.return_value = [make_doc("A"), make_doc("B")]
    mock_bm25_store.search.return_value = [make_doc("B"), make_doc("C")]

    results = await retriever.retrieve([0.1, 0.2], "query", top_k=3)

    chunk_ids = [r["chunk_id"] for r in results]
    # B appears in both lists → should rank highest
    assert chunk_ids[0] == "B"
    assert len(results) == 3


@pytest.mark.asyncio
async def test_top_k_limit_respected(retriever, mock_vector_store, mock_bm25_store):
    mock_vector_store.query.return_value = [make_doc(f"v{i}") for i in range(10)]
    mock_bm25_store.search.return_value = [make_doc(f"b{i}") for i in range(10)]

    results = await retriever.retrieve([0.1], "query", top_k=5)
    assert len(results) == 5


@pytest.mark.asyncio
async def test_vector_only_when_bm25_empty(retriever, mock_vector_store, mock_bm25_store):
    mock_vector_store.query.return_value = [make_doc("A"), make_doc("B"), make_doc("C")]
    mock_bm25_store.search.return_value = []

    results = await retriever.retrieve([0.1], "query", top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == "A"


@pytest.mark.asyncio
async def test_bm25_only_when_vector_empty(retriever, mock_vector_store, mock_bm25_store):
    mock_vector_store.query.return_value = []
    mock_bm25_store.search.return_value = [make_doc("X"), make_doc("Y")]

    results = await retriever.retrieve([0.1], "query", top_k=2)
    assert len(results) == 2
    assert results[0]["chunk_id"] == "X"


@pytest.mark.asyncio
async def test_score_field_is_rrf_value(retriever, mock_vector_store, mock_bm25_store):
    """Results have a 'score' field with RRF value (not original score)."""
    mock_vector_store.query.return_value = [make_doc("A")]
    mock_bm25_store.search.return_value = [make_doc("A")]

    results = await retriever.retrieve([0.1], "query", top_k=1)
    # A appears at rank 0 in both → rrf = 1/60 + 1/60 = 2/60 ≈ 0.0333
    expected = 1.0 / 60 + 1.0 / 60
    assert abs(results[0]["score"] - expected) < 1e-9


@pytest.mark.asyncio
async def test_rrf_rank_order(retriever, mock_vector_store, mock_bm25_store):
    """Earlier ranks contribute more to RRF score."""
    # A is rank 0 in vector, C is rank 0 in BM25, B is rank 1 in both
    mock_vector_store.query.return_value = [make_doc("A"), make_doc("B")]
    mock_bm25_store.search.return_value = [make_doc("C"), make_doc("B")]

    results = await retriever.retrieve([0.1], "query", top_k=3)
    # B at rank 1 in both: 1/61 + 1/61 ≈ 0.0328
    # A at rank 0 in vector only: 1/60 ≈ 0.0167
    # C at rank 0 in bm25 only: 1/60 ≈ 0.0167
    chunk_ids = [r["chunk_id"] for r in results]
    assert chunk_ids[0] == "B"
