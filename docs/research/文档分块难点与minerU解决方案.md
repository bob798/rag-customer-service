# 中文文本分块最佳实践

> 调研日期：2026-04-08 | 定位：通用技术选型参考
> 信息来源：NVIDIA RAG Benchmark 2024、Anthropic Contextual Retrieval、CRUD-RAG ACM TOIS 2024、Chroma 2024 评测

---

## 一、中文分块的特有问题

### 1.1 Token 计数失效

英文 `len(text.split())` 按空格分词即可粗略估算 token 数，但中文无空格：

| 方法 | 中文准确度 | 速度 | 适用场景 |
|------|-----------|------|---------|
| `len(text.split())` | ❌ 极差（接近 0） | 极快 | **禁止用于中文** |
| `len(text)` 字符数 | ✅ 良好 | 极快 | **通用首选，零依赖** |
| `len(text) // 1.5` | ✅ 良好 | 极快 | 中英混合文档修正 |
| jieba 分词后计数 | ✅ 精确 | 慢 | 需要词粒度控制 |
| tiktoken `cl100k_base` | ✅ 精确 | 快 | 与 OpenAI 模型对齐 |

**核心结论**：中文字符与 BPE token 比约为 1.4–1.76:1（Microsoft CJK 研究）。`len(text)` 是最简单可靠的跨模型通用度量。

### 1.2 分隔符缺失

只按 `\n\n` 分段会遗漏大量中文段落边界。中文需要完整的标点分隔符层级：

```python
CHINESE_SEPARATORS = [
    "\n\n",   # 段落边界（最高优先级）
    "\n",     # 单换行
    "。",      # 句号（最常用句终符）
    "！",      # 感叹号
    "？",      # 问号
    "；",      # 分号
    "……",     # 省略号
    "，",      # 逗号（最后手段）
    "、",      # 顿号
    " ",      # 英文空格（混合内容）
    "",       # 字符级兜底
]
```

