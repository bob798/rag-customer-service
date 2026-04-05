# Week 1 补全 + 集成测试 + 架构文档计划

## Context

Phase 1 基础组件已完成（72 tests passing），但 `core/rag/` 完全为空——这是 Week 1 遗漏的部分。RAG 核心链路编排（意图识别、Query改写、混合检索、重排序、置信度评估、生成、管道）均未实现。

本计划分三个部分：
1. **补全 core/rag/ 组件**（Week 1 遗漏）
2. **集成测试 + 冒烟测试**（验证真实链路）
3. **系统架构文档**（Mermaid 图表）

---

## 架构师评估修正的关键设计决策

在实施前锁定以下决策（避免 A7/A8 阶段大规模返工）：

**决策1：Pipeline 内部做 embedding，不接受外部传入 query_vec**
- `RAGPipeline.__init__` 注入 `embedder: BaseEmbedder`
- `run(question, session_id, session_history=[])` 只接受文本
- embedding 在 pipeline 内部第 3 步完成

**决策2：sources 格式在 A3 时就约定包含 title**
- ChromaVectorStore.add() 时，metadata 必须包含 `source_title`（文档文件名）
- sources 返回格式：`{doc_id, title(=source_title), content_preview, chunk_id}`
- pipeline 调用方在调用 add() 时传入 `{"source_title": doc.filename, ...}` 的 metadata

**决策3：session_history 由 API 层查 DB 传入（pipeline 不依赖 db 层）**
- `run(question, session_id, session_history: list[dict] = [])` 的 history 由 API 路由层传入
- 格式：`[{"role": "user"|"assistant", "content": str}]`

**决策4：ambiguous 意图返回澄清问题**
- IntentClassifier 返回：`{intent, confidence, clarification_question: Optional[str]}`
- pipeline 检测到 ambiguous → 直接返回 clarification_question，不走 RAG

**决策5：run() 和 run_stream() 共享 _run_pre_generation()**
- `_run_pre_generation(question, session_id, session_history)` → `PreGenContext`（dataclass）
- `run()` 和 `run_stream()` 均调用此方法，分叉点在生成步骤

**决策6：StructuredLogTracer 使用 contextvars.ContextVar 存 trace_id**
- 解决并发请求下多个请求共享同一 tracer 实例时 trace_id 互相覆盖问题

**决策7：增加 PipelineBuilder 工厂函数**
- `core/rag/pipeline_builder.py`：`create_default_pipeline(settings) → RAGPipeline`
- Pipeline 自身保持 clean DI，Builder 负责从环境变量/Config 组装

---

## 推荐实施顺序（增量验证节奏）

```
A3（HybridRetriever + RRF）→ 立即可测，验证 RRF 手算结果
↓
A4（NoopReranker 先）→ 让 A3 可以被集成
↓
A5（ConfidenceEvaluator）→ 用硬编码候选列表验证三路权重
↓
A8 骨架（_run_pre_generation，用 mock intent + NoopReranker 跑通主链路）
↓
A1（IntentClassifier，含 ambiguous 分支）
↓
A2（QueryRewriter）
↓
A7（LLMGenerator，含 title 字段）
↓
A8 完整（run + run_stream + PipelineBuilder）
↓
A4 补全（BGEReranker 生产实现）
↓
A6（StructuredLogTracer + TellUserFallbackHandler，最后加）
```

---

## Part A：补全 core/rag/ 核心链路

### Step A1：意图识别

**文件：** `core/rag/intent.py`

```
IntentClassifier:
  async classify(question: str) → {
    "intent": "in_scope"|"out_of_scope"|"ambiguous",
    "confidence": float,
    "clarification_question": Optional[str]  # 仅 ambiguous 时非 None
  }
  
  使用 LLMFactory.complete() 调用 LLM，system prompt 定义范围边界
  返回结构化 JSON（含简单 retry 逻辑）
  
  依赖: LLMFactory（注入）
```

测试文件：`tests/core/test_intent.py`（mock LLM）

---

### Step A2：Query 改写

**文件：** `core/rag/query_rewriter.py`

