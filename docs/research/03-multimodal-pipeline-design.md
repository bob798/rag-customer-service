# 多模态文档内容处理方案

> 系列文档 3/4 | [① 工具选型](./01-parsing-tools-selection.md) → [② DOCX 解析](./02-docx-parsing-research.md) ← 本文 → [④ 中文分块策略](./04-chinese-chunking-strategy.md)
>
> 调研日期：2026-04-09 | 定位：技术选型参考
> 聚焦：五层 Pipeline 各层方案选型 — 解析 → 分类 → 模态处理 → 关系建模 → Chunk

---

## 一、问题定义

现实文档不只有纯文字，还包含需要特殊处理的多模态内容：

```
文档内容
├── 纯文字段落       → 直接分块
├── 表格            → 需要结构化提取，保留行列关系
├── 图片
│   ├── 含文字的图   → OCR 提取文字
│   ├── 示意图/图表  → Vision LLM 生成描述
│   └── 装饰性图片   → 可忽略
├── 公式            → 需转为 LaTeX 或可搜索文本
└── 代码块          → 保留语法格式
```

核心挑战不仅是**识别**每种内容，更是**建模它们之间的关系**——图片与其标题、表格与其说明文字、公式与其上下文。

---

## 二、五层 Pipeline 总览与方案选型

```
原始文档 (PDF / DOCX / 图片)
    │
    ▼
[① 文档解析层] ─── MinerU（CLI wrapper）
    │                 输出：content_list.json + images/ + *.md
    │
    ▼
[② 元素分类层] ─── MinerU content_list 原生 type 字段（零开发）
    │                 text / table / image / equation / code / list / chart
    │
    ▼
[③ 模态处理层] ─── 按类型分流处理
    │   ├── text     → 直接使用 content_list 的 text 字段
    │   ├── table    → HTML 原文 + 可选 LLM 摘要
    │   ├── image    → MinerU OCR 文字 + 可选 Vision LLM 描述
    │   ├── equation → LaTeX 原文 + 可选自然语言描述
    │   └── code     → 原文保留
    │
    ▼
[④ 关系建模层] ─── content_list 原生 caption/footnote 字段 + 正文引用匹配
    │
    ▼
[⑤ 统一 Chunk 层] ─── SemanticChunker（中文修复版）+ 原子 chunk
```

---

## 三、各层详细方案

### ① 文档解析层：MinerU

**选型结论**：MinerU（CLI wrapper，`-b pipeline` 后端）

**为什么不用其他方案**：

| 方案 | 不选的原因 |
|------|-----------|
| PyMuPDF | 表格拉平、图片丢失、无 OCR |
| Unstructured | 中文效果一般，hi_res 模式慢且需额外模型 |
| Docling | 中文支持不如 MinerU，速度慢 |
| Vision LLM 整页 | 成本高、不适合批量、无法精确提取表格结构 |

**MinerU 输出结构**（关键）：

```
output_dir/
├── {filename}.md                    # 完整 Markdown（供人阅读）
├── {filename}_content_list.json     # ★ 核心：按阅读序的元素列表
├── {filename}_middle.json           # 详细层级结构（页→块→行→span）
├── {filename}_layout.pdf            # 版面分析可视化
└── images/                          # 提取的图片文件
    ├── abc123.jpg
    └── ...
```

**`content_list.json` 结构**（决定下游所有设计）：

```json
[
  {
    "type": "text",
    "text": "第一章 产品概述",
    "text_level": 1,
    "page_idx": 0,
    "bbox": [72, 100, 540, 130]
  },
  {
    "type": "text",
    "text": "本产品是一款企业级客服系统...",
    "text_level": 0,
    "page_idx": 0,
    "bbox": [72, 150, 540, 300]
  },
  {
    "type": "table",
    "img_path": "images/table_abc.jpg",
    "table_body": "<html><body><table><tr><td>功能</td><td>说明</td></tr>...</table></body></html>",
    "table_caption": ["表1：核心功能对比"],
    "table_footnote": ["注：数据截至2025年"],
    "page_idx": 1,
    "bbox": [72, 200, 540, 500]
  },
  {
    "type": "image",
    "img_path": "images/arch_diagram.jpg",
    "image_caption": ["图2：系统架构图"],
    "image_footnote": [],
    "page_idx": 2,
    "bbox": [100, 150, 500, 400]
  },
  {
    "type": "equation",
    "img_path": "images/eq_001.jpg",
    "text": "E = mc^2",
    "text_format": "latex",
    "page_idx": 3,
    "bbox": [200, 300, 400, 340]
  }
]
```

