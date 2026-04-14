# 调研文档索引

## 中文文档解析系列（1 → 2 → 3 递进）

| # | 文档 | 内容 | 日期 |
|---|------|------|------|
| 1 | [01-parsing-tools-selection.md](./01-parsing-tools-selection.md) | **选什么工具？** 工具对比（MinerU/PaddleOCR/Docling），OmniDocBench 排名，选型决策树 | 2026-04-08 |
| 2 | [02-multimodal-pipeline-design.md](./02-multimodal-pipeline-design.md) | **怎么组合？** 五层 Pipeline 设计（解析→分类→模态处理→关系建模→Chunk），开源替代方案 | 2026-04-09 |
| 3 | [03-chinese-chunking-strategy.md](./03-chinese-chunking-strategy.md) | **怎么切块？** 中文分块策略、Contextual Retrieval、CRUD-RAG benchmark | 2026-04-08 |

## RAG 检索质量

| 文档 | 内容 | 日期 |
|------|------|------|
| [04-ambiguous-query-disambiguation.md](./04-ambiguous-query-disambiguation.md) | **模糊查询消歧**：一词多模块问题（"静音"→5个模块），5种开源方案对比，推荐 Metadata Filtering + 检索后聚类澄清 | 2026-04-14 |
| [procedural-qa-in-rag.md](./procedural-qa-in-rag.md) | **流程类问答**：学术定义（ProPara/TechQA/Lost in the Middle）、开源方案（LlamaIndex/LangChain/RAGFlow）、四层解决路径 | 2026-04-10 |

## 架构设计

| 文档 | 内容 | 日期 |
|------|------|------|
| [multimodal-output-design.md](./multimodal-output-design.md) | **多模态输出**：ContentBlock 协议、图片存储三阶段（本地→Docker→S3）、全栈改动清单 | 2026-04-10 |

## 测试标准

| 文档 | 内容 | 日期 |
|------|------|------|
| [testing-standards.md](./testing-standards.md) | 回归测试标准 + 解析测试标准（5 个质量维度 + 测试矩阵） | 2026-04-09 |

## 实验报告

| 文档 | 内容 | 日期 |
|------|------|------|
| [experiments/experiment-ecommerce-reranker-synonym-2x2.md](./experiments/experiment-ecommerce-reranker-synonym-2x2.md) | BGEReranker × SynonymAugmentor 电商场景 2×2 实验 | 2026-04-07 |
| [experiments/experiment-audio-reranker-synonym-2x2.md](./experiments/experiment-audio-reranker-synonym-2x2.md) | BGEReranker × SynonymAugmentor 音频场景实验 | 2026-04-07 |
| [experiments/rag-retrieval-quality.md](./experiments/rag-retrieval-quality.md) | RAG 检索质量分析 | 2026-04-07 |

## 开发日志

| 文档 | 内容 |
|------|------|
| [qa-log.md](./qa-log.md) | 开发过程中的技术 Q&A 记录 |
