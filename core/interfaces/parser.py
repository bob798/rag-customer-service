from abc import ABC, abstractmethod


class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        """Return True if this parser can handle the given file type."""
        ...

    @abstractmethod
    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        """Parse document and return list of chunks.
        Each chunk: {"chunk_id": str, "doc_id": str, "content": str, "metadata": dict}
        """
        ...
