import re
import uuid

from core.interfaces import BaseChunker


class SemanticChunker(BaseChunker):
    """Splits text at paragraph and sentence boundaries with character-based size control.

    Strategy:
    1. Split by double newlines (paragraph boundaries)
    2. Further split long paragraphs on Chinese/English sentence-ending punctuation
    3. Merge short segments until chunk_size characters
    4. Add overlap characters from the end of previous chunk to start of next

    Note: chunk_size and overlap are measured in **characters** (not tokens).
    For Chinese text, 1 character ≈ 1 semantic unit. This avoids the CJK
    whitespace-splitting problem entirely.
    """

    def __init__(self, chunk_size: int = 500, overlap: int = 50) -> None:
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, content: str, doc_id: str, metadata: dict) -> list[dict]:
        paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
        # Split long paragraphs on sentence boundaries
        segments = []
        for p in paragraphs:
            segments.extend(self._split_long_paragraph(p))
        raw_chunks = self._merge_paragraphs(segments)
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

    def _char_count(self, text: str) -> int:
        """Character count — works correctly for both Chinese and English."""
        return len(text)

    def _split_long_paragraph(self, para: str) -> list[str]:
        """Split a paragraph exceeding chunk_size on sentence boundaries."""
        if len(para) <= self.chunk_size:
            return [para]
        sentences = re.split(r'(?<=[。！？；\n.!?])', para)
        return [s for s in sentences if s.strip()]

    def _merge_paragraphs(self, paragraphs: list[str]) -> list[str]:
        """Merge short paragraphs up to chunk_size characters."""
        chunks: list[str] = []
        current: list[str] = []
        current_chars = 0

        for para in paragraphs:
            para_chars = self._char_count(para)
            if current_chars + para_chars > self.chunk_size and current:
                chunks.append("\n\n".join(current))
                current = []
                current_chars = 0
            current.append(para)
            current_chars += para_chars

        if current:
            chunks.append("\n\n".join(current))
        return chunks

    def _add_overlap(self, chunks: list[str]) -> list[str]:
        """Prepend the last `overlap` characters of previous chunk to current chunk."""
        if len(chunks) <= 1:
            return chunks
        result = [chunks[0]]
        for i in range(1, len(chunks)):
            overlap_text = chunks[i - 1][-self.overlap:]
            result.append(overlap_text + "\n\n" + chunks[i])
        return result
