import pytest
from core.interfaces import (
    BaseParser, BaseChunker, BaseEmbedder, BaseRetriever,
    BaseReranker, BaseConfidenceEvaluator, BaseFallbackHandler, BaseTracer
)

# --- Abstractness checks (all 8) ---

def test_base_parser_is_abstract():
    with pytest.raises(TypeError):
        BaseParser()

def test_base_chunker_is_abstract():
    with pytest.raises(TypeError):
        BaseChunker()

def test_base_embedder_is_abstract():
    with pytest.raises(TypeError):
        BaseEmbedder()

def test_base_retriever_is_abstract():
    with pytest.raises(TypeError):
        BaseRetriever()

def test_base_reranker_is_abstract():
    with pytest.raises(TypeError):
        BaseReranker()

def test_base_confidence_evaluator_is_abstract():
    with pytest.raises(TypeError):
        BaseConfidenceEvaluator()

def test_base_fallback_handler_is_abstract():
    with pytest.raises(TypeError):
        BaseFallbackHandler()

def test_base_tracer_is_abstract():
    with pytest.raises(TypeError):
        BaseTracer()

# --- Concrete subclass works ---

def test_concrete_parser_works():
    class ConcreteParser(BaseParser):
        def can_handle(self, file_type: str, content_hint: str = "") -> bool:
            return True
        def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
            return []
    p = ConcreteParser()
    assert p.can_handle("pdf") is True

async def test_concrete_embedder_works():
    class ConcreteEmbedder(BaseEmbedder):
        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[0.1] * 4 for _ in texts]
    e = ConcreteEmbedder()
    result = await e.embed(["hello"])
    assert len(result) == 1

def test_concrete_confidence_evaluator_returns_tuple():
    class ConcreteEval(BaseConfidenceEvaluator):
        def evaluate(self, query: str, candidates: list[dict], reranked: list[dict]) -> tuple[float, str]:
            return (0.9, "high")
    ev = ConcreteEval()
    score, tier = ev.evaluate("q", [], [])
    assert score == 0.9
    assert tier == "high"

def test_concrete_tracer_works():
    class ConcreteTracer(BaseTracer):
        def start_trace(self, trace_id: str) -> None: pass
        def log_step(self, step: str, data: dict) -> None: pass
        def end_trace(self) -> None: pass
    t = ConcreteTracer()
    t.start_trace("t-123")
    t.log_step("retrieval", {"k": 5})
    t.end_trace()
