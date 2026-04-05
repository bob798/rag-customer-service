# RAG 查询流程

## 七步查询主流程

```mermaid
flowchart TD
    Start([用户提问]) --> Intent["1. 意图识别 IntentClassifier"]

    Intent -->|out_of_scope| Fallback1["兜底响应：超出服务范围"]
    Intent -->|ambiguous| Clarify["返回澄清问题 clarification_question"]
    Intent -->|in_scope| Rewrite["2. Query 改写 QueryRewriter"]

    Rewrite --> Embed["3a. 向量化 Embedder.embed"]
    Embed --> Retrieve["3b. 混合检索 HybridRetriever<br>向量检索 + BM25 / RRF 融合"]

    Retrieve --> Rerank["4. 重排序 BGEReranker"]
    Rerank --> Confidence["5. 置信度评估 SignalFusionEvaluator"]

    Confidence -->|tier = low| Fallback2["兜底响应：没有足够把握"]
    Confidence -->|tier = medium / high| Generate["6. LLM 生成 LLMGenerator"]

    Generate -->|tier = medium| Uncertain["答案前加：以下回答仅供参考"]
    Generate -->|tier = high| Direct["直接返回答案"]

    Uncertain --> Response([返回结果：answer / sources / confidence / trace_id])
    Direct --> Response
    Fallback1 --> Response
    Fallback2 --> Response
    Clarify --> Response
```

## 置信度三路信号

```mermaid
flowchart LR
    R["retrieval_score<br>= top1.rerank_score<br>权重 0.6"] --> Fusion
    C["coverage_score<br>= query tokens 在 top1 content 中的覆盖率<br>权重 0.3"] --> Fusion
    G["score_gap<br>= top1.score - top2.score<br>权重 0.1"] --> Fusion

    Fusion["加权求和"] --> Score["confidence ∈ 0~1"]

    Score -->|">= 0.75"| High["high：直接回答"]
    Score -->|">= 0.50"| Medium["medium：加仅供参考前缀"]
    Score -->|"< 0.50"| Low["low：触发 fallback"]
```

## SSE 流式输出时序

```mermaid
sequenceDiagram
    participant Client as 客户端
    participant API as FastAPI
    participant Pipeline as RAGPipeline
    participant LLM as LiteLLM

    Client->>API: POST /chat/stream
    API->>Pipeline: run_stream(question, session_id)
    
    Note over Pipeline: 步骤 1-5（非流式）
    Pipeline->>Pipeline: 意图/改写/检索/重排/置信度
    
    Pipeline->>LLM: complete_stream(messages)
    
    loop 每个 token
        LLM-->>Pipeline: delta chunk
        Pipeline-->>API: {"type": "delta", "content": "..."}
        API-->>Client: data: {...}\n\n
    end
    
    Pipeline-->>API: {"type": "done", "sources": [...], "confidence": 0.85, "trace_id": "..."}
    API-->>Client: data: {...}\n\n
    API-->>Client: [DONE]
```

## RRF 融合算法

RRF（Reciprocal Rank Fusion）将向量检索和 BM25 结果合并：

```
rrf_score(doc) = Σ 1 / (k + rank_i)
```

- `k = 60`（平滑参数，减少顶部排名的影响）
- `rank_i` 为文档在第 i 路结果中的排名（从 0 开始）
- 同时出现在两路结果中的文档得到双重加分

示例（k=60）：

| 文档 | 向量排名 | BM25 排名 | RRF 分数 |
|------|---------|---------|---------|
| A | 0 | 0 | 1/60 + 1/60 ≈ 0.0333 |
| B | 1 | - | 1/61 ≈ 0.0164 |
| C | - | 1 | 1/61 ≈ 0.0164 |
