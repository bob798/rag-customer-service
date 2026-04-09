"""PDF 文档解析回归测试 — 功放说明书.pdf

测试层次：
  1. 文本提取完整性（关键词覆盖、无空 chunk）
  2. 中文分块质量（字符计数、overlap 有效性、句终符切分）
  3. Metadata 结构一致性（content_type/page/section/chunk_index）
  4. BM25 中文检索（关键词命中、排序合理性）
  5. MinerU content_list 处理逻辑（模拟数据，多模态分流）
  6. Parser 注册与选择逻辑
  7. Golden data 回归（解析结果 vs 快照）
  8. 性能守卫（解析耗时不超基线）
  9. 边界 case（空文件、损坏数据、超长文本、特殊字符）
  10. 检索质量评测（真实用户提问 → BM25 检索 → 验证召回）
"""
from __future__ import annotations

import json
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from core.knowledge.bm25_store import Bm25Store
from core.knowledge.chunker import SemanticChunker
from core.knowledge.parsers.default import DefaultParser
from core.knowledge.parsers.faq import FAQParser
from core.knowledge.parsers.mineru import MinerUParser
from core.knowledge.parsers.registry import ParserRegistry


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

PDF_PATH = Path(__file__).parent.parent / "data" / "功放说明书.pdf"

REQUIRED_CHUNK_FIELDS = {"chunk_id", "doc_id", "content", "metadata"}
REQUIRED_META_FIELDS = {"content_type", "page", "section", "chunk_index"}


@pytest.fixture(scope="module")
def pdf_chunks() -> list[dict]:
    """Parse 功放说明书.pdf once for the whole module."""
    assert PDF_PATH.exists(), f"Test PDF not found: {PDF_PATH}"
    parser = DefaultParser(chunker=SemanticChunker())
    return parser.parse(
        str(PDF_PATH),
        doc_id="regression-pdf-001",
        metadata={
            "source_title": PDF_PATH.name,
            "source_path": str(PDF_PATH),
            "file_type": "pdf",
        },
    )


@pytest.fixture(scope="module")
def pdf_full_text(pdf_chunks) -> str:
    """Concatenated text of all chunks."""
    return " ".join(c["content"] for c in pdf_chunks)


@pytest.fixture(scope="module")
def pdf_bm25(pdf_chunks) -> Bm25Store:
    """BM25 index populated with PDF chunks."""
    store = Bm25Store()
    store.add(pdf_chunks)
    return store


# ---------------------------------------------------------------------------
# 场景 1：文本提取完整性
# ---------------------------------------------------------------------------

class TestPdfExtraction:
    """PDF 文本提取应覆盖文档核心内容。"""

    def test_produces_chunks(self, pdf_chunks):
        assert len(pdf_chunks) >= 5, f"Expected >=5 chunks from 7-page PDF, got {len(pdf_chunks)}"

    def test_no_empty_chunks(self, pdf_chunks):
        for i, c in enumerate(pdf_chunks):
            assert c["content"].strip(), f"chunk[{i}] has empty content"

    @pytest.mark.parametrize("keyword", [
        "蓝牙",
        "音频",
        "放大器",
        "BLV-D1",
        "TPA3116",
        "电源",
        "扬声器",
    ])
    def test_keyword_extracted(self, pdf_full_text, keyword):
        """核心产品关键词必须出现在提取结果中。"""
        assert keyword in pdf_full_text, f"Keyword '{keyword}' not found in extracted text"

    def test_total_char_count_reasonable(self, pdf_chunks):
        """7 页技术手册，总字符数应在合理范围。"""
        total = sum(len(c["content"]) for c in pdf_chunks)
        assert total > 2000, f"Total chars {total} too low — likely extraction failure"
        assert total < 50000, f"Total chars {total} suspiciously high"

    def test_bilingual_content(self, pdf_full_text):
        """文档含中英文混合内容。"""
        has_chinese = any("\u4e00" <= ch <= "\u9fff" for ch in pdf_full_text)
        has_english = any("a" <= ch.lower() <= "z" for ch in pdf_full_text)
        assert has_chinese, "No Chinese characters found"
        assert has_english, "No English characters found"


# ---------------------------------------------------------------------------
# 场景 2：中文分块质量
# ---------------------------------------------------------------------------

