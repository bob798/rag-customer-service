# 调研文档索引

## 选型速查（总纲）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 10 | [10-rag-selection-adr.md](./10-rag-selection-adr.md) | **RAG 全链路选型速查** — 12 节点推荐 + 决策树 + 引用链接（中文客服 · 本地部署优先） | 2026-04-20 |

## 文档解析系列（01 → 04 递进）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 01 | [01-parsing-tools-selection.md](./01-parsing-tools-selection.md) | **选什么工具？** 工具对比（MinerU/PaddleOCR/Docling），OmniDocBench 排名，选型决策树 | 2026-04-08 |
| 02 | [02-docx-parsing-research.md](./02-docx-parsing-research.md) | **DOCX 解析方案** — python-docx + PaddleOCR 方案设计 | 2026-04-14 |
| 03 | [03-multimodal-pipeline-design.md](./03-multimodal-pipeline-design.md) | **怎么组合？** 五层 Pipeline 设计（解析→分类→模态处理→关系建模→Chunk），开源替代方案 | 2026-04-09 |
| 04 | [04-chinese-chunking-strategy.md](./04-chinese-chunking-strategy.md) | **怎么切块？** 中文分块策略、Contextual Retrieval、CRUD-RAG benchmark | 2026-04-08 |

## RAG 检索质量（05 → 06）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 05 | [05-ambiguous-query-disambiguation.md](./05-ambiguous-query-disambiguation.md) | **模糊查询消歧** — 一词多模块问题（"静音"→5个模块），5种方案对比 | 2026-04-14 |
| 06 | [06-procedural-qa-in-rag.md](./06-procedural-qa-in-rag.md) | **流程类问答** — 学术定义、开源方案、四层解决路径 | 2026-04-10 |

## 架构设计（07 → 08）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 07 | [07-multimodal-output-patterns.md](./07-multimodal-output-patterns.md) | **多模态输出模式** — ContentBlock 设计模式 | 2026-04-18 |
| 08 | [08-multimodal-content-block-spec.md](./08-multimodal-content-block-spec.md) | **ContentBlock 协议规范** — 通用 RAG 多类型内容输出方案 | 2026-04-14 |

## 模型选型（09）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 09 | [09-embedding-reranker-survey.md](./09-embedding-reranker-survey.md) | **Embedding / Reranker 深度调研** — Qwen3 全系列对比、硬件需求、决策树 | 2026-04-17 |


## 图片处理（11）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 11 | [11-docx-image-text-association.md](./11-docx-image-text-association.md) | **DOCX 图文关联** — RAG 回答中嵌入文档原图，保持图文位置关系 | 2026-04-20 |

## 实验报告

| 文档 | 内容 | 日期 |
|------|------|------|
| [experiments/experiment-ecommerce-reranker-synonym-2x2.md](./experiments/experiment-ecommerce-reranker-synonym-2x2.md) | BGEReranker × SynonymAugmentor 电商场景 2×2 实验 | 2026-04-07 |
