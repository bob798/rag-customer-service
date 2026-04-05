"""Tests for SignalFusionConfidenceEvaluator."""
import pytest

from core.rag.confidence import SignalFusionConfidenceEvaluator


def make_reranked(rerank_score: float, content: str = "退款流程说明") -> dict:
    return {
        "chunk_id": "c1",
        "doc_id": "doc1",
        "content": content,
        "score": rerank_score,
        "rerank_score": rerank_score,
        "metadata": {},
    }


@pytest.fixture
def evaluator():
    return SignalFusionConfidenceEvaluator()


def test_empty_reranked_returns_low(evaluator):
    confidence, tier = evaluator.evaluate("退款", [], [])
    assert confidence == 0.0
    assert tier == "low"


def test_high_confidence(evaluator):
    # retrieval=1.0, coverage high (query token in content), gap=0.5
    top = make_reranked(1.0, "退款申请流程如何操作")
    second = make_reranked(0.5, "other content")
    confidence, tier = evaluator.evaluate("退款流程", [], [top, second])
    assert tier == "high"
    assert confidence >= 0.75


def test_low_confidence(evaluator):
    # retrieval=0.1, no coverage, no gap
    top = make_reranked(0.1, "产品颜色规格说明")
    confidence, tier = evaluator.evaluate("退款流程", [], [top])
    assert tier == "low"
    assert confidence < 0.50


def test_medium_confidence(evaluator):
    # retrieval=0.6 → weighted 0.36; coverage depends on content
    top = make_reranked(0.6, "退款说明文档")
    confidence, tier = evaluator.evaluate("退款", [], [top])
    assert tier in ("medium", "high")
    assert confidence >= 0.50


def test_score_gap_zero_when_single_result(evaluator):
    top = make_reranked(0.8, "退款申请退款退款")
    confidence, tier = evaluator.evaluate("退款", [], [top])
    # gap=0, coverage high, retrieval=0.8 → 0.6*0.8 + 0.3*high + 0.1*0 ≥ 0.75
    assert tier == "high"


def test_confidence_clamped_to_unit_interval(evaluator):
    top = make_reranked(1.0, "退款退款退款")
    second = make_reranked(0.0, "other")
    confidence, _ = evaluator.evaluate("退款", [], [top, second])
    assert 0.0 <= confidence <= 1.0


def test_tier_boundary_high(evaluator):
    evaluator_obj = SignalFusionConfidenceEvaluator()
    # Force known values: retrieval=1.0, coverage=1.0, gap=1.0 → confidence=1.0
    top = make_reranked(1.0, "退款流程申请如何")
    second = make_reranked(0.0, "other")
    _, tier = evaluator_obj.evaluate("退款流程", [], [top, second])
    assert tier == "high"


def test_candidates_not_required(evaluator):
    """candidates param is accepted but not used in computation."""
    top = make_reranked(0.8, "退款申请流程退款")
    confidence, tier = evaluator.evaluate("退款", [top, top], [top])
    assert tier in ("high", "medium")
