import json
import logging
import os
from typing import Optional

from core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

# 内联兜底 prompt（不依赖外部文件）
_DEFAULT_PROMPT = """你是一个客服意图分类器。判断用户问题是否属于客服范畴（退款、订单、发货、产品、账号等）。

请返回 JSON 格式，不要包含任何额外文字：
{
  "intent": "in_scope" | "out_of_scope" | "ambiguous",
  "confidence": <0.0~1.0的浮点数>,
  "clarification_question": <若为ambiguous则填澄清问题字符串，否则填null>
}

- in_scope: 明确属于客服业务范围
- out_of_scope: 明确不属于客服范围（如天气、新闻、编程等）
- ambiguous: 意图不明，需要追问"""


def _load_intent_prompt(
    variant: str,
    variables: Optional[dict] = None,
    prompts_dir: str = "prompts",
) -> str:
    """Load system prompt from prompts/intent_classifier.yaml.

    Falls back to _DEFAULT_PROMPT if file not found or variant missing.
    """
    yaml_path = os.path.join(prompts_dir, "intent_classifier.yaml")
    try:
        import yaml
        with open(yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        prompt = config["variants"][variant]["system"]
        if variables:
            prompt = prompt.format(**variables)
        return prompt.strip()
    except FileNotFoundError:
        logger.debug("prompts/intent_classifier.yaml not found, using default prompt")
        return _DEFAULT_PROMPT
    except KeyError:
        logger.warning("Variant %r not found in intent_classifier.yaml, using default", variant)
        return _DEFAULT_PROMPT
    except Exception as exc:
        logger.warning("Failed to load intent prompt %r: %s, using default", variant, exc)
        return _DEFAULT_PROMPT


def _load_from_app_config(config_path: str = "config/app.yaml") -> dict:
    """Read intent_classifier section from config/app.yaml.

    Returns {"variant": str, "variables": dict | None}.
    Returns {} (→ defaults) if file not found.
    """
    try:
        import yaml
        with open(config_path, encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
        ic = cfg.get("intent_classifier", {})
        variant = ic.get("variant", "ecommerce")
        variables: dict = {}
        if "domain_name" in ic:
            variables["domain_name"] = ic["domain_name"]
        if "scope_description" in ic:
            variables["scope_description"] = ic["scope_description"].strip()
        return {"variant": variant, "variables": variables or None}
    except FileNotFoundError:
        return {}
    except Exception as exc:
        logger.warning("Failed to load config/app.yaml: %s", exc)
        return {}


class IntentClassifier:
    """Classifies user question intent using LLM.

    Scope is configured in config/app.yaml (intent_classifier.scope_description).
    Prompt variant is loaded from prompts/intent_classifier.yaml.

    Priority for scope config:
      1. Explicit variant/variables passed to __init__
      2. config/app.yaml (intent_classifier section)
      3. Inline _DEFAULT_PROMPT (hardcoded ecommerce scope)
    """

    def __init__(
        self,
        llm: LLMFactory,
        max_retries: int = 2,
        variant: Optional[str] = None,
        variables: Optional[dict] = None,
        prompts_dir: str = "prompts",
    ) -> None:
        self._llm = llm
        self._max_retries = max_retries

        # Load from config/app.yaml if not explicitly provided
        if variant is None:
            app_cfg = _load_from_app_config()
            variant = app_cfg.get("variant", "ecommerce")
            if variables is None:
                variables = app_cfg.get("variables")

        self._system_prompt = _load_intent_prompt(variant, variables, prompts_dir)
        logger.debug("IntentClassifier loaded variant=%r", variant)

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
            {"role": "system", "content": self._system_prompt},
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