**关键认知**：MinerU 的 `content_list` 已经同时完成了**解析 + 分类 + 部分关系建模**（caption/footnote 已关联到对应元素），大幅减少了下游的工作量。

---

### ② 元素分类层：MinerU 原生 type 字段（零开发）

**方案**：直接使用 `content_list.json` 每个元素的 `type` 字段。

MinerU 提供的内容类型：

| content_list type | 说明 | 对应我们的 content_type |
|-------------------|------|----------------------|
| `text` (text_level=0) | 正文段落 | `text` |
| `text` (text_level≥1) | 标题（1=H1, 2=H2...） | `heading` |
| `table` | 表格（含 HTML body） | `table` |
| `image` | 图片（含提取文件路径） | `image` |
| `chart` | 图表 | `chart` |
| `equation` | 公式（含 LaTeX） | `formula` |
| `code` | 代码块 | `code` |
| `list` | 列表 | `text`（合入文本流） |
| `header/footer/page_number` | 页眉页脚页码 | **丢弃** |

**为什么不自建分类器**：
- MinerU 的版面分析模型（布局检测 mAP 97.5）已经是业界最高水平
- 自建分类器需要标注数据和训练，ROI 极低
- 如果 MinerU 分类错误，应在 MinerU 层面修复（上报 issue 或微调），而非在下游补救

**我们只需做一层映射**：将 MinerU 的 type 映射为我们系统的 content_type 枚举。

---

### ③ 模态处理层：按类型分流

每种类型的处理策略不同：

#### 3.1 文本 (text)

| 步骤 | 方案 | 说明 |
|------|------|------|
| 提取 | `content_list[i]["text"]` | MinerU 已提取 |
| 标题追踪 | `text_level` 字段 | 构建 section 层级路径 |
| 分块 | SemanticChunker（中文修复版） | 500 字符/chunk，中文标点分隔 |
| **可选增强** | **Contextual Retrieval** | 用 LLM 给每个 chunk 加上下文前缀 |

**Contextual Retrieval**（Anthropic 2024）是文本层最有价值的增强：
```
原始 chunk: "退款审核通过后，款项将在3-5个工作日内原路退回。"
加上下文:  "以下内容来自《客服FAQ手册》第三章'退款政策'部分。退款审核通过后，款项将在3-5个工作日内原路退回。"
```
- 一次性成本（导入时），不影响查询延迟
- Anthropic 数据：检索失败率降低 67%
- 实现：导入时用 LLM 生成 context prefix，拼接后再 embedding
- **推荐 P2 优先级**：先跑通基础 pipeline，再逐步加上

#### 3.2 表格 (table)

| 步骤 | 方案 | 说明 |
|------|------|------|
| 提取 | `content_list[i]["table_body"]` | MinerU 输出 HTML，含 rowspan/colspan |
| 标题 | `content_list[i]["table_caption"]` | MinerU 已关联 |
| 脚注 | `content_list[i]["table_footnote"]` | MinerU 已关联 |
| 存储 | **原子 chunk**，不拆分 | 拆表 = 破坏语义 |
| **可选增强** | LLM 生成表格摘要 | 提高语义检索召回率 |

**表格 chunk 组装**：
```python
content = f"[表格] {caption}\n{html_body}\n{footnote}"
# content_type = "table"
# 不经过 chunker，直接作为一个独立 chunk
```

**为什么用 HTML 而非纯文本**：HTML 表格保留行列语义，Embedding 模型和 LLM 都能理解 `<table><tr><td>` 结构，检索和生成效果显著优于拉平的纯文本。

**可选增强 — 表格摘要**（P3）：
```python
summary = llm.complete(f"用一句话概括这个表格的内容:\n{html_body}")
content = f"[表格] {caption}\n{summary}\n{html_body}"
```
摘要放在 HTML 前面，让 embedding 优先编码语义信息。

#### 3.3 图片 (image)