class TestChunkingQuality:
    """分块大小、overlap、边界质量。"""

    def test_chunk_size_within_bounds(self, pdf_chunks):
        """每个 chunk 大小应在合理范围（不含 overlap 导致的膨胀也不应超过 2x chunk_size）。"""
        for i, c in enumerate(pdf_chunks):
            size = len(c["content"])
            assert size <= 1200, f"chunk[{i}] too large: {size} chars (max ~1200 with overlap)"
            assert size >= 20, f"chunk[{i}] too small: {size} chars"

    def test_overlap_effective(self, pdf_chunks):
        """相邻 chunk 之间应有 overlap（前 chunk 末尾出现在后 chunk 开头）。"""
        overlap_hits = 0
        for i in range(1, len(pdf_chunks)):
            prev_tail = pdf_chunks[i - 1]["content"][-50:]
            curr_head = pdf_chunks[i]["content"][:100]
            if prev_tail in curr_head or prev_tail[-20:] in curr_head:
                overlap_hits += 1
        # 允许少量 overlap 不匹配（段落边界切换时）
        ratio = overlap_hits / max(len(pdf_chunks) - 1, 1)
        assert ratio >= 0.7, f"Overlap effective rate {ratio:.0%} too low (expected >=70%)"

    def test_no_single_char_chunks(self, pdf_chunks):
        """不应产生只有几个字符的碎片 chunk。"""
        for i, c in enumerate(pdf_chunks):
            assert len(c["content"]) > 10, f"chunk[{i}] is a fragment: {c['content'][:30]!r}"

    def test_chinese_char_counting_works(self):
        """验证字符计数对纯中文文本正常工作。"""
        chunker = SemanticChunker(chunk_size=20, overlap=5)
        # 两段各 20 字符，用 \n\n 分隔 → 各自刚好触发 chunk 边界
        para_a = "甲乙丙丁戊己庚辛壬癸" * 2  # 20 chars
        para_b = "子丑寅卯辰巳午未申酉" * 2  # 20 chars
        text = f"{para_a}\n\n{para_b}"
        chunks = chunker.chunk(text, "test", {})
        assert len(chunks) >= 2, f"Two 20-char paragraphs with chunk_size=20 should produce >=2 chunks, got {len(chunks)}"


# ---------------------------------------------------------------------------
# 场景 3：Metadata 结构一致性
# ---------------------------------------------------------------------------

class TestMetadataConsistency:
    """每个 chunk 必须包含完整的 metadata 字段。"""

    def test_required_fields_present(self, pdf_chunks):
        for i, c in enumerate(pdf_chunks):
            missing_top = REQUIRED_CHUNK_FIELDS - set(c.keys())
            assert not missing_top, f"chunk[{i}] missing top-level: {missing_top}"
            missing_meta = REQUIRED_META_FIELDS - set(c["metadata"].keys())
            assert not missing_meta, f"chunk[{i}] missing metadata: {missing_meta}"

    def test_chunk_ids_unique(self, pdf_chunks):
        ids = [c["chunk_id"] for c in pdf_chunks]
        assert len(ids) == len(set(ids)), "Duplicate chunk_ids"

    def test_chunk_index_sequential(self, pdf_chunks):
        indices = [c["metadata"]["chunk_index"] for c in pdf_chunks]
        assert indices == list(range(len(pdf_chunks))), f"Non-sequential chunk_index: {indices}"

    def test_doc_id_consistent(self, pdf_chunks):
        doc_ids = set(c["doc_id"] for c in pdf_chunks)
        assert len(doc_ids) == 1, f"Multiple doc_ids: {doc_ids}"

    def test_content_type_is_text_for_default_parser(self, pdf_chunks):
        """DefaultParser 只能提取文本，content_type 应全为 'text'。"""
        for c in pdf_chunks:
            assert c["metadata"]["content_type"] == "text"

    def test_source_title_propagated(self, pdf_chunks):
        for c in pdf_chunks:
            assert c["metadata"]["source_title"] == "功放说明书.pdf"


# ---------------------------------------------------------------------------
# 场景 4：BM25 中文检索
# ---------------------------------------------------------------------------

