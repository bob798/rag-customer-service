"""Tests for sessions, config, and auth enforcement."""
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_sessions_requires_admin():
    from api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/sessions")
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_sessions_returns_list(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/sessions", headers={"x-api-key": "test-admin-key"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_session_messages_after_chat(mock_pipeline):
    """After a /chat call, session messages are retrievable via /sessions/{id}/messages."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    session_id = "s-msg-test"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post(
            "/chat",
            json={"question": "退款多久", "session_id": session_id, "stream": False},
            headers={"x-widget-token": "test-widget-token"},
        )
        resp = await client.get(
            f"/sessions/{session_id}/messages",
            headers={"x-api-key": "test-admin-key"},
        )
    assert resp.status_code == 200
    msgs = resp.json()
    assert len(msgs) >= 1
    assert msgs[0]["question"] == "退款多久"


@pytest.mark.asyncio
async def test_config_get_returns_defaults(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/config", headers={"x-api-key": "test-admin-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, dict)
    assert "llm_model" in data


@pytest.mark.asyncio
async def test_config_update(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.put(
            "/config",
            json={"updates": {"bot_name": "测试客服"}},
            headers={"x-api-key": "test-admin-key"},
        )
    assert resp.status_code == 200
    assert "bot_name" in resp.json()["updated"]
