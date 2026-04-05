"""Tests for NoopReranker and BGEReranker."""
import pytest
from unittest.mock import MagicMock, patch

from core.rag.reranker import NoopReranker, BGEReranker


def make_doc(chunk_id: str, score: float) -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc1",
        "content": f"content {chunk_id}",
        "score": score,
        "metadata": {},
    }


class TestNoopReranker:
    @pytest.mark.asyncio
    async def test_copies_score_to_rerank_score(self):
        reranker = NoopReranker()
        docs = [make_doc("A", 0.9), make_doc("B", 0.7)]
        result = await reranker.rerank("query", docs, top_k=2)

        assert result[0]["rerank_score"] == 0.9
        assert result[1]["rerank_score"] == 0.7

    @pytest.mark.asyncio
    async def test_top_k_respected(self):
        reranker = NoopReranker()
        docs = [make_doc(str(i), float(i)) for i in range(10)]
        result = await reranker.rerank("query", docs, top_k=3)
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_preserves_original_order(self):
        reranker = NoopReranker()
        docs = [make_doc("A", 0.3), make_doc("B", 0.9), make_doc("C", 0.6)]
        result = await reranker.rerank("query", docs, top_k=3)
        assert [r["chunk_id"] for r in result] == ["A", "B", "C"]

    @pytest.mark.asyncio
    async def test_empty_input(self):
        reranker = NoopReranker()
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_does_not_mutate_original(self):
        reranker = NoopReranker()
        docs = [make_doc("A", 0.5)]
        await reranker.rerank("query", docs, top_k=1)
        assert "rerank_score" not in docs[0]


class TestBGEReranker:
    @pytest.mark.asyncio
    async def test_rerank_sorts_by_score(self):
        reranker = BGEReranker()
        docs = [make_doc("low", 0.3), make_doc("high", 0.9), make_doc("mid", 0.6)]

        mock_flag = MagicMock()
        mock_flag.compute_score.return_value = [0.3, 0.9, 0.6]

        with patch.object(reranker, "_get_model", return_value=mock_flag):
            result = await reranker.rerank("query", docs, top_k=3)

        assert result[0]["chunk_id"] == "high"
        assert result[1]["chunk_id"] == "mid"
        assert result[2]["chunk_id"] == "low"

    @pytest.mark.asyncio
    async def test_rerank_score_field_added(self):
        reranker = BGEReranker()
        docs = [make_doc("A", 0.5)]

        mock_flag = MagicMock()
        mock_flag.compute_score.return_value = [0.85]

        with patch.object(reranker, "_get_model", return_value=mock_flag):
            result = await reranker.rerank("query", docs, top_k=1)

        assert result[0]["rerank_score"] == pytest.approx(0.85)

    @pytest.mark.asyncio
    async def test_empty_candidates(self):
        reranker = BGEReranker()
        result = await reranker.rerank("query", [], top_k=5)
        assert result == []

    @pytest.mark.asyncio
    async def test_top_k_respected(self):
        reranker = BGEReranker()
        docs = [make_doc(str(i), 0.5) for i in range(10)]

        mock_flag = MagicMock()
        mock_flag.compute_score.return_value = [float(i) / 10 for i in range(10)]

        with patch.object(reranker, "_get_model", return_value=mock_flag):
            result = await reranker.rerank("query", docs, top_k=4)

        assert len(result) == 4
