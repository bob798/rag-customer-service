"""Tests for SemanticChunker."""
import pytest

from core.knowledge.chunker import SemanticChunker


DOC_ID = "doc-test-001"
BASE_METADATA = {"source": "unit-test"}


@pytest.fixture
def chunker():
    return SemanticChunker(chunk_size=512, overlap=10)


class TestSemanticChunker:
    def test_single_paragraph_no_split(self, chunker):
        """One short paragraph should produce exactly 1 chunk."""
        content = "This is a single short paragraph."
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        assert result[0]["content"] == content

    def test_multiple_paragraphs_merged(self, chunker):
        """Three short paragraphs each well under 512 tokens should be merged into 1 chunk."""
        paragraphs = [
            "First paragraph with some text.",
            "Second paragraph with some text.",
            "Third paragraph with some text.",
        ]
        content = "\n\n".join(paragraphs)
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        # All three paragraphs should be present in the merged chunk
        for para in paragraphs:
            assert para in result[0]["content"]

    def test_long_content_split(self):
        """Content exceeding chunk_size should be split into multiple chunks."""
        chunker = SemanticChunker(chunk_size=20, overlap=5)
        # Each paragraph is ~10 words; two of them exceed chunk_size=20
        para_a = "word " * 12  # 12 words
        para_b = "other " * 12  # 12 words
        para_c = "more " * 12  # 12 words
        content = f"{para_a.strip()}\n\n{para_b.strip()}\n\n{para_c.strip()}"
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) > 1

    def test_overlap_added(self):
        """Second chunk should start with the tail words of the first chunk."""
        chunker = SemanticChunker(chunk_size=10, overlap=3)
        # Two paragraphs of 8 words each — will be split
        para_a = "alpha bravo charlie delta echo foxtrot golf hotel"  # 8 words
        para_b = "india juliet kilo lima mike november oscar papa"    # 8 words
        content = f"{para_a}\n\n{para_b}"
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 2
        # The second chunk should begin with the last 3 words of the first chunk
        last_three = " ".join(para_a.split()[-3:])
        assert result[1]["content"].startswith(last_three)

    def test_chunk_metadata(self, chunker):
        """Every chunk must have chunk_id, doc_id, content, and metadata with chunk_index."""
        content = "Some content for metadata testing."
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        chunk = result[0]
        assert "chunk_id" in chunk
        assert chunk["chunk_id"]  # non-empty
        assert chunk["doc_id"] == DOC_ID
        assert "content" in chunk
        assert "metadata" in chunk
        assert chunk["metadata"]["chunk_index"] == 0
        # Original metadata should be preserved
        assert chunk["metadata"]["source"] == "unit-test"

    def test_empty_content_returns_no_chunks(self, chunker):
        """Empty or whitespace-only content should return an empty list."""
        assert chunker.chunk("", DOC_ID, BASE_METADATA) == []
        assert chunker.chunk("   \n\n   ", DOC_ID, BASE_METADATA) == []

    def test_chunk_ids_are_unique(self, chunker):
        """Each chunk must have a unique chunk_id."""
        chunker_small = SemanticChunker(chunk_size=5, overlap=2)
        content = "\n\n".join(["word " * 6 for _ in range(4)])
        result = chunker_small.chunk(content, DOC_ID, BASE_METADATA)
        ids = [c["chunk_id"] for c in result]
        assert len(ids) == len(set(ids))
