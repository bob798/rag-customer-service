# 系统架构

## 分层架构图

```mermaid
graph TB
    subgraph API["API 层"]
        A[FastAPI Router]
    end

    subgraph Pipeline["RAG Pipeline 层"]
        B[RAGPipeline]
        B1[IntentClassifier]
        B2[QueryRewriter]
        B3[LLMGenerator]
        B4[PipelineBuilder]
    end

    subgraph Ports["Port 接口层（抽象）"]
        P1[BaseRetriever]
        P2[BaseReranker]
        P3[BaseConfidenceEvaluator]
        P4[BaseFallbackHandler]
        P5[BaseTracer]
        P6[BaseEmbedder]
        P7[BaseParser]
        P8[BaseChunker]
    end

    subgraph Adapters["Adapter 实现层（可替换）"]
        AD1[HybridRetriever]
        AD2[NoopReranker / BGEReranker]
        AD3[SignalFusionConfidenceEvaluator]
        AD4[TellUserFallbackHandler]
        AD5[StructuredLogTracer]
        AD6[GteQwen2Embedder]
        AD7[FAQParser / DefaultParser]
        AD8[SemanticChunker]
    end

    subgraph Data["数据层"]
        D1[(ChromaDB\n向量库)]
        D2[(BM25 索引\n内存)]
        D3[(SQLite\n关系型DB)]
        D4[LiteLLM\nLLM 网关]
    end

    A --> B
    B --> B1 & B2 & B3
    B4 -.->|组装| B

    B --> P1 & P2 & P3 & P4 & P5 & P6
    B1 & B2 & B3 --> P6

    P1 --> AD1
    P2 --> AD2
    P3 --> AD3
    P4 --> AD4
    P5 --> AD5
    P6 --> AD6
    P7 --> AD7
    P8 --> AD8

    AD1 --> D1 & D2
    AD6 --> D4
    B1 & B2 & B3 --> D4
    A --> D3
```

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

## 核心设计原则

1. **Ports & Adapters（六边形架构）**：所有外部依赖通过接口抽象，业务逻辑不依赖具体实现
2. **依赖注入**：`RAGPipeline` 通过构造函数注入所有组件，`PipelineBuilder` 负责组装
3. **Pipeline 不依赖 DB**：`session_history` 由 API 层查询后传入，pipeline 保持无状态
4. **同步 + 异步分离**：`ConfidenceEvaluator.evaluate()` 为同步（纯计算），其余 I/O 操作为 async
