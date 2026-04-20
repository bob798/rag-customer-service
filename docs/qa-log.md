# RAG 系统研究 Q&A 日志

> 记录开发过程中的技术问题与解答。每次新增一个 `## QA-NNN` 节。
>
> **自动化更新约定**：每次研究对话结束后，将核心 Q&A 追加到本文件。
> 长期目标：通过 Claude Code hook 在对话结束时自动提取并追加。

---

## QA-001 · 2026-04-06 · 近义词检索质量

**Q: 为什么 GTE-Qwen2（47%）比 BM25（60%）还差？**

A: 不是 BERT 不懂中文同义词，是**高度同质化的小语料库里，向量空间失去区分度**。8 条音频故障 FAQ 全在「故障诊断」语义簇内，向量彼此太近，「爆音」和「没声音」的向量距离比「音响不出声」和「音箱没有声音」还小。这是 False Semantic Similarity 问题，不是泛化能力问题。

---

## QA-002 · 2026-04-06 · BERT 语义泛化价值

**Q: BERT 语义泛化在音响客服场景是否有效？**

A: 视知识库规模而定。

| 条件 | BERT 价值 |
|------|----------|
| 知识库 >100 条，覆盖多话题 | ✅ 有效 |
| 用户词汇和文档词汇完全不重合 | ✅ 有效 |
| 8-20 条同领域 FAQ | ❌ 向量空间无法区分 |
| 同义词在同一语义簇内 | ❌ False Similarity 问题 |

当前 8 条 FAQ 的结论不代表生产状态。知识库扩充到 100+ 条后，BERT 价值会显著回升。

---

## QA-003 · 2026-04-06 · 解决小知识库 BERT 失效

**Q: "同一产品 8-20 条 FAQ"、"同义词在同一文档簇" 这两个失效场景如何解决？**

见下方详细回答。

---

## QA-004 · 2026-04-06 · 结构化 Prompt 文件价值

**Q: 结构化 Prompt YAML 文件是否有工程价值？**

A: 对当前单一部署是轻度过度设计；对多租户/多行业部署价值高。最关键的价值点是 `domain_aware` variant——同一套代码部署给不同行业客服时，只换 YAML 不改代码。IntentClassifier 的 scope 描述是最高价值的配置项（业务边界经常变）。

---

## QA-005 · 2026-04-06 · Prompt 线上实时更新架构

**Q: Prompt 后续需要线上实时更新，当前 YAML 方案够用吗？**

见下方详细回答。

---

## QA-006 · 2026-04-06 · IntentClassifier scope 配置化

**Q: IntentClassifier 的 scope 描述做成配置形式是否有价值？**

A: **高价值**。scope 描述是整个客服系统的业务边界定义，是最容易因业务需求变化而需要修改的部分，且改错了影响所有请求。配置化后可以：热更新（不重启服务）、A/B 测试不同边界定义、多租户独立配置。

---

## QA-007 · 2026-04-06 · SPLADE / ColBERT 改造架构

**Q: 引入 SPLADE 或 ColBERT 后系统架构是什么样的？**

见下方详细回答。

---

## QA-008 · 2026-04-06 · LLM 模型选型

**Q: 实验用什么 LLM 模型？**

见下方详细回答。

---

## QA-003 详细 · 小知识库 BERT 失效解法

**优先级排序**：

1. **开启 BGEReranker**（零成本）：cross-encoder 在 query-doc 拼接后做 attention，能区分同簇文档。把 `use_noop_reranker=True` 改为 `False` 即可验证。

2. **知识库同义词扩展**（最高 ROI）：写入时把同义词写进 FAQ 文本，BM25 和向量都受益。

3. **分级检索**（中等成本）：先用 IntentClassifier 过滤话题子集，减少同簇候选数。

4. **Embedding 微调**（高成本）：用 query-doc 正负例对做 contrastive fine-tuning，需 50-200 条标注数据。

---

## QA-005 详细 · Prompt 线上实时更新架构

