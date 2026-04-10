"""PaddleOCR PP-StructureV3 解析评测脚本

在 Windows 上运行：
  1. pip install paddleocr paddlepaddle
  2. python scripts/eval/eval_paddleocr_parsing.py

输入：tests/data/功放说明书.pdf
输出：
  - tests/data/paddleocr_parsing_result.json  (结构化评测结果)
  - tests/data/paddleocr_raw_markdown.md      (原始 OCR markdown)
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 项目根目录
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")

PDF_PATH = ROOT / "tests" / "data" / "功放说明书.pdf"
RESULT_PATH = ROOT / "tests" / "data" / "paddleocr_parsing_result.json"
MARKDOWN_PATH = ROOT / "tests" / "data" / "paddleocr_raw_markdown.md"
QA_PATH = ROOT / "tests" / "data" / "eval_amplifier_qa.json"


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def strip_html(text: str) -> str:
    """Remove HTML tags and img references for cleaner BM25 indexing."""
    text = re.sub(r'<div[^>]*>|</div>', '', text)
    text = re.sub(r'<img[^>]*/?>', '', text)
    text = re.sub(r'</?(?:html|body|table|tbody|tr|td|th|br|span|p|div)[^>]*>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def eval_bm25(store, qa_pairs: list[dict], top_k: int = 3, label: str = "") -> dict:
    """Run BM25 eval with Hit@1, Hit@3, MRR metrics.

    Returns: {"hit1": int, "hit3": int, "total": int, "mrr_sum": float, "qa_details": [...]}
    """
    hit1 = 0
    hit3 = 0
    total = 0
    mrr_sum = 0.0
    qa_details = []

    for qa in qa_pairs:
        question = qa["question"]
        expected = qa.get("expected_source_keywords", [])
        results = store.search(question, top_k=top_k)

        if not expected:
            # No keywords to check — skip counting but still show
            top1_preview = strip_html(results[0]["content"][:60]) if results else "(无结果)"
            print(f"  [ ] [{qa['id']}] {question}")
            print(f"     Top-1: {top1_preview}...")
            qa_details.append({
                "id": qa["id"], "question": question,
                "hit_at_1": None, "hit_at_3": None, "rr": None,
                "top1_score": round(results[0]["score"], 2) if results else 0,
                "top1_preview": top1_preview,
            })
            continue

        total += 1

        # Hit@1
        h1 = bool(results) and any(kw in results[0]["content"] for kw in expected)
        if h1:
            hit1 += 1

        # Hit@3
        top3_text = " ".join(r["content"] for r in results)
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

        # Display
        if h1:
            status = "[1]"  # hit at rank 1
        elif h3:
            status = "[3]"  # hit but not at rank 1
        else:
            status = "[N]"
        top1_preview = strip_html(results[0]["content"][:60]) if results else "(无结果)"
        print(f"  {status} [{qa['id']}] {question}")
        print(f"     Top-1: {top1_preview}...")

        qa_details.append({
            "id": qa["id"], "question": question,
            "hit_at_1": h1, "hit_at_3": h3, "rr": round(rr, 3),
            "top1_score": round(results[0]["score"], 2) if results else 0,
            "top1_preview": top1_preview,
        })

    mrr = mrr_sum / total if total > 0 else 0
    print(f"\n  {label}Hit@1: {hit1}/{total} ({100*hit1/total:.0f}%)" if total else "")
    print(f"  {label}Hit@3: {hit3}/{total} ({100*hit3/total:.0f}%)" if total else "")
    print(f"  {label}MRR:   {mrr:.3f}" if total else "")

    return {
        "hit1": hit1, "hit3": hit3, "total": total,
        "mrr": round(mrr, 3), "qa_details": qa_details,
    }


def main():
    separator("PaddleOCR PP-StructureV3 解析评测")
    print(f"PDF:      {PDF_PATH}")
    print(f"Output:   {RESULT_PATH}")
    print(f"Markdown: {MARKDOWN_PATH}")

    # ================================================================
    # Step 1: PaddleOCR 解析 PDF + 保存原始 Markdown
    # ================================================================
    separator("Step 1: PaddleOCR 解析")

    from core.knowledge.parsers.paddleocr import PaddleOCRParser
    from core.knowledge.chunker import SemanticChunker

    assert PaddleOCRParser.is_available(), "paddleocr not installed"

    parser = PaddleOCRParser(chunker=SemanticChunker(), device="cpu")

    # 1a: 获取原始 markdown 并保存
    t0 = time.monotonic()
    raw_md = parser._run_paddleocr(str(PDF_PATH))
    ocr_time = time.monotonic() - t0

    MARKDOWN_PATH.write_text(raw_md, encoding="utf-8")
    print(f"  OCR 完成: {ocr_time:.1f}s, {len(raw_md)} 字符")
    print(f"  原始 Markdown 已保存: {MARKDOWN_PATH}")

    # 1b: 分段 + 分块
    t0 = time.monotonic()
    segments = parser._parse_markdown(raw_md)
    section_paths = parser._build_section_paths(segments)
    chunks = parser._segments_to_chunks(
        segments, section_paths,
        doc_id="paddleocr-eval-001",
        metadata={
            "source_title": PDF_PATH.name,
            "source_path": str(PDF_PATH),
            "file_type": "pdf",
        },
    )
    chunk_time = time.monotonic() - t0
    parse_time = ocr_time + chunk_time
    print(f"  分块完成: {len(chunks)} chunks, {chunk_time:.1f}s")
    print(f"  总耗时: {parse_time:.1f}s")

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
        print(f"    {'[Y]' if found else '[N]'} {kw}")
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
    # Step 4: BM25 检索评测（原始）
    # ================================================================
    separator("Step 4: BM25 检索评测（原始 chunks）")
    print("  图例: [1]=Hit@1  [3]=Hit@3但非Top1  [N]=未命中  [ ]=无关键词\n")

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

    raw_eval = eval_bm25(store, qa_pairs, label="")

    # ================================================================
    # Step 4b: 优化 BM25 — 清理 HTML + 拼入 section
    # ================================================================
    separator("Step 4b: 优化 BM25（去 HTML + section 拼接）")
    print("  图例: [1]=Hit@1  [3]=Hit@3但非Top1  [N]=未命中  [ ]=无关键词\n")

    enhanced_chunks = []
    for c in chunks:
        section = c["metadata"].get("section", "") or ""
        clean_content = strip_html(c["content"])
        # Prepend section path for better BM25 matching
        enhanced_content = f"{section} {clean_content}" if section else clean_content
        enhanced_chunks.append({**c, "content": enhanced_content})

    enhanced_store = Bm25Store()
    enhanced_store.add(enhanced_chunks)

    enh_eval = eval_bm25(enhanced_store, qa_pairs, label="优化后 ")

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

    # DefaultParser BM25 (with same metrics)
    print("  DefaultParser BM25 评测:")
    default_store = Bm25Store()
    default_store.add(default_chunks)
    default_eval = eval_bm25(default_store, qa_pairs, label="Default ")

    # 对比表
    separator("对比总结")

    r = raw_eval
    e = enh_eval
    d = default_eval

    print(f"  {'指标':<20} {'PaddleOCR':>12} {'Paddle优化':>12} {'Default':>12}")
    print(f"  {'-'*58}")
    print(f"  {'chunk 数':<20} {len(chunks):>12} {len(enhanced_chunks):>12} {len(default_chunks):>12}")
    print(f"  {'总字符数':<20} {total_chars:>12} {'-':>12} {sum(len(c['content']) for c in default_chunks):>12}")
    print(f"  {'content_type 种类':<20} {len(type_dist):>12} {'-':>12} {len(default_types):>12}")
    print(f"  {'关键词覆盖':<20} {f'{kw_hits}/{len(keywords)}':>12} {'-':>12} {f'{default_kw_hits}/{len(keywords)}':>12}")
    print(f"  {'Hit@1':<20} {f'{r['hit1']}/{r['total']}':>12} {f'{e['hit1']}/{e['total']}':>12} {f'{d['hit1']}/{d['total']}':>12}")
    print(f"  {'Hit@3':<20} {f'{r['hit3']}/{r['total']}':>12} {f'{e['hit3']}/{e['total']}':>12} {f'{d['hit3']}/{d['total']}':>12}")
    print(f"  {'MRR':<20} {r['mrr']:>12.3f} {e['mrr']:>12.3f} {d['mrr']:>12.3f}")
    print(f"  {'解析耗时':<20} {f'{parse_time:.1f}s':>12} {'-':>12} {f'{default_time:.1f}s':>12}")

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
        "metrics": {
            "paddleocr_raw": {
                "hit_at_1": f"{r['hit1']}/{r['total']}",
                "hit_at_3": f"{r['hit3']}/{r['total']}",
                "mrr": r["mrr"],
            },
            "paddleocr_enhanced": {
                "hit_at_1": f"{e['hit1']}/{e['total']}",
                "hit_at_3": f"{e['hit3']}/{e['total']}",
                "mrr": e["mrr"],
            },
            "default_parser": {
                "hit_at_1": f"{d['hit1']}/{d['total']}",
                "hit_at_3": f"{d['hit3']}/{d['total']}",
                "mrr": d["mrr"],
            },
        },
        "qa_results": r["qa_details"],
        "qa_results_enhanced": e["qa_details"],
        "comparison_with_default": {
            "paddleocr_chunks": len(chunks),
            "default_chunks": len(default_chunks),
            "paddleocr_types": type_dist,
            "default_types": default_types,
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
    print(f"  Markdown: {MARKDOWN_PATH}")


if __name__ == "__main__":
    main()
