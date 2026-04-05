"""Security tests: auth enforcement and token isolation."""
import os
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_chat_rejects_no_token():
    """Missing widget token header → 422 (FastAPI validation error)."""
    from api.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat", json={"question": "test", "session_id": "s1"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_chat_rejects_wrong_token(mock_pipeline):
    """Wrong widget token → 401."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/chat",
            json={"question": "test", "session_id": "s1"},
            headers={"x-widget-token": "wrong-token"},
        )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_widget_token_cannot_access_admin_sessions(mock_pipeline):
    """Widget Token must NOT be able to call Admin-only /sessions endpoint."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/sessions",
            headers={"x-widget-token": "test-widget-token"},
        )
    # Admin endpoint requires x-api-key header, widget token header is wrong key name
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_admin_endpoints_reject_widget_token(mock_pipeline):
    """Admin endpoints must reject widget tokens even with correct value."""
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Try to access knowledge upload with widget token header instead of api key
        resp = await client.get(
            "/knowledge/documents",
            headers={"x-widget-token": "test-widget-token"},
        )
    assert resp.status_code in (401, 422)
