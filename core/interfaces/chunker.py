from abc import ABC, abstractmethod


class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, content: str, doc_id: str, metadata: dict) -> list[dict]:
        """Split content into chunks.
        Returns: [{"chunk_id": str, "doc_id": str, "content": str, "metadata": dict}]
        """
        ...
