# 04 - 模糊查询消歧方案：一词多模块问题

## 问题定义

DSP 音频处理软件的客服 RAG 系统中，用户提问"静音"时，可能对应多个功能模块：

| 模块 | 示例场景 |
|------|---------|
| 输入通道 | 输入通道的 Mute 按钮，静音某路话筒/线路输入 |
| 输出 | 输出通道静音，静音某路扬声器/功放输出 |
| 分区 | 按区域静音，如会议室 A 整体静音 |
| 场景预设 | 预设场景中包含的静音状态切换 |
| ACE | ACE 模块中的静音相关功能 |

**核心矛盾：** "静音"是一个合法的 in_scope 查询，现有 `IntentClassifier` 不会拦截它；但检索结果会混合来自 5 个模块的 chunk，导致回答质量下降或答非所问。

## 现有架构分析

```
用户："静音"
  │
  ▼
IntentClassifier → in_scope ✅ (不会触发 ambiguous)
  │
  ▼
QueryRewriter → "静音" (无法消歧，关键词本身就是模糊的)
  │
  ▼
HybridRetriever (BM25 + Vector, RRF 融合)
  → 返回 top-20，混合了 5 个模块的 chunk
  │
  ▼
BGEReranker → top-5，可能来自 2-3 个不同模块
  │
  ▼
ConfidenceEvaluator
  → score_gap 小 (多个模块得分接近) → 置信度下降
  → 可能触发 medium tier (加免责声明) 或 low tier (fallback)
  │
  ▼
Generator → 用混合模块的 chunk 生成回答 → 答非所问或内容混杂
```

**问题出在哪：** 系统的消歧只在两个点——intent 层（太早，拦不住）和 confidence 层（太晚，只能 fallback 不能消歧）。**缺少检索后、生成前的"模块分散度检测 + 主动澄清"环节。**

## 开源通用方案对比

### 方案 1：检索后聚类 + 澄清

```
检索 top-k → 按 metadata 分组 → 多组则生成澄清问题 → 用户选择 → 用选定模块过滤后生成
```

- **代表：** LlamaIndex `SubQuestionQueryEngine`、LangChain multi-route retrieval
- **优点：** 不需要预标注（可按语义聚类）；实现简单；和现有 pipeline 兼容
- **缺点：** 聚类质量依赖 metadata 或额外语义计算
- **额外 LLM 调用：** 0（基于 metadata）或 1（语义聚类）

### 方案 2：Query Decomposition（查询分解）

```
用户 query → LLM 拆成多个子查询 → 分别检索 → 合并或让用户选
"静音" → ["输入通道静音", "输出静音", "分区静音", ...]
```

- **代表：** LlamaIndex `SubQuestionQueryEngine`、LangChain `MultiQueryRetriever`
- **优点：** 不需要改知识库
- **缺点：** LLM 需要知道有哪些模块才能拆（需要领域知识注入 prompt）；多次检索延迟高
- **额外 LLM 调用：** 1（分解）+ N（子查询，可并行）

### 方案 3：HyDE（Hypothetical Document Embeddings）

```
用户 query → LLM 为每种含义生成假设回答 → 用假设回答做向量检索 → 取最佳匹配
```

- **代表：** LangChain `HypotheticalDocumentEmbedder`
- **优点：** 向量匹配更精准
- **缺点：** 多次 LLM + Embedding 计算，延迟最高；不解决"用户到底问哪个"的问题
- **额外 LLM 调用：** N（每种含义一次）

### 方案 4：Metadata Filtering（元数据标签过滤）

```
入库时给 chunk 打 module 标签 → 检索时按标签聚合或过滤
```

- **优点：** 检索阶段就精准，零额外延迟；和方案 1 组合效果最好
- **缺点：** 需要前期打标工作（但可自动化）
- **额外 LLM 调用：** 0（规则提取）或入库时 1 次（LLM 打标）

