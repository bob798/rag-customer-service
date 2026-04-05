import uuid

from core.interfaces import BaseChunker


class SemanticChunker(BaseChunker):
    """Splits text at paragraph boundaries with size limit and token overlap.

    Strategy:
    1. Split by double newlines (paragraph boundaries)
    2. Merge short paragraphs until chunk_size tokens
    3. Add overlap_tokens from the end of previous chunk to start of next
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 100) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, content: str, doc_id: str, metadata: dict) -> list[dict]:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        raw_chunks = self._merge_paragraphs(paragraphs)
        raw_chunks = self._add_overlap(raw_chunks)

        return [
            {
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "content": chunk,
                "metadata": {**metadata, "chunk_index": i},
            }
            for i, chunk in enumerate(raw_chunks)
        ]

    def _token_count(self, text: str) -> int:
        """Approximate token count by whitespace splitting.

        Note: Under-counts CJK (Chinese/Japanese/Korean) characters since they
        are not whitespace-separated. For CJK-heavy content, consider character
        count (len(text) // 2) as an alternative estimate.
        """
        return len(text.split())

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Merge short paragraphs up to chunk_size tokens."""
        chunks: list[str] = []
        current: list[str] = []
        current_tokens = 0

        for para in paragraphs:
            para_tokens = self._token_count(para)
            if current_tokens + para_tokens > self.chunk_size and current:
                chunks.append("\n\n".join(current))
                current = []
                current_tokens = 0
            current.append(para)
            current_tokens += para_tokens

        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend the last `overlap` tokens of previous chunk to current chunk.

        Note: This inflates each chunk (except the first) by up to `overlap` tokens
        beyond `chunk_size`. This is intentional — overlap improves retrieval by
        ensuring context is not lost at chunk boundaries.
        """
        if len(chunks) <= 1:
            return chunks
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            prev_words = chunks[i - 1].split()
            overlap_text = (
                " ".join(prev_words[-self.overlap:])
                if len(prev_words) >= self.overlap
                else chunks[i - 1]
            )
            result.append(overlap_text + "\n\n" + chunks[i])
        return result
