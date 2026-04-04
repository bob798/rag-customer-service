import pytest
import pytest_asyncio
from unittest.mock import AsyncMock

@pytest.fixture
def mock_llm():
    """Mock LLM that returns a fixed response."""
    mock = AsyncMock()
    mock.return_value = "mocked response"
    return mock