> ⚠️ **LangChain 已知 Bug** (#18770)：`RecursiveCharacterTextSplitter` 处理中文时，句号 `。` 会出现在下一块开头而非当前块末尾。需手动后处理。

### 1.3 Overlap 机制退化

英文按空格分词取最后 N 个词作为 overlap，中文无空格会导致：
- overlap 取到整个 chunk（如果整个 chunk 被视为一个"词"）
- 或 overlap 为空

**解决**：改用字符切片 `chunks[i-1][-overlap_chars:]`，不依赖分词。

---

## 二、Chunk Size 选择

### 2.1 中文场景推荐值

| 场景 | 推荐字符数 | 等效 token 数 | 说明 |
|------|-----------|--------------|------|
| 事实性问答（FAQ、客服） | 200–400 字 | ~140–280 tokens | 短 chunk 精确度高 |
| 政策/合同/法规分析 | 500–800 字 | ~350–560 tokens | 需保留条款完整性 |
| 页级分块（PDF） | 800–1200 字 | ~560–840 tokens | NVIDIA 评测最稳定策略 |
| 技术文档 | 400–600 字 | ~280–420 tokens | 平衡精度与上下文 |

### 2.2 关键实验结论

来自 Chroma 2024、NVIDIA 2024、CRUD-RAG 等多项评测：

1. **同一语料，最好与最差分块策略的召回率差距达 9%**（Chroma）
2. **chunk < 100 字符**：语义不完整，召回率显著下降
3. **chunk > 1000 字符**：引入噪声，精度下降
4. **页级分块精度 0.648，标准差最低 0.107**——跨文档类型最稳定（NVIDIA）
5. **top-k 与 chunk_size 负相关**：chunk 越小 → top-k 越大（8–12），chunk 越大 → top-k 可小（4–6）
6. **Overlap 推荐 chunk_size 的 10–15%**：防止关键实体在边界处截断

### 2.3 Overlap 的价值

Overlap 不是"重复浪费"，而是：
- 防止实体名/术语在边界被截断
- 为相邻 chunk 提供过渡上下文
- 推荐值：chunk_size 的 10–15%，即 40–90 字符

---

## 三、分块策略对比

### 3.1 经典方法

| 策略 | 原理 | 优点 | 缺点 |
|------|------|------|------|
| **固定长度** | 按字符数/token 数切分 | 简单、可预测 | 语义截断 |
| **Recursive（递归分隔符）** | 按分隔符优先级递归切分 | 保留段落/句子边界 | 需配置中文分隔符 |
| **基于文档结构** | 按标题/章节/段落切分 | 保留逻辑结构 | 依赖文档格式 |
| **语义分块** | 按 embedding 相似度检测语义边界 | 语义完整性最好 | 需要 embedding 模型，慢 |
| **页级分块** | 按 PDF 页切分 | 最稳定（NVIDIA 结论） | 页面可能包含多个主题 |

### 3.2 前沿方法（2024-2025）

| 方法 | 原理 | 效果 | 成本 |
|------|------|------|------|
| **Late Chunking** (Jina 2024) | 先整文档 embedding，再按位置切分 | 召回率最高，保留跨块语义 | 中等 |
| **Meta-chunking** | 用 LLM 困惑度（PPL）检测语义边界 | 精度最高 | 高（需 LLM 推理） |
| **Contextual Retrieval** (Anthropic 2024) | 分块后用 LLM 给每个 chunk 加上下文说明 | 检索失败率降低 67% | 中（每 chunk 一次 LLM 调用） |
| **Jina Segmenter API** | 原生中文语义分割 | 良好 | API 费用 |
| **Agentic Chunking** | LLM 判断每句话属于哪个主题 chunk | 主题一致性最好 | 极高 |

### 3.3 Contextual Retrieval 详解

Anthropic 2024 年提出的方案，直接解决"chunk 脱离原文后失去身份信息"的问题：

**核心思路**：分块后，用 LLM 为每个 chunk 生成一段上下文前缀：

```
原始 chunk: "收入同比增长 3%，主要由云服务业务驱动。"
加上下文后: "这段内容来自某某公司 2024 年 Q3 财报的业务概览部分。收入同比增长 3%，主要由云服务业务驱动。"
```

**效果**（Anthropic 测试数据）：

| 配置 | 检索失败率 | 降幅 |
|------|-----------|------|
| 基线（标准 RAG） | 5.7% | — |
| + Contextual Embedding | 3.7% | -35% |
| + Contextual BM25 | 2.9% | -49% |
| + Reranking | **1.9%** | **-67%** |

**适用场景**：文档数量可控（数百~数千），对质量要求高。成本是每个 chunk 需一次 LLM 调用。

---

## 四、中文 RAG Benchmark

### 4.1 CRUD-RAG（ACM TOIS 2024，上海 AI 研究院）

中文 RAG 专项评测基准，4 类任务覆盖 RAG 全场景：

| 任务类型 | 说明 | 评估重点 |
|---------|------|---------|
| **Create** | 生成新内容（如摘要） | 生成质量 |
| **Read** | 回答事实性问题 | 检索精度 |
| **Update** | 基于新信息更新已有知识 | 知识融合 |
| **Delete** | 识别并拒绝无法回答的问题 | 幻觉控制 |

基线配置：chunk_size=128 tokens，top-k=8，bge-base embedding

### 4.2 RAGAS 评估指标

| 指标 | 含义 | 生产目标 |
|------|------|---------|
| Context Recall | 答案所需信息是否被检索回来 | > 0.8 |
| Context Precision | 检索到的内容有多少真正有用 | > 0.8 |
| Faithfulness | 回答是否忠实于检索内容（不幻觉） | > 0.8 |
| Answer Relevance | 回答与问题的相关度 | > 0.7 |

---

## 五、推荐策略选择

```
你的场景是什么？
│
├── 快速启动 / 资源有限
│   └── Recursive + 中文标点分隔符，chunk_size=400-600 字符
│       （零成本，效果已不错）
│
├── 追求检索质量
│   ├── 文档量 < 1000 → + Contextual Retrieval（每 chunk 加上下文）
│   └── 文档量 > 1000 → + Late Chunking（Jina）或语义分块
│
├── 文档结构清晰（有标题层级）
│   └── 基于文档结构分块 + Recursive 兜底
│
└── 极端质量要求
    └── Meta-chunking 或 Agentic Chunking（LLM 驱动，成本高）
```

通用起步配置：

```python
# 中文 RAG 分块推荐配置
chunk_size = 500        # 字符数
overlap = 50            # 字符数（10%）
separators = ["\n\n", "\n", "。", "！", "？", "；", "……", "，", "、", " ", ""]
count_method = len      # 字符计数，非 split()
top_k = 8               # 配合 500 字 chunk
```

---

## 六、关键参考资料

| 资料 | 价值 |
|------|------|
| [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval) | 上下文增强检索，降低失败率 67% |
| [NVIDIA: Finding the Best Chunking Strategy](https://developer.nvidia.com/blog/finding-the-best-chunking-strategy-for-accurate-ai-responses/) | 页级分块评测，chunk_size 对比 |
| [CRUD-RAG Benchmark](https://arxiv.org/abs/2401.17043) | 中文 RAG 权威评测 |
| [Late Chunking (Jina)](https://jina.ai/news/late-chunking-in-long-context-embedding-models/) | 跨块语义保留 |
| [Best Chunking Strategies 2025 (Firecrawl)](https://www.firecrawl.dev/blog/best-chunking-strategies-rag) | 策略综述 |
| [LangChain Issue #18770](https://github.com/langchain-ai/langchain/issues/18770) | 中文分隔符 Bug |
| [CJK in AI (Microsoft)](https://tonybaloney.github.io/posts/cjk-chinese-japanese-korean-llm-ai-best-practices.html) | 字符/token 比例研究 |
| [RAGAS 文档](https://docs.ragas.io/) | RAG 评估框架 |
| [腾讯 2024 RAG 实践](https://cloud.tencent.cn/developer/article/2483415) | 中文 chunk_size 200-500 字 |
| [RAG 分块策略：Meta-chunking/Late chunking](https://www.cnblogs.com/ting1/p/18598176) | 前沿方法中文解读 |