```
QueryRewriter:
  async rewrite(question: str) → str
  
  调用 LLM 将口语化问题规范化（"退款咋整" → "如何申请退款流程"）
  失败时原样返回 question（不阻断流程）
  
  依赖: LLMFactory（注入）
```

测试文件：`tests/core/test_query_rewriter.py`（mock LLM）

---

### Step A3：混合检索（HybridRetriever）

**文件：** `core/rag/retriever.py`

```
HybridRetriever(implements BaseRetriever):
  __init__(vector_store: ChromaVectorStore, bm25_store: Bm25Store, vector_weight: float = 0.6)
  
  async retrieve(query_vec, query_text, top_k=5) → list[dict]
    1. vector_results = await vector_store.query(query_vec, top_k=20)
    2. bm25_results   = bm25_store.search(query_text, top_k=20)
    3. RRF 融合: rrf_score = Σ 1/(60 + rank_i)
    4. 返回按 rrf_score 降序 top_k 结果
    
每个结果: {"chunk_id", "doc_id", "content", "score"(rrf), "metadata"}
```

测试文件：`tests/core/test_hybrid_retriever.py`（mock VectorStore + mock Bm25Store）

---

### Step A4：重排序

**文件：** `core/rag/reranker.py`

```
NoopReranker(implements BaseReranker):
  # 测试用，不依赖 FlagEmbedding 模型文件
  async rerank(query, candidates, top_k=5) → candidates[:top_k]
  # 添加 rerank_score = candidate.get("score", 0.0)

BGEReranker(implements BaseReranker):
  # 生产用，依赖 FlagEmbedding（lazy import）
  __init__(model_name="BAAI/bge-reranker-v2-m3")
  async rerank(query, candidates, top_k=5) → list[dict]
  # 使用 FlagReranker.compute_score() 在 run_in_executor 中运行
  # 添加 rerank_score 字段
```

测试文件：`tests/core/test_reranker.py`（NoopReranker 真实测试，BGEReranker mock FlagEmbedding）

---

### Step A5：置信度评估

**文件：** `core/rag/confidence.py`

```
SignalFusionConfidenceEvaluator(implements BaseConfidenceEvaluator):
  evaluate(query, candidates, reranked) → (float, str)
  
  三路信号:
    retrieval_score = reranked[0]["rerank_score"]
    coverage_score  = jieba token 覆盖率（query tokens 在 top-1 content 中的比例）
    score_gap       = reranked[0].score - reranked[1].score（不足2个时=0）
  
  confidence = 0.6*retrieval + 0.3*coverage + 0.1*gap
  tier: >= 0.75 → "high", >= 0.50 → "medium", < 0.50 → "low"
```

测试文件：`tests/core/test_confidence.py`

---

### Step A6：Tracer 和 FallbackHandler

**文件：** `core/rag/tracer.py`

```
StructuredLogTracer(implements BaseTracer):
  start_trace(trace_id) → JSON log: {"event": "trace_start", "trace_id": ...}
  log_step(step, data)  → JSON log: {"event": "step", "step": ..., "data": ...}
  end_trace()           → JSON log: {"event": "trace_end"}
  零外部依赖，仅 logging 模块
```

**文件：** `core/rag/fallback_handler.py`

```
TellUserFallbackHandler(implements BaseFallbackHandler):
  async handle(question, session_id, reason) → str
  
  reason 映射:
    "low_confidence"  → "抱歉，我对这个问题没有足够把握，建议联系人工客服"
    "out_of_scope"    → "这个问题超出了我的服务范围，请联系人工客服"
    "error"           → "系统暂时出现问题，请稍后重试"
```

测试文件：`tests/core/test_tracer.py`，`tests/core/test_fallback.py`

---

### Step A7：LLM 生成

**文件：** `core/rag/generator.py`

```
LLMGenerator:
  __init__(llm: LLMFactory)
  
  async generate(question, chunks, confidence_tier, session_history=[]) → {"answer": str, "sources": list}
    - system prompt: 根据 chunks 回答，不编造，引用来源
    - 若 confidence_tier == "medium": 在 answer 前加"以下回答仅供参考："
    - sources: [{doc_id, title(=chunk.metadata["source_title"]), content_preview, chunk_id}]
    
  async generate_stream(question, chunks, confidence_tier, session_history=[]) → AsyncGenerator
    - SSE 格式：{"type": "delta", "content": token}
    - 最终帧：{"type": "done", "sources": [...], "confidence": float, "uncertain": bool}
```

