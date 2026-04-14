# DOCX 解析方案调研报告

> 日期：2026-04-14 | 项目：RAG 客服系统 | 分支：feat/paddleocr-parser

## 1. 需求背景

RAG 系统需要解析 Word 文档，文档中包含：
- **图文混排** — 文本与图片交错排列
- **表格** — 含合并单元格
- **图片中的中文字** — 需要 OCR 识别（核心需求）

现有系统中 `DefaultParser` 处理 DOCX 只提取段落纯文本，丢失表格和图片内容。

## 2. 方案全景对比

| # | 方案 | 原理 | 图片OCR | 表格 | 图文位置 | 外部依赖 | 代码量 |
|---|------|------|---------|------|----------|----------|--------|
| A | DOCX → PDF → PaddleOCR | LibreOffice 转 PDF，PP-StructureV3 全链路 | ✅ 内置 | ✅ 强 | ✅ 版面级 | LibreOffice ~200MB | 小 |
| B | python-docx + PaddleOCR | python-docx 提文本/表格，图片单独 OCR | ✅ 手动调 | ✅ 原生 | ✅ body 遍历保序 | 无 | 中 |
| C | DOCX → 图片 → PaddleOCR | 每页渲染为图片，全部当扫描件 OCR | ✅ 内置 | ✅ 强 | ✅ 保留 | LibreOffice / pdf2image | 中 |
| D | Pandoc → Markdown + OCR | `pandoc docx → md --extract-media`，图片单独 OCR | ✅ 手动调 | ✅ 中 | ⚠️ Markdown 级 | Pandoc CLI | 中 |
| E | mammoth → HTML → 提取 | mammoth 转语义 HTML，解析 DOM | ❌ 需补 | ✅ 中 | ⚠️ 部分 | mammoth | 中 |
| F | 云端 API（Graph/Google） | 上传云端解析 | ✅ 云端 | ✅ 强 | ✅ 保留 | 云服务账号 | 中 |
| G | MinerU 原生 DOCX | MinerU 新版原生支持 | ❌ 不OCR | ✅✅ 强 | ✅ 线性 | MinerU + torch | 小 |
| H | docx2python 深度提取 | 比 python-docx 更底层 | ✅ 手动调 | ✅ 中 | ⚠️ 段落级 | 无 | 大 |
| I | Unstructured.io | 开源文档解析库 | ✅ 内置策略 | ✅ 强 | ✅ 保留 | 依赖链重 | 小 |
| J | MarkItDown + PaddleOCR | 微软 MarkItDown 转 Markdown，图片单独 OCR | ✅ 手动调 | ✅ mammoth | ⚠️ inline 级 | markitdown | 中 |
| K | python-docx + Vision LLM | RAGFlow 方式，图片发给 GPT-4V/Qwen-VL | ✅ LLM | ✅ HTML | ✅ 线性 | LLM API | 中 |

## 3. 开源框架实现分析

### 3.1 RAGFlow（infiniflow/ragflow）

- **库**：python-docx
- **文本**：遍历 `doc._element.body` 保持文档顺序
- **表格**：渲染成 HTML `<table>`，支持合并单元格，注入最近标题作为 `<caption>`
- **图片**：XPath 提取 `<pic:pic>` blob，发给 Vision LLM（GPT-4V/Qwen-VL）做描述
- **图文位置**：body 遍历保序；独立图片用 `last_image` 缓冲关联下一个文本段；Caption 样式自动合并
- **局限**：**不做本地 OCR**，无 Vision LLM 则图片内文字丢失
- **代码位置**：`deepdoc/parser/docx_parser.py` + `rag/app/naive.py`

### 3.2 MinerU（opendatalab/MinerU）

- **库**：python-docx + lxml + mammoth（表格专用）
- **文本**：`_walk_linear(body)` 按 XML 元素类型分发处理
- **表格**：mammoth 全文预解析 HTML + OMML 公式注入 + colspan 修复（最强表格处理）
- **图片**：提取 blob + base64 编码，**不做 OCR**
- **图文位置**：线性顺序保留，浮动图片先文本后图片；Caption 通过启发式前缀匹配（"图"/"fig"/"表"/"table"）
- **额外能力**：文本框提取、DrawingML 图表（读嵌入 xlsx）、OMML → LaTeX 公式
- **局限**：**图片不 OCR**；WMF/EMF 在 macOS/Linux 上变灰色占位符
- **代码位置**：`mineru/model/docx/docx_converter.py`（~2700 行），PR #4564，2026-03-03 合并

