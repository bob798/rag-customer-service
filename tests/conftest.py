import sys
import types
from unittest.mock import AsyncMock

import pytest

# Provide a minimal litellm stub so tests can run without litellm installed.
# Individual test modules that need to mock litellm.acompletion use
# unittest.mock.patch, which replaces the attribute on this stub module.
if "litellm" not in sys.modules:
    _litellm_stub = types.ModuleType("litellm")
    _litellm_stub.acompletion = AsyncMock()
    sys.modules["litellm"] = _litellm_stub


@pytest.fixture(scope="function")
def mock_llm():
    """Mock LLM that returns a fixed response."""
    mock = AsyncMock()
    mock.return_value = "mocked response"
    return mock
