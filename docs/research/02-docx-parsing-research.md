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

## 10. .doc vs .docx 格式差异（2026-04-16）

### 10.1 本质区别

| | .doc (OLE2) | .docx (OOXML) |
|---|---|---|
| **诞生** | 1997，Word 97 | 2007，Word 2007 |
| **格式** | **二进制复合文档**（OLE2 容器） | **ZIP 压缩包**（内含 XML + 媒体文件） |
| **图片存储** | 嵌入在 `Data` 二进制流中，无标准路径 | `word/media/image1.png` 独立文件 |
| **表格** | 二进制结构体（TAP），需专用解析器 | `<w:tbl>` XML 节点，结构清晰 |
| **样式** | 二进制样式表（`0Table`/`1Table` 流） | `word/styles.xml` |
| **可读性** | 不可读，必须用专用库 | 解压即可看到 XML |

两种**完全不同的文件格式**，只是都叫 "Word 文档"。

### 10.2 .doc 内部 OLE2 结构

```
.doc (OLE2 复合文档)
├── WordDocument      ← 主文档流（二进制，文字+格式混在一起）
├── 0Table / 1Table   ← 格式信息（表格属性也在这里）
├── Data              ← 嵌入的图片/OLE对象（二进制 blob）
├── CompObj           ← 复合对象信息
└── \001Ole           ← OLE 元信息
```

对比 .docx：
```
.docx (ZIP)
├── word/document.xml     ← 文字（XML，结构清晰）
├── word/media/image1.png ← 图片（独立文件，直接读取）
└── word/styles.xml       ← 样式（XML）
```

### 10.3 .doc 各提取方案可行性

| 方案 | 文本 | 图片 | 表格 | 样式 | 部署成本 |
|------|------|------|------|------|---------|
| **textutil**（macOS 自带） | ✅ 有域代码污染 | ❌ | ❌ | ❌ | 零 |
| **Apache Tika** | ✅ 干净 | ❌ | ❌ | ❌ | 中（需 JRE ~300MB） |
| **LibreOffice 转 .docx** | ✅ 干净 | ✅ | ✅ | ✅ | 高（~1.5GB） |
| **olefile 手动提取** | 部分 | 部分 ✅ | ❌ | ❌ | 轻量（pip） |
| **用户手动另存 .docx** | ✅ | ✅ | ✅ | ✅ | 零（但需人工） |

### 10.4 olefile 图片提取验证

用 `internet-file.doc`（10.4MB，WPS 创建）验证：

```
OLE2 内部流：
  WordDocument   7,668,690 bytes
  Data           3,078,569 bytes  ← 图片在这里
  0Table            43,709 bytes
```

从 `Data` 流按 PNG 签名（`\x89PNG...IEND`）扫描，成功提取 11 张图片：

| 图片 | 尺寸 | 大小 | 内容 |
|------|------|------|------|
| 0 | 680×680 | 8KB | 公司 Logo |
| 1 | 865×193 | 130KB | 产品图 |
| 2 | 865×1589 | 1.2MB | 产品详情图 |
| 3 | 501×298 | 186KB | 教室示意图 |
| ... | ... | ... | ... |
| 10 | 1647×1092 | 184KB | 布局方案图 |

**结论**：olefile + 签名扫描提取 PNG/JPEG 完全可行，但有两个局限：
1. **无法关联到具体段落**（只知道文档内的大致顺序）
2. **WMF/EMF 矢量图**需要额外转换

## 11. DocxParser 代码审查（Critic Review，2026-04-16）

### 11.1 审查结论：REVISE

核心架构正确（body 遍历保序、heading 层级栈、表格合并处理、图片提取 + OCR、上下文融合），对**规范的 .docx** 工作良好。问题在于对**真实世界脏输入零防御**。

### 11.2 问题责任划分

| 责任方 | 问题 |
|--------|------|
| **textutil 转换** | 图片丢失（10.4MB→11KB）、表格消失、Heading 样式丢失 |
| **DocxParser 自身** | 域代码泄漏、无输入校验、无降级检测 |

### 11.3 必须修复（Critical）

**C1: 零文本清洗 — 域代码直接灌入 RAG 向量库**

`docx_parser.py:125` 的 `para.text.strip()` 不做任何过滤。当 textutil/WPS 等工具把域指令（`TOC \o "1-2"`、`HYPERLINK \l _Toc...`、`PAGEREF ... \h 2`、`PAGE 37`）平铺成 `w:t` 文本时，垃圾直接成为 chunk 内容，污染嵌入向量和检索结果。

**修复方向**：增加 `_clean_text()` 方法，正则过滤 `TOC \o`、`HYPERLINK \l`、`PAGEREF`、`NUMPAGES`、`PAGE \d+` 等域标记。

**C2: 无 .doc 格式支持策略**

`can_handle` 只认 `"docx"`，pipeline 没有 `.doc` 的检测、拒绝或转换路径。用户使用 textutil 等工具自行转换，产生劣质输入且系统无任何提示。

**修复方向**：检测 `.doc` 明确报错推荐转换方案，或集成 olefile 文本+图片提取作为降级路径。

### 11.4 建议改进（Major）