### 3.3 MarkItDown（microsoft/markitdown）

- **库**：mammoth（底层）
- **DOCX → Markdown**：文本+表格+标题层级保留
- **图片**：检测到但不 OCR，输出 `![](...)` 占位
- **图文位置**：inline 图片准确，浮动图片可能错位（mammoth 限制）
- **优势**：纯 pip install，轻量；输出 Markdown 可直接复用 `_parse_markdown()`

## 4. 关键技术点

### 4.1 DOCX 图片的两种存储方式

| 类型 | XML 标签 | 位置 | python-docx 可达性 |
|------|----------|------|-------------------|
| Inline（嵌入式） | `<wp:inline>` | 在段落文本流中 | ✅ XPath `.//pic:pic` |
| Floating（浮动式） | `<wp:anchor>` | 锚定在段落，有坐标偏移 | ✅ XPath `.//pic:pic`（同样能拿到） |

**关键发现**：两种图片在 XML 层面都在 `<w:p>` 内，遍历 `doc._element.body` 都能捕获。浮动图片的"丢失"问题主要是 mammoth/python-docx 高级 API 的限制，用 XPath 直接查 XML 可以解决。

### 4.2 图片提取代码模式

```python
NSMAP = {
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
}

def extract_images(paragraph, doc):
    for pic in paragraph._element.findall(".//pic:pic", NSMAP):
        blip = pic.find(".//a:blip", NSMAP)
        embed = blip.get(f'{{{NSMAP["r"]}}}embed')
        blob = doc.part.related_parts[embed].image.blob
        yield blob
```

## 5. 最终选型

### 选定方案：B — python-docx + PaddleOCR

```
DOCX → python-docx 遍历 body → 文本直接提取（精确）
                              → 表格渲染 Markdown（原生支持合并单元格）
                              → 图片 XPath 提取 blob → PaddleOCR OCR 中文
     → 输出结构化 Markdown → 复用 _parse_markdown() → chunks
```

### 选型理由

| 维度 | 评价 |
|------|------|
| **图片中文 OCR** | ✅ 唯一的纯本地方案（RAGFlow 要 LLM API，MinerU 不 OCR） |
| **纯文本精度** | ✅ 直接提取不走 OCR，零误差（优于方案 A 全页 OCR） |
| **外部依赖** | ✅ 无 — python-docx 已在项目中，PaddleOCR 已集成 |
| **代码复用** | ✅ 复用现有 `_parse_markdown()` + PaddleOCR 引擎 |
| **表格** | ✅ python-docx 原生支持，后续可引入 mammoth 增强 |
| **图文位置** | ✅ body 遍历保序，RAGFlow 已验证可行性 |
| **部署** | ✅ 纯 pip install，无 LibreOffice/Pandoc |

### 后续增强方向

1. 表格处理：如果 python-docx 原生表格不够，引入 mammoth（参考 MinerU）
2. 公式支持：OMML → LaTeX（参考 MinerU 的 `oMath2Latex`）
3. 文本框提取：XPath 查 `<mc:txbxContent>`（参考 MinerU）

## 6. 解析质量验证方案

### 三层验证体系

| 层级 | 方法 | 验证目标 |
|------|------|----------|
| Layer 1 | 可视化对比报告 | 人工确认大方向正确 |
| Layer 2 | 自动化评测（文本覆盖率 + 表格 cell 命中率 + 图片关键词召回） | CI 可跑的回归测试 |
| Layer 3 | 端到端 RAG 检索评测（Hit@1/Hit@3/MRR，按 source_type 分组） | 检索质量 |

### 图片 OCR 评测

基于 golden data 关键词召回：
```json
{
  "images": [
    {"index": 0, "keywords": ["BLV-D1", "蓝牙", "放大器"], "expected_ocr_text": "BLV-D1 蓝牙放大器"}
  ]
}
```

## 7. 实现过程中修复的 Bug

