import pytest
from unittest.mock import AsyncMock, patch

from core.llm.factory import LLMFactory


@pytest.mark.asyncio
async def test_factory_returns_response():
    factory = LLMFactory(model="deepseek/deepseek-chat")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value.choices = [
            type("C", (), {"message": type("M", (), {"content": "hello"})()})()
        ]
        result = await factory.complete([{"role": "user", "content": "hi"}])
    assert result == "hello"


@pytest.mark.asyncio
async def test_factory_fallback_on_error():
    factory = LLMFactory(
        model="claude-3-5-sonnet-20241022", fallback="deepseek/deepseek-chat"
    )
    fallback_response = type(
        "R",
        (),
        {
            "choices": [
                type("C", (), {"message": type("M", (), {"content": "fallback"})()})()
            ]
        },
    )()
    with patch(
        "litellm.acompletion",
        side_effect=[Exception("API error"), fallback_response],
    ):
        result = await factory.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback"


@pytest.mark.asyncio
async def test_factory_raises_without_fallback():
    factory = LLMFactory(model="claude-3-5-sonnet-20241022")
    with patch("litellm.acompletion", side_effect=Exception("API error")):
        with pytest.raises(Exception, match="API error"):
            await factory.complete([{"role": "user", "content": "hi"}])


@pytest.mark.asyncio
async def test_factory_complete_stream_calls_litellm_with_stream_true():
    factory = LLMFactory(model="deepseek/deepseek-chat")
    mock_stream = AsyncMock()
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_stream
        result = await factory.complete_stream([{"role": "user", "content": "hi"}])
        mock_acompletion.assert_called_once_with(
            model="deepseek/deepseek-chat",
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
        )
    assert result is mock_stream


@pytest.mark.asyncio
async def test_factory_complete_stream_passes_kwargs():
    factory = LLMFactory(model="deepseek/deepseek-chat")
    mock_stream = AsyncMock()
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock_acompletion:
        mock_acompletion.return_value = mock_stream
        await factory.complete_stream(
            [{"role": "user", "content": "hi"}], temperature=0.5
        )
        mock_acompletion.assert_called_once_with(
            model="deepseek/deepseek-chat",
            messages=[{"role": "user", "content": "hi"}],
            stream=True,
            temperature=0.5,
        )


@pytest.mark.asyncio
async def test_factory_complete_stream_false_returns_content():
    """stream=False (default) returns string content, not raw response."""
    factory = LLMFactory(model="deepseek/deepseek-chat")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value.choices = [
            type("C", (), {"message": type("M", (), {"content": "world"})()})()
        ]
        result = await factory.complete(
            [{"role": "user", "content": "hi"}], stream=False
        )
    assert result == "world"


@pytest.mark.asyncio
async def test_factory_complete_stream_true_returns_raw_response():
    """stream=True returns the raw response object, not extracted content."""
    factory = LLMFactory(model="deepseek/deepseek-chat")
    raw_response = AsyncMock()
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value = raw_response
        result = await factory.complete(
            [{"role": "user", "content": "hi"}], stream=True
        )
    assert result is raw_response
