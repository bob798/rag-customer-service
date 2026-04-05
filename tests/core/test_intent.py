"""Tests for IntentClassifier."""
import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.rag.intent import IntentClassifier


def make_llm(response: str) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


def make_response(intent: str, confidence: float = 0.9, clarification: str = None) -> str:
    data = {"intent": intent, "confidence": confidence, "clarification_question": clarification}
    return json.dumps(data, ensure_ascii=False)


@pytest.mark.asyncio
async def test_in_scope_classification():
    llm = make_llm(make_response("in_scope", 0.95))
    classifier = IntentClassifier(llm)
    result = await classifier.classify("我的订单什么时候发货？")
    assert result["intent"] == "in_scope"
    assert result["confidence"] == pytest.approx(0.95)
    assert result["clarification_question"] is None


@pytest.mark.asyncio
async def test_out_of_scope_classification():
    llm = make_llm(make_response("out_of_scope", 0.98))
    classifier = IntentClassifier(llm)
    result = await classifier.classify("今天北京天气如何？")
    assert result["intent"] == "out_of_scope"
    assert result["clarification_question"] is None


@pytest.mark.asyncio
async def test_ambiguous_returns_clarification_question():
    llm = make_llm(make_response("ambiguous", 0.6, "请问您是想了解哪类问题？"))
    classifier = IntentClassifier(llm)
    result = await classifier.classify("帮我查一下")
    assert result["intent"] == "ambiguous"
    assert result["clarification_question"] == "请问您是想了解哪类问题？"


@pytest.mark.asyncio
async def test_ambiguous_default_clarification_when_none():
    """ambiguous without clarification_question gets a default."""
    data = {"intent": "ambiguous", "confidence": 0.6, "clarification_question": None}
    llm = make_llm(json.dumps(data))
    classifier = IntentClassifier(llm)
    result = await classifier.classify("帮我查")
    assert result["intent"] == "ambiguous"
    assert result["clarification_question"] is not None
    assert len(result["clarification_question"]) > 0


@pytest.mark.asyncio
async def test_invalid_json_falls_back_to_in_scope():
    llm = make_llm("这不是JSON格式")
    classifier = IntentClassifier(llm, max_retries=2)
    result = await classifier.classify("问题")
    assert result["intent"] == "in_scope"
    assert result["confidence"] == pytest.approx(0.5)


@pytest.mark.asyncio
async def test_llm_exception_falls_back_to_in_scope():
    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM error"))
    classifier = IntentClassifier(llm, max_retries=2)
    result = await classifier.classify("问题")
    assert result["intent"] == "in_scope"


@pytest.mark.asyncio
async def test_confidence_clamped():
    llm = make_llm(make_response("in_scope", 1.5))  # over 1.0
    classifier = IntentClassifier(llm)
    result = await classifier.classify("退款问题")
    assert result["confidence"] <= 1.0


@pytest.mark.asyncio
async def test_markdown_fenced_json_parsed():
    raw = '```json\n{"intent": "in_scope", "confidence": 0.9, "clarification_question": null}\n```'
    llm = make_llm(raw)
    classifier = IntentClassifier(llm)
    result = await classifier.classify("退款")
    assert result["intent"] == "in_scope"


@pytest.mark.asyncio
async def test_unknown_intent_defaults_to_in_scope():
    llm = make_llm(make_response("weird_intent", 0.9))
    classifier = IntentClassifier(llm)
    result = await classifier.classify("问题")
    assert result["intent"] == "in_scope"