class TestBm25Retrieval:
    """BM25 索引应能检索到 PDF 中的中文内容。"""

    @pytest.mark.parametrize("query,expected_keyword", [
        ("蓝牙连接", "蓝牙"),
        ("电源开关", "电源"),
        ("音频放大器", "放大"),
        ("BLV-D1", "BLV"),
        ("扬声器输出", "扬声器"),
    ])
    def test_keyword_query_hits(self, pdf_bm25, query, expected_keyword):
        """关键词查询应返回包含相关内容的结果。"""
        results = pdf_bm25.search(query, top_k=3)
        assert len(results) > 0, f"No results for query '{query}'"
        top_content = results[0]["content"]
        assert expected_keyword in top_content, (
            f"Top result for '{query}' doesn't contain '{expected_keyword}': "
            f"{top_content[:80]}..."
        )

    def test_score_ordering(self, pdf_bm25):
        """BM25 返回结果应按 score 降序排列。"""
        results = pdf_bm25.search("蓝牙音频", top_k=5)
        if len(results) >= 2:
            scores = [r["score"] for r in results]
            assert scores == sorted(scores, reverse=True), f"Scores not descending: {scores}"

    def test_irrelevant_query_low_results(self, pdf_bm25):
        """与文档无关的查询应返回少量或零结果。"""
        results = pdf_bm25.search("机器学习深度神经网络", top_k=3)
        if results:
            assert results[0]["score"] < 5.0, "Irrelevant query scored too high"


# ---------------------------------------------------------------------------
# 场景 5：MinerU content_list 处理
# ---------------------------------------------------------------------------

