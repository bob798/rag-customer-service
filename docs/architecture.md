# 系统架构

## 分层架构图

```mermaid
graph TB
    subgraph Frontend["前端层（待实现）"]
        F1["Web Chat Widget<br>widget/"]
    end

    subgraph API["API 层"]
        A1["FastAPI Router<br>api/routes/"]
        A2["Session 管理<br>查询 DB / 写入 DB"]
    end

    subgraph Pipeline["RAG Pipeline 层"]
        B["RAGPipeline<br>core/rag/pipeline.py"]
        B1["IntentClassifier"]
        B2["QueryRewriter"]
        B3["LLMGenerator"]
    end

    subgraph LLMAdp["LLM 适配层"]
        LF["LLMFactory<br>core/llm/factory.py<br>LiteLLM 统一接口"]
    end

    subgraph Ports["Port 接口层（抽象）"]
        P1["BaseRetriever"]
        P2["BaseReranker"]
        P3["BaseConfidenceEvaluator"]
        P4["BaseFallbackHandler"]
        P5["BaseTracer"]
        P6["BaseEmbedder"]
        P7["BaseParser"]
        P8["BaseChunker"]
    end

    subgraph Adapters["Adapter 实现层（可替换）"]
        AD1["HybridRetriever"]
        AD2["NoopReranker / BGEReranker"]
        AD3["SignalFusionConfidenceEvaluator"]
        AD4["TellUserFallbackHandler"]
        AD5["StructuredLogTracer"]
        AD6["GteQwen2Embedder"]
        AD7["FAQParser / DefaultParser"]
        AD8["SemanticChunker"]
    end

    subgraph Data["数据层"]
        D1[("ChromaDB 向量库")]
        D2[("BM25 索引 内存")]
        D3[("SQLite 关系型DB")]
        D4["LLM 服务<br>Claude / DeepSeek / 通义"]
    end

    PB["PipelineBuilder<br>core/rag/pipeline_builder.py<br>启动时组装依赖"]

    F1 -->|"HTTP / SSE"| A1
    A1 --> B
    A1 --> A2
    A2 --> D3

    B --> B1
    B --> B2
    B --> B3
    B1 --> LF
    B2 --> LF
    B3 --> LF

    B --> P1
    B --> P2
    B --> P3
    B --> P4
    B --> P5
    B --> P6

    P1 --> AD1
    P2 --> AD2
    P3 --> AD3
    P4 --> AD4
    P5 --> AD5
    P6 --> AD6
    P7 --> AD7
    P8 --> AD8

    AD1 --> D1
    AD1 --> D2
    AD6 --> LF
    LF --> D4

    PB -.->|"注入"| B
```

> `PipelineBuilder` 仅在服务启动时运行，负责将所有组件组装注入到 `RAGPipeline`，不在请求链路上。

---

## 前端说明

| 目录 | 状态 | 说明 |
|------|------|------|
| `widget/` | 待实现（Week 2） | 嵌入式客服聊天 Widget，纯 JS/HTML，零依赖 |

预期功能：
- 悬浮按钮 + 对话气泡窗口
- 流式打字机效果（对接 SSE 接口）
- 历史消息展示
- 置信度低时显示"仅供参考"标识

API 接口（后端已实现占位，待连接）：
- `POST /api/v1/chat` — 非流式问答
- `POST /api/v1/chat/stream` — SSE 流式问答

---

## Ports & Adapters 对照表

| Port 接口 | 职责 | 默认 Adapter | 可替换为 |
|-----------|------|-------------|---------|
| `BaseRetriever` | 混合检索（向量 + BM25） | `HybridRetriever` | 纯向量检索、ES 检索 |
| `BaseReranker` | 候选重排序 | `NoopReranker`（测试）/ `BGEReranker`（生产） | 其他 CrossEncoder 模型 |
| `BaseConfidenceEvaluator` | 三路信号置信度评估 | `SignalFusionConfidenceEvaluator` | 基于阈值的简单评估 |
| `BaseFallbackHandler` | 低置信度/越界兜底 | `TellUserFallbackHandler` | 转人工、FAQ 搜索 |
| `BaseTracer` | 链路追踪日志 | `StructuredLogTracer` | OpenTelemetry、Jaeger |
| `BaseEmbedder` | 文本向量化 | `GteQwen2Embedder` | OpenAI Embedding、BGE |
| `BaseParser` | 文档解析为原始文本 | `FAQParser`、`DefaultParser` | PDF专用、OCR解析 |
| `BaseChunker` | 文本分块 | `SemanticChunker` | 按段落、按Token |

---

## 核心设计原则

1. **Ports & Adapters（六边形架构）**：所有外部依赖通过接口抽象，业务逻辑不依赖具体实现
2. **依赖注入**：`RAGPipeline` 通过构造函数注入所有组件，`PipelineBuilder` 负责启动时组装
3. **Pipeline 不依赖 DB**：`session_history` 由 API 层查询后传入，pipeline 保持无状态
4. **同步 + 异步分离**：`ConfidenceEvaluator.evaluate()` 为同步（纯计算），其余 I/O 操作为 async
5. **LLM 统一网关**：`LLMFactory` 封装 LiteLLM，所有 LLM 调用（意图/改写/生成）走同一接口，支持 fallback
