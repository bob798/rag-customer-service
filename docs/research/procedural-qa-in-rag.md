# RAG 系统中的流程类问答：学术定义、开源方案与最佳实践

> 调研日期：2026-04-10 | 定位：通用技术调研
> 问题：RAG 对「流程引导」「实操指导」类问题效果差，业界如何解决

---

## 一、学术定义

### 1.1 问题命名

学术界没有一个统一术语，该问题处于多个研究领域交叉点：

```
                Complex QA (复杂问答)
               /         |          \
     Multi-hop QA   Compositional QA   Long-form QA
     (跨文档推理)     (组合式问答)        (长答案生成)
              \           |               /
               \          |              /
            Procedural Question Answering
            (流程类问答：有序步骤 + 状态变化 + 因果依赖)
```

最精确的学术描述：**"Context fragmentation of procedural knowledge in retrieval-augmented generation"**（检索增强生成中程序性知识的上下文碎片化）

### 1.2 核心 Benchmark

| Dataset | 年份 | 测什么 | 规模 | 与流程 QA 的关系 |
|---------|------|--------|------|-----------------|
| **ProPara** | 2018 NAACL | 程序文本中的实体状态追踪 | 488 段落 | 核心：理解步骤间状态变化 |
| **TechQA** | 2020 ACL | 技术支持问答（IBM） | 600 QA + 801k 文档 | 最接近客服场景 |
| **HotpotQA** | 2018 EMNLP | 跨文档多跳推理 | 113k QA 对 | 跨 chunk 信息聚合 |
| **ELI5** | 2019 ACL | 长答案生成 | 272k QA 对 | 流程类回答天然是长文 |
| **DoQA** | 2020 | 多轮 how-to 对话 | 2.4k 对话 | 对话式流程引导 |
| **MuSiQue** | 2022 | 多步组合推理 | 25k QA 对 | 更难的多跳推理 |
| **ASQA** | 2022 EMNLP | 歧义长答案 QA | 6.3k QA 对 | 多面回答 |
| **WIQA** | 2019 EMNLP | 程序文本反事实推理 | - | "如果跳过步骤 2 会怎样？" |

### 1.3 关键论文

| 论文 | 年份 | 贡献 |
|------|------|------|
| Dalvi et al. "Tracking State Changes in Procedural Text" | 2018 NAACL | 形式化程序文本理解为状态追踪 |
| Tandon et al. "WIQA" | 2019 EMNLP | 扩展到反事实推理 |
| Yang et al. "HotpotQA" | 2018 EMNLP | 多跳 QA 基准 |
| Fan et al. "ELI5" | 2019 ACL | 长答案生成 |
| Castelli et al. "TechQA" | 2020 ACL | 技术支持 QA，最接近客服 |
| **Liu et al. "Lost in the Middle"** | 2023 TACL | LLM 对中间 context 注意力不足 |
| Stelmakh et al. "ASQA" | 2022 EMNLP | 事实问题与长答案的桥梁 |

### 1.4 RAG 特有的失败模式

**Lost in the Middle** (Liu et al., 2023)
- LLM 对 context 中间位置的 chunk 注意力最弱
- 流程的中间步骤（步骤 3/4/5）最容易被忽略
- 解决方案：将最相关的 chunk 放在首尾位置

**Context Fragmentation**
- 步骤被 chunking 切断后，每个 chunk 语义不完整
- 检索到 chunk A（步骤 1-2）但漏了 chunk B（步骤 3-5）
- 标准 top-K 检索无法保证完整覆盖

### 1.5 四个技术断点

```
① Chunking   步骤序列被字符数切断
② Embedding  向量空间无顺序信息，"步骤1"和"步骤5"可能距离很远
③ Retrieval  Top-K 按相关度排序，不保证步骤完整覆盖
④ Generation Prompt 没要求 LLM 组织成步骤输出
```

---

## 二、开源社区解决方案

### 2.1 LlamaIndex

| 组件 | 解决的断点 | 机制 | 适用场景 |
|------|-----------|------|---------|
| **`SentenceWindowNodeParser`** | ① Chunking | 每句话作为检索单元，但元数据中保留前后 N 句窗口。检索命中一句后，用 `MetadataReplacementPostProcessor` 替换为完整窗口 | 步骤散落在相邻句子中 |
| **`HierarchicalNodeParser`** | ① Chunking | 多层级切分（如 2048→512→128），建立 parent-child 树 | 流程集中在一个段落但段落过长 |
| **`AutoMergingRetriever`** | ③ Retrieval | 当某 parent 下超阈值比例的 child 被命中时，自动合并返回 parent | 配合 HierarchicalNodeParser |
| **`RecursiveRetriever`** | ③ Retrieval | 检索小 chunk → 递归获取 parent node | 精确检索 + 完整上下文 |
| **`SubQuestionQueryEngine`** | ③ Retrieval | 将复杂问题拆为子问题分别检索后合并 | "退款流程"拆为"条件+步骤+时间" |