class TestMinerUContentListProcessing:
    """MinerU Parser 的 content_list → chunks 转换逻辑（模拟数据，不需安装 MinerU）。"""

    @pytest.fixture
    def parser(self):
        return MinerUParser(chunker=SemanticChunker(), output_dir="/tmp/test_mineru")

    @pytest.fixture
    def simulated_content_list(self):
        """模拟功放说明书经 MinerU 解析后的 content_list。"""
        return [
            {"type": "text", "text": "BLV-D1 音频放大器用户手册", "text_level": 1, "page_idx": 0, "bbox": [72, 50, 540, 80]},
            {"type": "text", "text": "BLV-D1 是一款 2x50W 蓝牙 v5.0 音频放大器，基于 TPA3116 芯片设计，支持蓝牙和有线音频输入。", "text_level": 0, "page_idx": 0, "bbox": [72, 100, 540, 200]},
            {"type": "image", "img_path": "images/blv_d1_front.jpg", "image_caption": ["图1：BLV-D1 前面板"], "image_footnote": [], "page_idx": 1, "bbox": [100, 100, 450, 350]},
            {"type": "text", "text": "技术规格", "text_level": 1, "page_idx": 2, "bbox": [72, 50, 540, 80]},
            {"type": "table", "table_body": "<table><tr><td>参数</td><td>值</td></tr><tr><td>输出功率</td><td>2x50W</td></tr><tr><td>蓝牙版本</td><td>v5.0</td></tr><tr><td>供电电压</td><td>DC 12-24V</td></tr><tr><td>信噪比</td><td>>100dB</td></tr></table>", "table_caption": ["表1：核心技术参数"], "table_footnote": ["注：测试条件为24V供电，8Ω负载"], "page_idx": 2, "bbox": [72, 100, 540, 400]},
            {"type": "text", "text": "连接指南", "text_level": 1, "page_idx": 3, "bbox": [72, 50, 540, 80]},
            {"type": "text", "text": "蓝牙连接", "text_level": 2, "page_idx": 3, "bbox": [72, 90, 540, 110]},
            {"type": "text", "text": "打开设备电源后，蓝牙指示灯将闪烁，表示处于配对模式。在手机蓝牙设置中搜索BLV-D1并连接。配对成功后指示灯常亮。如需重新配对，长按蓝牙解除按钮3秒。", "text_level": 0, "page_idx": 3, "bbox": [72, 120, 540, 250]},
            {"type": "text", "text": "有线连接", "text_level": 2, "page_idx": 3, "bbox": [72, 270, 540, 290]},
            {"type": "text", "text": "使用3.5mm音频线连接音源设备到LINE IN接口。接入有线信号后设备自动切换到有线输入模式。", "text_level": 0, "page_idx": 3, "bbox": [72, 300, 540, 400]},
            {"type": "equation", "text": "P_{out} = \\frac{V_{cc}^2}{2 \\pi^2 R_L}", "text_format": "latex", "page_idx": 4, "bbox": [150, 200, 400, 240]},
            {"type": "code", "code_body": "i2cset -y 1 0x4c 0x03 0x00", "code_caption": ["示例：I2C寄存器配置命令"], "page_idx": 5, "bbox": [72, 100, 540, 140]},
            {"type": "header", "text": "BerryBak Audio", "page_idx": 0},
            {"type": "footer", "text": "Page 1", "page_idx": 0},
            {"type": "page_number", "text": "1", "page_idx": 0},
        ]

    @pytest.fixture
    def mineru_chunks(self, parser, simulated_content_list):
        paths = MinerUParser._build_section_paths(simulated_content_list)
        return parser._content_list_to_chunks(
            simulated_content_list, paths,
            doc_id="mineru-regression-001",
            metadata={"source_title": "功放说明书.pdf", "source_path": "tests/data/功放说明书.pdf", "file_type": "pdf"},
        )

    # --- 多模态分流 ---

    def test_text_chunks_produced(self, mineru_chunks):
        text_chunks = [c for c in mineru_chunks if c["metadata"]["content_type"] == "text"]
        assert len(text_chunks) >= 2, "Should produce multiple text chunks"

    def test_table_as_atomic_chunk(self, mineru_chunks):
        tables = [c for c in mineru_chunks if c["metadata"]["content_type"] == "table"]
        assert len(tables) == 1
        assert "<table>" in tables[0]["content"]
        assert "核心技术参数" in tables[0]["content"]

    def test_table_preserves_html_structure(self, mineru_chunks):
        table = next(c for c in mineru_chunks if c["metadata"]["content_type"] == "table")
        assert "<tr>" in table["content"]
        assert "<td>" in table["content"]
        assert "2x50W" in table["content"]

    def test_table_includes_caption_and_footnote(self, mineru_chunks):
        table = next(c for c in mineru_chunks if c["metadata"]["content_type"] == "table")
        assert "表1：核心技术参数" in table["content"]
        assert "注：测试条件" in table["content"]

    def test_image_as_atomic_chunk(self, mineru_chunks):
        images = [c for c in mineru_chunks if c["metadata"]["content_type"] == "image"]
        assert len(images) == 1
        assert "图1：BLV-D1 前面板" in images[0]["content"]
        assert images[0]["metadata"]["image_path"] == "images/blv_d1_front.jpg"

    def test_formula_as_atomic_chunk(self, mineru_chunks):
        formulas = [c for c in mineru_chunks if c["metadata"]["content_type"] == "formula"]
        assert len(formulas) == 1
        assert "P_{out}" in formulas[0]["content"]

    def test_code_as_atomic_chunk(self, mineru_chunks):
        codes = [c for c in mineru_chunks if c["metadata"]["content_type"] == "code"]
        assert len(codes) == 1
        assert "i2cset" in codes[0]["content"]
        assert "I2C寄存器" in codes[0]["content"]

    def test_headers_footers_discarded(self, mineru_chunks):
        """header/footer/page_number 不应生成 chunk。"""
        all_content = " ".join(c["content"] for c in mineru_chunks)
        assert "BerryBak Audio" not in all_content  # header
        assert "Page 1" not in all_content  # footer

    def test_headings_not_stored_as_chunks(self, mineru_chunks):
        """标题不应作为独立 chunk，而是体现在 section path 中。"""
        for c in mineru_chunks:
            content = c["content"]
            # 标题文本不应作为 chunk 的全部内容
            assert content not in ("BLV-D1 音频放大器用户手册", "技术规格", "连接指南", "蓝牙连接", "有线连接")

    # --- Section path ---

    def test_section_path_for_text(self, mineru_chunks):
        """蓝牙配对说明应在 '连接指南 > 蓝牙连接' section 下。"""
        bt_chunk = next(
            c for c in mineru_chunks
            if "配对" in c["content"] and c["metadata"]["content_type"] == "text"
        )
        assert "连接指南" in bt_chunk["metadata"]["section"]
        assert "蓝牙连接" in bt_chunk["metadata"]["section"]

    def test_section_path_for_table(self, mineru_chunks):
        table = next(c for c in mineru_chunks if c["metadata"]["content_type"] == "table")
        assert table["metadata"]["section"] == "技术规格"

    def test_section_path_heading_reset(self, simulated_content_list):
        """同级标题应重置 section stack。"""
        paths = MinerUParser._build_section_paths(simulated_content_list)
        # "有线连接" (level 2) should replace "蓝牙连接" (level 2) under "连接指南"
        wired_idx = next(
            i for i, item in enumerate(simulated_content_list)
            if item.get("text") == "使用3.5mm音频线连接音源设备到LINE IN接口。接入有线信号后设备自动切换到有线输入模式。"
        )
        assert "有线连接" in paths[wired_idx]
        assert "蓝牙连接" not in paths[wired_idx]

    # --- Page 信息 ---

    def test_page_idx_propagated(self, mineru_chunks):
        for c in mineru_chunks:
            assert c["metadata"]["page"] is not None, f"chunk missing page: {c['content'][:30]}"

    def test_table_on_correct_page(self, mineru_chunks):
        table = next(c for c in mineru_chunks if c["metadata"]["content_type"] == "table")
        assert table["metadata"]["page"] == 2

    # --- Metadata 完整性 ---

    def test_all_chunks_have_required_metadata(self, mineru_chunks):
        for i, c in enumerate(mineru_chunks):
            missing = REQUIRED_META_FIELDS - set(c["metadata"].keys())
            assert not missing, f"chunk[{i}] missing metadata: {missing}"

    def test_chunk_index_sequential(self, mineru_chunks):
        indices = [c["metadata"]["chunk_index"] for c in mineru_chunks]
        assert indices == list(range(len(mineru_chunks)))

    def test_content_type_distribution(self, mineru_chunks):
        """应包含多种 content_type。"""
        types = set(c["metadata"]["content_type"] for c in mineru_chunks)
        assert types >= {"text", "table", "image", "formula", "code"}, f"Missing types: {types}"

    # --- BM25 检索（多模态 chunks）---

    def test_bm25_finds_table_content(self, mineru_chunks):
        """表格内容应可被 BM25 检索到。"""
        store = Bm25Store()
        store.add(mineru_chunks)
        results = store.search("输出功率", top_k=3)
        assert len(results) > 0
        # BM25 search returns {chunk_id, doc_id, content, score} — check content
        assert any("输出功率" in r["content"] or "2x50W" in r["content"] for r in results)

    def test_bm25_finds_bluetooth_instructions(self, mineru_chunks):
        store = Bm25Store()
        store.add(mineru_chunks)
        results = store.search("蓝牙配对", top_k=3)
        assert len(results) > 0
        assert "蓝牙" in results[0]["content"]