| 步骤 | 方案 | 说明 |
|------|------|------|
| 提取 | `content_list[i]["img_path"]` | MinerU 已提取图片文件 |
| 标题 | `content_list[i]["image_caption"]` | MinerU 已关联 |
| OCR 文字 | MinerU 内置 PaddleOCR | 含文字的图片已 OCR |
| **可选增强** | Vision LLM 生成描述 | 示意图/架构图/流程图 |

**两级策略**：

```
图片类型判断
├── 有 caption 且 caption 信息充分 → 直接用 caption 作为 chunk content
├── OCR 提取到文字 → 用 OCR 文字 + caption
└── 无文字的示意图 → Vision LLM 生成描述（P3 阶段）
```

**基础版图片 chunk**（P1，零 LLM 调用）：
```python
content = f"[图片] {caption}"
if ocr_text:
    content += f"\n{ocr_text}"
# content_type = "image"
```

**增强版**（P3，用 Vision LLM）：
```python
desc = vision_llm.describe(image_path, prompt="描述这张图片的内容和含义")
content = f"[图片] {caption}\n{desc}"
```

Vision LLM 选型：

| 方案 | 成本 | 中文效果 | 推荐度 |
|------|------|---------|--------|
| Claude Vision (claude-haiku-4-5) | 低 | 优秀 | ⭐⭐⭐⭐⭐（项目已用 LiteLLM） |
| Qwen-VL (开源) | 本地部署 | 优秀 | ⭐⭐⭐⭐（需 GPU） |
| GPT-4o | 中 | 优秀 | ⭐⭐⭐⭐ |

#### 3.4 公式 (equation)

| 步骤 | 方案 | 说明 |
|------|------|------|
| 提取 | `content_list[i]["text"]` | MinerU 输出 LaTeX |
| 格式 | `text_format: "latex"` | 已标记 |
| 存储 | 原子 chunk | LaTeX 原文 |
| **可选增强** | LLM 生成自然语言描述 | 提高检索召回率 |

**基础版**：
```python
content = f"[公式] {latex_text}"
# content_type = "formula"
```

**增强版**（P3）：
```python
desc = llm.complete(f"用自然语言解释这个公式: {latex_text}")
content = f"[公式] {desc}\n{latex_text}"
```

#### 3.5 代码 (code)

```python
content = f"[代码]\n{code_body}"
if code_caption:
    content = f"[代码] {code_caption}\n{code_body}"
# content_type = "code"
# 原子 chunk，不拆分
```

---

### ④ 关系建模层：content_list 原生 + 正文引用匹配

**核心认知**：MinerU 的 `content_list` 已经完成了大部分关系建模工作。

#### 4.1 MinerU 已处理的关系（零开发）

| 关系 | MinerU 字段 | 说明 |
|------|------------|------|
| 表格 → 标题 | `table_caption` | 已关联，列表形式 |
| 表格 → 脚注 | `table_footnote` | 已关联 |
| 图片 → 标题 | `image_caption` | 已关联 |
| 图片 → 脚注 | `image_footnote` | 已关联 |
| 阅读顺序 | content_list 数组顺序 | 已按阅读序排列 |
| 页面归属 | `page_idx` | 每个元素都有 |
| 空间位置 | `bbox` | 归一化坐标 [0, 1000] |

#### 4.2 需要自建的关系

| 关系 | 实现方案 | 优先级 |
|------|---------|--------|
| **标题层级追踪** | 扫描 `text_level` 字段，维护 section stack | **P1** |
| **正文引用匹配** | 正则匹配 "如图X所示"、"见表Y" → 关联到对应图/表 chunk | P2 |
| **相邻上下文** | 为图/表 chunk 附加前后 N 个文本块的摘要 | P2 |

**标题层级追踪**实现（P1，核心）：

```python
def build_section_path(content_list: list[dict]) -> list[str]:
    """为每个元素计算其所属的章节路径。"""
    section_stack = []  # [(level, title), ...]
    result = []
    for item in content_list:
        if item["type"] == "text" and item.get("text_level", 0) > 0:
            level = item["text_level"]
            title = item["text"]
            # 弹出同级及更低级别的标题
            while section_stack and section_stack[-1][0] >= level:
                section_stack.pop()
            section_stack.append((level, title))
        # 当前元素的 section = stack 中所有标题拼接
        path = " > ".join(t for _, t in section_stack)
        result.append(path)
    return result
```

输出示例：`"第一章 产品概述 > 1.1 核心功能 > 1.1.2 退款流程"`