**最佳组合**：`SentenceWindowNodeParser` + `MetadataReplacementPostProcessor` — 检索精准（句子级），返回完整（窗口级）。

**对比**：

| | Sentence Window | Auto-Merging |
|---|---|---|
| 适用 | 信息紧密相邻 | 信息分散但在同一段落 |
| 粒度 | 句子 + 窗口 | child chunk + parent chunk |
| 配置复杂度 | 低 | 中（需要设阈值） |
| 额外存储 | 低（metadata 中存窗口文本） | 中（多层级 chunk） |

Sources: [LlamaIndex Node Parsers](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/), [Sentence Window API](https://docs.llamaindex.ai/en/stable/api_reference/node_parsers/sentence_window/)

### 2.2 LangChain

| 组件 | 解决的断点 | 机制 | 适用场景 |
|------|-----------|------|---------|
| **`ParentDocumentRetriever`** | ①③ | 小 chunk 检索 → 返回父文档/大 chunk。需要额外 docstore | 最直接的"检索精确+返回完整" |
| **`MultiQueryRetriever`** | ③ | LLM 将 query 改写为多个变体，分别检索后合并去重 | 一个流程问题覆盖多个方面 |
| **`MultiVectorRetriever`** | ② | 同一文档存多个向量（摘要/问题/原文），匹配任一 | 提升召回多样性 |
| **`EnsembleRetriever`** | ③ | 融合多个 retriever 结果（BM25 + dense），RRF | 已在本项目使用 |
| **`ContextualCompressionRetriever`** | ④ | LLM 压缩检索结果只保留相关部分 | ⚠️ 可能删除中间步骤 |

**注意**：`ContextualCompressionRetriever` 对流程类问题可能**适得其反**——"压缩"掉了中间步骤。

Sources: [Parent Document Retriever](https://blog.lancedb.com/modified-rag-parent-document-bigger-chunk-retriever-62b3d1e79bc6/), [Context Enrichment Strategies](https://pixion.co/blog/rag-strategies-context-enrichment)

### 2.3 Haystack

| 组件 | 解决的断点 | 机制 |
|------|-----------|------|
| **`LostInTheMiddleRanker`** | ④ | 将最相关结果放在首尾，避免 LLM 忽略中间内容 |
| **`DocumentJoiner`** | ③ | 合并多路 Retriever 结果（RRF/concatenation） |
| **`MetaFieldRanker`** | ③④ | 按 metadata 排序，可恢复原文顺序 |
| **Auto-Merging Pipeline** | ①③ | 2024 新增，类似 LlamaIndex 的层级合并 |

Sources: [Haystack Auto-Merging](https://haystack.deepset.ai/blog/improve-retrieval-with-auto-merging), [Auto-Merging RAG](https://www.davidsbatista.net/blog/2024/09/12/Auto-Merging-RAG-Haystack/)

### 2.4 中文 RAG 框架

| 框架 | 核心方案 | Stars | 适用场景 |
|------|---------|-------|---------|
| **RAGFlow** | Template-based Chunking（"Manual" 模板按手册结构切分）+ TOC 提取 + Chunk 可视化编辑 | ~30k | **产品手册/说明书最佳选择** |
| **Dify** | Workflow 可视化编排（拆问题→多次检索→合并） | ~55k | 灵活但 RAG 不够深度 |
| **FastGPT** | QA 对索引（直接存"问→完整步骤"） | ~20k | 暴力有效，绕过 chunking |
| **QAnything** | BCEmbedding 中英双语 + BCE Reranker | ~13k | 中文检索质量 |

**RAGFlow 特别方案**：
- "Manual" 模板：按手册章节/步骤结构切分，保持流程完整性
- TOC 提取（2025 新增）：自动生成文档目录结构，缓解 chunking 导致的上下文丢失
- Chunk 可视化编辑：最后兜底，人工调整 chunk 边界

Sources: [RAGFlow Configure Knowledge Base](https://ragflow.io/docs/configure_knowledge_base)

### 2.5 独立工具

| 工具 | 解决什么 | 原理 |
|------|---------|------|
| **Anthropic Contextual Retrieval** | ②③ | 每个 chunk 加 LLM 生成的上下文前缀，检索失败率 -67% |
| **DSPy** | 全链路 | 自动优化 prompt 和参数，可发现最优 retrieval 策略 |
| **Unstructured.io** | ① | 解析为结构化元素（Title/ListItem 等），保留文档结构 |
| **Chonkie** | ① | 轻量分块库，支持 semantic/sentence chunking |

---

## 三、最佳实践总结

### 3.1 四层解决方案

| 层级 | 方案 | 成本 | 效果 |
|------|------|------|------|
| **L1 Prompt** | Generator 增加流程意识 + 检索后按原文排序 + 增大 top-K | 零 | 30-40% |
| **L2 检索增强** | Parent-Child Chunking + 邻居扩展 + Multi-Query | 低 | 60-70% |
| **L3 架构改造** | 结构化知识预处理 + 两阶段检索 + 意图路由 | 中 | 80-90% |
| **L4 范式转换** | Graph RAG + Agentic Workflow + 决策树混合 | 高 | 90%+ |

### 3.2 推荐实施路径

```
Day 1:  L1 — 改 prompt + 原文排序 + top_k=10
         → 零成本，30 分钟部署

Week 1: L2 — SentenceWindowNodeParser 思路（检索小 chunk，返回上下文窗口）
              + post-retrieval 邻居扩展（chunk_index ±1）
         → 投入产出比最高

Week 2: L2 — 意图子分类（factual vs procedural）+ 条件参数路由
         → 不同类型问题走不同参数

按需:   L3 — 结构化知识预处理（LLM 提取为 JSON 步骤）
              或 RAGFlow "Manual" 模板
         → 流程类问题占比 > 30% 时值得投入
```

### 3.3 方案对比评测方法

使用 RAG Triad 评估（LlamaIndex TruLens）：

| 指标 | 含义 | 流程类特别关注 |
|------|------|--------------|
| **Context Relevance** | 检索到的 chunk 与问题相关吗？ | 步骤完整性：5 步是否都被检索到 |
| **Groundedness** | 回答是否忠实于检索内容？ | 步骤顺序：LLM 是否编造了不存在的步骤 |
| **Answer Relevance** | 回答与问题相关吗？ | 操作可行性：回答是否可执行 |

额外指标（流程类专用）：
- **Step Completeness**：回答包含的步骤数 / 标准答案步骤数
- **Step Ordering**：步骤顺序与标准答案的 Kendall tau 相关性
- **Prerequisite Coverage**：前置条件是否被提及

---

## 四、关键参考资料

### 论文
- [ProPara (Dalvi et al., 2018)](https://arxiv.org/abs/1805.06975) — 程序文本状态追踪
- [HotpotQA (Yang et al., 2018)](https://arxiv.org/abs/1809.09600) — 多跳 QA
- [TechQA (Castelli et al., 2020)](https://arxiv.org/abs/1911.02984) — 技术支持 QA
- [Lost in the Middle (Liu et al., 2023)](https://arxiv.org/abs/2307.03172) — LLM 中间注意力缺失
- [ASQA (Stelmakh et al., 2022)](https://arxiv.org/abs/2204.06092) — 长答案 QA
- [Awesome RAG Reasoning (EMNLP 2025)](https://github.com/DavidZWZ/Awesome-RAG-Reasoning) — RAG 推理资源汇总

### 框架文档
- [LlamaIndex Node Parsers](https://developers.llamaindex.ai/python/framework/module_guides/loading/node_parsers/modules/)
- [LangChain Parent Document Retriever](https://blog.lancedb.com/modified-rag-parent-document-bigger-chunk-retriever-62b3d1e79bc6/)
- [Haystack Auto-Merging](https://haystack.deepset.ai/blog/improve-retrieval-with-auto-merging)
- [RAGFlow Knowledge Base Config](https://ragflow.io/docs/configure_knowledge_base)
- [Context Enrichment Strategies](https://pixion.co/blog/rag-strategies-context-enrichment)

### 实践指南
- [Unstructured Chunking Best Practices](https://unstructured.io/blog/chunking-for-rag-best-practices)
- [Weaviate Chunking Strategies](https://weaviate.io/blog/chunking-strategies-for-rag)
- [Databricks RAG Chunking Guide](https://community.databricks.com/t5/technical-blog/the-ultimate-guide-to-chunking-strategies-for-rag-applications/ba-p/113089)
- [Sentence Window vs Auto-Merging](https://medium.com/@p.saha/optimizing-rag-pipelines-sentence-window-retrieval-or-auto-merging-retrieval-950b50a4eb76)
- [Anthropic Contextual Retrieval](https://www.anthropic.com/news/contextual-retrieval)
