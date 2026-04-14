"""评估 DocxParser 的 OCR 质量 + 检索容错能力。

第一步：收集 6 张测试图片的 OCR 置信度分布
第二步：模拟 RAG 检索，验证上下文融合能否兜住 OCR 错误

用法：
  PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    .venv/bin/python scripts/eval_docx_ocr_quality.py
"""
import json
import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "tests" / "data" / "docx"
EVAL_DIR = Path(__file__).parent.parent / "tests" / "data" / "eval_results"


# =====================================================================
# Part 1: OCR 置信度分析
# =====================================================================

def analyze_ocr_scores():
    """对 6 张测试图片逐张跑 OCR，记录每行的文本+置信度。"""
    import numpy as np
    from PIL import Image
    from paddleocr import PaddleOCR

    print("=" * 60)
    print("Part 1: OCR 置信度分析")
    print("=" * 60)

    ocr = PaddleOCR(use_textline_orientation=True, lang="ch")

    # 测试图片 + 预期文本
    test_images = [
        ("complex_img_label.png", "BLV-D1 蓝牙功放 50W×2"),
        ("complex_img_ports.png", "AUX IN | USB-C | SPK L/R | DC 12-24V"),
        ("complex_img_step1.png", "步骤1: 连接电源适配器 DC12V"),
        ("complex_img_step2.png", "步骤2: 连接音箱线 左右声道"),
        ("complex_img_led.png", "指示灯位置示意图 前面板左侧"),
        ("complex_img_warranty.png", "保修期限12个月 自购买之日起计算 人为损坏不在保修范围内"),
    ]

    results = []
    for filename, expected in test_images:
        img_path = DATA_DIR / "images" / filename
        if not img_path.exists():
            print(f"  [跳过] {filename} 不存在")
            continue

        image = Image.open(img_path).convert("RGB")
        img_array = np.array(image)

        ocr_result = list(ocr.predict(img_array))

        lines = []
        for page in ocr_result:
            if not page:
                continue
            texts = page.get("rec_texts", [])
            scores = page.get("rec_scores", [])
            for text, score in zip(texts, scores):
                lines.append({"text": text.strip(), "score": round(score, 4)})

        ocr_text = " ".join(l["text"] for l in lines)
        avg_score = sum(l["score"] for l in lines) / len(lines) if lines else 0

        # 关键词匹配
        expected_keywords = [w for w in expected.replace("|", " ").split() if len(w) >= 2]
        keyword_hits = [kw for kw in expected_keywords if kw in ocr_text]
        keyword_miss = [kw for kw in expected_keywords if kw not in ocr_text]

        entry = {
            "image": filename,
            "size": f"{image.width}x{image.height}",
            "expected": expected,
            "ocr_text": ocr_text,
            "lines": lines,
            "avg_score": round(avg_score, 4),
            "min_score": round(min(l["score"] for l in lines), 4) if lines else 0,
            "max_score": round(max(l["score"] for l in lines), 4) if lines else 0,
            "keyword_recall": f"{len(keyword_hits)}/{len(expected_keywords)}",
            "keywords_hit": keyword_hits,
            "keywords_miss": keyword_miss,
        }
        results.append(entry)

        # 打印
        print(f"\n{'─'*50}")
        print(f"图片: {filename} ({image.width}x{image.height})")
        print(f"预期: {expected}")
        print(f"OCR:  {ocr_text}")
        print(f"逐行置信度:")
        for l in lines:
            flag = "✓" if l["score"] >= 0.9 else ("?" if l["score"] >= 0.7 else "✗")
            print(f"  [{flag}] {l['score']:.4f}  \"{l['text']}\"")
        print(f"平均: {avg_score:.4f}  最低: {entry['min_score']}  最高: {entry['max_score']}")
        print(f"关键词: {len(keyword_hits)}/{len(expected_keywords)} "
              f"命中={keyword_hits} 缺失={keyword_miss}")

    return results


# =====================================================================
# Part 2: RAG 检索容错测试
# =====================================================================