这个 section path 写入每个 chunk 的 metadata，用于：
- Contextual Retrieval 的上下文生成
- 检索结果展示时的面包屑导航
- 按章节过滤检索范围

---

### ⑤ 统一 Chunk 层

所有模态的内容最终归一为统一格式的 chunk：

#### 5.1 分块策略（按类型区分）

| 类型 | 分块方式 | 说明 |
|------|---------|------|
| **text** | SemanticChunker（500字符，50 overlap，中文标点分隔） | 正常分块 |
| **table** | **原子 chunk**（不拆分） | 拆表 = 破坏行列语义 |
| **image** | **原子 chunk**（不拆分） | caption + OCR/描述 合为一块 |
| **formula** | **原子 chunk**（不拆分） | LaTeX + 可选描述 合为一块 |
| **code** | **原子 chunk**（不拆分） | 代码不应被切割 |
| **heading** | **不单独存储** | 合入 section path metadata |

#### 5.2 统一 Chunk 结构

```python
{
    "chunk_id": "uuid",
    "doc_id": "uuid",
    "content": "实际文本内容",
    "metadata": {
        # --- 来源信息 ---
        "source_title": "产品手册.pdf",
        "source_path": "/data/docs/产品手册.pdf",
        "file_type": "pdf",
        # --- 内容类型 ---
        "content_type": "text|table|image|formula|code",
        # --- 位置信息 ---
        "page": 3,                          # 页码（来自 page_idx）
        "section": "第一章 > 1.1 核心功能",  # 章节路径
        "bbox": [72, 200, 540, 500],        # 可选，归一化坐标
        # --- 分块信息 ---
        "chunk_index": 0,                   # 在文档中的序号
        # --- 类型特有字段 ---
        "image_path": "images/xxx.jpg",     # image 类型
        "table_caption": "表1：...",         # table 类型
    }
}
```

#### 5.3 Chunk 质量增强选项（分阶段）

| 增强方案 | 原理 | 效果 | 优先级 |
|---------|------|------|--------|
| **Contextual Retrieval** | 用 LLM 给每个 chunk 加上下文前缀 | 检索失败率 -67% | P2 |
| **表格 LLM 摘要** | LLM 生成表格一句话描述 | 表格语义检索提升 | P3 |
| **图片 Vision LLM** | Vision LLM 描述图片 | 图片可被语义检索 | P3 |
| **Late Chunking** | 先整文档 embedding 再切分 | 跨块语义保留 | P4（实验性） |

---

## 四、端到端处理流程（详细）

```python
async def process_document(file_path: str, doc_id: str, metadata: dict) -> list[dict]:
    # ① 解析层：MinerU CLI
    output_dir = run_mineru(file_path)
    content_list = load_json(output_dir / "content_list.json")

    # ② 分类层：MinerU 已完成（type 字段）
    # ③ 关系建模层：计算 section path
    section_paths = build_section_path(content_list)

    # ④ 模态处理 + ⑤ Chunk 层
    chunks = []
    for i, item in enumerate(content_list):
        item_type = item["type"]
        base_meta = {
            **metadata,
            "page": item.get("page_idx"),
            "section": section_paths[i],
            "bbox": item.get("bbox"),
        }

        if item_type == "text" and item.get("text_level", 0) == 0:
            # 正文 → chunker 分块
            text_chunks = chunker.chunk(item["text"], doc_id, {
                **base_meta, "content_type": "text"
            })
            chunks.extend(text_chunks)

        elif item_type == "text" and item.get("text_level", 0) > 0:
            # 标题 → 不单独存储，已体现在 section path 中
            pass

        elif item_type == "table":
            # 表格 → 原子 chunk
            caption = " ".join(item.get("table_caption", []))
            footnote = " ".join(item.get("table_footnote", []))
            html = item.get("table_body", "")
            content = f"[表格] {caption}\n{html}"
            if footnote:
                content += f"\n注：{footnote}"
            chunks.append(make_chunk(content, doc_id, {
                **base_meta, "content_type": "table",
                "table_caption": caption,
            }))

        elif item_type == "image":
            # 图片 → 原子 chunk
            caption = " ".join(item.get("image_caption", []))
            content = f"[图片] {caption}" if caption else "[图片]"
            chunks.append(make_chunk(content, doc_id, {
                **base_meta, "content_type": "image",
                "image_path": item.get("img_path"),
            }))

        elif item_type == "equation":
            # 公式 → 原子 chunk
            latex = item.get("text", "")
            content = f"[公式] {latex}"
            chunks.append(make_chunk(content, doc_id, {
                **base_meta, "content_type": "formula",
            }))

        elif item_type == "code":
            code = item.get("code_body", "")
            caption = " ".join(item.get("code_caption", []))
            content = f"[代码] {caption}\n{code}" if caption else f"[代码]\n{code}"
            chunks.append(make_chunk(content, doc_id, {
                **base_meta, "content_type": "code",
            }))

        # header/footer/page_number → 丢弃

    return chunks
```

