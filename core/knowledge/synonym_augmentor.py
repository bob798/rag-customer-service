"""SynonymAugmentor — document-side synonym expansion for improved recall.

Design principle: Single Responsibility.
  - FAQParser / DefaultParser: file → raw chunks (unchanged)
  - SynonymAugmentor: raw chunks → synonym-augmented chunks

Usage:
    from core.knowledge.synonym_augmentor import SynonymAugmentor

    # Domain synonym map: {canonical_word: [synonyms...]}
    synonym_map = {
        "音箱": ["音响", "扬声器", "喇叭"],
        "没有声音": ["不出声", "无声", "没响"],
    }
    augmentor = SynonymAugmentor(synonym_map)

    # Wrap any parser output
    raw_chunks = faq_parser.parse(file_path, doc_id, metadata)
    chunks = augmentor.augment(raw_chunks)
    await vector_store.add(chunks)
    bm25_store.add(chunks)

Why document-side (not query-side only):
    BM25 is a bag-of-words model — it only matches tokens present in the
    document. Appending synonyms to documents makes BM25 match queries that
    use any synonym, not just the canonical term.
    Vector retrieval also benefits: the embedding of an augmented chunk
    covers a broader semantic region.
"""
from __future__ import annotations


class SynonymAugmentor:
    """Appends synonym annotations to chunk content at index time.

    Does NOT modify the original Q&A text — appends a separate annotation
    line to avoid corrupting the original format. This keeps the stored
    content human-readable while giving BM25/vector retrieval extra signals.

    Example output:
        Q: 音箱没有声音怎么办？
        A: 请检查电源是否打开...
        [同义词: 音箱/音响/扬声器/喇叭 没有声音/不出声/无声/没响]
    """

    def __init__(self, synonym_map: dict[str, list[str]]) -> None:
        """
        Args:
            synonym_map: {canonical_word: [synonym1, synonym2, ...]}
                         Key is the word to detect in document content.
                         Value is the list of synonyms to inject.
        """
        self._map = synonym_map

    def augment(self, chunks: list[dict]) -> list[dict]:
        """Return new chunk list with synonym annotations appended.

        Original chunks are not mutated — returns copies.
        """
        result = []
        for chunk in chunks:
            augmented = dict(chunk)
            augmented["content"] = self._expand(chunk["content"])
            result.append(augmented)
        return result

    def _expand(self, text: str) -> str:
        """Append synonym groups found in text as a single annotation line."""
        found = []
        for word, synonyms in self._map.items():
            if word in text:
                group = "/".join([word] + synonyms)
                found.append(group)
        if found:
            return text + "\n[同义词: " + " ".join(found) + "]"
        return text