def analyze_retrieval_tolerance(chunks: list[dict]):
    """模拟 RAG 检索：用 BM25 关键词匹配测试 OCR 错误是否影响检索。"""
    print(f"\n\n{'=' * 60}")
    print("Part 2: RAG 检索容错测试（BM25 关键词匹配）")
    print("=" * 60)

    # 测试问题 — 需要从图片内容中找到答案
    test_queries = [
        {
            "question": "产品面板上写了什么型号？",
            "expected_answer": "BLV-D1",
            "answer_source": "图片OCR",
            "must_hit_keywords": ["BLV-D1"],
        },
        {
            "question": "产品背面有哪些接口？",
            "expected_answer": "AUX, USB-C, SPK, DC",
            "answer_source": "图片OCR + 表格",
            "must_hit_keywords": ["AUX", "USB-C"],  # AUX 被 OCR 丢了，但表格有
        },
        {
            "question": "安装第一步是什么？",
            "expected_answer": "连接电源适配器",
            "answer_source": "图片OCR",
            "must_hit_keywords": ["电源", "连接"],
        },
        {
            "question": "保修期限是多久？",
            "expected_answer": "12个月",
            "answer_source": "图片OCR",
            "must_hit_keywords": ["12个月"],
        },
        {
            "question": "保修条款的内容是什么？",
            "expected_answer": "保修期限12个月",
            "answer_source": "上下文融合",
            "must_hit_keywords": ["保修"],  # OCR 出错写成"买修"，但上下文有"保修"
        },
        {
            "question": "输出功率是多少？",
            "expected_answer": "50W × 2",
            "answer_source": "表格",
            "must_hit_keywords": ["50W"],
        },
        {
            "question": "蓝牙配对怎么操作？",
            "expected_answer": "长按配对键3秒",
            "answer_source": "文本",
            "must_hit_keywords": ["配对"],
        },
        {
            "question": "指示灯在哪个位置？",
            "expected_answer": "前面板左侧",
            "answer_source": "图片OCR",
            "must_hit_keywords": ["前面板", "左侧"],
        },
    ]

    results = []
    for q in test_queries:
        question = q["question"]
        keywords = q["must_hit_keywords"]

        # 简单 BM25 模拟：关键词在 chunk content 中出现
        hits = []
        for i, chunk in enumerate(chunks):
            content = chunk["content"]
            matched_kw = [kw for kw in keywords if kw in content]
            if matched_kw:
                hits.append({
                    "chunk_index": chunk["metadata"]["chunk_index"],
                    "content_type": chunk["metadata"]["content_type"],
                    "section": chunk["metadata"].get("section", ""),
                    "matched_keywords": matched_kw,
                    "content_preview": content[:100],
                })

        hit_at_1 = len(hits) >= 1
        source_types = list(set(h["content_type"] for h in hits))

        entry = {
            "question": question,
            "expected_answer": q["expected_answer"],
            "answer_source": q["answer_source"],
            "keywords": keywords,
            "hit@1": hit_at_1,
            "total_hits": len(hits),
            "hit_types": source_types,
            "hits": hits[:3],  # top 3
        }
        results.append(entry)

        status = "PASS" if hit_at_1 else "FAIL"
        print(f"\n  [{status}] \"{question}\"")
        print(f"         期望来源: {q['answer_source']}  关键词: {keywords}")
        print(f"         命中: {len(hits)} chunks  类型: {source_types}")
        if hits:
            for h in hits[:2]:
                preview = h["content_preview"].replace("\n", "\\n")
                print(f"         → [{h['content_type']}] {preview}...")

    # 汇总
    total = len(results)
    passed = sum(1 for r in results if r["hit@1"])
    print(f"\n{'─'*50}")
    print(f"  检索命中率: {passed}/{total} ({passed/total*100:.0f}%)")

    # 按来源分析
    by_source = {}
    for r in results:
        src = r["answer_source"]
        by_source.setdefault(src, {"total": 0, "hit": 0})
        by_source[src]["total"] += 1
        if r["hit@1"]:
            by_source[src]["hit"] += 1

    print("  按来源:")
    for src, stats in by_source.items():
        rate = stats["hit"] / stats["total"] * 100
        print(f"    {src}: {stats['hit']}/{stats['total']} ({rate:.0f}%)")

    return results


# =====================================================================
# Main
# =====================================================================

def main():
    from core.knowledge.chunker import SemanticChunker
    from core.knowledge.parsers.docx_parser import DocxParser

    docx_path = DATA_DIR / "功放说明书_复杂版.docx"
    if not docx_path.exists():
        print(f"[错误] {docx_path} 不存在，先运行 scripts/create_complex_test_docx.py")
        sys.exit(1)

    # Part 1: OCR 置信度
    ocr_results = analyze_ocr_scores()

    # Part 2: 解析文档 + 检索测试
    print(f"\n\n解析文档用于检索测试...")
    parser = DocxParser(chunker=SemanticChunker())
    chunks = parser.parse(
        str(docx_path),
        doc_id=str(uuid.uuid4()),
        metadata={"source_title": docx_path.name, "source_path": str(docx_path), "file_type": "docx"},
    )
    retrieval_results = analyze_retrieval_tolerance(chunks)

    # 保存完整结果
    output = {
        "doc": docx_path.name,
        "ocr_analysis": ocr_results,
        "retrieval_analysis": retrieval_results,
        "summary": {
            "ocr_images": len(ocr_results),
            "ocr_avg_score": round(
                sum(r["avg_score"] for r in ocr_results) / len(ocr_results), 4
            ) if ocr_results else 0,
            "retrieval_hit_rate": f"{sum(1 for r in retrieval_results if r['hit@1'])}/{len(retrieval_results)}",
        },
    }
    out_path = EVAL_DIR / "docx_ocr_eval_result.json"
    out_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n\n完整结果已保存: {out_path}")


if __name__ == "__main__":
    main()