---

## 五、方案对比总结

| 层 | 方案 | 替代方案 | 选择理由 |
|----|------|---------|---------|
| **解析** | MinerU CLI (`-b pipeline`) | Unstructured, Docling | 中文最优，OmniDocBench #3，内置 PaddleOCR |
| **分类** | MinerU `content_list.type` | 自建分类器 | 布局检测 mAP 97.5，无需自建 |
| **模态处理** | MinerU 原生字段 + 可选 LLM 增强 | 全 Vision LLM | 基础版零 LLM 调用，按需增强 |
| **关系建模** | MinerU caption/footnote + section path | 手动 bbox 匹配 | MinerU 已完成 80% 关系建模 |
| **Chunk** | SemanticChunker（中文修复）+ 原子 chunk | LangChain splitter | 已有实现，修复中文即可 |

---

## 六、分阶段落地路线

| 阶段 | 内容 | LLM 调用 | 新依赖 |
|------|------|---------|--------|
| **P1 基础版** | MinerU 解析 + content_list 分流 + section path + SemanticChunker | 无 | mineru |
| **P2 上下文增强** | Contextual Retrieval（chunk 加上下文前缀） | 每 chunk 1 次 | 无 |
| **P3 多模态增强** | 图片 Vision LLM 描述 + 表格 LLM 摘要 + 公式自然语言描述 | 每图/表/公式 1 次 | 无 |
| **P4 实验性** | Late Chunking / ColPali 视觉检索 | 视情况 | jina-embeddings / colpali |

**P1 即可显著提升解析质量**（表格结构保留、图片提取、中文分块修复），且零 LLM 额外调用。

---

## 七、开源替代方案调研（后续升级参考）

当前选型为 MinerU + 自实现分流/分块。以下为各层的开源替代方案，供后续升级决策参考。

### 7.1 模态处理层

当前方案：自实现，从 MinerU content_list 按 type 分流处理，约 50 行代码。

| 框架 | 模态处理能力 | 中文效果 | 集成方式 | 评估 |
|------|------------|---------|---------|------|
| **Unstructured** | `partition_pdf()` 自动输出 typed elements (Title/Table/Image/NarrativeText)，内置 OCR，`strategy="hi_res"` 支持深度解析 | 一般 | `pip install unstructured[pdf]` | 通用性强但中文不如 MinerU；hi_res 需额外模型下载 |
| **Docling** (IBM) | DoclingDocument 对象包含 typed segments，TableFormer 表格识别精度高 | 弱于 MinerU | `pip install docling` | 学术文档强，中文企业文档不推荐 |
| **Chunkr** (YC 2024) | 按元素类型分流，可为不同类型配置不同策略（fast OCR / VLM） | 未知 | 开源自部署 | 较新，社区小，生产验证不足 |

**结论**：这三个框架的模态处理能力**绑定各自的解析层**，不能单独替换我们的模态处理逻辑。如果要换，就是整体替换 MinerU → Unstructured/Docling，而非只换模态处理。当前自实现分流代码量极小且完全可控，无需引入额外框架。

### 7.2 关系建模层

当前方案：MinerU 原生 caption/footnote 字段 + 自建 section_path 标题追踪（~30 行）。

| 框架 | 关系建模能力 | 评估 |
|------|------------|------|
| **Docling** | DoclingDocument 天然保留标题→段落→表格/图片的层级关系，最结构化 | 绑定 Docling 解析层，无法单独使用 |
| **Unstructured** | Element 有 parent_id 和 category 字段，Title 元素标记 section 边界 | 结构化程度不如 Docling |
| **LlamaIndex** | `NodeParser` 支持 metadata injection 和 parent-child 关系 | 可独立使用但需引入整个 LlamaIndex |

