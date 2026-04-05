import json
import logging
from typing import AsyncGenerator

from core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个专业的客服助手。请根据提供的参考资料回答用户问题。

要求：
1. 只根据参考资料中的内容回答，不要编造信息
2. 回答要简洁清晰
3. 若参考资料不足以回答问题，请说明"""


def _build_context(chunks: list[dict]) -> str:
    parts = []
    for i, chunk in enumerate(chunks, 1):
        parts.append(f"[{i}] {chunk['content']}")
    return "\n\n".join(parts)


def _build_sources(chunks: list[dict]) -> list[dict]:
    sources = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        sources.append({
            "doc_id": chunk.get("doc_id", ""),
            "chunk_id": chunk.get("chunk_id", ""),
            "title": meta.get("source_title", ""),
            "content_preview": chunk.get("content", "")[:100],
        })
    return sources


class LLMGenerator:
    """Generates answers from retrieved chunks using LLM."""

    def __init__(self, llm: LLMFactory) -> None:
        self._llm = llm

    def _build_messages(
        self,
        question: str,
        chunks: list[dict],
        confidence_tier: str,
        session_history: list[dict],
    ) -> list[dict]:
        context = _build_context(chunks)
        user_content = f"参考资料：\n{context}\n\n问题：{question}"

        messages = [{"role": "system", "content": _SYSTEM_PROMPT}]
        messages.extend(session_history)
        messages.append({"role": "user", "content": user_content})
        return messages

    async def generate(
        self,
        question: str,
        chunks: list[dict],
        confidence_tier: str,
        session_history: list[dict] = [],
    ) -> dict:
        """Generate answer. Returns {"answer": str, "sources": list[dict]}."""
        messages = self._build_messages(question, chunks, confidence_tier, session_history)
        answer = await self._llm.complete(messages)

        if confidence_tier == "medium":
            answer = "以下回答仅供参考：\n" + answer

        return {
            "answer": answer,
            "sources": _build_sources(chunks),
        }

    async def generate_stream(
        self,
        question: str,
        chunks: list[dict],
        confidence_tier: str,
        session_history: list[dict] = [],
    ) -> AsyncGenerator[dict, None]:
        """Stream answer as SSE-style dicts.

        Yields {"type": "delta", "content": str} for each token chunk.
        Final frame: {"type": "done", "sources": list, "uncertain": bool}
        """
        messages = self._build_messages(question, chunks, confidence_tier, session_history)
        stream = await self._llm.complete_stream(messages)

        prefix_sent = False

        async for chunk in stream:
            delta = chunk.choices[0].delta
            content = getattr(delta, "content", None) or ""
            if not content:
                continue

            if not prefix_sent and confidence_tier == "medium":
                yield {"type": "delta", "content": "以下回答仅供参考：\n"}
                prefix_sent = True

            yield {"type": "delta", "content": content}

        yield {
            "type": "done",
            "sources": _build_sources(chunks),
            "uncertain": confidence_tier == "medium",
        }
