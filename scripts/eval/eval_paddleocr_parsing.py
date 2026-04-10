"""PaddleOCR PP-StructureV3 解析评测脚本

在 Windows 上运行：
  1. pip install paddleocr paddlepaddle
  2. python scripts/eval/eval_paddleocr_parsing.py

输入：tests/data/功放说明书.pdf
输出：tests/data/paddleocr_parsing_result.json
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

PDF_PATH = ROOT / "tests" / "data" / "功放说明书.pdf"
RESULT_PATH = ROOT / "tests" / "data" / "paddleocr_parsing_result.json"
QA_PATH = ROOT / "tests" / "data" / "eval_amplifier_qa.json"


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    separator("PaddleOCR PP-StructureV3 解析评测")
    print(f"PDF:    {PDF_PATH}")
    print(f"Output: {RESULT_PATH}")

    # ================================================================
    # Step 1: PaddleOCR 解析 PDF
    # ================================================================
    separator("Step 1: PaddleOCR 解析")

    from core.knowledge.parsers.paddleocr import PaddleOCRParser
    from core.knowledge.chunker import SemanticChunker

    assert PaddleOCRParser.is_available(), "paddleocr not installed"

    parser = PaddleOCRParser(chunker=SemanticChunker(), device="cpu")

    t0 = time.monotonic()
    chunks = parser.parse(
        str(PDF_PATH),
        doc_id="paddleocr-eval-001",
        metadata={
            "source_title": PDF_PATH.name,
            "source_path": str(PDF_PATH),
            "file_type": "pdf",
        },
    )
    parse_time = time.monotonic() - t0
    print(f"  解析完成: {len(chunks)} chunks, {parse_time:.1f}s")

    # ================================================================
    # Step 2: 解析质量分析
    # ================================================================
    separator("Step 2: 解析质量分析")

    # content_type 分布
    type_dist = {}
    for c in chunks:
        t = c["metadata"]["content_type"]
        type_dist[t] = type_dist.get(t, 0) + 1
    print(f"  content_type 分布: {type_dist}")

    total_chars = sum(len(c["content"]) for c in chunks)
    print(f"  总字符数: {total_chars}")
    print(f"  平均 chunk 大小: {total_chars // max(len(chunks), 1)} 字符")

    # section path
    sections = set(c["metadata"].get("section", "") for c in chunks if c["metadata"].get("section"))
    print(f"  section 种类: {len(sections)}")
    for s in sorted(sections)[:10]:
        print(f"    - {s}")

    # 关键词检查
    full_text = " ".join(c["content"] for c in chunks)
    keywords = ["蓝牙", "音频", "放大器", "BLV-D1", "TPA3116", "电源", "扬声器"]
    print(f"\n  关键词检查:")
    kw_hits = 0
    for kw in keywords:
        found = kw in full_text
        if found:
            kw_hits += 1
        print(f"    {'✅' if found else '❌'} {kw}")
    print(f"  关键词覆盖率: {kw_hits}/{len(keywords)}")

    # ================================================================
    # Step 3: 打印每个 chunk 详情
    # ================================================================
    separator("Step 3: Chunk 详情")

    for i, c in enumerate(chunks):
        meta = c["metadata"]
        preview = c["content"][:100].replace("\n", " ")
        section = meta.get("section", "") or ""
        print(f"  [{i:2d}] {meta['content_type']:8s} section={section:30s} | {preview}...")

    # ================================================================
    # Step 4: BM25 检索评测
    # ================================================================
    separator("Step 4: BM25 检索评测")

    from core.knowledge.bm25_store import Bm25Store

    store = Bm25Store()
    store.add(chunks)

    if QA_PATH.exists():
        with open(QA_PATH, "r", encoding="utf-8") as f:
            qa_pairs = json.load(f)
    else:
        qa_pairs = [
            {"id": "q1", "question": "BLV-D1 的输出功率是多少？", "expected_source_keywords": ["50W"]},
            {"id": "q2", "question": "如何连接蓝牙？", "expected_source_keywords": ["蓝牙"]},
            {"id": "q3", "question": "支持什么电压供电？", "expected_source_keywords": ["12", "24"]},
            {"id": "q4", "question": "用的什么芯片？", "expected_source_keywords": ["TPA3116"]},
            {"id": "q5", "question": "扬声器怎么接线？", "expected_source_keywords": ["扬声器"]},
        ]

    qa_results = []
    hits = 0
    total_with_kw = 0

    for qa in qa_pairs:
        question = qa["question"]
        expected = qa.get("expected_source_keywords", [])
        results = store.search(question, top_k=3)
        top3_text = " ".join(r["content"] for r in results)

        hit = any(kw in top3_text for kw in expected) if expected else None
        if expected:
            total_with_kw += 1
            if hit:
                hits += 1

        status = "✅" if hit is True else ("⬜" if hit is None else "❌")
        top1_preview = results[0]["content"][:60].replace("\n", " ") if results else "(无结果)"
        print(f"  {status} [{qa['id']}] {question}")
        print(f"     Top-1: {top1_preview}...")

        qa_results.append({
            "id": qa["id"],
            "question": question,
            "hit": hit,
            "top1_score": round(results[0]["score"], 2) if results else 0,
            "top1_preview": top1_preview,
        })

    recall = hits / total_with_kw if total_with_kw > 0 else 0
    print(f"\n  BM25 召回率: {hits}/{total_with_kw} ({100*recall:.0f}%)")

    # ================================================================
    # Step 5: 与 DefaultParser 对比
    # ================================================================
    separator("Step 5: 与 DefaultParser 对比")

    from core.knowledge.parsers.default import DefaultParser

    t0 = time.monotonic()
    default_chunks = DefaultParser(chunker=SemanticChunker()).parse(
        str(PDF_PATH), doc_id="default-001",
        metadata={"source_title": PDF_PATH.name, "source_path": str(PDF_PATH), "file_type": "pdf"},
    )
    default_time = time.monotonic() - t0

    default_types = {}
    for c in default_chunks:
        t = c["metadata"]["content_type"]
        default_types[t] = default_types.get(t, 0) + 1

    default_text = " ".join(c["content"] for c in default_chunks)
    default_kw_hits = sum(1 for kw in keywords if kw in default_text)

    # DefaultParser BM25
    default_store = Bm25Store()
    default_store.add(default_chunks)
    default_hits = 0
    for qa in qa_pairs:
        expected = qa.get("expected_source_keywords", [])
        if not expected:
            continue
        results = default_store.search(qa["question"], top_k=3)
        top3 = " ".join(r["content"] for r in results)
        if any(kw in top3 for kw in expected):
            default_hits += 1

    print(f"  {'指标':<20} {'PaddleOCR':>15} {'DefaultParser':>15}")
    print(f"  {'-'*50}")
    print(f"  {'chunk 数':<20} {len(chunks):>15} {len(default_chunks):>15}")
    print(f"  {'总字符数':<20} {total_chars:>15} {sum(len(c['content']) for c in default_chunks):>15}")
    print(f"  {'content_type 种类':<20} {len(type_dist):>15} {len(default_types):>15}")
    print(f"  {'关键词覆盖':<20} {f'{kw_hits}/{len(keywords)}':>15} {f'{default_kw_hits}/{len(keywords)}':>15}")
    print(f"  {'BM25 召回率':<20} {f'{hits}/{total_with_kw}':>15} {f'{default_hits}/{total_with_kw}':>15}")
    print(f"  {'解析耗时':<20} {f'{parse_time:.1f}s':>15} {f'{default_time:.1f}s':>15}")

    # ================================================================
    # 保存结果
    # ================================================================
    separator("保存结果")

    report = {
        "parser": "PaddleOCR PP-StructureV3",
        "pdf": str(PDF_PATH),
        "parse_time_seconds": round(parse_time, 2),
        "chunk_count": len(chunks),
        "total_chars": total_chars,
        "content_type_distribution": type_dist,
        "sections": sorted(sections),
        "keyword_coverage": f"{kw_hits}/{len(keywords)}",
        "bm25_recall": f"{hits}/{total_with_kw} ({100*recall:.0f}%)",
        "qa_results": qa_results,
        "comparison_with_default": {
            "paddleocr_chunks": len(chunks),
            "default_chunks": len(default_chunks),
            "paddleocr_types": type_dist,
            "default_types": default_types,
            "paddleocr_bm25_recall": f"{hits}/{total_with_kw}",
            "default_bm25_recall": f"{default_hits}/{total_with_kw}",
        },
        "chunks": [
            {
                "content": c["content"][:200],
                "content_type": c["metadata"]["content_type"],
                "section": c["metadata"].get("section"),
            }
            for c in chunks
        ],
    }

    with open(RESULT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    print(f"  结果已保存: {RESULT_PATH}")


if __name__ == "__main__":
    main()
