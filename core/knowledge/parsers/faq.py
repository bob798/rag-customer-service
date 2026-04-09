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
        """Handle FAQ files.

        Matches if:
        - file_type is explicitly "faq", OR
        - file_type is "txt" AND (content_hint contains "faq" OR Chinese Q&A patterns found)
        """
        if file_type == "faq":
            return True
        if file_type != "txt":
            return False
        hint_lower = content_hint.lower()
        # English FAQ hint
        if "faq" in hint_lower:
            return True
        # Chinese FAQ pattern detection
        import re
        if re.search(r"(问[：:]\s*|Q[：:]\s*)", content_hint):
            return True
        return False

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        with open(file_path, "r", encoding="utf-8") as f:
            text = f.read()
        return self._extract_qa_pairs(text, doc_id, metadata)

    def _extract_qa_pairs(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        """Extract Q&A pairs using regex. Each pair becomes one chunk.

        Supports both English (Q:/A:) and Chinese (问：/答：) patterns,
        with ASCII or fullwidth colons.
        """
        # Pattern: Q:/问： ... A:/答： ... (multi-line), supports both ASCII and fullwidth colons
        pattern = re.compile(
            r'(?:Q|问)[：:]\s*(.+?)\s*\n+(?:A|答)[：:]\s*(.+?)(?=\n+(?:Q|问)[：:]|\Z)',
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
                    "metadata": {
                        **metadata,
                        "type": "faq",
                        "content_type": "text",
                        "question": question,
                        "page": None,
                        "section": None,
                    },
                }
            )
        return chunks
