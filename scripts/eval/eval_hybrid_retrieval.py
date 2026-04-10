"""混合检索评测脚本 — 基于预生成的 PaddleOCR markdown

从 paddleocr_raw_markdown.md 出发，不跑 OCR，只测检索质量。
对比: BM25-only / Vector-only / Hybrid (RRF)

在 Mac 端运行（需要 GteQwen2 模型缓存）：
  .venv/bin/python scripts/eval/eval_hybrid_retrieval.py

输入：tests/data/paddleocr_raw_markdown.md + eval_amplifier_qa.json
输出：tests/data/hybrid_retrieval_result.json
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

MARKDOWN_PATH = ROOT / "tests" / "data" / "paddleocr_raw_markdown.md"
QA_PATH = ROOT / "tests" / "data" / "eval_amplifier_qa.json"
RESULT_PATH = ROOT / "tests" / "data" / "hybrid_retrieval_result.json"


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def strip_html(text: str) -> str:
    """Remove HTML tags for cleaner indexing."""
    text = re.sub(r"<div[^>]*>|</div>", "", text)
    text = re.sub(r"<img[^>]*/>", "", text)
    text = re.sub(r"</?(?:html|body|table|tbody|tr|td|th|br|span|p|div)[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def eval_retrieval(
    results_per_query: list[list[dict]],
    qa_pairs: list[dict],
    label: str = "",
) -> dict:
    """Evaluate retrieval results with Hit@1, Hit@3, MRR.

    Args:
        results_per_query: list of search results per query (same order as qa_pairs)
        qa_pairs: QA dataset
        label: display prefix
    Returns: {"hit1", "hit3", "total", "mrr", "qa_details"}
    """
    hit1 = hit3 = total = 0
    mrr_sum = 0.0
    qa_details = []

    for qa, results in zip(qa_pairs, results_per_query):
        question = qa["question"]
        expected = qa.get("expected_source_keywords", [])

        if not expected:
            top1_preview = strip_html(results[0]["content"][:60]) if results else "(无结果)"
            print(f"  [ ] [{qa['id']}] {question}")
            print(f"     Top-1: {top1_preview}...")
            qa_details.append({
                "id": qa["id"], "question": question,
                "hit_at_1": None, "hit_at_3": None, "rr": None,
                "top1_score": round(results[0]["score"], 4) if results else 0,
                "top1_preview": top1_preview,
            })
            continue

        total += 1

        # Hit@1
        h1 = bool(results) and any(kw in results[0]["content"] for kw in expected)
        if h1:
            hit1 += 1

        # Hit@3
        top3_text = " ".join(r["content"] for r in results[:3])
        h3 = any(kw in top3_text for kw in expected)
        if h3:
            hit3 += 1

        # Reciprocal Rank
        rr = 0.0
        for rank, r in enumerate(results, 1):
            if any(kw in r["content"] for kw in expected):
                rr = 1.0 / rank
                break
        mrr_sum += rr

        status = "[1]" if h1 else ("[3]" if h3 else "[N]")
        top1_preview = strip_html(results[0]["content"][:60]) if results else "(无结果)"
        print(f"  {status} [{qa['id']}] {question}")
        print(f"     Top-1: {top1_preview}...")

        qa_details.append({
            "id": qa["id"], "question": question,
            "hit_at_1": h1, "hit_at_3": h3, "rr": round(rr, 3),
            "top1_score": round(results[0]["score"], 4) if results else 0,
            "top1_preview": top1_preview,
        })

    mrr = mrr_sum / total if total > 0 else 0
    if total:
        print(f"\n  {label}Hit@1: {hit1}/{total} ({100*hit1/total:.0f}%)")
        print(f"  {label}Hit@3: {hit3}/{total} ({100*hit3/total:.0f}%)")
        print(f"  {label}MRR:   {mrr:.3f}")

    return {
        "hit1": hit1, "hit3": hit3, "total": total,
        "mrr": round(mrr, 3), "qa_details": qa_details,
    }


async def main():
    separator("混合检索评测（基于 PaddleOCR Markdown）")
    print(f"Markdown: {MARKDOWN_PATH}")
    print(f"QA:       {QA_PATH}")
    print(f"Output:   {RESULT_PATH}")

    # ================================================================
    # Step 1: 从 markdown 重建 chunks
    # ================================================================
    separator("Step 1: 从 markdown 重建 chunks")

    assert MARKDOWN_PATH.exists(), f"Markdown 文件不存在: {MARKDOWN_PATH}"

    raw_md = MARKDOWN_PATH.read_text(encoding="utf-8")
    print(f"  Markdown: {len(raw_md)} 字符")

    from core.knowledge.parsers.paddleocr import PaddleOCRParser
    from core.knowledge.chunker import SemanticChunker

    chunker = SemanticChunker()
    # 用静态方法，不需要 PaddlePaddle
    segments = PaddleOCRParser._parse_markdown(raw_md)
    section_paths = PaddleOCRParser._build_section_paths(segments)

    # 需要一个 parser 实例来调 _segments_to_chunks（非静态方法，需要 chunker）
    parser = PaddleOCRParser.__new__(PaddleOCRParser)
    parser.chunker = chunker
    chunks = parser._segments_to_chunks(
        segments, section_paths,
        doc_id="paddleocr-eval-001",
        metadata={
            "source_title": "功放说明书.pdf",
            "source_path": str(ROOT / "tests" / "data" / "功放说明书.pdf"),
            "file_type": "pdf",
        },
    )
    print(f"  Chunks: {len(chunks)}")

    # 加载 QA
    if QA_PATH.exists():
        with open(QA_PATH, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)
    else:
        raise FileNotFoundError(f"QA 文件不存在: {QA_PATH}")

    print(f"  QA: {len(qa_pairs)} 题")

    # ================================================================
    # Step 2: 初始化 Embedder + 向量库 + BM25
    # ================================================================
    separator("Step 2: 初始化检索组件")

    from core.knowledge.embedder import GteQwen2Embedder
    from core.knowledge.vector_store import ChromaVectorStore
    from core.knowledge.bm25_store import Bm25Store
    from core.rag.retriever import HybridRetriever

    # Embedder
    t0 = time.monotonic()
    embedder = GteQwen2Embedder()
    # Warm up — embed a short text to trigger model loading
    await embedder.embed(["warmup"])
    embed_load_time = time.monotonic() - t0
    print(f"  Embedder 加载: {embed_load_time:.1f}s")

    # Vector store (临时目录，评测完丢弃)
    tmpdir = tempfile.mkdtemp(prefix="eval_hybrid_")
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="eval_paddleocr",
        persist_directory=tmpdir,
    )

    t0 = time.monotonic()
    await vector_store.add(chunks)
    index_time = time.monotonic() - t0
    print(f"  向量索引: {len(chunks)} chunks, {index_time:.1f}s")

    # BM25
    bm25_store = Bm25Store()
    bm25_store.add(chunks)
    print(f"  BM25 索引: {bm25_store.count()} docs")

    # Hybrid retriever
    retriever = HybridRetriever(vector_store=vector_store, bm25_store=bm25_store)

    # ================================================================
    # Step 3: BM25-only 评测
    # ================================================================
    separator("Step 3: BM25-only 评测")
    print("  图例: [1]=Hit@1  [3]=Hit@3但非Top1  [N]=未命中  [ ]=无关键词\n")

    bm25_results_all = []
    for qa in qa_pairs:
        results = bm25_store.search(qa["question"], top_k=5)
        bm25_results_all.append(results)

    bm25_eval = eval_retrieval(bm25_results_all, qa_pairs, label="BM25 ")

    # ================================================================
    # Step 4: Vector-only 评测
    # ================================================================
    separator("Step 4: Vector-only 评测")
    print("  图例: [1]=Hit@1  [3]=Hit@3但非Top1  [N]=未命中  [ ]=无关键词\n")

    vector_results_all = []
    for qa in qa_pairs:
        query_vec = (await embedder.embed([qa["question"]]))[0]
        results = await vector_store.query(query_vec, top_k=5)
        vector_results_all.append(results)

    vector_eval = eval_retrieval(vector_results_all, qa_pairs, label="Vector ")

    # ================================================================
    # Step 5: Hybrid (RRF) 评测
    # ================================================================
    separator("Step 5: Hybrid (BM25 + Vector RRF) 评测")
    print("  图例: [1]=Hit@1  [3]=Hit@3但非Top1  [N]=未命中  [ ]=无关键词\n")

    hybrid_results_all = []
    for qa in qa_pairs:
        query_vec = (await embedder.embed([qa["question"]]))[0]
        results = await retriever.retrieve(query_vec, qa["question"], top_k=5)
        hybrid_results_all.append(results)

    hybrid_eval = eval_retrieval(hybrid_results_all, qa_pairs, label="Hybrid ")

    # ================================================================
    # Step 6: 对比总结
    # ================================================================
    separator("对比总结")

    b, v, h = bm25_eval, vector_eval, hybrid_eval

    print(f"  {'指标':<12} {'BM25':>10} {'Vector':>10} {'Hybrid':>10}")
    print(f"  {'-'*44}")
    print(f"  {'Hit@1':<12} {f'{b['hit1']}/{b['total']}':>10} {f'{v['hit1']}/{v['total']}':>10} {f'{h['hit1']}/{h['total']}':>10}")
    print(f"  {'Hit@3':<12} {f'{b['hit3']}/{b['total']}':>10} {f'{v['hit3']}/{v['total']}':>10} {f'{h['hit3']}/{h['total']}':>10}")
    print(f"  {'MRR':<12} {b['mrr']:>10.3f} {v['mrr']:>10.3f} {h['mrr']:>10.3f}")

    # ================================================================
    # 保存结果
    # ================================================================
    separator("保存结果")

    report = {
        "source": "paddleocr_raw_markdown.md",
        "chunk_count": len(chunks),
        "qa_count": len(qa_pairs),
        "embedder": "GteQwen2Embedder (gte-Qwen2-1.5B-instruct)",
        "embed_load_time_seconds": round(embed_load_time, 2),
        "index_time_seconds": round(index_time, 2),
        "metrics": {
            "bm25_only": {
                "hit_at_1": f"{b['hit1']}/{b['total']}",
                "hit_at_3": f"{b['hit3']}/{b['total']}",
                "mrr": b["mrr"],
            },
            "vector_only": {
                "hit_at_1": f"{v['hit1']}/{v['total']}",
                "hit_at_3": f"{v['hit3']}/{v['total']}",
                "mrr": v["mrr"],
            },
            "hybrid_rrf": {
                "hit_at_1": f"{h['hit1']}/{h['total']}",
                "hit_at_3": f"{h['hit3']}/{h['total']}",
                "mrr": h["mrr"],
            },
        },
        "qa_details": {
            "bm25": b["qa_details"],
            "vector": v["qa_details"],
            "hybrid": h["qa_details"],
        },
    }

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存: {RESULT_PATH}")

    # Cleanup hint
    print(f"\n  临时向量库: {tmpdir}")
    print(f"  (可手动删除)")


if __name__ == "__main__":
    asyncio.run(main())
