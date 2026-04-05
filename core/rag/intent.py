import json
import logging
from typing import Optional

from core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """你是一个客服意图分类器。判断用户问题是否属于客服范畴（退款、订单、发货、产品、账号等）。

请返回 JSON 格式，不要包含任何额外文字：
{
  "intent": "in_scope" | "out_of_scope" | "ambiguous",
  "confidence": <0.0~1.0的浮点数>,
  "clarification_question": <若为ambiguous则填澄清问题字符串，否则填null>
}

- in_scope: 明确属于客服业务范围
- out_of_scope: 明确不属于客服范围（如天气、新闻、编程等）
- ambiguous: 意图不明，需要追问"""


class IntentClassifier:
    """Classifies user question intent using LLM."""

    def __init__(self, llm: LLMFactory, max_retries: int = 2) -> None:
        self._llm = llm
        self._max_retries = max_retries

    async def classify(self, question: str) -> dict:
        """Classify question intent.

        Returns:
            {
                "intent": "in_scope" | "out_of_scope" | "ambiguous",
                "confidence": float,
                "clarification_question": Optional[str]
            }
        """
        messages = [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": question},
        ]

        for attempt in range(self._max_retries):
            try:
                raw = await self._llm.complete(messages)
                return self._parse(raw)
            except Exception as exc:
                logger.warning("IntentClassifier attempt %d failed: %s", attempt + 1, exc)
                if attempt == self._max_retries - 1:
                    logger.error("IntentClassifier exhausted retries, defaulting to in_scope")
                    return self._default()

        return self._default()

    def _parse(self, raw: str) -> dict:
        # Strip markdown code fences if present
        text = raw.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

        data = json.loads(text)
        intent = data.get("intent", "in_scope")
        if intent not in ("in_scope", "out_of_scope", "ambiguous"):
            intent = "in_scope"

        confidence = float(data.get("confidence", 0.8))
        confidence = max(0.0, min(1.0, confidence))

        clarification_question: Optional[str] = None
        if intent == "ambiguous":
            clarification_question = data.get("clarification_question") or "请问您具体想了解哪方面的问题？"

        return {
            "intent": intent,
            "confidence": confidence,
            "clarification_question": clarification_question,
        }

    def _default(self) -> dict:
        return {"intent": "in_scope", "confidence": 0.5, "clarification_question": None}
