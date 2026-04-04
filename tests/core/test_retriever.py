"""Tests for GteQwen2Embedder and ChromaVectorStore (vector retrieval part).

All external dependencies (sentence_transformers, chromadb) are mocked via
sys.modules stubs or unittest.mock.patch — they are not installed.
"""
import sys
import types
import asyncio
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Stub sentence_transformers and chromadb before importing any project code
# ---------------------------------------------------------------------------

def _make_st_stub():
    stub = types.ModuleType("sentence_transformers")
    stub.SentenceTransformer = MagicMock()
    sys.modules["sentence_transformers"] = stub
    return stub


def _make_chromadb_stub():
    stub = types.ModuleType("chromadb")
    stub.PersistentClient = MagicMock()
    sys.modules["chromadb"] = stub
    return stub


_make_st_stub()
_make_chromadb_stub()


# Now safe to import
from core.knowledge.embedder import GteQwen2Embedder  # noqa: E402
from core.knowledge.vector_store import ChromaVectorStore  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# GteQwen2Embedder tests
# ---------------------------------------------------------------------------

class TestGteQwen2Embedder:
    def _make_embedder_with_mock_model(self):
        """Return (embedder, mock_model) with SentenceTransformer pre-loaded."""
        embedder = GteQwen2Embedder(model_name="test-model")
        mock_model = MagicMock()
        embedder._model = mock_model  # inject directly — skips lazy load
        return embedder, mock_model

    def test_embedder_returns_embeddings(self):
        """embed() should return a list-of-lists matching input length."""
        embedder, mock_model = self._make_embedder_with_mock_model()
        # encode returns a numpy array
        fake_vectors = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
        mock_model.encode.return_value = fake_vectors

        result = run(embedder.embed(["hello", "world"]))

        mock_model.encode.assert_called_once_with(
            ["hello", "world"], normalize_embeddings=True
        )
        assert isinstance(result, list)
        assert len(result) == 2
        assert isinstance(result[0], list)
        assert result[0] == pytest.approx([0.1, 0.2, 0.3])
        assert result[1] == pytest.approx([0.4, 0.5, 0.6])

    def test_embedder_empty_input_returns_empty(self):
        """embed([]) should short-circuit and return []."""
        embedder = GteQwen2Embedder()
        result = run(embedder.embed([]))
        assert result == []

    def test_embedder_uses_executor(self):
        """embed() must delegate synchronous work via run_in_executor.

        Strategy: spy on the real event loop's run_in_executor so we can
        confirm it is called with (None, _encode_sync) — the signature used
        for offloading blocking work to the default thread pool.
        """
        embedder, mock_model = self._make_embedder_with_mock_model()
        mock_model.encode.return_value = np.array([[0.0, 1.0]])

        loop = asyncio.new_event_loop()
        executor_calls = []
        original_run_in_executor = loop.run_in_executor

        async def _spy_embed():
            # Wrap run_in_executor to record calls without changing behaviour
            def recording_run_in_executor(executor, func, *args):
                executor_calls.append((executor, func, args))
                return original_run_in_executor(executor, func, *args)

            loop.run_in_executor = recording_run_in_executor
            return await embedder.embed(["test"])

        try:
            result = loop.run_until_complete(_spy_embed())
        finally:
            loop.close()

        assert len(executor_calls) == 1
        executor, func, args = executor_calls[0]
        assert executor is None  # default thread pool
        assert func == embedder._encode_sync
        assert result == [[pytest.approx(0.0), pytest.approx(1.0)]]

    def test_embedder_lazy_loads_model(self):
        """_load_model() should construct SentenceTransformer only once."""
        embedder = GteQwen2Embedder(model_name="my-model")
        assert embedder._model is None

        with patch.dict(sys.modules, {"sentence_transformers": sys.modules["sentence_transformers"]}):
            mock_st_class = sys.modules["sentence_transformers"].SentenceTransformer
            mock_st_class.reset_mock()
            fake_instance = MagicMock()
            mock_st_class.return_value = fake_instance

            embedder._load_model()
            embedder._load_model()  # second call — should NOT create again

        mock_st_class.assert_called_once_with("my-model")
        assert embedder._model is fake_instance


# ---------------------------------------------------------------------------
# ChromaVectorStore tests
# ---------------------------------------------------------------------------

