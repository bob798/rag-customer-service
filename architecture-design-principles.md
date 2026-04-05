# AI 客服系统·架构设计思想

> 整理自 Phase 1 设计过程中的架构讨论，作为面试素材和工程决策参考。
> 更新：2026-03-28

---

## 一、为什么手搓 RAG，而不用 LangChain/LlamaIndex

### 核心问题

框架能快速搭起来，但每一步的工程决策都变成黑盒：混合检索为什么用 RRF、置信度为什么三路信号、FAQ 为什么要专用 Parser——用框架时这些都说不清楚。手搓核心链路，每步决策有依据，出问题也能精确定位。

### 对比

| 维度 | 手搓 RAG | LangChain/LlamaIndex |
|------|----------|---------------------|
| 面试展示深度 | ✅ 每步有工程决策，说得清楚 | ❌ 框架黑盒，停在 API 层 |
| 代码可理解性 | ✅ 企业开发者能直接看懂改 | ❌ 需先学框架抽象 |
| 调试能力 | ✅ 直接断点，链路透明 | ❌ 层层回调，难追踪 |
| 替换灵活性 | ✅ 接口清晰，换实现不改调用方 | ❌ 框架版本升级有破坏性变更 |
| 上手速度 | ❌ 初期慢 | ✅ 快 |

### 结论

手搓是默认选择，但不封闭——通过抽象接口（Ports & Adapters）保留后续引入框架的通道。

---

## 二、Ports & Adapters（六边形架构）

### 问题背景

如果直接在业务代码里 `from langchain import ...`，未来想换掉就得全局改。如果只手搓，以后真的需要 LangChain 某个能力，又要大改。

### 解法

核心层定义抽象接口（Ports），手搓默认实现。外部框架通过 Adapter 接入，核心层完全不感知。

```
┌─────────────────────────────────────────────────┐
│                   RAGPipeline                   │
│    （只依赖抽象接口，不感知具体实现）                │
└──────────────┬────────────┬────────────┬────────┘
               │            │            │
        BaseRetriever  BaseEmbedder  BaseParser
          （Port）       （Port）      （Port）
               │            │            │
    ┌──────────┴──┐  ┌───────┴──┐  ┌─────┴──────────┐
    │ HybridRet.  │  │ Embedder │  │ ParserRegistry │
    │（手搓默认）  │  │（默认）   │  │（默认）         │
    └──────────┬──┘  └───────┬──┘  └─────┬──────────┘
               │ (可选)      │(可选)      │(可选)
    LangChainRetriever   HFAdapter   UnstructuredAdapter
       （Adapter）         (Adapter)     (Adapter)
```

### 抽象接口定义

```python
from abc import ABC, abstractmethod

class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[dict]:
        """返回: [{"chunk_id", "content", "score", ...}]"""
        ...

class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """返回: 归一化向量列表"""
        ...

class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        """判断此 Parser 是否能处理该类型"""
        ...

    @abstractmethod
    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        """返回: [{"chunk_id", "doc_id", "content", "metadata"}]"""
        ...
```

### 替换方式

```python
# 默认：手搓
pipeline = RAGPipeline(
    retriever=HybridRetriever(vector_store, bm25_store),
    embedder=Embedder("Alibaba-NLP/gte-Qwen2-1.5B-instruct"),
)

# 替换 Retriever 为 LangChain：只改注入，Pipeline 代码不动
pipeline = RAGPipeline(
    retriever=LangChainRetrieverAdapter(lc_retriever),
    embedder=Embedder("Alibaba-NLP/gte-Qwen2-1.5B-instruct"),
)
```

### 工程价值

- 单元测试：mock 接口，不依赖真实模型
- 替换成本：换 Embedding 模型 → 只改 Embedder 实现，接口不变
- 开源扩展：社区贡献者只需实现接口，不需要理解 Pipeline 内部

---

## 三、Parser 组件化（Strategy Pattern + Plugin Registry）

### 问题背景

不同文档类型的"语义单元"不同：

- **FAQ 文档**：语义单元是"一个 QA 对"。如果按字数切割，Q 和 A 可能被拆到不同 chunk——检索命中了问题，但 LLM 拿到的 chunk 里没有答案，导致幻觉。
- **政策文档**：语义单元是"一个段落"，按段落边界切割。
- **技术手册**：语义单元是"一个章节"，按标题层级切割。

