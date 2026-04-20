# 文档解析测试标准

> 日期：2026-04-09 | 定位：本项目文档解析模块的测试规范

---

## 一、回归测试标准（Regression Testing Standard）

回归测试的目标：**确保新改动不破坏已有行为**。不是发现新 bug，而是守住已验证的基线。

### 1.1 回归测试必须满足的特性

| 特性 | 要求 | 反例 |
|------|------|------|
| **确定性** | 同一输入永远产出同一结果 | 随机种子未固定、依赖外部服务 |
| **幂等性** | 重复运行结果不变 | 写入了全局状态但没清理 |
| **独立性** | 用例之间无顺序依赖 | test_B 依赖 test_A 的副作用 |
| **基线对比** | 对比 golden data，而非只断言"有结果" | `assert len(chunks) > 0` 不是回归测试 |
| **覆盖关键路径** | 每个 parser、每种文件类型、每个处理分支 | 只测了 PDF 没测 DOCX |
| **性能守卫** | 耗时不超过基线的 N 倍 | 解析慢 10 倍无人发现 |
| **自动化** | pytest 标记 + CI 可运行 | 需要人肉检查输出 |

### 1.2 回归测试的层次

```
Level 1: 单元回归（chunker、parser 各方法）
  → tests/core/test_chunker.py, test_mineru_parser.py, test_document_processor.py

Level 2: 集成回归（parser + chunker + BM25 端到端）
  → tests/integration/test_pdf_parsing.py

Level 3: Golden data 回归（解析结果 vs 快照）
  → tests/regression/test_golden_*.py  ← 缺失，需新建

Level 4: 性能回归（耗时 + 内存 baseline）
  → tests/regression/test_perf_*.py    ← 缺失，需新建
```

### 1.3 Golden Data 回归的做法

```
首次运行:
  parse(功放说明书.pdf) → 生成 chunks → 保存为 golden_amplifier.json

后续每次:
  parse(功放说明书.pdf) → 生成 chunks → 与 golden_amplifier.json 对比
  - chunk 数量相同
  - 每个 chunk 的 content_type 相同
  - 每个 chunk 的 content 文本相似度 > 0.95（允许微小差异）
  - metadata 结构字段一致
```

更新基线的流程：
```bash
# 有意改变了解析逻辑后，重新生成基线
.venv/bin/pytest tests/regression/ --update-golden
# 审查 diff → git commit golden data
```

---

## 二、解析测试标准（Parsing Quality Standard）

解析测试的目标：**验证文档解析的质量达标**。关注提取的完整性、准确性、结构化程度。

### 2.1 五个质量维度

#### 维度 1：提取完整性（Extraction Completeness）

| 指标 | 计算方式 | 达标阈值 |
|------|---------|---------|
| 关键词覆盖率 | 文档中已知关键词被提取到的比例 | ≥ 95% |
| 页面覆盖率 | 产出 chunk 覆盖的页面 / 总页面数 | ≥ 90% |
| 字符保留率 | 提取字符数 / 预期字符数（人工标注或 OCR 基线） | ≥ 80% |
| 无空 chunk | 所有 chunk 的 content 非空 | 100% |

测试方法：
```python
# 关键词覆盖
GOLDEN_KEYWORDS = ["蓝牙", "音频", "放大器", "BLV-D1", ...]
coverage = sum(1 for kw in GOLDEN_KEYWORDS if kw in full_text) / len(GOLDEN_KEYWORDS)
assert coverage >= 0.95

# 页面覆盖
pages_covered = set(c["metadata"]["page"] for c in chunks if c["metadata"]["page"] is not None)
assert len(pages_covered) / total_pages >= 0.9
```

#### 维度 2：分块质量（Chunking Quality）

| 指标 | 计算方式 | 达标阈值 |
|------|---------|---------|
| Chunk 大小方差 | std(chunk_sizes) / mean(chunk_sizes) | CV < 0.5 |
| Overlap 有效率 | 相邻 chunk 有有效 overlap 的比例 | ≥ 70% |
| 无碎片 chunk | content 长度 > 20 字符的比例 | 100% |
| 无超大 chunk | content 长度 < 2x chunk_size 的比例 | 100% |
| 句终符结尾率 | chunk 以。！？等结尾的比例 | ≥ 50%（中文文档） |

#### 维度 3：结构化程度（Structure Preservation）