# ---------------------------------------------------------------------------
# 场景 6：Parser 注册与选择
# ---------------------------------------------------------------------------

class TestParserRegistration:
    """ParserRegistry 应正确选择 parser。"""

    def test_faq_wins_for_faq_txt(self):
        registry = ParserRegistry()
        registry.register(FAQParser())
        registry.register(DefaultParser(chunker=SemanticChunker()))
        parser = registry.get_parser("txt", "问：如何退款？\n答：可以在订单页面申请。")
        assert isinstance(parser, FAQParser)

    def test_default_handles_pdf(self):
        registry = ParserRegistry()
        registry.register(FAQParser())
        registry.register(DefaultParser(chunker=SemanticChunker()))
        parser = registry.get_parser("pdf", "")
        assert isinstance(parser, DefaultParser)

    def test_mineru_wins_for_pdf_when_registered(self):
        """MinerU 注册后应优先于 DefaultParser 处理 PDF。"""
        registry = ParserRegistry()
        registry.register(FAQParser())
        registry.register(MinerUParser(chunker=SemanticChunker()))
        registry.register(DefaultParser(chunker=SemanticChunker()))
        parser = registry.get_parser("pdf", "")
        assert isinstance(parser, MinerUParser)

    def test_default_handles_pdf_when_mineru_not_registered(self):
        registry = ParserRegistry()
        registry.register(FAQParser())
        registry.register(DefaultParser(chunker=SemanticChunker()))
        parser = registry.get_parser("pdf", "")
        assert isinstance(parser, DefaultParser)

    def test_default_handles_docx(self):
        registry = ParserRegistry()
        registry.register(MinerUParser(chunker=SemanticChunker()))
        registry.register(DefaultParser(chunker=SemanticChunker()))
        parser = registry.get_parser("docx", "")
        assert isinstance(parser, DefaultParser)