测试文件：`tests/core/test_generator.py`（mock LLMFactory）

---

### Step A8：RAG Pipeline 编排

**文件：** `core/rag/pipeline.py`

```
RAGPipeline:
  __init__(
    intent_classifier: IntentClassifier,
    query_rewriter: QueryRewriter,
    retriever: BaseRetriever,
    reranker: BaseReranker,
    confidence_evaluator: BaseConfidenceEvaluator,
    fallback_handler: BaseFallbackHandler,
    generator: LLMGenerator,
    tracer: BaseTracer,
    embedder: BaseEmbedder,
  )
  
  async run(question, session_id, session_history=[]) → dict
    trace_id = uuid4()
    tracer.start_trace(trace_id)
    
    1. intent_result = await intent_classifier.classify(question)
       if intent_result["intent"] == "out_of_scope" → return fallback_handler.handle(..., reason="out_of_scope")
       if intent_result["intent"] == "ambiguous" → return {"answer": intent_result["clarification_question"], "sources": [], "trace_id": trace_id}
    
    2. rewritten = await query_rewriter.rewrite(question)
    
    3. query_vec = await embedder.embed([rewritten])[0]
       candidates = await retriever.retrieve(query_vec, rewritten, top_k=20)
    
    4. reranked = await reranker.rerank(rewritten, candidates, top_k=5)
    
    5. confidence, tier = confidence_evaluator.evaluate(rewritten, candidates, reranked)
       if tier == "low" → return fallback_handler.handle(...)
    
    6. result = await generator.generate(question, reranked, tier, session_history)
    
    tracer.end_trace()
    return {answer, sources, confidence, uncertain=(tier=="medium"), trace_id}
  
  async run_stream(question, session_id, session_history=[]) → AsyncGenerator
    # 同上，步骤 1-5 同步完成后，步骤6改用 generator.generate_stream()
```

测试文件：`tests/core/test_pipeline.py`（所有组件 mock）

---

## Part B：集成测试

**目录：** `tests/integration/`

### `tests/integration/conftest.py`

```python
fixtures:
- real_chunker: SemanticChunker(chunk_size=256, overlap=50)
- real_bm25_store: Bm25Store()
- deterministic_embedder: 返回固定向量（hash(text) 生成），不依赖模型
- async tmp_chroma_store(tmp_path): ChromaVectorStore 使用 tmp_path
- sample_faq_file(tmp_path): 含5个Q&A对的真实 txt 文件
- mock_llm_factory: AsyncMock，返回固定答案
- full_pipeline(所有 mock): 使用 NoopReranker + mock LLM 的完整 pipeline
```

### `tests/integration/test_ingestion_pipeline.py`

```
test_faq_txt_end_to_end:
  FAQParser → 5个 chunks → BM25.add() → bm25.search("退款") 返回退款相关chunk

test_txt_chunking_to_bm25:
  DefaultParser + SemanticChunker → chunks → BM25.add() → 可检索

test_chunk_structure_consistency:
  所有 chunk 都有 chunk_id / doc_id / content / metadata
```

### `tests/integration/test_hybrid_retriever.py`

```
test_rrf_combines_both_sources:
  向量+BM25都有结果时，两路互补

test_vector_dominates_semantic_query:
  精确词不匹配时，向量结果出现在最终列表

test_bm25_surfaces_keyword_match:
  语义距离远但词完全匹配时，BM25结果出现在最终列表

test_top_k_limit_respected:
  融合后只返回 top_k 个结果
```

### `tests/integration/test_pipeline_flow.py`

```
test_in_scope_question_returns_answer:
  mock intent=in_scope，给定 chunks → 返回 answer + sources + confidence

test_out_of_scope_triggers_fallback:
  mock intent=out_of_scope → 返回兜底文案，不调用 generator

test_low_confidence_triggers_fallback:
  mock confidence=0.3 → 返回兜底，不生成 LLM 答案

test_medium_confidence_marks_uncertain:
  mock confidence=0.6 → answer 含"仅供参考"，uncertain=True

test_trace_id_present_in_result:
  结果包含 trace_id 字段
```

