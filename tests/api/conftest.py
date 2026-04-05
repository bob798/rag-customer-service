"""Fixtures for API tests — isolated from tests/conftest.py."""
import os
import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock

# Set test env vars before any app imports
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["WIDGET_TOKEN_SECRET"] = "test-widget-token"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_api.db"
os.environ["USE_NOOP_RERANKER"] = "true"


@pytest_asyncio.fixture(autouse=True)
async def setup_test_db():
    """Ensure DB tables exist for every API test."""
    from db.session import init_db
    await init_db()


@pytest.fixture
def mock_pipeline():
    p = MagicMock()
    p.run = AsyncMock(return_value={
        "answer": "退款需要3个工作日",
        "sources": [{"chunk_id": "c1", "doc_id": "d1", "title": "FAQ.txt", "content_preview": "退款3天..."}],
        "confidence": 0.88,
        "uncertain": False,
        "fallback_triggered": False,
        "trace_id": "t-001",
    })
    p.retriever = MagicMock()
    p.retriever.vector_store = MagicMock()
    p.retriever.bm25_store = MagicMock()
    return p
