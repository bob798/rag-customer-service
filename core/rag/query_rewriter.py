import logging

from core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个查询优化助手。将用户的口语化问题改写为清晰、规范的检索查询语句。
只返回改写后的查询语句，不要包含任何解释或额外文字。
若问题已经足够清晰，原样返回即可。"""


class QueryRewriter:
    """Rewrites colloquial user questions into clean retrieval queries."""

    def __init__(self, llm: LLMFactory) -> None:
        self._llm = llm

    async def rewrite(self, question: str) -> str:
        """Rewrite question for retrieval. Returns original on failure."""
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]
        try:
            rewritten = await self._llm.complete(messages)
            rewritten = rewritten.strip()
            return rewritten if rewritten else question
        except Exception as exc:
            logger.warning("QueryRewriter failed, using original question: %s", exc)
            return question