一个 `DocumentProcessor` 类搞不定所有场景。

### 解法：Strategy Pattern + Plugin Registry

```python
class ParserRegistry:
    _parsers: list[BaseParser] = []

    @classmethod
    def register(cls, parser: BaseParser):
        """插件扩展入口：外部实现通过 register 注入，不改核心代码"""
        cls._parsers.insert(0, parser)

    @classmethod
    def get_parser(cls, file_type: str, content_hint: str = "") -> BaseParser:
        for p in cls._parsers:
            if p.can_handle(file_type, content_hint):
                return p
        return DefaultParser()  # 兜底：通用语义分块


# 内置注册
ParserRegistry.register(FAQParser())
ParserRegistry.register(PDFParser())
ParserRegistry.register(DocxParser())
```

### FAQ 专用 Parser 设计要点

```python
class FAQParser(BaseParser):
    """
    支持格式：
    1. Q: 问题\n   A: 答案
    2. ## 问题标题\n   答案正文
    3. 问：...\n   答：...
    """
    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        # 通过文件名或内容前 500 字符检测 FAQ 特征
        return "faq" in content_hint.lower() or self._detect_qa_pattern(content_hint)

    def parse(self, file_path, doc_id, metadata):
        text = Path(file_path).read_text(encoding="utf-8")
        qa_pairs = self._extract_qa_pairs(text)
        return [
            {
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "content": f"Q: {q}\nA: {a}",  # Q+A 整体作为一个 chunk
                "metadata": {**metadata, "type": "faq", "question": q}
            }
            for q, a in qa_pairs
        ]
```

### 扩展路径

| 新场景 | 新 Parser | 接入方式 |
|--------|----------|---------|
| 表格密集 PDF | `UnstructuredPDFParser` | `ParserRegistry.register(...)` |
| Markdown 文档 | `MarkdownParser`（按 heading 切割）| 同上 |
| 结构化 JSON | `JSONParser` | 同上 |
| 企业 Wiki 爬取 | `WikiParser` | 同上 |

---

## 四、RAG 全链路设计

### 链路总览

```
用户提问
  │
  ▼
意图识别（LLM）→ 范围外直接兜底 / 模糊返回澄清问题
  │ 范围内
  ▼
Query 改写（LLM）→ 口语化 → 规范化检索语句
  │
  ▼
混合检索：向量检索（gte-Qwen2-1.5B + ChromaDB）+ BM25（rank_bm25 + jieba）
  │         RRF 融合（Reciprocal Rank Fusion，k=60）
  ▼
BGE-Reranker-v2-m3 重排序（精排 top-5）
  │
  ▼
多信号置信度评分 → 三档分流
  │ >= 0.75  正常回答
  │ 0.50–0.75  附注"以下回答仅供参考"
  │ < 0.50  触发兜底
  ▼
LLM 生成回答（附来源引用）
  │
  ▼
SSE 流式输出（delta 帧 + done 帧）
```

### 每步的工程决策依据

**意图识别**：为什么不直接检索？因为范围外问题（"帮我写代码"）如果直接进 RAG，会取到不相关 chunks，LLM 强行生成答案，产生幻觉。

**Query 改写**：用户输入"退款咋整"，向量检索的结果会比"如何申请退款流程"差很多。LLM 改写一次，语义对齐，召回率提升明显。

**混合检索 + RRF**：
- 向量检索好在语义理解（"退款流程"匹配"申请退款需要"）
- BM25 好在精确关键词（"3 个工作日"精确命中）
- RRF 融合：`score = Σ 1/(k + rank_i)`，两路各自排名后互补，不需要归一化分值

**Reranker**：RRF 只看排名不看分值，精度有限。BGE-Reranker 用 Cross-Encoder 对 query-chunk 联合编码，精排质量更高。

**流式输出 + 置信度**：SSE 边输出边推，但置信度要全链路跑完才有。解法：先跑完 RAG 得到 confidence，再流式推 tokens，最终帧携带完整元数据（sources/confidence/uncertain）。

---

## 五、多信号置信度设计

### 为什么不用单一余弦相似度

