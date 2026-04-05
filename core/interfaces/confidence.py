from abc import ABC, abstractmethod


class BaseConfidenceEvaluator(ABC):
    @abstractmethod
    def evaluate(
        self,
        query: str,
        candidates: list[dict],
        reranked: list[dict]
    ) -> tuple[float, str]:
        """Compute confidence score and tier.
        Returns: (confidence: float in [0.0, 1.0], tier: str in {"high", "medium", "low"})
        Tier thresholds: >= 0.75 → "high", >= 0.50 → "medium", < 0.50 → "low"
        """
        ...
