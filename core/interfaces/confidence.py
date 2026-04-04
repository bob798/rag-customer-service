from abc import ABC, abstractmethod


class BaseConfidenceEvaluator(ABC):
    @abstractmethod
    def evaluate(
        self,
        query: str,
        candidates: list[dict],
        reranked: list[dict]
    ) -> float:
        """Compute confidence score in [0.0, 1.0].
        Higher = more confident the retrieved context answers the query.
        """
        ...
