import asyncio
import threading
from typing import Optional

from core.interfaces.reranker import BaseReranker


class NoopReranker(BaseReranker):
    """Pass-through reranker for testing. Copies score → rerank_score."""

    async def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        result = []
        for doc in candidates[:top_k]:
            entry = dict(doc)
            entry["rerank_score"] = doc.get("score", 0.0)
            result.append(entry)
        return result


class BGEReranker(BaseReranker):
    """Production reranker using BAAI/bge-reranker-v2-m3 via FlagEmbedding."""

    def __init__(self, model_name: str = "BAAI/bge-reranker-v2-m3") -> None:
        self._model_name = model_name
        self._model: Optional[object] = None
        self._load_lock = threading.Lock()

    def _get_model(self):
        if self._model is None:
            with self._load_lock:
                if self._model is None:
                    from FlagEmbedding import FlagReranker  # lazy import
                    self._model = FlagReranker(self._model_name, use_fp16=True)
        return self._model

    def _score_sync(self, query: str, contents: list[str]) -> list[float]:
        model = self._get_model()
        pairs = [[query, content] for content in contents]
        scores = model.compute_score(pairs, normalize=True)
        # compute_score may return a single float when given one pair
        if isinstance(scores, float):
            scores = [scores]
        return list(scores)

    async def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        if not candidates:
            return []

        loop = asyncio.get_running_loop()
        contents = [doc["content"] for doc in candidates]
        scores = await loop.run_in_executor(None, self._score_sync, query, contents)

        scored = []
        for doc, score in zip(candidates, scores):
            entry = dict(doc)
            entry["rerank_score"] = float(score)
            scored.append(entry)

        scored.sort(key=lambda d: d["rerank_score"], reverse=True)
        return scored[:top_k]
