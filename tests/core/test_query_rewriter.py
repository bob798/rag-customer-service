"""Tests for QueryRewriter."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.rag.query_rewriter import QueryRewriter


def make_llm(response: str) -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=response)
    return llm


@pytest.mark.asyncio
async def test_rewrites_colloquial_question():
    llm = make_llm("如何申请退款流程")
    rewriter = QueryRewriter(llm)
    result = await rewriter.rewrite("退款咋整")
    assert result == "如何申请退款流程"


@pytest.mark.asyncio
async def test_returns_original_on_llm_failure():
    llm = MagicMock()
    llm.complete = AsyncMock(side_effect=RuntimeError("LLM unavailable"))
    rewriter = QueryRewriter(llm)
    result = await rewriter.rewrite("退款问题")
    assert result == "退款问题"


@pytest.mark.asyncio
async def test_returns_original_when_response_empty():
    llm = make_llm("   ")  # whitespace only
    rewriter = QueryRewriter(llm)
    result = await rewriter.rewrite("退款问题")
    assert result == "退款问题"


@pytest.mark.asyncio
async def test_strips_whitespace_from_response():
    llm = make_llm("  如何申请退款  ")
    rewriter = QueryRewriter(llm)
    result = await rewriter.rewrite("退款")
    assert result == "如何申请退款"


@pytest.mark.asyncio
async def test_passes_question_to_llm():
    llm = make_llm("如何查询订单状态")
    rewriter = QueryRewriter(llm)
    await rewriter.rewrite("订单到哪了")
    call_messages = llm.complete.call_args[0][0]
    user_msg = next(m for m in call_messages if m["role"] == "user")
    assert user_msg["content"] == "订单到哪了"