**Config 表已有**（`db/models.py` Config + `GET/PUT /config`）。扩展方案：

```
管理员 PUT /config {"updates": {"query_rewriter.variant": "synonym_expansion"}}
    ↓
Config 表写入
    ↓
QueryRewriter.rewrite() 调用前查询 Config 表（缓存 TTL=60s）
    ↓
热更新，无需重启
```

关键字段：`intent_classifier.scope`（业务边界，最高频修改项）、`query_rewriter.variant`、`generator.bot_name`

---

## QA-007 详细 · SPLADE / ColBERT 改造架构

当前架构：

  Query
    ├─ embed(query) → 稠密向量 → ChromaDB ANN搜索 → Top-K 候选
    └─ jieba(query) → 稀疏词袋 → rank_bm25 全量扫描 → Top-K 候选
          ↓ RRF 融合
     Top-20 候选
          ↓ BGEReranker cross-encoder 精排
     Top-5 结果

**SPLADE**（替换 BM25，侵入性小）：
- 输入 query → SPLADE 模型 → 词汇空间稀疏向量（隐式同义词扩展）
- 检索：倒排索引（和 ES 兼容），可保留现有 RRF + Reranker 架构

  引入 SPLADE 后（替换 BM25 那条腿）：

  Query
    ├─ embed(query) → 稠密向量 → ChromaDB ANN搜索 → Top-K
    └─ SPLADE(query) → 稀疏扩展向量（词汇空间，dim=30522）
                     → 倒排索引检索（和 Elasticsearch 兼容）→ Top-K
          ↓ RRF 融合
     （SPLADE 隐式做了同义词扩展：「喇叭」→激活「音箱」「音响」「扬声器」权重）

  SPLADE 的核心改变：它输出的不是"喇叭=1, 没=1"这样的词袋，而是把模型认为相关的词都激活：
  输入：「喇叭没响」
  SPLADE输出：{喇叭:1.2, 音响:0.8, 扬声器:0.7, 声音:0.9, 无声:0.6, 故障:0.5, 静音:0.3}
  这就是隐式同义词扩展，不需要任何外部词典。

**ColBERT**（架构级变化）：
- 文档索引时存储 token 级向量（存储 10-20×）
- 检索时 MaxSim(query_tokens, doc_tokens)，token 级语义对齐
- 需要替换向量数据库（Qdrant / RAGatouille）
- 适用场景：召回率要求极高（医疗/法律），现阶段不推荐

索引阶段（写入时）：
    每条文档 → ColBERT encoder → 每个 token 一个向量
    doc: "音箱没有声音怎么办" → [[0.1,0.3,...], [0.5,0.2,...], ...]  (7个向量)
    存储代价：是单向量的 7-20 倍

  检索阶段：
  Query → ColBERT encoder → query token 向量列表 [q1, q2, ..., qm]

  相似度计算（MaxSim）：
    score(query, doc) = Σ_i  max_j  sim(qi, dj)
    即：query 的每个 token 找 doc 中最相似的 token，加总

  「喇叭」(q1) → max_sim with [音箱,没有,声音,怎么,办]
                 = sim(「喇叭」, 「音箱」) = 高！（token 级语义对齐）

  ColBERT 的工程影响：
  - ChromaDB 无法直接支持，需要换 Qdrant 或使用 RAGatouille 库
  - 存储成本 10-20×
  - 检索延迟高于单向量（但有近似算法优化）
  - 效果在 BEIR 上接近 cross-encoder reranker

---

## QA-008 详细 · LLM 模型选型

| 任务 | 推荐 | 费用 |
|------|------|------|
| Intent + Rewrite | DeepSeek-V3 | $0.27/M tokens |
| Generator | Claude Haiku 4.5 或 DeepSeek-V3 | $0.27-0.80/M |

实验阶段：`claude-haiku-4-5-20251001`（稳定可调试）。生产降本：`deepseek/deepseek-chat`（一行环境变量切换，LiteLLM 原生支持）。