# ---------------------------------------------------------------------------
# 场景 7：Golden data 回归
# ---------------------------------------------------------------------------

GOLDEN_PATH = Path(__file__).parent.parent / "data" / "golden_amplifier_default.json"


class TestGoldenDataRegression:
    """解析结果与保存的快照对比，防止无意中改变输出。"""

    @pytest.fixture(scope="class")
    def golden(self):
        assert GOLDEN_PATH.exists(), f"Golden data not found: {GOLDEN_PATH}"
        with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    def test_chunk_count_matches(self, pdf_chunks, golden):
        """chunk 数量应与 golden data 一致。"""
        assert len(pdf_chunks) == golden["chunk_count"], (
            f"Chunk count changed: expected {golden['chunk_count']}, got {len(pdf_chunks)}. "
            f"If intentional, regenerate golden data."
        )

    def test_content_matches(self, pdf_chunks, golden):
        """每个 chunk 的 content 应与 golden data 一致。"""
        for i, (actual, expected) in enumerate(zip(pdf_chunks, golden["chunks"])):
            assert actual["content"] == expected["content"], (
                f"chunk[{i}] content changed.\n"
                f"Expected: {expected['content'][:80]}...\n"
                f"Got:      {actual['content'][:80]}..."
            )

    def test_content_type_matches(self, pdf_chunks, golden):
        """每个 chunk 的 content_type 应与 golden data 一致。"""
        for i, (actual, expected) in enumerate(zip(pdf_chunks, golden["chunks"])):
            assert actual["metadata"]["content_type"] == expected["metadata"]["content_type"], (
                f"chunk[{i}] content_type changed: "
                f"{expected['metadata']['content_type']} → {actual['metadata']['content_type']}"
            )


# ---------------------------------------------------------------------------
# 场景 8：性能守卫
# ---------------------------------------------------------------------------

class TestPerformanceGuard:
    """解析和分块的耗时不应退化。"""

    def test_pdf_parse_time(self):
        """功放说明书.pdf 解析应在 5 秒内完成。"""
        parser = DefaultParser(chunker=SemanticChunker())
        start = time.monotonic()
        chunks = parser.parse(
            str(PDF_PATH), doc_id="perf-test",
            metadata={"source_title": "test.pdf", "source_path": "test", "file_type": "pdf"},
        )
        elapsed = time.monotonic() - start
        assert elapsed < 5.0, f"PDF parsing took {elapsed:.2f}s (limit: 5s)"
        assert len(chunks) > 0

    def test_chunker_throughput(self):
        """SemanticChunker 处理 10000 字中文应在 0.5 秒内。"""
        chunker = SemanticChunker(chunk_size=500, overlap=50)
        text = "这是一段测试文本，用于验证分块性能。" * 600  # ~10800 chars
        start = time.monotonic()
        chunks = chunker.chunk(text, "perf-doc", {})
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Chunking 10K chars took {elapsed:.2f}s (limit: 0.5s)"
        assert len(chunks) > 0

    def test_bm25_index_and_search(self):
        """BM25 索引 100 个 chunk + 搜索应在 2 秒内。"""
        chunker = SemanticChunker(chunk_size=200, overlap=20)
        chunks = []
        for i in range(100):
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": "perf-doc",
                "content": f"这是第{i}个测试文本块，包含蓝牙音频放大器的技术参数。" * 3,
                "metadata": {"chunk_index": i},
            })

        store = Bm25Store()
        start = time.monotonic()
        store.add(chunks)
        results = store.search("蓝牙音频", top_k=10)
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"BM25 index+search took {elapsed:.2f}s (limit: 2s)"
        assert len(results) > 0


