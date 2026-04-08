"""Tests for knowledge management API."""
import io
import pytest
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_upload_returns_doc_id(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/upload",
            files={"file": ("faq.txt", io.BytesIO(b"Q: \xe9\x80\x80\xe6\xac\xbe\nA: 3\xe5\xa4\xa9"), "text/plain")},
            headers={"x-api-key": "test-admin-key"},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "id" in data
    assert data["status"] == "indexing"


@pytest.mark.asyncio
async def test_upload_requires_admin_key(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/upload",
            files={"file": ("f.txt", io.BytesIO(b"test"), "text/plain")},
        )
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_qa_entry_stored(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/qa",
            json={"question": "如何退款", "answer": "联系客服"},
            headers={"x-api-key": "test-admin-key"},
        )
    assert resp.status_code == 200
    assert "id" in resp.json()


@pytest.mark.asyncio
async def test_list_documents_requires_admin(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/knowledge/documents")
    assert resp.status_code in (401, 422)


@pytest.mark.asyncio
async def test_list_documents_returns_list(mock_pipeline):
    from api.main import app
    app.state.pipeline = mock_pipeline
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            "/knowledge/documents",
            headers={"x-api-key": "test-admin-key"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