| 问题 | 场景 | 影响 |
|------|------|------|
| 假高分 | "客服电话" 和 "退款电话" 余弦相似度高，但一个答不了另一个 | 错误给出高置信度 |
| 假低分 | Query 改写后语义偏移，导致相似度下降 | 错误触发兜底 |
| 无法区分"相关但不够"| top-1 和 top-2 分值接近，说明没有明确答案 | 应降低置信度 |

### 三路信号融合

```python
def compute_confidence(chunks: list[dict], query: str) -> float:
    if not chunks:
        return 0.0

    # 信号 1：向量语义相关度（BGE-Reranker 输出，normalize=True）
    retrieval_score = chunks[0].get("rerank_score", 0.0)

    # 信号 2：关键词覆盖率（query 分词后在 top-1 chunk 中的覆盖比例）
    query_tokens = set(jieba.cut(query))
    chunk_text = chunks[0]["content"]
    covered = sum(1 for t in query_tokens if t in chunk_text)
    coverage_score = covered / len(query_tokens) if query_tokens else 0.0

    # 信号 3：top-1 vs top-2 分差（gap 越大，top-1 越突出）
    score_gap = 0.0
    if len(chunks) >= 2:
        score_gap = retrieval_score - chunks[1].get("rerank_score", 0.0)
    score_gap = min(score_gap, 1.0)  # 归一化上限

    # 加权融合
    confidence = 0.6 * retrieval_score + 0.3 * coverage_score + 0.1 * score_gap
    return round(confidence, 3)
```

### 阈值校准方法

不拍脑袋定 0.5/0.75，用数据驱动：

1. 用黄金问答集（50-100 题）跑完整 RAG 链路，收集所有 confidence 分值
2. 人工标注每题答案质量（Correct / Partial / Wrong）
3. 画 Precision-Recall 曲线：
   - `high` 阈值：P=0.95 时的 confidence 分值（确保高置信度的答案基本正确）
   - `low` 阈值：R=0.95 时的 confidence 分值（确保大多数能答的都不触发兜底）
4. 初始值 0.75/0.50，实测后调整

### 参考开源设计

| 项目 | 置信度方案 | 对我们的启发 |
|------|-----------|------------|
| RAGAS | faithfulness + context_recall + answer_relevancy 三维评分 | Phase 2 引入 LLM-as-judge 替换 coverage_score |
| TruLens | RAG Triad（Answer Relevance / Context Relevance / Groundedness）三轴评估，定位瓶颈 | 三轴独立评分，能精确区分"检索差"还是"生成差" |
| RAGFlow | per-chunk 评分 + 文档时效性权重 | 知识库旧文档降权是个好思路，Phase 2 可加 |
| Haystack | 阈值可配置，运营侧调参 | 对应我们的配置管理模块 |

**最值得借鉴：RAGAS `answer_relevancy` 反推法**
用生成的答案逆向生成 N 个可能问题，计算这些问题与原始输入的相似度。
逻辑：好答案反推出的问题应该和原问题很像。不需要 ground truth，是无监督评估答案相关性的聪明方案。
→ Phase 2 引入，可直接作为答案质量的补充信号。

---

## 六、可观测性 & 数据飞轮

### 为什么可观测性是一等公民

RAG 系统上线后最大的问题是"不知道哪里出了问题"：
- 用户反馈"回答不对"→ 不知道是召回问题还是生成问题
- 兜底触发率高 → 不知道是知识库盲区还是阈值太高
- 延迟高 → 不知道是 Embedding 慢还是 LLM 慢

结构化日志 + trace_id 让每个问题都可追溯。

### trace_id 全链路追踪

```json
{
  "trace_id": "t-abc123",
  "session_id": "sess_xyz",
  "timestamp": "2026-03-28T10:00:00Z",
  "query": {
    "original": "退款咋整",
    "rewritten": "如何申请退款"
  },
  "retrieval": {
    "top_k_chunks": ["c1", "c2", "c3"],
    "confidence": 0.87,
    "confidence_tier": "high",
    "signals": {
      "retrieval_score": 0.91,
      "coverage_score": 0.80,
      "score_gap": 0.22
    }
  },
  "latency_ms": {
    "intent": 120,
    "query_rewrite": 150,
    "retrieval": 80,
    "rerank": 30,
    "generate": 900,
    "total": 1280
  },
  "fallback_triggered": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

### 语料数据三层来源

```
L1 合成语料（RAGAS generate_testset）
   ↓ 从知识库文档自动生成 QA 对，无需人工标注
   ↓ 用途：快速验证检索覆盖率，冷启动

