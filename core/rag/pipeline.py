"""RAG pipeline orchestrator."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import AsyncGenerator
from uuid import uuid4

from core.interfaces.confidence import BaseConfidenceEvaluator
from core.interfaces.embedder import BaseEmbedder
from core.interfaces.fallback_handler import BaseFallbackHandler
from core.interfaces.reranker import BaseReranker
from core.interfaces.retriever import BaseRetriever
from core.interfaces.tracer import BaseTracer
from core.rag.generator import LLMGenerator
from core.rag.intent import IntentClassifier
from core.rag.query_rewriter import QueryRewriter

logger = logging.getLogger(__name__)


@dataclass
class PreGenContext:
    """Intermediate context shared by run() and run_stream()."""
    question: str
    session_id: str
    session_history: list[dict]
    reranked: list[dict]
    confidence: float
    tier: str
    trace_id: str


class RAGPipeline:
    """End-to-end RAG pipeline.

    Dependency-injection: all components are passed in via __init__.
    session_history is supplied by the caller (API layer), not queried internally.
    """

    def __init__(
        self,
        intent_classifier: IntentClassifier,
        query_rewriter: QueryRewriter,
        retriever: BaseRetriever,
        reranker: BaseReranker,
        confidence_evaluator: BaseConfidenceEvaluator,
        fallback_handler: BaseFallbackHandler,
        generator: LLMGenerator,
        tracer: BaseTracer,
        embedder: BaseEmbedder,
    ) -> None:
        self._intent_classifier = intent_classifier
        self._query_rewriter = query_rewriter
        self._retriever = retriever
        self._reranker = reranker
        self._confidence_evaluator = confidence_evaluator
        self._fallback_handler = fallback_handler
        self._generator = generator
        self._tracer = tracer
        self._embedder = embedder

    @property
    def retriever(self) -> BaseRetriever:
        return self._retriever

    async def _run_pre_generation(
        self,
        question: str,
        session_id: str,
        session_history: list[dict],
    ) -> PreGenContext | dict:
        """Steps 1–5: intent → rewrite → embed → retrieve → rerank → confidence.

        Returns PreGenContext on success, or a fallback dict if short-circuit needed.
        """
        trace_id = str(uuid4())
        self._tracer.start_trace(trace_id)

        # Step 1: intent classification
        intent_result = await self._intent_classifier.classify(question)
        self._tracer.log_step("intent", {"result": intent_result["intent"]})

        if intent_result["intent"] == "out_of_scope":
            self._tracer.end_trace()
            fallback_msg = await self._fallback_handler.handle(
                question, session_id, "out_of_scope"
            )
            return {
                "answer": fallback_msg,
                "sources": [],
                "confidence": 0.0,
                "uncertain": False,
                "trace_id": trace_id,
            }

        if intent_result["intent"] == "ambiguous":
            self._tracer.end_trace()
            return {
                "answer": intent_result["clarification_question"],
                "sources": [],
                "confidence": 0.0,
                "uncertain": False,
                "trace_id": trace_id,
            }

        # Step 2: query rewrite
        rewritten = await self._query_rewriter.rewrite(question)
        self._tracer.log_step("rewrite", {"rewritten": rewritten})

        # Step 3: embed + retrieve
        vecs = await self._embedder.embed([rewritten])
        query_vec = vecs[0]
        candidates = await self._retriever.retrieve(query_vec, rewritten, top_k=20)
        self._tracer.log_step("retrieve", {"count": len(candidates)})

        # Step 4: rerank
        reranked = await self._reranker.rerank(rewritten, candidates, top_k=5)
        self._tracer.log_step("rerank", {"count": len(reranked)})

        # Step 5: confidence evaluation
        confidence, tier = self._confidence_evaluator.evaluate(rewritten, candidates, reranked)
        self._tracer.log_step("confidence", {"score": confidence, "tier": tier})

        if tier == "low":
            self._tracer.end_trace()
            fallback_msg = await self._fallback_handler.handle(
                question, session_id, "low_confidence"
            )
            return {
                "answer": fallback_msg,
                "sources": [],
                "confidence": confidence,
                "uncertain": True,
                "trace_id": trace_id,
            }

        return PreGenContext(
            question=question,
            session_id=session_id,
            session_history=session_history,
            reranked=reranked,
            confidence=confidence,
            tier=tier,
            trace_id=trace_id,
        )

    async def run(
        self,
        question: str,
        session_id: str,
        session_history: list[dict] = [],
    ) -> dict:
        """Run pipeline and return complete answer dict."""
        ctx = await self._run_pre_generation(question, session_id, session_history)

        # Short-circuit (fallback dict)
        if isinstance(ctx, dict):
            return ctx

        # Step 6: generate
        result = await self._generator.generate(
            ctx.question, ctx.reranked, ctx.tier, ctx.session_history
        )
        self._tracer.end_trace()

        return {
            "answer": result["answer"],
            "sources": result["sources"],
            "confidence": ctx.confidence,
            "uncertain": ctx.tier == "medium",
            "trace_id": ctx.trace_id,
        }

    async def run_stream(
        self,
        question: str,
        session_id: str,
        session_history: list[dict] = [],
    ) -> AsyncGenerator[dict, None]:
        """Run pipeline and stream answer tokens."""
        ctx = await self._run_pre_generation(question, session_id, session_history)

        if isinstance(ctx, dict):
            # Emit short-circuit as a single done frame
            yield {"type": "done", **ctx}
            return

        # Step 6: stream generate
        async for frame in self._generator.generate_stream(
            ctx.question, ctx.reranked, ctx.tier, ctx.session_history
        ):
            if frame["type"] == "done":
                frame["confidence"] = ctx.confidence
                frame["trace_id"] = ctx.trace_id
            yield frame

        self._tracer.end_trace()
