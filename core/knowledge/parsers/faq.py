import re
import uuid

from core.interfaces import BaseParser


class FAQParser(BaseParser):
    """Parses FAQ documents where Q&A pairs are atomic units.

    Handles patterns:
      Q: <question>
      A: <answer>

    Or numbered patterns:
      1. Q: ...
         A: ...
    """

    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        """Handle .txt files with FAQ content hint, or explicit faq type."""
        return file_type in ("faq", "txt") and "faq" in content_hint.lower()

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return self._extract_qa_pairs(text, doc_id, metadata)

    def _extract_qa_pairs(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        """Extract Q&A pairs using regex. Each pair becomes one chunk."""
        # Pattern: Q: ... A: ... (multi-line), supports both ASCII and fullwidth colons
        pattern = re.compile(
            r'Q[：:]\s*(.+?)\s*\n+A[：:]\s*(.+?)(?=\n+Q[：:]|\Z)',
            re.DOTALL | re.IGNORECASE,
        )
        chunks = []
        for match in pattern.finditer(text):
            question = match.group(1).strip()
            answer = match.group(2).strip()
            content = f"Q: {question}\nA: {answer}"
            chunk_id = str(uuid.uuid4())
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "doc_id": doc_id,
                    "content": content,
                    "metadata": {**metadata, "type": "faq", "question": question},
                }
            )
        return chunks
