"""In-memory BM25 index for keyword-based retrieval."""
import logging
import threading
from typing import Optional

import jieba
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)


class Bm25Store:
    """In-memory BM25 index for keyword-based retrieval.

    Uses jieba for Chinese tokenization.
    Index is rebuilt from DB on service restart (fast, < 1s for typical knowledge bases).
    Not persistent — caller must call rebuild_from_chunks() on startup.

    Thread-safe: all mutations (add, delete, rebuild) are protected by a lock.
    """

    def __init__(self):
        self._bm25: Optional[BM25Okapi] = None
        self._chunk_ids: list[str] = []
        self._doc_ids: list[str] = []
        self._contents: list[str] = []
        self._lock = threading.Lock()

    def _tokenize(self, text: str) -> list[str]:
        """Tokenize text using jieba. Handles mixed Chinese/English."""
        return list(jieba.cut(text))

    def add(self, chunks: list[dict]) -> None:
        """Add chunks to BM25 index. Rebuilds the index.

        Each chunk: {"chunk_id": str, "doc_id": str, "content": str, ...}
        """
        with self._lock:
            for chunk in chunks:
                self._chunk_ids.append(chunk["chunk_id"])
                self._doc_ids.append(chunk["doc_id"])
                self._contents.append(chunk["content"])
            self._rebuild_index_unsafe()

    def _rebuild_index_unsafe(self) -> None:
        """Rebuild BM25 index. Must be called while holding self._lock."""
        if not self._contents:
            self._bm25 = None
            return
        tokenized = [self._tokenize(c) for c in self._contents]
        self._bm25 = BM25Okapi(tokenized)
        logger.debug(f"BM25 index rebuilt with {len(self._contents)} documents")

    def search(self, query: str, top_k: int = 20) -> list[dict]:
        """Search BM25 index. Returns top_k results.

        Returns: [{"chunk_id": str, "doc_id": str, "content": str, "score": float}]
        Scores are raw BM25 scores (not normalized to [0,1]).
        """
        if self._bm25 is None:
            return []

        query_tokens = self._tokenize(query)
        scores = self._bm25.get_scores(query_tokens)

        # Get top_k by score (descending)
        indexed = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

        results = []
        for idx, score in indexed:
            if score <= 0:
                continue  # skip zero-score matches
            results.append({
                "chunk_id": self._chunk_ids[idx],
                "doc_id": self._doc_ids[idx],
                "content": self._contents[idx],
                "score": float(score),
            })
        return results

    def delete_by_doc_id(self, doc_id: str) -> int:
        """Remove all chunks for a document. Rebuilds index.

        Returns count of removed chunks.
        """
        with self._lock:
            before = len(self._chunk_ids)
            indices_to_keep = [
                i for i, did in enumerate(self._doc_ids) if did != doc_id
            ]
            self._chunk_ids = [self._chunk_ids[i] for i in indices_to_keep]
            self._doc_ids = [self._doc_ids[i] for i in indices_to_keep]
            self._contents = [self._contents[i] for i in indices_to_keep]
            self._rebuild_index_unsafe()
            removed = before - len(self._chunk_ids)
        logger.info(f"Removed {removed} chunks for doc_id={doc_id}")
        return removed

    def rebuild_from_chunks(self, chunks: list[dict]) -> None:
        """Rebuild the entire index from a list of chunks.

        Called on service startup to restore in-memory index from DB.
        """
        with self._lock:
            self._chunk_ids = []
            self._doc_ids = []
            self._contents = []
            for chunk in chunks:
                self._chunk_ids.append(chunk["chunk_id"])
                self._doc_ids.append(chunk["doc_id"])
                self._contents.append(chunk["content"])
            self._rebuild_index_unsafe()
        logger.info(f"BM25 index rebuilt from {len(chunks)} chunks")

    def count(self) -> int:
        """Return number of indexed documents."""
        return len(self._contents)
