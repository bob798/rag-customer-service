from abc import ABC, abstractmethod


class BaseReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, candidates: list[dict], top_k: int = 5) -> list[dict]:
        """Rerank candidates by relevance to query, returning top_k results.
        Returns top_k items sorted by relevance score descending.
        Each item should have a "rerank_score": float field added.
        """
        ...
