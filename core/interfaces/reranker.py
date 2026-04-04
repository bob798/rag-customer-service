from abc import ABC, abstractmethod


class BaseReranker(ABC):
    @abstractmethod
    async def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """Rerank candidates by relevance to query.
        Returns same shape as input, sorted by relevance score descending.
        Each item should have a "rerank_score": float field added.
        """
        ...
