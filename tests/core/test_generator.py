"""Tests for LLMGenerator."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.rag.generator import LLMGenerator


def make_chunk(chunk_id: str, content: str, source_title: str = "FAQ.txt") -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc1",
        "content": content,
        "score": 0.9,
        "rerank_score": 0.9,
        "metadata": {"source_title": source_title},
    }


def make_llm(answer: str = "根据资料，退款需要3-5个工作日。") -> MagicMock:
    llm = MagicMock()
    llm.complete = AsyncMock(return_value=answer)
    return llm


@pytest.mark.asyncio
async def test_generate_returns_answer_and_sources():
    llm = make_llm("退款处理中。")
    gen = LLMGenerator(llm)
    chunks = [make_chunk("c1", "退款需要3-5天")]
    result = await gen.generate("退款多久", chunks, "high")
    assert result["answer"] == "退款处理中。"
    assert len(result["sources"]) == 1


@pytest.mark.asyncio
async def test_medium_confidence_prefixes_answer():
    llm = make_llm("退款需3天。")
    gen = LLMGenerator(llm)
    chunks = [make_chunk("c1", "退款信息")]
    result = await gen.generate("退款", chunks, "medium")
    assert result["answer"].startswith("以下回答仅供参考：")


@pytest.mark.asyncio
async def test_high_confidence_no_prefix():
    llm = make_llm("退款需3天。")
    gen = LLMGenerator(llm)
    chunks = [make_chunk("c1", "退款信息")]
    result = await gen.generate("退款", chunks, "high")
    assert not result["answer"].startswith("以下回答仅供参考：")


@pytest.mark.asyncio
async def test_sources_contain_title():
    llm = make_llm("答案")
    gen = LLMGenerator(llm)
    chunks = [make_chunk("c1", "内容", source_title="帮助中心.txt")]
    result = await gen.generate("问题", chunks, "high")
    assert result["sources"][0]["title"] == "帮助中心.txt"


@pytest.mark.asyncio
async def test_sources_contain_content_preview():
    llm = make_llm("答案")
    gen = LLMGenerator(llm)
    content = "这是一段较长的退款说明内容" * 10
    chunks = [make_chunk("c1", content)]
    result = await gen.generate("退款", chunks, "high")
    assert len(result["sources"][0]["content_preview"]) <= 100


@pytest.mark.asyncio
async def test_session_history_included_in_messages():
    llm = make_llm("答案")
    gen = LLMGenerator(llm)
    history = [
        {"role": "user", "content": "之前问题"},
        {"role": "assistant", "content": "之前回答"},
    ]
    await gen.generate("当前问题", [make_chunk("c1", "内容")], "high", history)
    call_messages = llm.complete.call_args[0][0]
    roles = [m["role"] for m in call_messages]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_generate_stream_yields_deltas():
    llm = MagicMock()

    # Build mock stream chunks
    def make_stream_chunk(text):
        chunk = MagicMock()
        chunk.choices[0].delta.content = text
        return chunk

    async def mock_stream():
        for token in ["退", "款", "需", "3", "天"]:
            yield make_stream_chunk(token)

    llm.complete_stream = AsyncMock(return_value=mock_stream())
    gen = LLMGenerator(llm)

    frames = []
    async for frame in gen.generate_stream("退款", [make_chunk("c1", "内容")], "high"):
        frames.append(frame)

    delta_frames = [f for f in frames if f["type"] == "delta"]
    done_frames = [f for f in frames if f["type"] == "done"]

    assert len(delta_frames) == 5
    assert len(done_frames) == 1
    assert done_frames[0]["uncertain"] is False


@pytest.mark.asyncio
async def test_generate_stream_medium_adds_prefix():
    llm = MagicMock()

    async def mock_stream():
        chunk = MagicMock()
        chunk.choices[0].delta.content = "退款需3天"
        yield chunk

    llm.complete_stream = AsyncMock(return_value=mock_stream())
    gen = LLMGenerator(llm)

    frames = []
    async for frame in gen.generate_stream("退款", [make_chunk("c1", "内容")], "medium"):
        frames.append(frame)

    # First delta should be the prefix
    first_content = frames[0]["content"]
    assert "仅供参考" in first_content
    assert frames[-1]["uncertain"] is True