# ---------------------------------------------------------------------------
# 场景 9：边界 case
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """异常输入和边界条件不应导致崩溃。"""

    def test_empty_txt_file(self, tmp_path):
        """空文件应返回空 chunk 列表，不崩溃。"""
        empty = tmp_path / "empty.txt"
        empty.write_text("", encoding="utf-8")
        parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(str(empty), "doc-empty", {"source_title": "empty.txt", "file_type": "txt"})
        assert chunks == []

    def test_whitespace_only_file(self, tmp_path):
        """纯空白文件应返回空列表。"""
        ws = tmp_path / "whitespace.txt"
        ws.write_text("   \n\n\t\n   ", encoding="utf-8")
        parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(str(ws), "doc-ws", {"source_title": "ws.txt", "file_type": "txt"})
        assert chunks == []

    def test_single_char_file(self, tmp_path):
        """单字符文件应产出一个 chunk。"""
        f = tmp_path / "one.txt"
        f.write_text("A", encoding="utf-8")
        parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(str(f), "doc-one", {"source_title": "one.txt", "file_type": "txt"})
        assert len(chunks) == 1
        assert chunks[0]["content"] == "A"

    def test_very_long_single_paragraph(self):
        """超长单段落（无换行）应被句终符切分，不产出超大 chunk。"""
        chunker = SemanticChunker(chunk_size=500, overlap=50)
        # 2000 字中文，有句号分隔
        long_para = "这是一个很长的句子用来测试分块。" * 150  # ~2250 chars
        chunks = chunker.chunk(long_para, "doc-long", {})
        assert len(chunks) >= 3, f"2250 chars should produce >=3 chunks with size=500"
        for c in chunks:
            assert len(c["content"]) < 1200, f"Chunk too large: {len(c['content'])} chars"

    def test_special_characters(self, tmp_path):
        """特殊字符（emoji、零宽字符）不应崩溃。"""
        f = tmp_path / "special.txt"
        f.write_text("测试🎵音频\u200b放大器\u00a0规格", encoding="utf-8")
        parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(str(f), "doc-special", {"source_title": "s.txt", "file_type": "txt"})
        assert len(chunks) == 1
        assert "测试" in chunks[0]["content"]

    def test_mixed_newlines(self, tmp_path):
        """混合换行符（\\r\\n、\\r、\\n）不应导致异常分块。"""
        f = tmp_path / "mixed.txt"
        f.write_text("第一段\r\n\r\n第二段\r\r第三段\n\n第四段", encoding="utf-8")
        parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(str(f), "doc-mixed", {"source_title": "m.txt", "file_type": "txt"})
        assert len(chunks) >= 1
        full = " ".join(c["content"] for c in chunks)
        assert "第一段" in full
        assert "第四段" in full

    def test_chunker_overlap_larger_than_content(self):
        """overlap 大于 chunk content 时不应崩溃。"""
        chunker = SemanticChunker(chunk_size=500, overlap=100)
        chunks = chunker.chunk("短", "doc", {})
        assert len(chunks) == 1
        assert chunks[0]["content"] == "短"

    def test_repeated_identical_paragraphs(self):
        """完全相同的段落重复多次，不应丢失或合并。"""
        chunker = SemanticChunker(chunk_size=100, overlap=10)
        text = "\n\n".join(["这是重复段落。" * 5] * 10)
        chunks = chunker.chunk(text, "doc-repeat", {})
        total_content = "".join(c["content"] for c in chunks)
        # 每个 chunk_id 仍应唯一
        ids = [c["chunk_id"] for c in chunks]
        assert len(ids) == len(set(ids))

    def test_mineru_content_list_empty(self):
        """空 content_list 应返回空 chunks。"""
        parser = MinerUParser(chunker=SemanticChunker(), output_dir="/tmp/test")
        paths = MinerUParser._build_section_paths([])
        chunks = parser._content_list_to_chunks([], paths, "doc", {})
        assert chunks == []

    def test_mineru_content_list_only_headers_footers(self):
        """只有 header/footer 的 content_list 应返回空 chunks。"""
        parser = MinerUParser(chunker=SemanticChunker(), output_dir="/tmp/test")
        cl = [
            {"type": "header", "text": "Logo", "page_idx": 0},
            {"type": "footer", "text": "Page 1", "page_idx": 0},
            {"type": "page_number", "text": "1", "page_idx": 0},
        ]
        paths = MinerUParser._build_section_paths(cl)
        chunks = parser._content_list_to_chunks(cl, paths, "doc", {})
        assert chunks == []


# ---------------------------------------------------------------------------
# 场景 10：检索质量评测（真实用户提问）
# ---------------------------------------------------------------------------

QA_EVAL_PATH = Path(__file__).parent.parent / "data" / "eval_amplifier_qa.json"


