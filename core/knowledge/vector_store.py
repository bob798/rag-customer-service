import logging
import threading
from typing import Optional
from core.interfaces import BaseEmbedder

logger = logging.getLogger(__name__)


class ChromaVectorStore:
    """ChromaDB vector store for document chunks.

    Provides add, query, and delete operations.
    ChromaDB client is created lazily on first use.
    """

    def __init__(
        self,
        embedder: BaseEmbedder,
        collection_name: str = "knowledge_base",
        persist_directory: str = "./data/chroma",
    ):
        self.embedder = embedder
        self.collection_name = collection_name
        self.persist_directory = persist_directory
        self._client = None
        self._collection = None
        self._init_lock = threading.Lock()

    def _get_collection(self):
        """Lazy init ChromaDB client and collection."""
        if self._collection is None:
            with self._init_lock:
                if self._collection is None:  # double-checked locking
                    import chromadb
                    self._client = chromadb.PersistentClient(path=self.persist_directory)
                    self._collection = self._client.get_or_create_collection(
                        name=self.collection_name,
                        metadata={"hnsw:space": "cosine"},
                    )
        return self._collection

    async def add(self, chunks: list[dict]) -> None:
        """Add chunks to the vector store.

        Each chunk: {"chunk_id": str, "doc_id": str, "content": str, "metadata": dict}
        """
        if not chunks:
            return

        texts = [c["content"] for c in chunks]
        embeddings = await self.embedder.embed(texts)

        collection = self._get_collection()
        collection.add(
            ids=[c["chunk_id"] for c in chunks],
            embeddings=embeddings,
            documents=texts,
            metadatas=[
                {k: v for k, v in {"doc_id": c["doc_id"], **c.get("metadata", {})}.items() if v is not None}
                for c in chunks
            ],
        )
        logger.info(f"Added {len(chunks)} chunks to vector store")

    async def query(
        self,
        query_embedding: list[float],
        top_k: int = 20,
        doc_ids: Optional[list[str]] = None,
    ) -> list[dict]:
        """Query vector store by embedding. Returns top_k results.

        Returns: [{"chunk_id", "doc_id", "content", "score", "metadata"}]
        """
        collection = self._get_collection()

        where = {"doc_id": {"$in": doc_ids}} if doc_ids else None

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        chunks = []
        for i, chunk_id in enumerate(results["ids"][0]):
            distance = results["distances"][0][i]
            # Cosine distance → similarity score (clamped to [0.0, 1.0])
            score = max(0.0, min(1.0, 1.0 - distance))
            metadata = dict(results["metadatas"][0][i])
            metadata.pop("doc_id", None)  # already a top-level key
            chunks.append({
                "chunk_id": chunk_id,
                "doc_id": results["metadatas"][0][i].get("doc_id", ""),
                "content": results["documents"][0][i],
                "score": score,
                "metadata": metadata,
            })
        return chunks

    async def delete_by_doc_id(self, doc_id: str) -> int:
        """Delete all chunks for a document. Returns count deleted."""
        collection = self._get_collection()
        results = collection.get(where={"doc_id": doc_id})
        if not results["ids"]:
            return 0
        collection.delete(ids=results["ids"])
        logger.info(f"Deleted {len(results['ids'])} chunks for doc_id={doc_id}")
        return len(results["ids"])

    async def count(self) -> int:
        """Return total number of chunks in the store."""
        collection = self._get_collection()
        return collection.count()
