"""Tests for POST /chat endpoint."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_chat_non_stream_returns_answer(mock_pipeline):
    """Non-streaming chat returns answer, confidence, message_id."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/chat",
            json={"question": "退款多久", "session_id": "s-test-1", "stream": False},
            headers={"x-widget-token": "test-widget-token"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "confidence" in data
    assert "message_id" in data
    assert data["session_id"] == "s-test-1"


@pytest.mark.asyncio
async def test_chat_stream_returns_sse(mock_pipeline):
    """Streaming chat returns SSE with done frame containing confidence."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with client.stream(
            "POST", "/chat",
            json={"question": "退款多久", "session_id": "s-test-2", "stream": True},
            headers={"x-widget-token": "test-widget-token"},
        ) as resp:
            assert resp.status_code == 200
            chunks = [c async for c in resp.aiter_text()]
    full = "".join(chunks)
    assert '"type": "done"' in full
    assert '"confidence"' in full


@pytest.mark.asyncio
async def test_chat_requires_widget_token():
    """No token → 422."""
    from api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat", json={"question": "test", "session_id": "s1"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_saves_message_to_db(mock_pipeline):
    """After chat, message is persisted to DB and retrievable."""
    from api.main import app
    from db.session import AsyncSessionLocal
    from db.models import Message
    from sqlalchemy import select

    app.state.pipeline = mock_pipeline
    session_id = "s-test-persist"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/chat",
            json={"question": "退款多久", "session_id": session_id, "stream": False},
            headers={"x-widget-token": "test-widget-token"},
        )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Message).where(Message.session_id == session_id)
        )
        msgs = result.scalars().all()
    assert len(msgs) >= 1
    assert msgs[0].question == "退款多久"
