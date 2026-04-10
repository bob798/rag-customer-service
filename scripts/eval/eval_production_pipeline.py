"""生产链路 QA 评测 — 真实 Embedding + 真实检索 + 真实 LLM

完整链路：
  PDF → DefaultParser → SemanticChunker → chunks
  → GteQwen2Embedder → ChromaVectorStore + Bm25Store
  → HybridRetriever(Vector+BM25+RRF) → NoopReranker → ConfidenceEvaluator
  → IntentClassifier → QueryRewriter → LLMGenerator

使用方式：
  .venv/bin/python scripts/eval_production_pipeline.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 加载 .env
for line in open(Path(__file__).parent.parent / ".env"):
    if "=" in line and not line.startswith("#"):
        k, v = line.strip().split("=", 1)
        os.environ.setdefault(k, v)

LLM_MODEL = os.environ.get("DEFAULT_MODEL", "openai/deepseek-v3-250324")
PDF_PATH = Path("tests/data/功放说明书.pdf")
QA_PATH = Path("tests/data/eval_amplifier_qa.json")
def _next_result_path() -> Path:
    """Auto-increment version: qa_eval_results_v1.json → v2 → v3 ..."""
    data_dir = Path("tests/data")
    existing = sorted(data_dir.glob("qa_eval_results_v*.json"))
    if existing:
        last = existing[-1].stem  # qa_eval_results_v3
        ver = int(last.rsplit("v", 1)[-1]) + 1
    else:
        ver = 1
    return data_dir / f"qa_eval_results_v{ver}.json"


RESULT_PATH = _next_result_path()


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


async def main():
    separator("生产链路 QA 评测")
    print(f"PDF:   {PDF_PATH}")
    print(f"LLM:   {LLM_MODEL}")
    print(f"评测集: {QA_PATH}")

    # ================================================================
    # Step 1: 解析文档
    # ================================================================
    separator("Step 1: 解析文档")
    from core.knowledge.chunker import SemanticChunker
    from core.knowledge.parsers.default import DefaultParser

    t0 = time.monotonic()
    parser = DefaultParser(chunker=SemanticChunker())
    chunks = parser.parse(str(PDF_PATH), doc_id="eval-prod-001", metadata={
        "source_title": PDF_PATH.name,
        "source_path": str(PDF_PATH),
        "file_type": "pdf",
    })
    print(f"  解析完成: {len(chunks)} chunks, {time.monotonic()-t0:.1f}s")

    # ================================================================
    # Step 2: 构建索引（真实 Embedding + ChromaDB + BM25）
    # ================================================================
    separator("Step 2: 构建索引")
    from core.knowledge.embedder import GteQwen2Embedder
    from core.knowledge.vector_store import ChromaVectorStore
    from core.knowledge.bm25_store import Bm25Store

    t0 = time.monotonic()
    embedder = GteQwen2Embedder()
    print(f"  Embedding 模型加载: {time.monotonic()-t0:.1f}s")

    tmpdir = tempfile.mkdtemp(prefix="eval_chroma_")
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="eval_amplifier",
        persist_directory=tmpdir,
    )

    t0 = time.monotonic()
    await vector_store.add(chunks)
    print(f"  向量索引构建: {time.monotonic()-t0:.1f}s ({len(chunks)} chunks embedded)")

    bm25_store = Bm25Store()
    bm25_store.add(chunks)
    print(f"  BM25 索引构建完成")

    # ================================================================
    # Step 3: 组装生产 Pipeline
    # ================================================================
    separator("Step 3: 组装 Pipeline")
    from core.llm.factory import LLMFactory
    from core.rag.confidence import SignalFusionConfidenceEvaluator
    from core.rag.fallback_handler import TellUserFallbackHandler
    from core.rag.generator import LLMGenerator
    from core.rag.intent import IntentClassifier
    from core.rag.pipeline import RAGPipeline
    from core.rag.query_rewriter import QueryRewriter
    # NoopReranker 仅用于 CI 测试；生产评测用 BGEReranker
    from core.rag.retriever import HybridRetriever
    from core.rag.tracer import StructuredLogTracer

    llm = LLMFactory(model=LLM_MODEL)
    from core.rag.reranker import BGEReranker

    retriever = HybridRetriever(vector_store=vector_store, bm25_store=bm25_store)
    reranker = BGEReranker(model_name="BAAI/bge-reranker-v2-m3")

    pipeline = RAGPipeline(
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
    print(f"  Pipeline 组装完成")
    print(f"  组件: GteQwen2Embedder → HybridRetriever(Vector+BM25) → BGEReranker → DeepSeek V3")

    # ================================================================
    # Step 4: 逐个评测
    # ================================================================
    separator("Step 4: QA 评测")
    with open(QA_PATH, "r", encoding="utf-8") as f:
        qa_pairs = json.load(f)

    results = []
    hits = 0
    total_with_keywords = 0

    for qa in qa_pairs:
        qid = qa["id"]
        question = qa["question"]
        expected_kws = qa.get("expected_source_keywords", [])

        print(f"\n  [{qid}] {question}")

        try:
            t0 = time.monotonic()
            result = await pipeline.run(question, f"eval-session-{qid}")
            elapsed = time.monotonic() - t0

            answer = result.get("answer", "")
            sources = result.get("sources", [])
            confidence = result.get("confidence", 0)
            uncertain = result.get("uncertain", False)

            # 检查 sources 中是否包含期望关键词
            all_source_text = " ".join(
                s.get("content_preview", "") + " " + s.get("title", "")
                for s in sources
            )
            hit = any(kw in all_source_text or kw in answer for kw in expected_kws) if expected_kws else None

            if expected_kws:
                total_with_keywords += 1
                if hit:
                    hits += 1

            status = "✅" if hit is True else ("⬜" if hit is None else "❌")
            print(f"       {status} confidence={confidence:.2f} uncertain={uncertain} sources={len(sources)} time={elapsed:.1f}s")
            print(f"       回答: {answer[:100]}...")
            if not hit and expected_kws:
                print(f"       ❌ 未命中关键词: {expected_kws}")
                print(f"       sources内容: {all_source_text[:150]}...")

            results.append({
                "id": qid,
                "question": question,
                "category": qa.get("category", ""),
                "expected_keywords": expected_kws,
                "hit": hit,
                "confidence": round(confidence, 3),
                "uncertain": uncertain,
                "source_count": len(sources),
                "answer_preview": answer[:200],
                "elapsed_seconds": round(elapsed, 2),
            })

        except Exception as e:
            print(f"       ❌ 错误: {e}")
            results.append({
                "id": qid,
                "question": question,
                "hit": False,
                "error": str(e),
            })

    # ================================================================
    # Step 5: 汇总报告
    # ================================================================
    separator("评测结果汇总")

    recall = hits / total_with_keywords if total_with_keywords > 0 else 0

    report = {
        "config": {
            "llm_model": LLM_MODEL,
            "embedding": "GteQwen2-1.5B-instruct",
            "retriever": "HybridRetriever(Vector+BM25+RRF)",
            "reranker": "BGEReranker(bge-reranker-v2-m3)",
            "chunker": "SemanticChunker(500chars, 50overlap)",
            "pdf": str(PDF_PATH),
        },
        "summary": {
            "total_questions": len(qa_pairs),
            "questions_with_keywords": total_with_keywords,
            "hits": hits,
            "recall_rate": f"{hits}/{total_with_keywords} ({100*recall:.0f}%)",
            "avg_confidence": round(sum(r.get("confidence", 0) for r in results) / len(results), 3) if results else 0,
            "avg_latency": round(sum(r.get("elapsed_seconds", 0) for r in results) / len(results), 2) if results else 0,
        },
        "details": results,
    }

    # 打印汇总表
    print(f"  召回率: {report['summary']['recall_rate']}")
    print(f"  平均置信度: {report['summary']['avg_confidence']}")
    print(f"  平均延迟: {report['summary']['avg_latency']}s")
    print()
    print(f"  {'ID':<10} {'问题':<25} {'命中':^6} {'置信度':^8} {'Sources':^8} {'延迟':>6}")
    print(f"  {'-'*10} {'-'*25} {'-'*6} {'-'*8} {'-'*8} {'-'*6}")
    for r in results:
        status = "✅" if r.get("hit") is True else ("⬜" if r.get("hit") is None else "❌")
        conf = f"{r.get('confidence', 0):.2f}" if "confidence" in r else "ERR"
        src = str(r.get("source_count", 0)) if "source_count" in r else "ERR"
        lat = f"{r.get('elapsed_seconds', 0):.1f}s" if "elapsed_seconds" in r else "ERR"
        print(f"  {r['id']:<10} {r['question']:<25} {status:^6} {conf:^8} {src:^8} {lat:>6}")

    # 保存结果
    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"\n  结果已保存: {RESULT_PATH}")

    # 清理临时 ChromaDB
    import shutil
    shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    asyncio.run(main())