### 方案 5：Multi-turn Clarification（多轮澄清）

```
检测到模糊 → 返回澄清问题 → 用户回答 → 带约束重新检索
```

- **代表：** Microsoft Copilot "Did you mean..."、现有 IntentClassifier.ambiguous 分支
- **现状：** 本系统已实现，但触发点在 intent 层，拦不住"静音"这类领域内模糊查询
- **本质：** 方案 5 的正确实现 = 方案 1（检索后触发，而非 intent 层触发）

## 决策分析

### 评估维度

| 维度 | 方案 1 (聚类+澄清) | 方案 2 (查询分解) | 方案 3 (HyDE) | 方案 4 (元数据) |
|------|:--:|:--:|:--:|:--:|
| 实现复杂度 | 中 | 高 | 高 | 低 |
| 额外延迟 | 无~低 | 高 (多次检索) | 高 (多次LLM) | 无 |
| 额外 LLM 成本 | 0~1 次 | 1+N 次 | N 次 | 0 次 |
| 消歧准确度 | 依赖 metadata 质量 | 依赖 LLM 领域知识 | 不直接消歧 | 精准 |
| 用户体验 | 好 (主动问) | 好 (自动拆) | 透明 | 透明 |
| 对现有架构改动 | 小 (pipeline 加一步) | 中 (query 层改造) | 大 (embedding 流程) | 小 (parser + ingest) |
| 可维护性 | 好 | 中 | 差 | 好 |

### 决策：方案 1 优先，方案 4 备选

**优先方案 1（检索后 LLM 聚类 + 澄清）：**

- 不改知识库，不改 parser/ingest 流程
- rerank 后用 LLM 判断 top-k 结果是否来自不同模块
- 多模块时返回纯文本模块列表让用户选择
- 用户选择后，用"模块名 + 原始查询"作为新 query 重新走完整 pipeline
- **触发条件：** top-k 结果中出现 ≥2 个不同模块即触发（不看占比）

**备选方案 4（Metadata 打标）：** 如果方案 1 的 LLM 模块判断准确率不够（<85%），再考虑在入库时给 chunk 打 `module` 标签，将 LLM 语义聚类替换为确定性 groupby。

**为什么这个顺序：**

1. **方案 1 不需要改知识库**——可以快速验证消歧交互本身的价值，降低试错成本
2. **方案 4 是优化手段**——如果 LLM 判断模块的准确率不够，再补上 metadata 打标提升精度
3. **方案 2（查询分解）不选**——需要把模块列表硬编码到 prompt 里，新增模块时要同步更新 prompt。且"静音"这种单词查询，LLM 拆分的质量不稳定
4. **方案 3（HyDE）不选**——延迟和成本最高，且不解决"用户到底问哪个"的问题。客服场景下猜错的代价远大于多问一句的代价
5. **方案 5 不是独立方案**——它是方案 1 的子集，只是触发位置从 intent 层移到了检索后

### 竞品对标

| 产品 | 消歧能力 | 说明 |
|------|---------|------|
| **RAGFlow** | 无主动消歧 | 有 Agentic RAG 循环改写（猜而不问）；元数据只支持文档级，不支持 chunk 级 |
| **MinerU** | 不涉及 | 纯结构解析器，提供 `text_level` heading 层级，消歧是下游 RAG 的职责 |
| **本方案** | 主动消歧 | 检索后 LLM 判断模块分布 → 列出选项让用户选 → 重新检索 |

**结论：** 一词多模块的主动消歧在开源 RAG 生态中没有现成方案，属于差异化能力。

## 实现方案

### 方案 1（优先）：检索后 LLM 聚类 + 澄清

#### 架构变更

