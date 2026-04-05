# AI 客服系统 · 技术选型依据

> **用途**：技术选型的过程文档，记录比较维度、候选方案、决策依据。结论汇总见 [phase1-product-spec.md](./phase1-product-spec.md)。
> **目标读者**：需要理解"为什么这样选"的开发者或审查者。
> **最后更新**：2026-03-28

---

## 向量数据库

| 维度 | **ChromaDB** ✅ | Qdrant | Milvus | pgvector |
|------|--------------|--------|--------|---------|
| 部署复杂度 | 零依赖，pip 安装即用 | 需独立进程 | 需 Docker + etcd | 需 PostgreSQL |
| 性能上限 | 百万级向量 | 千万级 | 亿级 | 千万级 |
| 生产成熟度 | 中 | 高 | 高 | 高 |
| 适合阶段 | Phase 1 | Phase 2 | Phase 3 | 已有 PG 的企业 |

**选 ChromaDB**：Phase 1 核心是验证 RAG 链路正确性，不是验证向量库性能。零依赖让本地开发和企业部署都极简。知识库 > 100 万条时迁移 Milvus。

---

## Embedding 模型

> 参考榜单：[MTEB Leaderboard（中文子集）](https://huggingface.co/spaces/mteb/leaderboard) → Language: Chinese

| 维度 | **gte-Qwen2-1.5B** ✅ | BGE-M3 | gte-Qwen2-7B | Qwen API |
|------|---------------------|--------|-------------|---------|
| MTEB 中文均分 | ~70 | ~68-70 | ~73（最高）| ~71 |
| 模型大小 | 1.5B / ~3GB | 568M / ~1.1GB | 7B / ~14GB | API |
| 中文效果 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 英文效果 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 最大 token | 32K | 8K | 32K | 8K |
| 运行成本 | 本地免费 | 本地免费 | 本地免费 | ¥0.0007/1K |

**选 gte-Qwen2-1.5B**：企业客服以中文为主，Qwen 系中文 MTEB 均分更高。7B 内存需求过高（14GB），1.5B 是效果/资源最优平衡点。内存不足 8GB 时降级 Qwen API（¥0.0007/千次，成本可忽略）。

> ⚠️ BGE-M3 在 RAG 教程中出现频率最高，但不代表中文场景最优。选型应以 MTEB 榜单为依据，而非"教程惯性"。

---

## Reranker

| 维度 | **BGE-Reranker-v2-m3** ✅ | Cohere Rerank | bce-reranker |
|------|--------------------------|---------------|-------------|
| 中文效果 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ |
| 运行成本 | 本地免费 | $1/1000次 | 本地免费 |
| 数据隐私 | ✅ 本地 | ❌ 数据出境 | ✅ 本地 |
| 延迟 | ~30ms/pair | ~200ms（网络）| ~30ms |

**选 BGE-Reranker-v2-m3**：中文效果最好，本地运行零 API 成本，数据不出境（企业合规要求）。数据可出境且对延迟极敏感时可换 Cohere。

---

## BM25 实现

| 维度 | **rank_bm25** ✅ | Elasticsearch | Whoosh |
|------|----------------|--------------|--------|
| 部署复杂度 | pip，无服务 | 需 JVM + ES | pip，无服务 |
| 中文分词 | 搭配 jieba | 内置 IK | 需插件 |
| 持久化 | 需自实现（DB 重建）| 自带 | 自带 |
| 适合规模 | < 10 万条 | 百万级 | < 10 万条 |

**选 rank_bm25**：轻量，无外部服务依赖。BM25 索引重启后从 SQLite 重建（< 1s），满足 Phase 1 需求。知识库 > 10 万条时迁移 ES。

---

## LLM SDK 代理

| 维度 | **LiteLLM** ✅ | 直调各家 SDK | LangChain |
|------|--------------|------------|----------|
| 统一接口 | ✅ 100+ 模型 | ❌ 每家不同 | ✅ 但抽象层厚 |
| Fallback 支持 | 原生支持 | 自己实现 | 需配置 |
| 依赖复杂度 | 轻 | 零 | 重 |

**选 LiteLLM**：统一接口屏蔽各家 SDK 差异，原生支持 Fallback，依赖轻。LangChain 需要其专属 Agent Tools 生态时再引入。

---

## 文档解析

| 维度 | **PyMuPDF + python-docx** ✅ | Unstructured.io | MarkItDown |
|------|---------------------------|----------------|-----------|
| PDF 普通文本 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ |
| PDF 表格提取 | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ |
| 依赖复杂度 | 轻 | 重（需系统库）| 中 |
| 速度 | 快 | 慢 | 中 |

**选 PyMuPDF + python-docx**：企业客服知识库多为文字型 PDF，表格场景少。表格 PDF 占比 > 30% 时 Phase 2 引入 Unstructured。

---

## 可观测性工具

| 工具 | 定位 | 推荐场景 |
|------|------|---------|
| **StructuredLogTracer**（自研）| JSON 日志，零依赖 | Phase 1 默认 |
| **Langfuse** | 开源 LLM observability，可自托管 | Phase 2：需要 Web UI、RAGAS 集成 |
| **Phoenix (Arize)** | RAG 专项，OpenTelemetry 兼容 | 需要深度 retrieval 可视化 |
| **OpenLLMetry** | OpenTelemetry for LLMs | 已有 OTEL 基础设施的企业 |
| LangSmith | 绑定 LangChain，数据上传 LangChain 服务器 | ❌ 不选：数据出境，生态绑定 |

**Phase 1 选自研 StructuredLogTracer**：零依赖，trace_id 全链路追踪，JSON 结构化日志。BaseTracer 接口保证 Phase 2 换 Langfuse 不改 Pipeline。

---

## 决策汇总

| 组件 | 选择 | 放弃 | 重新考虑的触发条件 |
|------|------|------|-----------------|
| 向量库 | ChromaDB | Milvus | 知识库 > 100 万条 |
| Embedding | gte-Qwen2-1.5B | BGE-M3 | 需要强英文支持 |
| Reranker | BGE-Reranker-v2-m3 | Cohere | 数据可出境且延迟敏感 |
| BM25 | rank_bm25 | Elasticsearch | 知识库 > 10 万条 |
| 文档解析 | PyMuPDF | Unstructured | 表格 PDF 占比 > 30% |
| LLM 代理 | LiteLLM | LangChain | 需要 LangChain Agent Tools |
| Observability | StructuredLogTracer | Langfuse | Phase 2 升级 |