**结论**：MinerU content_list 已提供 caption/footnote/page_idx/bbox，覆盖了 80% 的关系建模需求。剩余 20%（section_path）自建 30 行代码解决。Docling 的 DoclingDocument 是最成熟的结构化方案，但绑定其解析层。**后续如果整体替换解析层，Docling 是关系建模方面的最佳选择**。

### 7.3 Chunk 层

当前方案：SemanticChunker（字符计数，中文标点分隔）+ 非文本原子 chunk。

| 框架 | Chunk 能力 | 表格处理 | 中文支持 | 评估 |
|------|-----------|---------|---------|------|
| **Docling HybridChunker** | token-aware 分块，`max_tokens` 控制，自动合并同 section 小块 | `repeat_table_header=True` 跨 chunk 重复表头 | 支持 | **最成熟的结构感知分块**，但绑定 Docling |
| **Docling HierarchicalChunker** | 一个结构单元=一个 chunk（段落/表格/图片） | 表格不拆分 | 支持 | 结构完整但 chunk 大小不可控 |
| **Unstructured chunk_by_title** | 按 Title 元素分 section，section 边界不跨越 | 不感知表格结构 | 支持 | 简单有效，但粒度粗 |
| **LangChain RecursiveCharacterTextSplitter** | 递归分隔符分块 | 不感知 | 有 Bug (#18770) | 中文句号 Bug 未修复 |
| **LlamaIndex SentenceSplitter** | 句子级分块 | 不感知 | 支持 | 纯文本分块，不感知文档结构 |

**结论**：Docling HybridChunker 是当前最先进的结构感知分块方案——token-aware、表头重复、section 合并。但它**强绑定 Docling 的 DoclingDocument 输入**，无法直接消费 MinerU 的 content_list。我们的 SemanticChunker 配合原子 chunk 策略已经覆盖了核心需求。**后续如果整体迁移到 Docling，HybridChunker 是最大升级收益之一**。

### 7.4 整体升级路径评估

| 路径 | 改动范围 | 收益 | 风险 |
|------|---------|------|------|
| **保持 MinerU + 自实现**（当前） | 无 | 中文最优解析，代码可控 | MinerU 社区较新，API 可能变动 |
| **整体迁移 Docling** | 替换整个 parser 层 | HybridChunker + DoclingDocument 结构化 | 中文效果弱于 MinerU |
| **整体迁移 Unstructured** | 替换整个 parser 层 | 生态最大，LangChain/LlamaIndex 集成 | 中文效果一般，商业版更好 |
| **MinerU 解析 → Docling Chunker** | 需写适配层 | 两者优势结合 | 维护两个框架的兼容性 |

**推荐**：短期保持当前方案（MinerU + 自实现），中期关注 Docling 的中文能力提升。如果 Docling 中文追上 MinerU，整体迁移是最优路径。

---

## 八、关键参考资料

| 资料 | 价值 |
|------|------|
| [MinerU Output Format Spec](https://opendatalab.github.io/MinerU/reference/output_files/) | content_list 字段定义 |
| [OmniDocBench CVPR 2025](https://arxiv.org/abs/2412.07626) | 文档解析质量评测 |
| [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) | 上下文增强检索，-67% 失败率 |
| [Jina Late Chunking](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) | 跨块语义保留 |
| [ColPali: Vision Retrieval](https://arxiv.org/abs/2407.01449) | 视觉检索新范式 |
| [Docling Technical Report](https://arxiv.org/abs/2408.09869) | IBM 文档理解架构参考 |
| [Docling Chunking](https://docling-project.github.io/docling/concepts/chunking/) | HybridChunker/HierarchicalChunker 文档 |
| [Unstructured Chunking](https://docs.unstructured.io/open-source/core-functionality/chunking) | chunk_by_title 元素感知分块 |
| [Chunkr (YC)](https://github.com/lumina-ai-inc/chunkr) | 新一代文档解析+分块 |
| [PaddleOCR 表格识别](https://github.com/PaddlePaddle/PaddleOCR/blob/main/docs/ppstructure/overview.md) | MinerU 内置 OCR 原理 |
| [Nougat (Meta)](https://arxiv.org/abs/2308.13418) | 学术 PDF 理解参考 |