| # | 问题 | 说明 | 改进方向 |
|---|------|------|---------|
| M1 | Heading 检测无降级 | `para.style.name.startswith("Heading")` 在非标准 .docx 中失败 | 增加后备：`pPr/outlineLvl`、字号/加粗启发式、中文结构模式 |
| M2 | 无解析质量检测 | 大文档 0 图片 + 0 表格 + 0 标题完全沉默 | `_walk_body` 后统计类型分布，异常时 WARNING |
| M3 | OCR 引擎 `False` 哨兵值 | `None`（未初始化）和 `False`（失败）用 truthy/falsy 区分 | 用显式枚举或 sentinel 对象 |
| M4 | 无文本标准化 | 全角空格、NFC/NFKC 未处理 | 参考 RAGFlow 的 `\u3000` 替换 |

## 12. RAGFlow vs MinerU 深度对比（2026-04-16）

### 12.1 架构对比

| 模块 | RAGFlow | MinerU | 我们的 DocxParser |
|------|---------|--------|-------------------|
| **核心库** | python-docx | python-docx + mammoth + lxml | python-docx |
| **表格** | python-docx → HTML，colspan 启发式 | **mammoth 全文档预解析** → HTML，失败回退 XML | python-docx → Markdown，vMerge XML |
| **图片** | `pic:pic` XPath + LazyImage | `a:blip` XPath + Pillow 格式转换 | `pic:pic` XPath + PaddleOCR |
| **标题** | `Heading\s*\d+` 正则，无降级 | 样式名 + **列表编号预扫描**（`heading_list_numids`） | 样式名，无降级 |
| **域代码/TOC** | 不处理，依赖 `p.text` 自动跳过 | **预收集 `_Toc` 锚点**，TOC 转 INDEX block | 不处理 |
| **公式** | 不处理 | OMML → LaTeX（`oMath2Latex`） | 不处理 |
| **超链接** | `document.part.rels` 提取 URL | 三种形式：`w:hyperlink` / `fldChar` / TOC 锚点 | 不处理 |
| **图片 OCR** | Vision LLM（需 API） | 不做 OCR | **PaddleOCR 本地 OCR** ✅ |
| **.doc 支持** | Apache Tika 纯文本 | ❌ 不支持 | ❌ 不支持 |
| **代码量** | ~400 行 | ~2700 行（DocxConverter） | ~460 行 |

### 12.2 MinerU 值得借鉴的 3 个设计

**① 表格用 mammoth 全文档预解析**

mammoth 在完整文档上下文中转换表格，能正确处理：
- 表格内的列表项（需要 `word/numbering.xml`）
- 表格内的图片（需要关系文件）
- 表格内的样式继承

逐个表格孤立解析会丢失这些上下文。

**② TOC 锚点预收集**

```python
self.toc_anchor_set = self._collect_toc_anchor_set()
# 遇到 TOC 段落 → 识别为 INDEX block，不当正文处理
```

解决域代码泄漏的另一种思路：不是清洗域代码，而是**识别并归类为目录 block**。

**③ 列表编号标题检测**

很多中文文档用编号列表做标题（"一、概述"、"1.1 背景"），样式名是 `ListParagraph` 不是 `Heading`。MinerU 预扫描识别这类 numId，当作标题处理。

### 12.3 域代码问题的根因分析

RAGFlow 和 MinerU 都不主动清洗域代码，因为**正规 .docx 中不是问题**：

- `python-docx` 的 `p.text` 只拼接 `w:t` 节点
- 正规 OOXML 把域指令放在 `w:instrText`（不在 `w:t`），所以自动跳过
- **textutil 转换**打破了这个假设——它把域结构打平成普通 `w:t` 文本

因此域代码泄漏的根因是**输入质量劣化**，但 parser 仍应有防御性清洗。

## 13. .doc 推荐处理策略（2026-04-16）

### 13.1 综合方案

```
.doc 输入
  ├── 文本 → textutil（macOS）/ catdoc（Linux）+ _clean_text() 清洗
  ├── 图片 → olefile 按签名提取 → PaddleOCR OCR（按文档顺序，但无段落级锚点）
  ├── 表格 → ❌ 放弃（二进制 TAP 解析不可行）
  └── metadata → 标记 degraded: true，提示用户转 .docx 获得完整解析
```

比 RAGFlow（Tika 只提文本）多了**图片 OCR**，对 RAG 检索质量有实际帮助。

### 13.2 待决策事项

以下问题需要在实施前明确：

1. **采用 MinerU 模式（mammoth 双轨）还是在当前基础上迭代？**
   - MinerU 模式：表格质量更高，但代码量大幅增加（~2700 行 vs ~460 行）
   - 迭代模式：优先修 Critical 问题（`_clean_text()` + `.doc` 降级），逐步引入 mammoth
2. **基于当前版本还是新建版本？**
   - 当前版本测试覆盖完善（26 个单元测试），改动需保持兼容
   - 新版本可以重构但需重建测试
3. **.doc 支持的优先级？** — 取决于目标知识库中 .doc 文件的占比

### 13.3 建议的优先级排序

| 优先级 | 改进项 | 复杂度 | 收益 |
|--------|--------|--------|------|
| **P0** | `_clean_text()` 域代码清洗 | 低 | 直接修复检索质量 |
| **P0** | 全角空格等文本标准化 | 低 | 与清洗一起做 |
| **P1** | TOC 识别（参考 MinerU `toc_anchor_set`） | 中 | 避免目录污染 |
| **P1** | 解析质量检测 + WARNING 日志 | 低 | 运维可观测性 |
| **P2** | 表格改用 mammoth 预解析 | 中 | 表格内列表/图片支持 |
| **P2** | .doc 文本提取 + olefile 图片提取 | 中 | 新格式支持 |
| **P3** | Heading 降级启发式 | 中 | 非标准 .docx 兼容 |
| **P3** | 列表编号标题检测 | 中 | 中文文档结构识别 |