class TestChromaVectorStore:
    def _make_store_with_mock_collection(self):
        """Return (store, mock_embedder, mock_collection)."""
        mock_embedder = AsyncMock(spec=GteQwen2Embedder)
        store = ChromaVectorStore(
            embedder=mock_embedder,
            collection_name="test_col",
            persist_directory="/tmp/test_chroma",
        )
        mock_collection = MagicMock()
        store._collection = mock_collection  # bypass lazy init
        return store, mock_embedder, mock_collection

    def test_vector_store_add_chunks(self):
        """add() should embed texts then call collection.add with correct args."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()

        chunks = [
            {"chunk_id": "c1", "doc_id": "d1", "content": "hello", "metadata": {"page": 1}},
            {"chunk_id": "c2", "doc_id": "d1", "content": "world", "metadata": {"page": 2}},
        ]
        mock_embedder.embed.return_value = [[0.1, 0.2], [0.3, 0.4]]

        run(store.add(chunks))

        mock_embedder.embed.assert_called_once_with(["hello", "world"])
        mock_collection.add.assert_called_once_with(
            ids=["c1", "c2"],
            embeddings=[[0.1, 0.2], [0.3, 0.4]],
            documents=["hello", "world"],
            metadatas=[
                {"doc_id": "d1", "page": 1},
                {"doc_id": "d1", "page": 2},
            ],
        )

    def test_vector_store_add_empty_is_noop(self):
        """add([]) should return immediately without calling embed or collection."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()
        run(store.add([]))
        mock_embedder.embed.assert_not_called()
        mock_collection.add.assert_not_called()

    def test_vector_store_query_returns_results(self):
        """query() should shape chromadb results into expected dicts."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()

        mock_collection.query.return_value = {
            "ids": [["c1", "c2"]],
            "documents": [["hello", "world"]],
            "metadatas": [[{"doc_id": "d1", "page": 1}, {"doc_id": "d1", "page": 2}]],
            "distances": [[0.1, 0.3]],
        }

        query_emb = [0.5, 0.6]
        results = run(store.query(query_emb, top_k=5))

        mock_collection.query.assert_called_once_with(
            query_embeddings=[[0.5, 0.6]],
            n_results=5,
            where=None,
            include=["documents", "metadatas", "distances"],
        )
        assert len(results) == 2
        r0 = results[0]
        assert r0["chunk_id"] == "c1"
        assert r0["doc_id"] == "d1"
        assert r0["content"] == "hello"
        assert r0["score"] == pytest.approx(0.9)  # 1.0 - 0.1
        assert r0["metadata"] == {"doc_id": "d1", "page": 1}

    def test_vector_store_query_score_conversion(self):
        """score must equal 1.0 - distance for every result."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()

        distances = [0.0, 0.25, 0.5, 0.75, 1.0]
        mock_collection.query.return_value = {
            "ids": [[f"c{i}" for i in range(5)]],
            "documents": [[f"doc{i}" for i in range(5)]],
            "metadatas": [[{"doc_id": "d1"} for _ in range(5)]],
            "distances": [distances],
        }

        results = run(store.query([0.1], top_k=5))

        for result, dist in zip(results, distances):
            assert result["score"] == pytest.approx(1.0 - dist)

    def test_vector_store_query_with_doc_ids_filter(self):
        """query() with doc_ids should pass $in filter to chromadb."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()

        mock_collection.query.return_value = {
            "ids": [[]],
            "documents": [[]],
            "metadatas": [[]],
            "distances": [[]],
        }

        run(store.query([0.1, 0.2], top_k=3, doc_ids=["d1", "d2"]))

        call_kwargs = mock_collection.query.call_args[1]
        assert call_kwargs["where"] == {"doc_id": {"$in": ["d1", "d2"]}}

    def test_vector_store_delete_by_doc_id(self):
        """delete_by_doc_id() should delete matching chunk ids and return count."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()
        mock_collection.get.return_value = {"ids": ["c1", "c2", "c3"]}

        count = run(store.delete_by_doc_id("d1"))

        mock_collection.get.assert_called_once_with(where={"doc_id": "d1"})
        mock_collection.delete.assert_called_once_with(ids=["c1", "c2", "c3"])
        assert count == 3

    def test_vector_store_delete_nonexistent_doc(self):
        """delete_by_doc_id() with no matching chunks should return 0 without calling delete."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()
        mock_collection.get.return_value = {"ids": []}

        count = run(store.delete_by_doc_id("nonexistent"))

        mock_collection.delete.assert_not_called()
        assert count == 0

    def test_vector_store_count(self):
        """count() should return the integer from collection.count()."""
        store, mock_embedder, mock_collection = self._make_store_with_mock_collection()
        mock_collection.count.return_value = 42

        result = run(store.count())

        mock_collection.count.assert_called_once()
        assert result == 42
        assert isinstance(result, int)
