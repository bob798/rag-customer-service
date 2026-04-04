import pytest
from unittest.mock import AsyncMock

@pytest.fixture(scope="function")
def mock_llm():
    """Mock LLM that returns a fixed response."""
    mock = AsyncMock()
    mock.return_value = "mocked response"
    return mock
