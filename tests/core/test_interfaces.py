import pytest
from core.interfaces import (
    BaseParser, BaseChunker, BaseEmbedder, BaseRetriever,
    BaseReranker, BaseConfidenceEvaluator, BaseFallbackHandler, BaseTracer
)


def test_all_interfaces_importable():
    """All 8 interfaces are importable from core.interfaces"""
    interfaces = [BaseParser, BaseChunker, BaseEmbedder, BaseRetriever,
                  BaseReranker, BaseConfidenceEvaluator, BaseFallbackHandler, BaseTracer]
    assert len(interfaces) == 8


def test_interfaces_are_abstract():
    """Cannot instantiate abstract classes directly"""
    with pytest.raises(TypeError):
        BaseParser()


def test_concrete_subclass_works():
    """A subclass that implements all methods can be instantiated"""
    class ConcreteParser(BaseParser):
        def can_handle(self, file_type: str, content_hint: str = "") -> bool:
            return True
        def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
            return []

    parser = ConcreteParser()
    assert parser.can_handle("pdf") is True
    assert parser.parse("f.pdf", "doc1", {}) == []
