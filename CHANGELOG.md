# Changelog

## [0.2.0] — 2026-04-06  Week 2: API 层

### 新增

**API 路由**
- `POST /chat` — 支持非流式 JSON 和 SSE 流式两种模式，自动加载多轮历史，落库 Message 记录
- `POST /knowledge/upload` — 上传文档，后台异步索引（FAQParser / DefaultParser）
- `POST /knowledge/qa` — 直接写入 Q&A 条目到向量库和 BM25
- `GET  /knowledge/documents` — 列出所有文档及状态
- `DELETE /knowledge/documents/{id}` — 删除文档
- `GET  /sessions` — 列出最近 50 个会话
- `GET  /sessions/{id}/messages` — 获取会话消息历史
- `GET  /config` — 读取系统配置（key-value）
- `PUT  /config` — 更新配置项

**认证**
- 双层认证：Admin API Key（管理接口）+ Widget Token（`/chat`），互不通用
- 安全负例测试：Widget Token 无法访问 Admin 接口

**基础设施**
- FastAPI `lifespan`：Pipeline 单例初始化、BM25 重启后重建、Config 默认值播种
- Pipeline 在测试中支持 mock 注入（跳过重建逻辑）
- `api/schemas.py`：完整 Pydantic v2 请求/响应模型
- `api/dependencies.py`：认证依赖项

**测试**
- 新增 19 个 API 测试（`tests/api/`）
- 总计：179 tests，覆盖率 93%

### 修复
- `RAGPipeline.retriever`、`HybridRetriever.vector_store/bm25_store` 添加 `@property` 暴露

---

## [0.1.0] — 2026-04-05  Phase 1: RAG 核心链路

### 新增

**RAG 全链路组件**
- `IntentClassifier` — LLM 意图识别，支持 in_scope / out_of_scope / ambiguous 三态
- `QueryRewriter` — 口语化问题规范化，失败时原样透传
- `HybridRetriever` — 向量检索 + BM25 双路 + RRF 融合排序
- `NoopReranker` / `BGEReranker` — 测试用直通 + 生产用 bge-reranker-v2-m3
- `SignalFusionConfidenceEvaluator` — 三路信号（retrieval/coverage/gap）加权置信度
- `LLMGenerator` — 流式 + 非流式生成，medium 置信度自动加免责声明
- `TellUserFallbackHandler` — 低置信度 / out_of_scope / error 三类兜底
- `StructuredLogTracer` — ContextVar 并发安全的 JSON 结构化追踪
- `RAGPipeline` — 七步编排（`run()` + `run_stream()`，共享 `_run_pre_generation()`）

**知识库**
- `FAQParser` — `Q: / A:` 格式自动识别
- `DefaultParser` — 通用文档解析
- `SemanticChunker` — 语义分块，中文支持
- `GteQwen2Embedder` — 本地 gte-Qwen2-1.5B，中文 MTEB ~70
- `ChromaVectorStore` — 向量存储与相似度查询
- `Bm25Store` — jieba 分词 + rank_bm25

**基础设施**
- SQLAlchemy async 数据模型：Document / Chunk / Session / Message / Config
- `core/interfaces/` — 8 个 Port 接口（BaseEmbedder、BaseRetriever 等）
- `core/rag/pipeline_builder.py` — 工厂函数，从环境变量组装完整 Pipeline
- `scripts/demo_pipeline.py` — mock 模式零依赖验证完整链路
- `scripts/ingest.py` — 知识库导入脚本

**文档**
- `docs/architecture.md`、`docs/rag-query-flow.md`、`docs/data-model.md`
- `docs/llm-guide.md`、`docs/ingestion-guide.md`

**测试**
- 单元测试（`tests/core/`）+ 集成测试（`tests/integration/`）+ 冒烟测试（`tests/smoke/`）
- 160 tests，覆盖率 91%