| Bug | 原因 | 修复方式 |
|-----|------|----------|
| 纵向合并单元格文本重复 | python-docx `merge()` 拼接文本 + `row.cells` 返回重复 `_tc` | `id(cell._tc)` 去重 + `<w:vMerge>` 检测 continuation cell + master cell 内文本行去重 |
| Heading 层级丢失 | 单变量 `current_heading` 被子标题覆盖 | 改为 `heading_stack: list[tuple[int, str]]`，section 输出 `"H2 > H3"` 路径 |
| PaddleOCR 3.x API 不兼容 | `ocr()` + `cls` 参数废弃，`predict()` 不接受 PIL Image | 改用 `predict(numpy_array)`，结果用 `page_result.get("rec_texts")` |

## 8. OCR 错误处理决策（2026-04-14）

### 决策：当前不做 OCR 纠错

**依据：** 对 6 张测试图片的实测数据（`tests/data/eval_results/docx_ocr_eval_result.json`）

### OCR 置信度分析

| 图片 | OCR 结果 | 置信度 | 错误类型 |
|------|----------|--------|----------|
| 面板标识 | BLV-D1蓝牙功放50Wx2 | 0.952 | ×→x 微小 |
| 接口标注 | N/USB-C/SPKL/R/DC12-24V | 0.931 | AUX IN 丢失（检测器漏检） |
| 步骤1 | 骤1：连接电源适配器DC12V | 0.972 | 首字截断 |
| 步骤2 | 步骤2：连接音箱线左右声道 | 0.951 | OK |
| 指示灯 | 指示灯位置示意图前面板左侧 | 0.968 | OK |
| 保修 | 买修期限12个月... | 0.972 | 保→买 形近字 |

**关键发现：** 所有置信度 > 0.93，包括错误结果。置信度过滤方案无效。

### 检索容错验证

8 个测试问题，**8/8 全部命中（100%）**，包括：
- "保修期限是多久？" → OCR 写成"买修"但"12个月"关键词匹配成功
- "保修条款的内容？" → 上下文融合中的"保修条款"提供了匹配
- "产品背面有哪些接口？" → OCR 丢了"AUX"但表格 chunk 有完整数据

**结论：** 上下文融合 + BM25/向量混合检索已经兜住了 OCR 错误，无需额外纠错。

### 被否决的方案

| 方案 | 否决原因 |
|------|----------|
| 图片预处理（加白边+放大） | Critic 挑战：对"AUX IN 丢失"无效（是检测器漏检不是边缘裁剪）；对测试文档优化可能伤害其他文档；检索已 100%，ROI 低 |
| 置信度过滤（0.8/0.5 阈值） | 数据证伪：所有错误置信度 > 0.93，阈值无论怎么设都无效 |
| 领域词典纠错 | 不可扩展：手工维护，只对已知文档有效 |
| LLM 纠错 | 成本高，当前不需要 |

### 后续触发条件

以下情况出现时重新评估 OCR 纠错：
- 真实用户文档的检索命中率低于 80%
- 出现 OCR 错误导致关键信息完全不可检索（无其他 chunk 兜底）
- 文档中图片占比 > 50%（当前文档以文本/表格为主）

## 9. 文件目录结构

```
tests/data/
├── docx/                              # DOCX 测试文档
│   ├── 功放说明书.docx                 # 简单版（文本+1表格+2图片）
│   ├── 功放说明书_复杂版.docx           # 复杂版（多级标题+合并单元格+6图片+列表）
│   └── images/                        # 生成的测试图片（含中文）
│       ├── complex_img_*.png          # 复杂版用
│       └── test_*_image.png           # 简单版用
├── eval_results/                      # 评测结果
│   ├── docx_smoke_功放说明书.json       # 简单版冒烟测试 6/6 PASS
│   ├── docx_smoke_功放说明书_复杂版.json # 复杂版冒烟测试 10/10 PASS
│   └── docx_ocr_eval_result.json      # OCR 质量 + 检索容错评测
├── eval_amplifier_qa.json             # QA 评测集
├── golden_amplifier_default.json      # Golden data 基线
├── 功放说明书.pdf                      # PDF 测试文档
└── ...                                # 其他已有文件
```
