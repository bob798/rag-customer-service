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

### 决策：方案 4 + 方案 1 组合

**选择理由：**

1. **方案 4 是基础设施**——给 chunk 打 `module` 标签，是所有上层消歧策略的前提。无论用哪种方案，知道"这个 chunk 属于哪个模块"都是必要信息

2. **方案 1 是交互层**——检索后按 `module` 标签分组，多模块时触发澄清。利用方案 4 的标签，聚类变成简单的 groupby 操作，无需语义计算

3. **为什么不选方案 2（查询分解）**——需要把模块列表硬编码到 prompt 里，新增模块时要同步更新 prompt。且"静音"这种单词查询，LLM 拆分的质量不稳定

4. **为什么不选方案 3（HyDE）**——延迟和成本最高，且不解决"用户到底问哪个"的问题，只是让检索更准。在客服场景下，猜错的代价（用户按错误操作指引操作设备）远大于多问一句的代价

5. **方案 5 不是独立方案**——它是方案 1 的子集。现有 `IntentClassifier.ambiguous` 已实现 intent 层消歧，但"静音"会通过 in_scope 直接放行。方案 1 在检索后实现消歧，本质就是方案 5 的正确触发位置

## 推荐实现方案

### 架构变更

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
HybridRetriever → top-20 (每个 chunk 带 module 标签)     ← 方案 4：入库时打标
  │
  ▼
BGEReranker → top-5
  │
  ▼
┌─────────────────────────────────────────────────┐
│ [NEW] ModuleDisambiguator                       │  ← 方案 1：检索后消歧
│                                                 │
│ 1. 按 metadata["module"] 分组 top-5 结果        │
│ 2. if 单一模块 → 直通                           │
│ 3. if 多模块 → 生成澄清问题，短路返回            │
│    "您是在问以下哪个模块的静音功能？"             │
│    - 输入通道静音（静音某路话筒/线路输入）        │
│    - 输出静音（静音某路扬声器输出）               │
│    - 分区静音（按区域整体静音）                   │
└─────────────────────────────────────────────────┘
  │
  ▼
ConfidenceEvaluator → tier
  │
  ▼
Generator → 回答
```

### 实现步骤（概要）

#### Step 1：Chunk 元数据增强（方案 4）

在 parser/chunker 阶段，给每个 chunk 的 metadata 添加 `module` 字段。

**标签来源策略（按优先级）：**

| 策略 | 条件 | 方法 | 成本 |
|------|------|------|------|
| A. Section 路径提取 | 文档 heading 按模块组织 | 从 `metadata["section"]` 路径中提取顶层模块名 | 零 |
| B. 关键词规则匹配 | 内容含明确模块关键词 | 正则匹配"输入通道""输出""分区""ACE"等 | 零 |
| C. LLM 自动打标 | 上述两种无法覆盖 | 入库时调用 LLM 分类 | 低（一次性） |

**建议：** 先实现 A+B 覆盖大部分场景，C 作为兜底。

#### Step 2：检索后消歧组件（方案 1）

新增 `ModuleDisambiguator` 组件，插入 pipeline 的 rerank 和 confidence 之间。

**核心逻辑：**

```python
class ModuleDisambiguator:
    def __init__(self, min_modules_for_clarification: int = 2):
        self.min_modules = min_modules_for_clarification

    def check(self, reranked: list[dict]) -> dict | None:
        """返回 None 表示无需消歧，返回 dict 表示需要澄清。"""
        modules = {}
        for chunk in reranked:
            module = chunk.get("metadata", {}).get("module", "unknown")
            modules.setdefault(module, []).append(chunk)

        if len(modules) < self.min_modules:
            return None  # 单一模块，直通

        # 多模块 → 生成澄清选项
        options = []
        for module_name, chunks in modules.items():
            preview = chunks[0].get("content", "")[:50]
            options.append({"module": module_name, "preview": preview})

        return {
            "needs_clarification": True,
            "modules": options,
            "question": f"您的问题涉及 {len(modules)} 个模块，请问您想了解哪个？"
        }
```

#### Step 3：Pipeline 集成

在 `pipeline.py` 的 `_run_pre_generation` 中，rerank 之后、confidence 之前插入消歧检查。

### 开放问题

| # | 问题 | 影响 | 状态 |
|---|------|------|------|
| 1 | 文档 heading 结构是否能区分模块？ | 决定 Step 1 用策略 A 还是 B/C | **待确认** |
| 2 | 用户选择模块后，是重新检索还是过滤已有 top-k？ | 过滤更快但结果可能不够；重新检索更准但多一次延迟 | 待定 |
| 3 | 澄清问题的格式——纯文本 vs 结构化选项？ | 取决于前端 Widget 是否支持按钮式选择 | 待定 |
| 4 | `module` 标签的粒度——5 个大模块 vs 更细的子模块？ | 太粗可能不够精准，太细选项太多 | 待定 |
| 5 | 多轮对话中是否记住用户选过的模块？ | 影响 session 内复用，避免反复追问 | 待定 |