---

## Part C：冒烟测试（真实依赖）

**目录：** `tests/smoke/`，标记 `@pytest.mark.smoke`

```
test_bm25_real_chinese: 真实 jieba + rank_bm25 中文检索
test_chunker_chinese_text: 真实中文文本分块
test_faq_parser_chinese_qa: 真实 FAQ 文件解析
```

运行命令：`pytest tests/smoke/ -v -m smoke`

---

## Part D：架构文档（Mermaid）

**目录：** `docs/`（新建）

### `docs/architecture.md`

- **系统分层架构图**（Mermaid graph TB）：API → Pipeline → Port → 实现层 → 数据层
- **Ports & Adapters 对照表**：每个 Port 的默认实现和可替换 Adapter

### `docs/rag-query-flow.md`

- **RAG 七步查询流程图**（Mermaid flowchart）：含 out_of_scope/低置信度分支
- **置信度三档决策图**（Mermaid flowchart）
- **SSE 时序图**（Mermaid sequenceDiagram）

### `docs/data-model.md`

- **ER 图**（Mermaid erDiagram）：Document/Chunk/Session/Message/Config
- **trace_id 全链路 JSON 示例**

### 更新 `README.md`：文档导航加入 docs/ 链接

---

## 关键文件路径

| 文件 | 状态 |
|------|------|
| `core/rag/intent.py` | 新建 |
| `core/rag/query_rewriter.py` | 新建 |
| `core/rag/retriever.py` | 新建（HybridRetriever） |
| `core/rag/reranker.py` | 新建（NoopReranker + BGEReranker） |
| `core/rag/confidence.py` | 新建（SignalFusionEvaluator） |
| `core/rag/tracer.py` | 新建（StructuredLogTracer） |
| `core/rag/fallback_handler.py` | 新建 |
| `core/rag/generator.py` | 新建 |
| `core/rag/pipeline.py` | 新建（RAGPipeline 编排） |
| `tests/core/test_intent.py` | 新建 |
| `tests/core/test_query_rewriter.py` | 新建 |
| `tests/core/test_hybrid_retriever.py` | 新建 |
| `tests/core/test_reranker.py` | 新建 |
| `tests/core/test_confidence.py` | 新建 |
| `tests/core/test_tracer.py` | 新建 |
| `tests/core/test_fallback.py` | 新建 |
| `tests/core/test_generator.py` | 新建 |
| `tests/core/test_pipeline.py` | 新建 |
| `tests/integration/conftest.py` | 新建 |
| `tests/integration/test_ingestion_pipeline.py` | 新建 |
| `tests/integration/test_hybrid_retriever.py` | 新建 |
| `tests/integration/test_pipeline_flow.py` | 新建 |
| `tests/smoke/test_bm25_real.py` | 新建 |
| `tests/smoke/test_chunker_real.py` | 新建 |
| `docs/architecture.md` | 新建 |
| `docs/rag-query-flow.md` | 新建 |
| `docs/data-model.md` | 新建 |
| `README.md` | 更新 |

## 可复用的现有代码

| 组件 | 路径 |
|------|------|
| `LLMFactory` | `core/llm/factory.py` |
| `GteQwen2Embedder` | `core/knowledge/embedder.py` |
| `ChromaVectorStore` | `core/knowledge/vector_store.py` |
| `Bm25Store` | `core/knowledge/bm25_store.py` |
| `SemanticChunker` | `core/knowledge/chunker.py` |
| `FAQParser / DefaultParser` | `core/knowledge/parsers/` |
| 所有 8 个 Port 接口 | `core/interfaces/` |
| `db_session fixture` | `tests/core/test_db_models.py` |
| litellm/chromadb stub 模式 | `tests/conftest.py` |

## 验证

```bash
# 单元测试（含新增 core/rag/ 测试）
pytest tests/core/ -v

# 集成测试
pytest tests/integration/ -v

# 冒烟测试
pytest tests/smoke/ -v -m smoke

# 全量
pytest tests/ -v --cov=core --cov=db --cov-report=term-missing
```

Week 1 完成标准：`pytest tests/core/` 全绿，pipeline.run() 能端到端处理一个问题。
