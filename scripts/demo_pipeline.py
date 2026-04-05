"""实际场景验证脚本 - 用真实 LLM + 内存 BM25 + 确定性向量跑完整 RAG 链路。

使用方式：
  # 设置 LLM API Key（任选其一）
  export ANTHROPIC_API_KEY=sk-ant-...
  # 或
  export OPENAI_API_KEY=sk-...
  # 或
  export DEEPSEEK_API_KEY=...

  # 运行（不需要下载 embedding 模型，使用 DeterministicEmbedder）
  .venv/bin/python scripts/demo_pipeline.py

功能：
  1. 内存中构建一个 5 条 FAQ 知识库
  2. 提几个问题，走完整 RAG 管道
  3. 打印每步结果（检索命中、置信度、最终回答、sources）
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from core.interfaces.confidence import BaseConfidenceEvaluator
from core.interfaces.embedder import BaseEmbedder
from core.knowledge.bm25_store import Bm25Store
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

logging.basicConfig(level=logging.ERROR)  # 只显示 ERROR 及以上
# 静默 chromadb/posthog/jieba 的 DEBUG/WARNING 噪音
for noisy in ("chromadb", "jieba", "httpx", "httpcore", "litellm"):
    logging.getLogger(noisy).setLevel(logging.CRITICAL)
logger = logging.getLogger("demo")


# ---------------------------------------------------------------------------
# 关键词 Embedder：基于词袋的稀疏向量，有真实语义（无需模型）
# ---------------------------------------------------------------------------

# 演示词汇表，覆盖 FAQ 内容和测试问题
_VOCAB = [
    "退款", "申请", "流程", "订单", "审核", "工作日", "原路",
    "发货", "时间", "通常", "节假日", "延迟",
    "换货", "7天", "原包装", "售后", "联系",
    "积分", "消费", "兑换", "优惠券", "有效期",
    "物流", "快递", "单号", "查询", "追踪",
    "怎么", "如何", "什么", "哪里", "我的",
    "诗", "写", "帮", "天气", "股票",
]


class KeywordEmbedder(BaseEmbedder):
    """基于词袋 TF 的稀疏向量，支持关键词匹配，零外部依赖。"""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        import jieba
        result = []
        for text in texts:
            tokens = set(jieba.cut(text))
            vec = np.array([1.0 if w in tokens else 0.0 for w in _VOCAB], dtype=float)
            norm = np.linalg.norm(vec)
            vec = vec / (norm + 1e-8)
            result.append(vec.tolist())
        return result


# ---------------------------------------------------------------------------
# FAQ 知识库数据
# ---------------------------------------------------------------------------
FAQ_CHUNKS = [
    {
        "chunk_id": "faq_001",
        "doc_id": "doc_faq",
        "content": '退款流程：在订单详情页点击"申请退款"，填写原因后提交。审核通过后 3-5 个工作日原路退回。',
        "metadata": {"source_title": "常见问题FAQ.txt"},
    },
    {
        "chunk_id": "faq_002",
        "doc_id": "doc_faq",
        "content": "发货时间：付款成功后通常 1-2 个工作日内发货。节假日期间可能延迟，以短信通知为准。",
        "metadata": {"source_title": "常见问题FAQ.txt"},
    },
    {
        "chunk_id": "faq_003",
        "doc_id": "doc_faq",
        "content": "换货政策：收货后 7 天内可申请换货，商品须保持原包装未使用状态。联系客服提供订单号即可。",
        "metadata": {"source_title": "常见问题FAQ.txt"},
    },
    {
        "chunk_id": "faq_004",
        "doc_id": "doc_faq",
        "content": "会员积分：每消费 1 元获得 1 积分，100 积分可兑换 1 元优惠券。积分有效期 2 年。",
        "metadata": {"source_title": "常见问题FAQ.txt"},
    },
    {
        "chunk_id": "faq_005",
        "doc_id": "doc_faq",
        "content": '物流查询：订单发货后会收到短信通知，包含快递单号。可在"我的订单"页面点击"查看物流"实时追踪。',
        "metadata": {"source_title": "常见问题FAQ.txt"},
    },
]


async def build_pipeline(llm_model: str) -> tuple[RAGPipeline, ChromaVectorStore, Bm25Store]:
    """组装管道并预加载知识库。"""
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="rag_demo_")

    embedder = KeywordEmbedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="demo",
        persist_directory=tmp_dir,
    )
    bm25_store = Bm25Store()
    llm = LLMFactory(model=llm_model)

    # 向知识库写入 FAQ（ChromaVectorStore.add 接受 list[dict] 并内部调用 embedder）
    print("📚 正在构建知识库...")
    await vector_store.add(FAQ_CHUNKS)
    bm25_store.add(FAQ_CHUNKS)
    print(f"  已导入 {len(FAQ_CHUNKS)} 条 FAQ\n")

    pipeline = RAGPipeline(
        intent_classifier=IntentClassifier(llm=llm),
        query_rewriter=QueryRewriter(llm=llm),
        retriever=HybridRetriever(vector_store=vector_store, bm25_store=bm25_store),
        reranker=NoopReranker(),
        confidence_evaluator=SignalFusionConfidenceEvaluator(),
        fallback_handler=TellUserFallbackHandler(),
        generator=LLMGenerator(llm=llm),
        tracer=StructuredLogTracer(),
        embedder=embedder,
    )
    return pipeline, vector_store, bm25_store


async def run_demo(llm_model: str):
    pipeline, _, _ = await build_pipeline(llm_model)

    questions = [
        "怎么申请退款？",
        "我的快递到哪了",
        "帮我写一首诗",           # 预期触发 out_of_scope
        "积分怎么用",
    ]

    for q in questions:
        print(f"{'='*60}")
        print(f"❓ 问题: {q}")
        result = await pipeline.run(q, session_id="demo_session")
        print(f"💬 回答: {result['answer']}")
        if result.get("sources"):
            for s in result["sources"]:
                print(f"   📄 来源: {s['title']}  chunk: {s['chunk_id']}")
                print(f"      预览: {s['content_preview'][:50]}...")
        conf = result.get("confidence")
        if conf is not None:
            tier = "高" if conf >= 0.75 else ("中" if conf >= 0.5 else "低")
            print(f"   🎯 置信度: {conf:.2f} ({tier})")
        if result.get("trace_id"):
            print(f"   🔍 trace_id: {result['trace_id']}")
        print()


def _is_real_key(val: str | None) -> bool:
    """返回 True 表示是真实 key（排除占位符）。"""
    return bool(val) and not val.startswith("sk-ant-xxx") and not val.endswith("xxx") and "placeholder" not in val.lower()


def detect_llm_model() -> str:
    """从环境变量推断 LLM model string。"""
    if _is_real_key(os.getenv("ANTHROPIC_API_KEY")):
        return "claude-haiku-4-5-20251001"   # 便宜快速，适合测试
    if _is_real_key(os.getenv("OPENAI_API_KEY")):
        return "gpt-4o-mini"
    if _is_real_key(os.getenv("DEEPSEEK_API_KEY")):
        return "deepseek/deepseek-chat"
    # 没有真实 key，使用 mock 模式
    return None


class _AlwaysHighConfidenceEvaluator(BaseConfidenceEvaluator):
    """仅用于 mock 演示，始终返回 high 置信度，使完整生成链路被执行。"""
    def evaluate(self, query, candidates, reranked):
        return 0.85, "high"


async def run_demo_with_mock():
    """无 LLM Key 时，用 mock LLM 演示整条链路（无真实 AI 回答）。"""
    from unittest.mock import AsyncMock, MagicMock

    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="rag_demo_mock_")

    embedder = KeywordEmbedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="demo_mock",
        persist_directory=tmp_dir,
    )
    bm25_store = Bm25Store()

    mock_llm = MagicMock()
    mock_llm.complete = AsyncMock()

    # FAQ 回答模板（模拟 LLM 基于检索上下文生成的答案）
    MOCK_ANSWERS = {
        "退款": '退款申请：在订单详情页点击"申请退款"，填写原因提交即可。审核通过后 3-5 工作日原路退回。',
        "积分": "会员积分：每消费 1 元得 1 积分，100 积分兑换 1 元优惠券，有效期 2 年。",
        "发货": "发货时间：付款后 1-2 工作日内发货，节假日可能延迟，以短信通知为准。",
        "物流": '物流查询：发货后会收到短信通知含快递单号，也可在"我的订单"页面查看实时物流。',
        "换货": "换货政策：收货后 7 天内可申请换货，商品须保持原包装未使用状态。",
    }

    def side_effect(messages, **kwargs):
        content = str(messages)
        content_lower = content.lower()
        # intent 分类
        if "意图" in content or "scope" in content_lower or "out_of_scope" in content_lower:
            question = messages[-1]["content"] if messages else ""
            if any(w in question for w in ["诗", "天气", "股票", "玩"]):
                return '{"intent": "out_of_scope", "confidence": 0.95, "clarification_question": null}'
            return '{"intent": "in_scope", "confidence": 0.9, "clarification_question": null}'
        # query 改写
        if "改写" in content or "rewrite" in content_lower or "规范" in content_lower:
            return messages[-1]["content"]
        # LLM 生成（基于检索内容）
        for kw, ans in MOCK_ANSWERS.items():
            if kw in content:
                return ans
        return "感谢您的提问。根据我们的知识库，您可以参考相关 FAQ 了解详情。如需更多帮助请联系客服。"

    mock_llm.complete.side_effect = side_effect

    print("📚 正在构建知识库 (mock 模式)...")
    await vector_store.add(FAQ_CHUNKS)
    bm25_store.add(FAQ_CHUNKS)
    print(f"  已导入 {len(FAQ_CHUNKS)} 条 FAQ\n")

    pipeline = RAGPipeline(
        intent_classifier=IntentClassifier(llm=mock_llm),
        query_rewriter=QueryRewriter(llm=mock_llm),
        retriever=HybridRetriever(vector_store=vector_store, bm25_store=bm25_store),
        reranker=NoopReranker(),
        confidence_evaluator=_AlwaysHighConfidenceEvaluator(),
        fallback_handler=TellUserFallbackHandler(),
        generator=LLMGenerator(llm=mock_llm),
        tracer=StructuredLogTracer(),
        embedder=embedder,
    )

    questions = ["怎么申请退款？", "积分怎么用", "帮我写一首诗"]
    for q in questions:
        print(f"{'='*60}")
        print(f"❓ 问题: {q}")
        result = await pipeline.run(q, session_id="mock_session")
        print(f"💬 回答: {result['answer'][:100]}")
        if result.get("sources"):
            for s in result["sources"]:
                print(f"   📄 来源: {s['title']} | {s['content_preview'][:40]}...")
        conf = result.get("confidence")
        if conf is not None:
            print(f"   🎯 置信度: {conf:.2f}")
        print()


if __name__ == "__main__":
    model = detect_llm_model()
    if model:
        print(f"🚀 使用真实 LLM: {model}\n")
        asyncio.run(run_demo(model))
    else:
        print("⚠️  未检测到 LLM API Key，使用 mock 模式（无真实 AI 回答）")
        print("   设置 ANTHROPIC_API_KEY / OPENAI_API_KEY / DEEPSEEK_API_KEY 可启用真实模式\n")
        asyncio.run(run_demo_with_mock())
