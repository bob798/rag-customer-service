"""Tests for RAGPipeline orchestration."""
import pytest
from unittest.mock import AsyncMock, MagicMock

from core.rag.pipeline import RAGPipeline


# ── helpers ──────────────────────────────────────────────────────────────────

def make_chunk(chunk_id: str = "c1", content: str = "退款需3天") -> dict:
    return {
        "chunk_id": chunk_id,
        "doc_id": "doc1",
        "content": content,
        "score": 0.8,
        "rerank_score": 0.8,
        "metadata": {"source_title": "FAQ.txt"},
    }


def make_pipeline(
    intent="in_scope",
    confidence=0.85,
    tier="high",
    answer="根据资料，退款需要3天。",
    clarification=None,
) -> RAGPipeline:
    intent_classifier = MagicMock()
    intent_classifier.classify = AsyncMock(return_value={
        "intent": intent,
        "confidence": 0.9,
        "clarification_question": clarification,
    })

    query_rewriter = MagicMock()
    query_rewriter.rewrite = AsyncMock(return_value="退款流程")

    retriever = MagicMock()
    retriever.retrieve = AsyncMock(return_value=[make_chunk()])

    reranker = MagicMock()
    reranker.rerank = AsyncMock(return_value=[make_chunk()])

    confidence_evaluator = MagicMock()
    confidence_evaluator.evaluate = MagicMock(return_value=(confidence, tier))

    fallback_handler = MagicMock()
    fallback_handler.handle = AsyncMock(return_value="请联系客服。")

    generator = MagicMock()
    generator.generate = AsyncMock(return_value={
        "answer": answer,
        "sources": [{"doc_id": "doc1", "chunk_id": "c1", "title": "FAQ.txt", "content_preview": "退款"}],
    })

    embedder = MagicMock()
    embedder.embed = AsyncMock(return_value=[[0.1, 0.2, 0.3]])

    tracer = MagicMock()
    tracer.start_trace = MagicMock()
    tracer.log_step = MagicMock()
    tracer.end_trace = MagicMock()

    return RAGPipeline(
        intent_classifier=intent_classifier,
        query_rewriter=query_rewriter,
        retriever=retriever,
        reranker=reranker,
        confidence_evaluator=confidence_evaluator,
        fallback_handler=fallback_handler,
        generator=generator,
        tracer=tracer,
        embedder=embedder,
    )


# ── tests ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_in_scope_returns_answer():
    pipeline = make_pipeline(intent="in_scope", confidence=0.85, tier="high")
    result = await pipeline.run("退款多久", "session-1")
    assert result["answer"] == "根据资料，退款需要3天。"
    assert "sources" in result
    assert "confidence" in result
    assert "trace_id" in result


@pytest.mark.asyncio
async def test_out_of_scope_triggers_fallback():
    pipeline = make_pipeline(intent="out_of_scope")
    result = await pipeline.run("今天天气", "session-1")
    assert result["answer"] == "请联系客服。"
    # Generator should NOT be called
    pipeline._generator.generate.assert_not_called()


@pytest.mark.asyncio
async def test_ambiguous_returns_clarification():
    pipeline = make_pipeline(intent="ambiguous", clarification="请问您想了解哪方面？")
    result = await pipeline.run("帮我查一下", "session-1")
    assert result["answer"] == "请问您想了解哪方面？"
    pipeline._generator.generate.assert_not_called()


@pytest.mark.asyncio
async def test_low_confidence_triggers_fallback():
    pipeline = make_pipeline(intent="in_scope", confidence=0.3, tier="low")
    result = await pipeline.run("退款", "session-1")
    assert result["answer"] == "请联系客服。"
    pipeline._fallback_handler.handle.assert_called_once()
    pipeline._generator.generate.assert_not_called()


@pytest.mark.asyncio
async def test_medium_confidence_marks_uncertain():
    pipeline = make_pipeline(intent="in_scope", confidence=0.6, tier="medium")
    result = await pipeline.run("退款", "session-1")
    assert result["uncertain"] is True


@pytest.mark.asyncio
async def test_high_confidence_not_uncertain():
    pipeline = make_pipeline(intent="in_scope", confidence=0.85, tier="high")
    result = await pipeline.run("退款", "session-1")
    assert result["uncertain"] is False


@pytest.mark.asyncio
async def test_trace_id_present():
    pipeline = make_pipeline()
    result = await pipeline.run("退款", "session-1")
    assert "trace_id" in result
    assert len(result["trace_id"]) > 0


@pytest.mark.asyncio
async def test_tracer_called_in_order():
    pipeline = make_pipeline()
    await pipeline.run("退款", "session-1")
    pipeline._tracer.start_trace.assert_called_once()
    pipeline._tracer.end_trace.assert_called_once()
    assert pipeline._tracer.log_step.call_count >= 3


@pytest.mark.asyncio
async def test_embedder_called_with_rewritten_query():
    pipeline = make_pipeline()
    await pipeline.run("退款咋整", "session-1")
    pipeline._embedder.embed.assert_called_once_with(["退款流程"])


@pytest.mark.asyncio
async def test_run_stream_yields_deltas_then_done():
    pipeline = make_pipeline()

    async def fake_stream(*args, **kwargs):
        yield {"type": "delta", "content": "退款"}
        yield {"type": "delta", "content": "需要3天"}
        yield {"type": "done", "sources": [], "uncertain": False}

    pipeline._generator.generate_stream = fake_stream

    frames = []
    async for frame in pipeline.run_stream("退款", "session-1"):
        frames.append(frame)

    done_frames = [f for f in frames if f["type"] == "done"]
    assert len(done_frames) == 1
    assert "trace_id" in done_frames[0]
    assert "confidence" in done_frames[0]


@pytest.mark.asyncio
async def test_run_stream_short_circuit_on_out_of_scope():
    pipeline = make_pipeline(intent="out_of_scope")

    frames = []
    async for frame in pipeline.run_stream("天气", "session-1"):
        frames.append(frame)

    assert len(frames) == 1
    assert frames[0]["type"] == "done"
    assert frames[0]["answer"] == "请联系客服。"
