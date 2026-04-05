from core.interfaces.retriever import BaseRetriever
from core.knowledge.vector_store import ChromaVectorStore
from core.knowledge.bm25_store import Bm25Store


class HybridRetriever(BaseRetriever):
    """Combines vector search and BM25 via Reciprocal Rank Fusion (RRF)."""

    def __init__(
        self,
        vector_store: ChromaVectorStore,
        bm25_store: Bm25Store,
        rrf_k: int = 60,
    ) -> None:
        self._vector_store = vector_store
        self._bm25_store = bm25_store
        self._rrf_k = rrf_k

    async def retrieve(
        self,
        query_vec: list[float],
        query_text: str,
        top_k: int = 5,
    ) -> list[dict]:
        fetch_k = max(top_k * 4, 20)

        vector_results = await self._vector_store.query(query_vec, top_k=fetch_k)
        bm25_results = self._bm25_store.search(query_text, top_k=fetch_k)

        return self._rrf_merge(vector_results, bm25_results, top_k)

    def _rrf_merge(
        self,
        vector_results: list[dict],
        bm25_results: list[dict],
        top_k: int,
    ) -> list[dict]:
        k = self._rrf_k
        scores: dict[str, float] = {}
        docs: dict[str, dict] = {}

        for rank, doc in enumerate(vector_results):
            cid = doc["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            docs[cid] = doc

        for rank, doc in enumerate(bm25_results):
            cid = doc["chunk_id"]
            scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
            if cid not in docs:
                docs[cid] = doc

        ranked = sorted(scores.keys(), key=lambda cid: scores[cid], reverse=True)

        results = []
        for cid in ranked[:top_k]:
            entry = dict(docs[cid])
            entry["score"] = scores[cid]
            results.append(entry)

        return results
