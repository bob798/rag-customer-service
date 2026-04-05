"""Factory for assembling RAGPipeline from configuration."""
from core.knowledge.bm25_store import Bm25Store
from core.knowledge.embedder import GteQwen2Embedder
from core.knowledge.vector_store import ChromaVectorStore
from core.llm.factory import LLMFactory
from core.rag.confidence import SignalFusionConfidenceEvaluator
from core.rag.fallback_handler import TellUserFallbackHandler
from core.rag.generator import LLMGenerator
from core.rag.intent import IntentClassifier
from core.rag.pipeline import RAGPipeline
from core.rag.query_rewriter import QueryRewriter
from core.rag.reranker import NoopReranker
from core.rag.retriever import HybridRetriever
from core.rag.tracer import StructuredLogTracer


def create_default_pipeline(
    llm_model: str = "openai/gpt-4o-mini",
    llm_fallback: str | None = None,
    chroma_path: str = "./data/chroma",
    collection_name: str = "knowledge",
    use_noop_reranker: bool = False,
    reranker_model: str = "BAAI/bge-reranker-v2-m3",
) -> RAGPipeline:
    """Assemble a production RAGPipeline from configuration.

    Args:
        llm_model: LiteLLM model string for intent/rewrite/generate calls.
        llm_fallback: Optional fallback model string.
        chroma_path: Path to ChromaDB persistent storage.
        collection_name: ChromaDB collection name.
        use_noop_reranker: Use NoopReranker instead of BGEReranker (for tests/dev).
        reranker_model: BGEReranker model name. Use "BAAI/bge-reranker-base" if you
            have it cached locally (~/.cache/huggingface/) and don't need v2-m3 yet.

    Returns:
        Fully-wired RAGPipeline ready to call .run() or .run_stream().
    """
    llm = LLMFactory(model=llm_model, fallback=llm_fallback)
    embedder = GteQwen2Embedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name=collection_name,
        persist_directory=chroma_path,
    )
    bm25_store = Bm25Store()

    retriever = HybridRetriever(vector_store=vector_store, bm25_store=bm25_store)

    if use_noop_reranker:
        reranker = NoopReranker()
    else:
        from core.rag.reranker import BGEReranker
        reranker = BGEReranker(model_name=reranker_model)

    return RAGPipeline(
        intent_classifier=IntentClassifier(llm=llm),
        query_rewriter=QueryRewriter(llm=llm),
        retriever=retriever,
        reranker=reranker,
        confidence_evaluator=SignalFusionConfidenceEvaluator(),
        fallback_handler=TellUserFallbackHandler(),
        generator=LLMGenerator(llm=llm),
        tracer=StructuredLogTracer(),
        embedder=embedder,
    )