```
用户："静音"
  │
  ▼
IntentClassifier → in_scope
  │
  ▼
QueryRewriter → "静音"
  │
  ▼
HybridRetriever → top-20
  │
  ▼
BGEReranker → top-5
  │
  ▼
┌─────────────────────────────────────────────────┐
│ [NEW] ModuleDisambiguator                       │
│                                                 │
│ 1. LLM 分析 top-5 结果，判断涉及哪些功能模块    │
│ 2. if 单一模块 → 直通                           │
│ 3. if ≥2 模块 → 短路返回澄清问题                │
│    "您的问题可能涉及以下功能模块，请问您想了解   │
│     哪个？"                                     │
│    1. 输入通道静音                               │
│    2. 输出静音                                   │
│    3. 分区静音                                   │
└─────────────────────────────────────────────────┘
  │ 单一模块
  ▼
ConfidenceEvaluator → tier
  │
  ▼
Generator → 回答

用户选择模块后：
  "输入通道静音" → 作为新 query 重新走完整 pipeline
```

#### 确认的交互规格

| 项目 | 决策 |
|------|------|
| 触发条件 | top-k 结果涉及 ≥2 个模块即触发（不看占比） |
| 澄清格式 | 纯文本模块列表，不带摘要 |
| 用户选择后 | 用"模块名 + 原始查询"重新走完整 pipeline |
| 模块判断方式 | LLM 分析 top-k chunk 内容，输出模块分类 |

#### 核心逻辑

```python
class ModuleDisambiguator:
    """检索后消歧：LLM 判断 top-k 结果是否来自不同模块。"""

    def __init__(self, llm_factory, min_modules: int = 2):
        self._llm = llm_factory
        self._min_modules = min_modules

    async def check(self, query: str, reranked: list[dict]) -> dict | None:
        """返回 None 表示无需消歧，返回 dict 表示需要澄清。"""
        # 用 LLM 分析 top-k 结果属于哪些功能模块
        chunks_text = "\n---\n".join(
            c.get("content", "")[:200] for c in reranked
        )
        prompt = f"""分析以下检索结果，判断它们分别属于产品的哪个功能模块。
用户查询："{query}"

检索结果：
{chunks_text}

请输出 JSON 格式：{{"modules": ["模块A", "模块B", ...]}}
只输出不同的模块名，不要重复。"""

        response = await self._llm.generate(prompt)
        modules = parse_modules(response)  # 解析 LLM 输出

        if len(modules) < self._min_modules:
            return None  # 单一模块，直通

        return {
            "needs_clarification": True,
            "modules": modules,
            "question": self._format_question(modules),
        }

    def _format_question(self, modules: list[str]) -> str:
        options = "\n".join(f"{i+1}. {m}" for i, m in enumerate(modules))
        return f"您的问题可能涉及以下功能模块，请问您想了解哪个？\n{options}"
```

#### Pipeline 集成

在 `pipeline.py` 的 `_run_pre_generation` 中，rerank（Step 4）之后、confidence（Step 5）之前插入消歧检查。

### 方案 4（备选）：Metadata 打标

当方案 1 的 LLM 模块判断准确率不足时启用。

#### 标签来源策略

| 策略 | 方法 | 成本 |
|------|------|------|
| A. Section 路径提取 | 从 `metadata["section"]` 提取顶层模块名 | 零 |
| B. 关键词规则匹配 | 正则匹配"输入通道""输出""分区""ACE"等 | 零 |
| C. LLM 入库打标 | 入库时调用 LLM 分类（看完整文档上下文，准确率 ~95%） | 低（一次性） |

启用后，`ModuleDisambiguator.check()` 中的 LLM 判断替换为确定性 `groupby(metadata["module"])`，运行时零额外 LLM 调用。

### 开放问题

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | `module` 标签粒度——5 个大模块 vs 更细的子模块？ | 太细选项太多 | 待定（方案 4 启用时再定） |
| 2 | 多轮对话中是否记住用户选过的模块？ | 避免反复追问 | 待定 |
| 3 | LLM 模块判断的 prompt 需要领域知识注入？ | 影响准确率 | 待验证 |
