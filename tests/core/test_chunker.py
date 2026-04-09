"""Tests for SemanticChunker (character-based sizing)."""
import pytest

from core.knowledge.chunker import SemanticChunker


DOC_ID = "doc-test-001"
BASE_METADATA = {"source": "unit-test"}


@pytest.fixture
def chunker():
    return SemanticChunker(chunk_size=500, overlap=50)


class TestSemanticChunker:
    def test_single_paragraph_no_split(self, chunker):
        """One short paragraph should produce exactly 1 chunk."""
        content = "This is a single short paragraph."
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        assert result[0]["content"] == content

    def test_multiple_paragraphs_merged(self, chunker):
        """Three short paragraphs well under 500 chars should be merged into 1 chunk."""
        paragraphs = [
            "First paragraph with some text.",
            "Second paragraph with some text.",
            "Third paragraph with some text.",
        ]
        content = "\n\n".join(paragraphs)
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        for para in paragraphs:
            assert para in result[0]["content"]

    def test_long_content_split(self):
        """Content exceeding chunk_size characters should be split."""
        chunker = SemanticChunker(chunk_size=100, overlap=10)
        # Three paragraphs each ~60 chars; pairs exceed 100
        para_a = "a" * 60
        para_b = "b" * 60
        para_c = "c" * 60
        content = f"{para_a}\n\n{para_b}\n\n{para_c}"
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) > 1

    def test_overlap_added(self):
        """Second chunk should start with the tail characters of the first chunk."""
        chunker = SemanticChunker(chunk_size=50, overlap=10)
        para_a = "A" * 50  # exactly 50 chars → becomes chunk 1
        para_b = "B" * 50  # exactly 50 chars → becomes chunk 2
        content = f"{para_a}\n\n{para_b}"
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 2
        # Chunk 2 should start with last 10 chars of chunk 1
        assert result[1]["content"].startswith("A" * 10)

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
        assert chunk["metadata"]["source"] == "unit-test"

    def test_empty_content_returns_no_chunks(self, chunker):
        """Empty or whitespace-only content should return an empty list."""
        assert chunker.chunk("", DOC_ID, BASE_METADATA) == []
        assert chunker.chunk("   \n\n   ", DOC_ID, BASE_METADATA) == []

    def test_chunk_ids_are_unique(self):
        """Each chunk must have a unique chunk_id."""
        chunker = SemanticChunker(chunk_size=30, overlap=5)
        content = "\n\n".join(["x" * 30 for _ in range(4)])
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        ids = [c["chunk_id"] for c in result]
        assert len(ids) == len(set(ids))

    # --- Chinese text tests ---

    def test_chinese_char_count(self):
        """Character count should work correctly for Chinese text."""
        chunker = SemanticChunker(chunk_size=500, overlap=50)
        assert chunker._char_count("你好世界") == 4
        assert chunker._char_count("Hello 你好") == 8

    def test_chinese_text_chunking(self):
        """Chinese text should be split based on character count, not word count."""
        chunker = SemanticChunker(chunk_size=20, overlap=5)
        # 30 Chinese chars → should be split
        content = "这是一段中文文本" * 4  # 32 chars
        para_a = "这是一段中文文本" * 2  # 16 chars — fits in one chunk
        para_b = "另外一段中文文本" * 2  # 16 chars
        full = f"{para_a}\n\n{para_b}"
        result = chunker.chunk(full, DOC_ID, BASE_METADATA)
        assert len(result) == 2

    def test_chinese_overlap(self):
        """Overlap should take last N characters, not words."""
        chunker = SemanticChunker(chunk_size=20, overlap=5)
        para_a = "甲乙丙丁戊己庚辛壬癸" * 2  # 20 chars
        para_b = "子丑寅卯辰巳午未申酉" * 2  # 20 chars
        content = f"{para_a}\n\n{para_b}"
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 2
        # Second chunk should start with last 5 chars of first
        assert result[1]["content"].startswith(para_a[-5:])

    def test_chinese_sentence_split(self):
        """Long Chinese paragraph with 。should be split on sentence boundaries."""
        chunker = SemanticChunker(chunk_size=30, overlap=5)
        # A single paragraph >30 chars, with sentence markers
        long_para = "第一句话在这里。第二句话在这里。第三句话也在这里。"  # 24 chars
        # This fits in one chunk (24 < 30), so make it longer
        long_para = "第一句话在这里讲的比较长。第二句话在这里讲的也很长。第三句话也在这里讲得更长。"
        result = chunker.chunk(long_para, DOC_ID, BASE_METADATA)
        # Should be split on 。 boundaries, not mid-sentence
        for chunk in result:
            content = chunk["content"]
            # Each chunk should end with a sentence ender or be the last chunk
            if chunk != result[-1]:
                assert content.rstrip().endswith(("。", "！", "？", "；"))

    def test_mixed_chinese_english(self):
        """Mixed Chinese/English content should be handled correctly."""
        chunker = SemanticChunker(chunk_size=500, overlap=50)
        content = "这是中文段落，包含English words混合在一起。\n\nThis is an English paragraph with 中文 mixed in."
        result = chunker.chunk(content, DOC_ID, BASE_METADATA)
        assert len(result) == 1
        assert "English" in result[0]["content"]
        assert "中文" in result[0]["content"]
