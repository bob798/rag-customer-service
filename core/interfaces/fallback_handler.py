from abc import ABC, abstractmethod


class BaseFallbackHandler(ABC):
    @abstractmethod
    async def handle(self, question: str, session_id: str, reason: str) -> str:
        """Handle a fallback case (low confidence or out-of-scope).
        Returns the fallback response string.
        reason: "low_confidence" | "out_of_scope" | "error"
        """
        ...
