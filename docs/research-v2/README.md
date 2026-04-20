# RAG 系统调研文档索引

> 按 RAG Pipeline 阶段组织：解析 → 分块 → 向量化与检索 → 查询理解 → 输出
>
> 全链路选型速查：[10-rag-selection-adr.md](./10-rag-selection-adr.md)

---

## 一、文档解析（Parsing）

> 文档解析是业务场景驱动的——先确定知识库的文档格式，再选择技术方案。

### 场景速查

| 你的知识库格式 | 推荐方案 | 阅读顺序 |
|--------------|---------|---------|
| **DOCX 为主** | python-docx 直接解析，轻量无依赖 | [02](./02-docx-parsing-research.md) → [11](./11-docx-image-text-association.md) |
| **PDF（可复制文字）** | PyMuPDF / pdfplumber，无需 OCR | [01 §二](./01-parsing-tools-selection.md) |
| **PDF（扫描件/图文混排）** | MinerU 或 PaddleOCR PP-StructureV3 | [01 §六](./01-parsing-tools-selection.md) |
| **混合格式（PDF + DOCX + ...）** | 统一 Pipeline，按格式路由 | [03](./03-multimodal-pipeline-design.md) → [01](./01-parsing-tools-selection.md) |
| **不确定 / 快速了解全链路** | 先看选型速查 | [10](./10-rag-selection-adr.md) |

### DOCX 专题

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 02 | [02-docx-parsing-research.md](./02-docx-parsing-research.md) | **DOCX 解析技术** — python-docx 文本/表格/图片提取、.doc vs .docx 差异、RAGFlow vs MinerU 对比 | 2026-04-14 |
| 11 | [11-docx-image-text-association.md](./11-docx-image-text-association.md) | **DOCX 图文关联** — RAG 回答中嵌入文档原图，保持图文位置关系 | 2026-04-20 |

### PDF 专题

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 01 | [01-parsing-tools-selection.md](./01-parsing-tools-selection.md) | **解析工具选型** — MinerU / PaddleOCR / Docling / PyMuPDF 对比，OmniDocBench 排名，OCR 方案 | 2026-04-08 |

### 跨格式架构（参考）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 03 | [03-multimodal-pipeline-design.md](./03-multimodal-pipeline-design.md) | **多模态 Pipeline 设计** — 五层架构（解析→分类→模态处理→关系建模→Chunk）。注：以 MinerU 为基础设计，具体选型以 [10](./10-rag-selection-adr.md) 为准 | 2026-04-09 |

---

## 二、分块策略（Chunking）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 04 | [04-chinese-chunking-strategy.md](./04-chinese-chunking-strategy.md) | **中文分块策略** — Token 计数失效问题、Recursive 分块、Contextual Retrieval、CRUD-RAG benchmark | 2026-04-08 |

---

## 三、向量化与检索（Embedding & Retrieval）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 09 | [09-embedding-reranker-survey.md](./09-embedding-reranker-survey.md) | **Embedding / Reranker 调研** — Qwen3 全系列对比、BGE 系列、BM25S 稀疏检索、硬件需求估算、决策树 | 2026-04-17 |

---

## 四、查询理解（Query Understanding）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 05 | [05-ambiguous-query-disambiguation.md](./05-ambiguous-query-disambiguation.md) | **模糊查询消歧** — 一词多模块问题（"静音"→5 个模块），5 种方案对比 | 2026-04-14 |
| 06 | [06-procedural-qa-in-rag.md](./06-procedural-qa-in-rag.md) | **流程类问答** — 学术定义、开源方案（RAGFlow/Dify/LlamaIndex）、四层解决路径 | 2026-04-10 |

---

## 五、多模态输出（Output）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 07 | [07-multimodal-output-patterns.md](./07-multimodal-output-patterns.md) | **多模态输出模式调研** — 业界方案对比（Claude API / RAGFlow / Dify）、Content Block 设计模式 | 2026-04-18 |
| 08 | [08-multimodal-content-block-spec.md](./08-multimodal-content-block-spec.md) | **ContentBlock 协议规范** — 6 种 Block 类型定义、SSE 流式协议、图片服务演进方案 | 2026-04-14 |

---

## 六、全链路选型（总纲）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 10 | [10-rag-selection-adr.md](./10-rag-selection-adr.md) | **RAG 全链路选型速查** — 12 个节点推荐方案 + 选型演变说明 + 决策树 + 引用链接 | 2026-04-20 |

---

## 实验报告

| 文档 | 内容 | 日期 |
|------|------|------|
| [experiments/experiment-ecommerce-reranker-synonym-2x2.md](./experiments/experiment-ecommerce-reranker-synonym-2x2.md) | BGEReranker x SynonymAugmentor 电商场景 2x2 实验 | 2026-04-07 |

---

## 可视化

| 文档 | 内容 |
|------|------|
| [diagrams/mineru-paddleocr-ragflow.html](./diagrams/mineru-paddleocr-ragflow.html) | MinerU vs PaddleOCR vs RAGFlow 交互式对比图 |