L2 公开数据集（DuReader / CMRC2018）
   ↓ 中文机器阅读理解标准 Benchmark
   ↓ 用途：校准通用中文理解能力，对齐行业标准

L3 真实业务数据（用户提问日志）
   ↓ 脱敏处理，结合人工标注或 LLM-as-judge
   ↓ 用途：真实分布，发现知识库盲区，长期驱动优化
```

### 数据飞轮

```
用户提问
  │
  ▼ trace_id 记录全链路
低置信度 / 兜底触发 / 用户反馈差
  │
  ▼ 标记为"覆盖盲区"
定期汇总（每周 review）
  │
  ▼
补充知识库 / 修正 Q&A
  │
  ▼
RAGAS 重跑评测集（faithfulness / context_recall / answer_relevancy）
  │
  ▼
指标提升验证 → 继续收集
```

### RAGAS 三项核心指标

| 指标 | 含义 | 目标值 |
|------|------|--------|
| `faithfulness` | 答案是否有知识库依据（防幻觉）| > 0.90 |
| `context_recall` | 问题是否被知识库充分覆盖（召回率）| > 0.85 |
| `answer_relevancy` | 答案是否切题（生成质量）| > 0.85 |

---

## 七、可追踪性组件化（BaseTracer）

### 为什么 Tracer 要组件化

RAG 系统的可追踪性需求会随阶段变化：
- Phase 1：结构化 JSON 日志写本地文件，零依赖
- Phase 2：接入 Langfuse（自托管），有可视化 UI
- 生产：接入 OpenTelemetry，对接企业已有的 Jaeger/Tempo

如果直接在 Pipeline 里写 `logger.info(json.dumps(...))`，切换到 Langfuse 就要改 Pipeline 核心代码。组件化后只换注入，Pipeline 不动。

### 开源 Observability 框架选型

| 框架 | 定位 | 推荐场景 |
|------|------|---------|
| **Langfuse** | 开源 LLM observability，可自托管 | Phase 2 首选：有 Web UI、支持 RAGAS 评分写入、数据不出境 |
| **Phoenix (Arize)** | RAG 专项可观测，OpenTelemetry 兼容 | 需要深度 retrieval 质量可视化 |
| **OpenLLMetry** | OpenTelemetry for LLMs | 已有 OTEL 基础设施的企业 |
| **StructuredLog** | 自研 JSON 日志 | Phase 1 默认，零依赖 |

### 接口设计

```python
# core/interfaces/tracer.py
class BaseTracer(ABC):
    @abstractmethod
    def start_trace(self, trace_id: str, session_id: str) -> dict: ...

    @abstractmethod
    def record_step(self, span: dict, step: str, data: dict): ...

    @abstractmethod
    def end_trace(self, span: dict, result: dict): ...

# core/rag/tracer.py — Phase 1 默认实现，零依赖
class StructuredLogTracer(BaseTracer):
    def start_trace(self, trace_id, session_id):
        return {"trace_id": trace_id, "session_id": session_id,
                "start_ts": time.time(), "steps": {}}

    def record_step(self, span, step, data):
        span["steps"][step] = {**data, "ts": time.time()}

    def end_trace(self, span, result):
        span["latency_ms"] = round((time.time() - span["start_ts"]) * 1000)
        span.update(result)
        logger.info(json.dumps(span, ensure_ascii=False))

# Phase 2 可选 Adapter（不在 requirements.txt 主依赖）
class LangfuseTracer(BaseTracer):
    def __init__(self):
        from langfuse import Langfuse
        self._client = Langfuse()  # 读 LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY

    def start_trace(self, trace_id, session_id):
        return self._client.trace(id=trace_id, session_id=session_id)

    def record_step(self, span, step, data):
        span.span(name=step, input=data)

    def end_trace(self, span, result):
        span.update(output=result)
```

### RAGPipeline 注入方式

```python
# 默认零依赖
pipeline = RAGPipeline(tracer=StructuredLogTracer(), ...)

