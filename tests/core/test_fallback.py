"""Tests for TellUserFallbackHandler."""
import pytest

from core.rag.fallback_handler import TellUserFallbackHandler


@pytest.fixture
def handler():
    return TellUserFallbackHandler()


@pytest.mark.asyncio
async def test_low_confidence_message(handler):
    msg = await handler.handle("退款问题", "session-1", "low_confidence")
    assert "客服" in msg or "把握" in msg


@pytest.mark.asyncio
async def test_out_of_scope_message(handler):
    msg = await handler.handle("今天天气如何", "session-1", "out_of_scope")
    assert "范围" in msg or "客服" in msg


@pytest.mark.asyncio
async def test_error_message(handler):
    msg = await handler.handle("问题", "session-1", "error")
    assert "系统" in msg or "重试" in msg


@pytest.mark.asyncio
async def test_unknown_reason_returns_default(handler):
    msg = await handler.handle("问题", "session-1", "unknown_reason")
    assert isinstance(msg, str)
    assert len(msg) > 0


@pytest.mark.asyncio
async def test_returns_string(handler):
    result = await handler.handle("any question", "s1", "low_confidence")
    assert isinstance(result, str)
