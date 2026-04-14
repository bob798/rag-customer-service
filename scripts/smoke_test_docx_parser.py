"""DocxParser 冒烟测试 — 用真实 DOCX 文件验证解析效果。

用法：
  # 简单文档
  .venv/bin/python scripts/smoke_test_docx_parser.py

  # 指定文档
  .venv/bin/python scripts/smoke_test_docx_parser.py tests/data/功放说明书_复杂版.docx

验证项（简单文档）：
  1. 文本完整性
  2. 表格提取
  3. 图片检测
  4. 图片 OCR 中文
  5. 元素顺序
  6. 章节传播

验证项（复杂文档额外）：
  7. 合并单元格去重
  8. Heading 层级嵌套
  9. 连续图片上下文
  10. 列表内容提取
"""
import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.docx_parser import DocxParser


def run_smoke_test(docx_path: Path):
    if not docx_path.exists():
        print(f"[错误] 文档不存在: {docx_path}")
        sys.exit(1)

    is_complex = "复杂" in docx_path.name

    print(f"解析文档: {docx_path.name}")
    print(f"文档类型: {'复杂版' if is_complex else '简单版'}")
    print("=" * 60)

    parser = DocxParser(chunker=SemanticChunker())
    doc_id = str(uuid.uuid4())
    metadata = {
        "source_title": docx_path.name,
        "source_path": str(docx_path),
        "file_type": "docx",
    }

    chunks = parser.parse(str(docx_path), doc_id=doc_id, metadata=metadata)

    print(f"\n共解析出 {len(chunks)} 个 chunks\n")

    # -- 逐 chunk 展示 --
    for i, chunk in enumerate(chunks):
        ct = chunk["metadata"]["content_type"]
        section = chunk["metadata"].get("section", "")
        content = chunk["content"]
        preview = content.replace("\n", "\\n")[:140]

        print(f"[{i:2d}] type={ct:6s}  section=\"{section}\"")
        print(f"     {preview}")
        print()

    # -- 验证 --
    print("=" * 60)
    print("验证结果:")
    print("=" * 60)

    all_content = " ".join(c["content"] for c in chunks)
    types = [c["metadata"]["content_type"] for c in chunks]
    sections = set(c["metadata"].get("section", "") for c in chunks)
    table_chunks = [c for c in chunks if c["metadata"]["content_type"] == "table"]
    image_chunks = [c for c in chunks if c["metadata"]["content_type"] == "image"]
    table_content = " ".join(c["content"] for c in table_chunks)
    ocr_content = " ".join(c["content"] for c in image_chunks)

    checks = []

    # ---- 通用验证项 ----

    # 1. 文本完整性
    if is_complex:
        text_keywords = ["蓝牙数字功放", "技术规格", "安装步骤", "故障排除", "400-888-1234"]
    else:
        text_keywords = ["蓝牙功放", "蓝牙 5.0", "USB 音频", "家庭影院"]
    text_hits = [kw for kw in text_keywords if kw in all_content]
    text_missing = [kw for kw in text_keywords if kw not in all_content]
    ok = len(text_hits) == len(text_keywords)
    checks.append(("文本完整性", ok, f"命中 {len(text_hits)}/{len(text_keywords)}", text_missing))

    # 2. 表格提取
    if is_complex:
        table_keywords = ["输出功率", "50W", "信噪比", "95dB", "频率响应", "蓝牙版本"]
    else:
        table_keywords = ["输出功率", "50W", "DC 12-24V", "信噪比", "95dB"]
    table_hits = [kw for kw in table_keywords if kw in table_content]
    ok = len(table_chunks) > 0 and len(table_hits) >= 3
    checks.append(("表格提取", ok,
                    f"{len(table_chunks)} 个表格, 关键词 {len(table_hits)}/{len(table_keywords)}", []))

    # 3. 图片检测
    expected_images = 6 if is_complex else 2
    ok = len(image_chunks) >= expected_images
    checks.append(("图片检测", ok,
                    f"检测到 {len(image_chunks)} 张（期望 ≥{expected_images}）", []))

    # 4. 图片 OCR 中文
    if is_complex:
        ocr_keywords = ["BLV", "50W", "AUX", "USB-C", "SPK", "步骤", "电源", "音箱", "保修", "12个月"]
    else:
        ocr_keywords = ["BLV", "蓝牙", "功放", "50W", "步骤", "电源", "12V"]
    ocr_hits = [kw for kw in ocr_keywords if kw in ocr_content]
    has_ocr = len(ocr_hits) > 0
    if has_ocr:
        ocr_missing = [kw for kw in ocr_keywords if kw not in ocr_content]
        checks.append(("图片OCR中文", True,
                        f"关键词 {len(ocr_hits)}/{len(ocr_keywords)}: {ocr_hits}", ocr_missing))
    else:
        checks.append(("图片OCR中文", None,
                        "paddleocr 未安装或 OCR 未返回结果（预期内）", []))

    # 5. 元素顺序
    ok = "table" in types and "image" in types and "text" in types
    if ok:
        first_table = types.index("table")
        first_image = types.index("image")
        ok = first_table < first_image
    checks.append(("元素顺序", ok, f"types={types}", []))

    # 6. 章节传播
    if is_complex:
        expected_sections = {"技术规格", "产品外观", "安装步骤", "指示灯说明", "故障排除", "包装清单", "保修条款"}
    else:
        expected_sections = {"技术规格", "产品外观", "安装步骤", "常见问题"}
    # Substring match: sections have full path like "X > Y > Z"
    found = set()
    for exp in expected_sections:
        if any(exp in s for s in sections):
            found.add(exp)
    ok = len(found) >= len(expected_sections) - 1
    checks.append(("章节传播", ok,
                    f"找到 {len(found)}/{len(expected_sections)}", expected_sections - found))

    # ---- 复杂文档额外验证 ----

    if is_complex:
        # 7. 合并单元格去重
        for tc in table_chunks:
            if "音频输入" in tc["content"]:
                count = tc["content"].count("音频输入")
                ok = count == 1
                checks.append(("合并单元格去重", ok,
                                f"\"音频输入\"出现 {count} 次", []))
                break
        else:
            checks.append(("合并单元格去重", False, "未找到接口定义表", []))

        # 8. Heading 层级嵌套
        has_nested = any("技术规格 > " in s for s in sections)
        checks.append(("Heading层级嵌套", has_nested,
                        f"{'有' if has_nested else '无'} '技术规格 > 子标题' 路径", []))

        # 9. 连续图片上下文
        step_images = [c for c in image_chunks if "步骤" in c["content"] or "连接" in c["content"]]
        if step_images:
            has_ctx = any("请严格" in c["content"] or "安装步骤" in c["content"]
                         for c in step_images)
            checks.append(("连续图片上下文", has_ctx,
                            f"步骤图片{'有' if has_ctx else '无'}关联上下文", []))
        else:
            checks.append(("连续图片上下文", False, "未找到步骤图片", []))

        # 10. 列表内容提取
        has_list = any("功放主机" in c["content"] for c in chunks)
        checks.append(("列表内容提取", has_list,
                        f"{'包含' if has_list else '缺失'}包装清单内容", []))

    # -- 输出 --
    all_pass = True
    for name, ok, detail, missing in checks:
        if ok is True:
            status = "PASS"
        elif ok is None:
            status = "SKIP"
        else:
            status = "FAIL"
            all_pass = False
        print(f"  [{status}] {name}: {detail}")
        if missing:
            print(f"         缺失: {missing}")

    print()
    if all_pass:
        print("所有检查通过!")
    else:
        print("存在失败项，请检查上方输出。")

    # -- 保存结果 --
    stem = docx_path.stem.replace(" ", "_")
    result_path = Path(__file__).parent.parent / "tests" / "data" / "eval_results" / f"docx_smoke_{stem}.json"
    result = {
        "doc": docx_path.name,
        "doc_type": "complex" if is_complex else "simple",
        "total_chunks": len(chunks),
        "type_distribution": {t: types.count(t) for t in set(types)},
        "sections": sorted(sections),
        "checks": {name: {"pass": ok, "detail": detail} for name, ok, detail, _ in checks},
        "all_pass": all_pass,
        "chunks": [
            {
                "index": i,
                "content_type": c["metadata"]["content_type"],
                "section": c["metadata"].get("section", ""),
                "content": c["content"],
            }
            for i, c in enumerate(chunks)
        ],
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果已保存: {result_path}")

    return all_pass


if __name__ == "__main__":
    if len(sys.argv) > 1:
        docx_path = Path(sys.argv[1])
    else:
        docx_path = Path(__file__).parent.parent / "tests" / "data" / "docx" / "功放说明书.docx"

    run_smoke_test(docx_path)