# 切换 Langfuse，Pipeline 代码不动
pipeline = RAGPipeline(tracer=LangfuseTracer(), ...)
```

---

## 八、完整组件化地图

### 所有可组件化的模块

```
RAGPipeline（编排层，只依赖抽象接口）
│
├── BaseParser          → ParserRegistry（Strategy + Plugin）
│     ├── DefaultParser（段落边界分块，Phase 1 默认）
│     ├── FAQParser（Q&A对原子分块）
│     └── [可扩展] UnstructuredAdapter, MarkdownParser...
│
├── BaseChunker         → 分块策略，与 Parser 正交
│     ├── SemanticChunker（段落+overlap，Phase 1 默认）
│     ├── FixedChunker（固定字数，简单场景）
│     └── [Phase 2] HierarchicalChunker（摘要+细节双层索引）
│
├── BaseEmbedder        → Embedding 模型
│     ├── Embedder（gte-Qwen2-1.5B，Phase 1 默认）
│     └── [可选] QwenAPIEmbedder（内存不足时降级）
│
├── BaseRetriever       → 检索策略
│     ├── HybridRetriever（向量+BM25+RRF，Phase 1 默认）
│     └── [可选] LangChainRetrieverAdapter
│
├── BaseReranker        → 重排序策略
│     ├── BGEReranker（本地，Phase 1 默认）
│     ├── NoopReranker（直接透传，测试用）
│     └── [可选] CohereRerankerAdapter（API）
│
├── BaseConfidenceEvaluator  → 置信度评估策略
│     ├── SignalFusionEvaluator（三路信号融合，Phase 1 默认）
│     └── [Phase 2] RAGASEvaluator（LLM-as-judge）
│
├── BaseFallbackHandler → 兜底动作策略（业务定制最强）
│     ├── TellUserHandler（直接告知无法回答，Phase 1 默认）
│     ├── WebhookHandler（推飞书/钉钉工单）
│     └── LeadCaptureHandler（留资表单）
│
└── BaseTracer          → 可观测性后端
      ├── StructuredLogTracer（JSON 日志，Phase 1 默认）
      ├── LangfuseTracer（自托管 UI，Phase 2）
      └── OTELTracer（企业级，Phase 3）
```

### Phase 1 实际需要实现的

| 模块 | Phase 1 实现 | 备注 |
|------|------------|------|
| BaseParser + Registry | ✅ 实现 | FAQParser + DefaultParser |
| BaseChunker | ✅ 实现 | SemanticChunker（从 DocumentProcessor 剥离）|
| BaseEmbedder | ✅ 实现 | gte-Qwen2-1.5B |
| BaseRetriever | ✅ 实现 | HybridRetriever |
| BaseReranker | ✅ 实现 | BGEReranker + NoopReranker（测试用）|
| BaseConfidenceEvaluator | ✅ 实现 | SignalFusionEvaluator |
| BaseFallbackHandler | ✅ 实现 | TellUserHandler（Phase 1 只需这个）|
| BaseTracer | ✅ 实现 | StructuredLogTracer（零依赖）|

### 目录结构（更新版）

```
core/
├── interfaces/               # 所有抽象接口（Ports）
│   ├── parser.py             # BaseParser
│   ├── chunker.py            # BaseChunker
│   ├── embedder.py           # BaseEmbedder
│   ├── retriever.py          # BaseRetriever
│   ├── reranker.py           # BaseReranker
│   ├── confidence.py         # BaseConfidenceEvaluator
│   ├── fallback_handler.py   # BaseFallbackHandler
│   └── tracer.py             # BaseTracer
├── knowledge/
│   ├── parsers/
│   │   ├── registry.py       # ParserRegistry（Strategy + Plugin）
│   │   ├── default.py        # DefaultParser
│   │   └── faq.py            # FAQParser
│   ├── chunker.py            # SemanticChunker（从 document_processor 剥离）
│   ├── embedder.py           # Embedder（gte-Qwen2-1.5B）
│   ├── vector_store.py       # ChromaDB
│   └── bm25_store.py         # rank_bm25 + jieba
└── rag/
    ├── intent.py
    ├── query_rewriter.py
    ├── retriever.py          # HybridRetriever
    ├── reranker.py           # BGEReranker
    ├── confidence.py         # SignalFusionEvaluator
    ├── tracer.py             # StructuredLogTracer
    ├── fallback_handler.py   # TellUserHandler
    ├── generator.py
    └── pipeline.py           # 注入所有组件
```


> 组件选型对比与决策汇总见 [tech-selection.md](./tech-selection.md)。
