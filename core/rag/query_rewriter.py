import logging
import os
from typing import Optional

from core.llm.factory import LLMFactory

logger = logging.getLogger(__name__)

# 默认 prompt（内联兜底，不依赖外部文件）
_DEFAULT_PROMPT = """你是一个查询优化助手。将用户的口语化问题改写为清晰、规范的检索查询语句。
只返回改写后的查询语句，不要包含任何解释或额外文字。
若问题已经足够清晰，原样返回即可。"""


def _load_prompt_from_yaml(
    variant: str,
    variables: Optional[dict] = None,
    prompts_dir: str = "prompts",
) -> str:
    """Load system prompt from prompts/query_rewriter.yaml.

    Falls back to _DEFAULT_PROMPT if file not found or variant missing.
    """
    yaml_path = os.path.join(prompts_dir, "query_rewriter.yaml")
    try:
        import yaml  # optional dependency
        with open(yaml_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)
        prompt = config["variants"][variant]["system"]
        if variables:
            prompt = prompt.format(**variables)
        return prompt.strip()
    except FileNotFoundError:
        logger.debug("prompts/query_rewriter.yaml not found, using default prompt")
        return _DEFAULT_PROMPT
    except KeyError:
        logger.warning("Variant %r not found in query_rewriter.yaml, using default", variant)
        return _DEFAULT_PROMPT
    except Exception as exc:
        logger.warning("Failed to load prompt variant %r: %s, using default", variant, exc)
        return _DEFAULT_PROMPT


class QueryRewriter:
    """Rewrites colloquial user questions into clean retrieval queries.

    Supports configurable prompt variants via prompts/query_rewriter.yaml.

    Usage:
        # Default (normalize)
        QueryRewriter(llm)

        # Synonym expansion for better recall on synonymous terms
        QueryRewriter(llm, variant="synonym_expansion")

        # Domain-aware with injected context
        QueryRewriter(llm, variant="domain_aware", variables={
            "domain_name": "桌面近场音响客服",
            "domain_keywords": '{"设备": ["音箱", "音响", "扬声器", "喇叭"]}',
        })
    """

    def __init__(
        self,
        llm: LLMFactory,
        variant: str = "normalize",
        variables: Optional[dict] = None,
        prompts_dir: str = "prompts",
    ) -> None:
        self._llm = llm
        self._system_prompt = _load_prompt_from_yaml(variant, variables, prompts_dir)
        logger.debug("QueryRewriter loaded variant=%r", variant)

    async def rewrite(self, question: str) -> str:
        """Rewrite question for retrieval. Returns original on failure."""
        messages = [
            {"role": "system", "content": self._system_prompt},
            {"role": "user", "content": question},
        ]
        try:
            rewritten = await self._llm.complete(messages)
            rewritten = rewritten.strip()
            return rewritten if rewritten else question
        except Exception as exc:
            logger.warning("QueryRewriter failed, using original question: %s", exc)
            return question
