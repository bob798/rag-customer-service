from abc import ABC, abstractmethod


class BaseRetriever(ABC):
    @abstractmethod
    async def retrieve(
        self,
        query_vec: list[float],
        query_text: str,
        top_k: int = 5
    ) -> list[dict]:
        """Retrieve top-k candidates.
        Returns: [{"chunk_id": str, "doc_id": str, "content": str, "score": float, "metadata": dict}]
        """
        ...