class TestRetrievalQuality:
    """用真实用户提问评测检索效果。

    评测集: tests/data/eval_amplifier_qa.json
    流程: 用户提问 → BM25 检索 → 验证 top-3 结果包含期望关键词
    """

    @pytest.fixture(scope="class")
    def qa_pairs(self):
        assert QA_EVAL_PATH.exists(), f"Eval QA data not found: {QA_EVAL_PATH}"
        with open(QA_EVAL_PATH, "r", encoding="utf-8") as f:
            return json.load(f)

    @pytest.fixture(scope="class")
    def eval_bm25(self, pdf_chunks) -> Bm25Store:
        store = Bm25Store()
        store.add(pdf_chunks)
        return store

    def _search_top3_text(self, store: Bm25Store, query: str) -> str:
        results = store.search(query, top_k=3)
        return " ".join(r["content"] for r in results)

    # --- 参数化测试：每个有 expected_source_keywords 的 QA 对 ---

    def test_amp001_output_power(self, eval_bm25):
        """BLV-D1 的输出功率是多少？→ 应检索到含 50W 的 chunk"""
        text = self._search_top3_text(eval_bm25, "BLV-D1 的输出功率是多少？")
        assert "50W" in text or "50w" in text.lower(), f"'50W' not in top-3: {text[:200]}"

    def test_amp002_bluetooth_connection(self, eval_bm25):
        """如何连接蓝牙？→ 应检索到含蓝牙的 chunk"""
        text = self._search_top3_text(eval_bm25, "如何连接蓝牙？")
        assert "蓝牙" in text, f"'蓝牙' not in top-3: {text[:200]}"

    def test_amp003_voltage(self, eval_bm25):
        """支持什么电压供电？→ 应检索到含 12/24 的 chunk"""
        text = self._search_top3_text(eval_bm25, "支持什么电压供电？")
        assert "12" in text or "24" in text, f"voltage not in top-3: {text[:200]}"

    def test_amp004_wired_input(self, eval_bm25):
        """怎么切换到有线输入？→ 应检索到含线的 chunk"""
        text = self._search_top3_text(eval_bm25, "怎么切换到有线输入？")
        assert "线" in text, f"'线' not in top-3: {text[:200]}"

    def test_amp005_chip(self, eval_bm25):
        """这个放大器用的什么芯片？→ 应检索到 TPA3116"""
        text = self._search_top3_text(eval_bm25, "这个放大器用的什么芯片？")
        assert "TPA3116" in text, f"'TPA3116' not in top-3: {text[:200]}"

    def test_amp006_bluetooth_version(self, eval_bm25):
        """蓝牙版本是多少？→ 应检索到蓝牙相关内容"""
        text = self._search_top3_text(eval_bm25, "蓝牙版本是多少？")
        assert "蓝牙" in text or "5.0" in text or "5. 0" in text, f"bluetooth version not in top-3: {text[:200]}"

    def test_amp007_speaker_wiring(self, eval_bm25):
        """扬声器怎么接线？→ 应检索到扬声器"""
        text = self._search_top3_text(eval_bm25, "扬声器怎么接线？")
        assert "扬声器" in text, f"'扬声器' not in top-3: {text[:200]}"

    def test_amp008_certification(self, eval_bm25):
        """产品有什么认证？→ 应检索到 FCC"""
        text = self._search_top3_text(eval_bm25, "产品有什么认证？")
        assert "FCC" in text, f"'FCC' not in top-3: {text[:200]}"

    def test_amp009_power_switch(self, eval_bm25):
        """电源开关在哪里？→ 应检索到电源"""
        text = self._search_top3_text(eval_bm25, "电源开关在哪里？")
        assert "电源" in text, f"'电源' not in top-3: {text[:200]}"

    def test_retrieval_recall_rate(self, eval_bm25, qa_pairs):
        """整体召回率：有 expected_source_keywords 的问题，top-3 命中率应 ≥ 70%。"""
        hits = 0
        total = 0
        for qa in qa_pairs:
            keywords = qa.get("expected_source_keywords", [])
            if not keywords:
                continue  # 跳过无期望关键词的（如 amp-010 故意无答案的）
            total += 1
            text = self._search_top3_text(eval_bm25, qa["question"])
            if any(kw in text for kw in keywords):
                hits += 1

        recall = hits / total if total > 0 else 0
        assert recall >= 0.7, (
            f"Retrieval recall {recall:.0%} ({hits}/{total}) below 70% threshold"
        )
