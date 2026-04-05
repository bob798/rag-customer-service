# AI 客服系统 · 面试素材

> **用途**：面试时的项目介绍素材、技术深度展示、常见问题标准答法。
> **目标读者**：Bob 本人，面试准备用。
> **最后更新**：2026-03-28

---

## 项目价值点（30秒 pitch）

独立开发的企业级 AI 客服系统，核心是 RAG 全链路手搓：
- **不用框架**：Ports & Adapters 架构，每一步有工程决策依据，说得清楚
- **Embedding 选型有数据**：拒绝"教程惯性"，查 MTEB 中文榜单选 gte-Qwen2-1.5B
- **置信度三档**：生产级系统不能只会答，还要知道"不知道"
- **组件化设计**：Parser/Chunker/Tracer/FallbackHandler 均可替换，开源可扩展
- **可观测性**：trace_id 全链路追踪 + 数据飞轮，持续优化有据可查

---

## 技术深度展示点

| 点 | 能说的内容 | 深度 |
|----|-----------|------|
| 混合检索 RRF | 向量补语义，BM25 补关键词，RRF 融合不依赖分值归一化 | ⭐⭐⭐ |
| Embedding 选型 | MTEB 中文榜单对比，LLM 频率偏见问题 | ⭐⭐⭐ |
| 多信号置信度 | retrieval_score + coverage_score + score_gap，PR 曲线校准阈值 | ⭐⭐⭐⭐ |
| FAQ 专用 Parser | 语义单元是 QA 对，通用分块会拆散 Q 和 A | ⭐⭐⭐ |
| Ports & Adapters | 核心手搓 + 接口抽象，框架作为可选 Adapter | ⭐⭐⭐⭐ |
| CPU 阻塞问题 | Embedding/Reranker 同步调用阻塞 event loop，run_in_executor 解法 | ⭐⭐⭐⭐ |
| 可观测性设计 | trace_id 定位问题层、数据飞轮持续优化 | ⭐⭐⭐ |

---

## 高频面试问题 & 标准答法

### RAG 架构

**Q: 你的 RAG 和直接用 LangChain 有什么区别？**

A（标准）：我用 Ports & Adapters 架构——核心是手搓的，接口是抽象的。LangChain 可以作为可选 Adapter 注入，不改核心代码。手搓的好处是每一步都说得清楚：混合检索为什么用 RRF、置信度为什么用三路融合、FAQ 为什么要专用 Parser。框架用多了这些都是黑盒。

加分延伸：手搓还有调试优势——LangChain 的回调链很难断点，我们的 Pipeline 每步都有 trace_id 记录，出问题直接查日志定位到是召回差还是生成差。

---

**Q: 混合检索怎么做的，RRF 是什么？**

A（标准）：向量检索负责语义理解（"退款流程"匹配"申请退款需要"），BM25 负责精确关键词（"3 个工作日"精确命中）。RRF 融合公式是 `score = Σ 1/(k + rank_i)`，用排名而非分值，不需要归一化两路分数，鲁棒性好。k=60 是经验值，防止排名第一的权重过于突出。

加分延伸：两路都命中的 chunk 会累加 RRF 分值，天然提升了高相关性 chunk 的排名。这比简单加权平均分数更稳定。

---

**Q: Reranker 是什么，为什么要加？**

A（标准）：RRF 只看排名不看分值，精度有限。BGE-Reranker 是 Cross-Encoder，对 query 和 chunk 联合编码，比 Bi-Encoder 的相似度计算精度高得多。代价是只能用在少量候选上（召回 top-10，rerank 选 top-3），所以放在检索后面做精排。

---

### 置信度设计

**Q: 置信度怎么定义的，0.5 和 0.75 这两个阈值是怎么来的？**

A（标准）：置信度是三路信号加权：Reranker 语义相关度（权重 0.6）+ Query 关键词覆盖率（0.3）+ top-1 vs top-2 分差（0.1）。单一余弦相似度有假高分（词汇匹配但答非所问）和假低分（Query 改写后语义偏移）问题，三路互补更准。

阈值不是拍脑袋：用黄金问答集画 Precision-Recall 曲线，在 F1 最优点附近选。0.5/0.75 是初始值，实测后调整。

