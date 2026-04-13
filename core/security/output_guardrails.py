"""Output guardrails: post-generation filtering based on configurable rules."""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import yaml

logger = logging.getLogger(__name__)


@dataclass
class GuardrailRule:
    pattern: re.Pattern
    action: str  # "fallback" | "add_disclaimer"
    message: str


@dataclass
class GuardrailConfig:
    forbidden_patterns: list[GuardrailRule] = field(default_factory=list)
    auto_disclaimer_triggers: list[GuardrailRule] = field(default_factory=list)


class OutputGuardrails:
    """Post-generation filter: check answer against configurable rules.

    Rules are loaded from a YAML config file. Two actions:
    - "fallback": replace the entire answer with the rule's message.
    - "add_disclaimer": append a disclaimer to the answer.
    """

    def __init__(self, config_path: str = "config/guardrails.yaml"):
        self._config = self._load_config(config_path)

    def _load_config(self, config_path: str) -> GuardrailConfig:
        if not os.path.exists(config_path):
            logger.warning("Guardrails config not found at %s, using empty config", config_path)
            return GuardrailConfig()

        with open(config_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw or "output_guardrails" not in raw:
            return GuardrailConfig()

        section = raw["output_guardrails"]
        config = GuardrailConfig()

        for item in section.get("forbidden_patterns", []):
            config.forbidden_patterns.append(GuardrailRule(
                pattern=re.compile(item["pattern"]),
                action=item.get("action", "fallback"),
                message=item["message"],
            ))

        for item in section.get("auto_disclaimer_triggers", []):
            config.auto_disclaimer_triggers.append(GuardrailRule(
                pattern=re.compile(item["pattern"]),
                action="add_disclaimer",
                message=item["message"],
            ))

        return config

    def filter(self, query: str, answer: str) -> tuple[str, list[str]]:
        """Apply guardrail rules to the generated answer.

        Args:
            query: The user's original question.
            answer: The generated answer from LLM.

        Returns:
            (filtered_answer, list_of_applied_rules)
        """
        applied: list[str] = []

        # Check forbidden patterns — these replace the entire answer
        for rule in self._config.forbidden_patterns:
            if rule.pattern.search(answer) or rule.pattern.search(query):
                if rule.action == "fallback":
                    return rule.message, [f"fallback:{rule.pattern.pattern}"]
                elif rule.action == "add_disclaimer":
                    applied.append(f"disclaimer:{rule.pattern.pattern}")
                    if rule.message not in answer:
                        answer = f"{answer}\n\n{rule.message}"

        # Check auto disclaimer triggers — append disclaimer
        for rule in self._config.auto_disclaimer_triggers:
            if rule.pattern.search(answer) or rule.pattern.search(query):
                applied.append(f"auto_disclaimer:{rule.pattern.pattern}")
                if rule.message not in answer:
                    answer = f"{answer}\n\n{rule.message}"

        return answer, applied
