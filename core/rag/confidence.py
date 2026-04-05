import jieba

from core.interfaces.confidence import BaseConfidenceEvaluator


class SignalFusionConfidenceEvaluator(BaseConfidenceEvaluator):
    """Three-signal confidence fusion.

    confidence = 0.6 * retrieval_score + 0.3 * coverage_score + 0.1 * score_gap

    Tiers:
      >= 0.75 → "high"
      >= 0.50 → "medium"
      <  0.50 → "low"
    """

    def evaluate(
        self,
        query: str,
        candidates: list[dict],
        reranked: list[dict],
    ) -> tuple[float, str]:
        if not reranked:
            return 0.0, "low"

        retrieval_score = float(reranked[0].get("rerank_score", 0.0))
        retrieval_score = max(0.0, min(1.0, retrieval_score))

        coverage_score = self._coverage(query, reranked[0].get("content", ""))

        if len(reranked) >= 2:
            score_gap = float(reranked[0].get("rerank_score", 0.0)) - float(
                reranked[1].get("rerank_score", 0.0)
            )
            score_gap = max(0.0, min(1.0, score_gap))
        else:
            score_gap = 0.0

        confidence = 0.6 * retrieval_score + 0.3 * coverage_score + 0.1 * score_gap
        confidence = max(0.0, min(1.0, confidence))

        tier = self._tier(confidence)
        return confidence, tier

    def _coverage(self, query: str, content: str) -> float:
        """Fraction of query tokens that appear in content."""
        query_tokens = set(jieba.cut(query))
        # Filter single whitespace/punctuation tokens
        query_tokens = {t for t in query_tokens if t.strip() and t not in "，。？！、；：""''（）【】"}
        if not query_tokens:
            return 0.0
        content_tokens = set(jieba.cut(content))
        matched = query_tokens & content_tokens
        return len(matched) / len(query_tokens)

    def _tier(self, confidence: float) -> str:
        if confidence >= 0.75:
            return "high"
        if confidence >= 0.50:
            return "medium"
        return "low"
