"""Input sanitization: detect and block prompt injection attempts."""
from __future__ import annotations

import re


class InputSanitizer:
    """Detects prompt injection patterns in user input.

    Uses regex pattern matching for known injection techniques.
    Returns (is_safe, matched_description) tuple.
    """

    INJECTION_PATTERNS: list[tuple[re.Pattern, str]] = [
        # English patterns
        (re.compile(r"ignore\s+(all\s+)?previous\s+instructions", re.IGNORECASE),
         "ignore previous instructions"),
        (re.compile(r"you\s+are\s+now\s+", re.IGNORECASE),
         "role override attempt"),
        (re.compile(r"system\s*:\s*", re.IGNORECASE),
         "system prompt injection"),
        (re.compile(r"<\|.*?\|>"),
         "special token injection"),
        (re.compile(r"forget\s+(everything|all)", re.IGNORECASE),
         "memory wipe attempt"),
        (re.compile(r"(?:do\s+not|don'?t)\s+follow\s+(?:the\s+)?(?:above|previous)", re.IGNORECASE),
         "instruction override"),
        (re.compile(r"pretend\s+(?:you\s+are|to\s+be)", re.IGNORECASE),
         "role pretend attempt"),
        (re.compile(r"output\s+(?:the|your)\s+(?:system|initial)\s+prompt", re.IGNORECASE),
         "prompt extraction attempt"),
        # Chinese patterns
        (re.compile(r"忽略.{0,5}(?:之前|上面|以上).{0,5}(?:指令|说明|要求|规则)"),
         "忽略指令"),
        (re.compile(r"你现在是"),
         "角色覆盖"),
        (re.compile(r"不要遵守"),
         "规则覆盖"),
        (re.compile(r"输出.{0,5}(?:系统|初始).{0,5}(?:提示|指令|prompt)"),
         "提示词提取"),
    ]

    def check(self, text: str) -> tuple[bool, str | None]:
        """Check input text for injection patterns.

        Returns:
            (True, None) if safe.
            (False, description) if injection detected.
        """
        for pattern, description in self.INJECTION_PATTERNS:
            if pattern.search(text):
                return False, description
        return True, None