| 指标 | 计算方式 | 达标阈值 |
|------|---------|---------|
| content_type 多样性 | 不同 content_type 的数量 | ≥ 3（对含图表的文档） |
| 表格 HTML 保留 | table chunk 中含 `<table>` 标签 | 100% |
| Section path 非空率 | section 字段非空的 chunk 比例 | ≥ 80%（有标题的文档） |
| Page 标注率 | page 字段非 None 的 chunk 比例 | ≥ 90% |
| 标题不独立成 chunk | heading 不作为 chunk content | 100% |
| Header/Footer 过滤 | 页眉页脚不出现在 chunk 中 | 100% |

#### 维度 4：检索有效性（Retrieval Effectiveness）

| 指标 | 计算方式 | 达标阈值 |
|------|---------|---------|
| BM25 命中率 | 预设查询命中相关 chunk 的比例 | ≥ 80% |
| BM25 排序正确性 | 相关 chunk 排在 top-3 的比例 | ≥ 70% |
| 无关查询抑制 | 无关查询的 top-1 score 低于阈值 | score < 5.0 |
| 跨类型检索 | 表格/图片 chunk 可被关键词检索到 | 有命中 |

#### 维度 5：Metadata 一致性（Metadata Consistency）

| 指标 | 计算方式 | 达标阈值 |
|------|---------|---------|
| 必填字段完整性 | chunk_id/doc_id/content/metadata 齐全 | 100% |
| metadata 子字段完整性 | content_type/page/section/chunk_index 齐全 | 100% |
| chunk_id 唯一性 | 无重复 chunk_id | 100% |
| chunk_index 连续性 | 0, 1, 2, ... 无跳跃 | 100% |
| doc_id 一致性 | 同文档所有 chunk 的 doc_id 相同 | 100% |
| source_title 传播 | 原始文件名正确传播到所有 chunk | 100% |

### 2.2 测试矩阵（文档类型 × 质量维度）

| 文档类型 | 提取完整性 | 分块质量 | 结构化 | 检索 | Metadata |
|---------|-----------|---------|--------|------|----------|
| **纯文本 TXT** | ✅ 关键词 | ✅ 大小/overlap | N/A | ✅ BM25 | ✅ 字段 |
| **FAQ TXT** | ✅ Q&A 对数 | N/A（原子 chunk） | ✅ type=faq | ✅ 问题检索 | ✅ question 字段 |
| **数字 PDF** | ✅ 关键词+页面 | ✅ 全套 | ✅ 表格/图片/section | ✅ 全套 | ✅ 全套 |
| **扫描 PDF** | ✅ OCR 关键词 | ✅ 大小 | ⚠️ OCR 可能降级 | ✅ BM25 | ✅ 字段 |
| **DOCX** | ✅ 关键词 | ✅ 大小/overlap | ✅ 表格 | ✅ BM25 | ✅ 字段 |

### 2.3 DefaultParser vs MinerU 对比测试

同一份 PDF 分别用两个 parser 解析，对比：

| 对比项 | DefaultParser 预期 | MinerU 预期 |
|--------|-------------------|-------------|
| chunk 数 | 较少（纯文本） | 较多（多类型） |
| content_type | 全部 "text" | text + table + image + formula |
| 表格内容 | 拉平为纯文本 | HTML 结构保留 |
| section path | 全部 None | 有层级路径 |
| page 字段 | 全部 None | 有页码 |
| 图片信息 | 丢失 | 有 img_path + caption |

---

## 三、当前 test_pdf_parsing.py 的差距与改进方向

### 已覆盖 ✅

- 提取完整性（关键词、字符数范围、中英文混合）
- 分块质量（大小范围、overlap 有效率、无碎片）
- Metadata 一致性（字段完整、chunk_id 唯一、index 连续）
- BM25 检索（关键词命中、排序、无关查询抑制）
- MinerU content_list 分流（模拟数据，5 种类型）
- Parser 注册优先级

### 缺失需补充 🔲

| 缺失项 | 优先级 | 说明 |
|--------|--------|------|
| **Golden data 对比** | P1 | 保存一次解析快照，后续对比 |
| **性能守卫** | P1 | 解析 + 分块耗时 < 基线 2x |
| **边界 case** | P1 | 空文件、损坏 PDF、超长单段落、纯图片 PDF |
| **DOCX 回归** | P2 | 当前只测了 PDF |
| **MinerU 真实输出测试** | P2 | 安装 MinerU 后用 smoke 标记 |
| **DefaultParser vs MinerU 对比** | P2 | 同一 PDF 两种 parser 的输出对比 |
| **页面覆盖率** | P3 | 验证 7 页 PDF 的所有页面都有 chunk |
| **句终符结尾率** | P3 | 统计中文句号结尾的比例 |