加分延伸：参考了 RAGAS 的 faithfulness 和 TruLens 的 RAG Triad 设计，Phase 2 计划引入 LLM-as-judge 替换 coverage_score，进一步提升准确性。

---

### 工程问题

**Q: FastAPI 是异步框架，Embedding 模型是同步的，怎么处理？**

A（标准）：直接在 async 路由里调 `model.encode()` 会阻塞整个 event loop，其他请求全部卡住。解法是用 `run_in_executor` 把 CPU 密集型任务派到独立线程池：
```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(_executor, self.embed, texts)
```
用独立的 `ThreadPoolExecutor(max_workers=2)` 隔离 Embedding 和 Reranker，不影响 HTTP 处理。

---

**Q: BM25 重启后数据丢了怎么办？**

A（标准）：BM25 是内存索引，重启确实丢。在 FastAPI lifespan 启动钩子里，从 SQLite 把所有 chunks 重新加载到 BM25 重建索引，10 万条以内重建时间通常 < 1s，对服务可用性无影响。

---

**Q: 知识库更新了，怎么保证旧向量被清掉？**

A（标准）：文档更新时先调 `vector_store.delete_by_doc(doc_id)` 删旧 chunks，再重新解析索引。Document 用状态机（pending → indexing → done/failed）防止中间态——如果索引过程中崩溃，状态停在 indexing，运营可以重试。

加分延伸：更生产级的做法是蓝绿索引——新 chunks 写入时打新版本号，写完后原子切换 active_version，老 chunks 异步清理，避免更新窗口期的服务中断。

---

**Q: FAQ 为什么要单独一个 Parser？**

A（标准）：FAQ 的语义单元是"一个 QA 对"，不是固定字数。通用分块可能把 Q 切在一个 chunk 结尾，A 切在下一个 chunk 开头。检索时命中了问题 chunk，但 LLM 拿到的上下文里没有答案，就会产生幻觉。FAQParser 用正则识别 Q:/A: 格式，把 QA 对整体作为一个 chunk，这个问题就消失了。

---

**Q: 上线后发现某类问题答得不好，怎么定位是哪一步的问题？**

A（标准）：每次请求有 trace_id，日志记录了意图识别结果、改写前后 Query、top-k chunks、置信度三路信号值、最终 tier。拿 trace_id 查日志：
- confidence_tier=high 但答错 → 生成问题（LLM 幻觉）
- retrieval_score 低 → 召回差（知识库缺相关内容）
- coverage_score 低 → 知识库有内容但关键词不匹配（考虑补充同义词 Q&A）
三个信号独立记录，定位精确。

---

**Q: 这个项目和 Dify 有什么区别，为什么不直接用 Dify？**

A（标准）：Dify 是低代码平台，适合快速搭建，但对技术深度展示不利。我的目标是展示 RAG 工程能力，所以选择手搓核心链路。差异化在于：Dify 用框架黑盒，我能说清每一步为什么这样设计；Dify 不方便组件替换，我的 Ports & Adapters 架构让 Embedding、Reranker、Tracer 都可以换注入；Dify 的可观测性是现成的，我自己实现了 trace_id 全链路追踪，更理解内部机制。

---

## 项目价值点（技术深度展示）

1. **RAG 全链路手搓**：意图识别 → Query 改写 → 混合检索(RRF) → BGE-Reranker → 置信度三档，每一步有工程决策依据
2. **Embedding 选型有数据支撑**：拒绝"教程惯性"，查 MTEB 中文榜单选 gte-Qwen2-1.5B（均分 ~70 vs BGE-M3 ~68-70）
3. **多信号置信度设计**：retrieval_score + coverage_score + score_gap 三路融合，阈值用黄金问答集 PR 曲线校准
4. **Ports & Adapters 架构**：手搓核心 + 抽象接口，框架作为可选 Adapter，可说性 + 可替换性兼顾
5. **Parser 组件化**：Strategy Pattern + Plugin Registry，FAQ 专用解析（QA 对原子分块）vs 通用语义分块
6. **可观测性 + 数据飞轮**：trace_id 全链路追踪，RAGAS 自动评测，持续优化闭环
7. **Webhook 工单集成**：展示系统集成思维，不是孤立 demo
8. **上线前完整测试集**：黄金问答集 + 负例集 + 难例集，有量化指标
