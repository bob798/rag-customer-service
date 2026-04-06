# 我用 AI 结对编程开发了一个企业级 RAG 客服系统——方法论篇

> 本文记录开发「AI 客服系统」的全过程方法。不是教你用 ChatGPT 写代码，是一套可复现的人机协作工程流程。
>
> 项目地址：github.com/bob798/rag-customer-service
> 技术栈：Python 3.12 · FastAPI · ChromaDB · BM25 · GTE-Qwen2 · BGE-Reranker · Claude

---

## 做了什么

一个企业级 RAG 知识库客服系统，从零手搓 RAG 全链路：

```
用户提问
  ↓ 意图识别（in_scope / out_of_scope / ambiguous）
  ↓ Query 改写（口语→检索语言，同义词扩展）
  ↓ 混合检索（向量 + BM25 + RRF 融合）
  ↓ 精排（BGE-Reranker-v2-m3，本地运行）
  ↓ 置信度评估（三路信号：检索分/覆盖率/分数差）
  ↓ LLM 生成（高置信→直接回答，中置信→加免责，低置信→转人工）
```

最终产物：API 服务（FastAPI）+ 完整测试（179 tests, 93% coverage）。

---

## 核心方法：人机协作编程

不是「让 AI 帮我写代码」，是**把 AI 当结对程序员来用**。关键区别：

| 传统用法 | 结对编程用法 |
|---------|-------------|
| 直接问「帮我写 XXX」 | 先设计方案，再让 AI 执行 |
| AI 输出什么就用什么 | AI 执行，人审查，发现问题继续迭代 |
| 每次从头描述需求 | 有完整计划文档，AI 每次任务都有完整上下文 |
| 一个大任务一个提示 | 任务拆解到 10-30 分钟粒度，逐步验证 |

---

## 工具链

**主工具：Claude Code（claude.ai/code）**

命令行 AI 编程工具，核心能力：
- 直接读写本地文件，不用复制粘贴
- 可以运行测试、看结果、自动修复
- Plan Mode：只思考规划，不写代码
- Subagent：派发独立子任务，不污染主上下文

**扩展套件：Superpowers（github.com/obra/superpowers）**

给 Claude Code 加了一套工作流纪律：

| Skill | 作用 |
|-------|------|
| `writing-plans` | 把需求写成结构化实施计划（含代码示例、测试步骤、commit 格式） |
| `subagent-driven-development` | 每个任务派发独立 subagent，完成后自动做两轮 review（规格合规 + 代码质量）|
| `test-driven-development` | 强制 TDD 纪律：先写测试，再写实现 |
| `systematic-debugging` | 遇到 bug 先诊断根因，再修复 |

---

## 工作流实录

### Phase 1：规划（先想清楚再动手）

**Step 1：产品规格**

先用自然语言写清楚要做什么（`phase1-product-spec.md`）：功能边界、API 契约、安全模型、不做什么。

**Step 2：架构设计**

确定核心设计决策，写死之前想清楚（`architecture-design-principles.md`）：

```
决策1：Pipeline 内部做 embedding，不接受外部传入 query_vec
决策2：sources 格式固定，title 来自 metadata["source_title"]
决策3：session_history 由 API 层查 DB 传入，pipeline 不依赖 db 层
```

每个决策都写了「为什么」，避免后期 AI 在执行时自作主张改掉。

**Step 3：进入 Plan Mode，写实施计划**

```bash
# 进入 Plan Mode（只思考，不写代码）
# 告诉 Claude：
"基于以上产品规格和架构文档，生成完整实施计划，
 每个任务要有：
 - 精确文件路径
 - 完整代码示例
 - 测试步骤和预期输出
 - commit message"
```

**计划自我审查循环（3 轮）**：

```
生成计划 → 发现问题 → 修复 → 再审查
                              ↓（3轮后）
                          批准执行
```

第一轮发现的典型问题：
- 字段名不一致（`doc_id` vs `id`）
- 循环导入风险（`knowledge.py` 里 `from api.main import app`）
- 测试隔离不够（API 测试和 core 测试用同一个 DB）

**关键经验**：计划越具体，执行越准确。模糊的「实现 XXX」不如「在 `core/rag/pipeline.py` 第 55 行添加 `retriever` property，返回 `self._retriever`」。

---

### Phase 2：执行（Subagent 驱动）

计划批准后，用 `subagent-driven-development` 执行：

```
Controller（我的主会话）
  ├─ Task 1 → 派发 Subagent A → 实现 + 自我审查 + commit
  │              ↓
  │           Spec Reviewer（验证：是否实现了计划要求的所有内容？）
  │              ↓
  │           Code Quality Reviewer（验证：代码质量是否合格？）
  │              ↓ 通过
  │           ✅ Task 1 完成
  │
  ├─ Task 2 → 派发 Subagent B → ...
  │
  └─ Task N → ...
```

**Subagent 的关键优势**：每个 subagent 启动时是全新的上下文，不会被之前任务的「思维惯性」影响。Controller 负责提供精确的任务描述，包括：
- 场景背景（这是一个 RAG 系统，正在实现第 N 个任务）
- 文件路径和已有代码结构
- 明确的成功标准（哪些测试必须通过）

---

### Phase 3：验证（不只看测试通不通过）

每个任务完成后，验证清单：

```
✅ 测试全绿
✅ 新写的代码符合架构原则（不破坏 Ports & Adapters 边界）
✅ 没有引入安全漏洞（SQL 注入、命令注入等）
✅ 没有超出任务范围的「好心改动」
✅ commit message 准确描述了做了什么
```

最容易出现的问题：**AI 会做「顺手」的改进**，比如帮你改了一个没有要求改的函数命名，这种「额外好意」会让代码审查变复杂。明确指示「只做任务要求的事」很重要。

---

## 踩坑记录

### 坑1：Try/Except 吞掉了路由注册错误

```python
# 错误写法：一个 import 失败，所有路由都没了
try:
    from api.routes import chat, knowledge, sessions, config
    app.include_router(chat.router)
    # ...
except ImportError:
    pass
```

**症状**：`/chat` 返回 404，但没有任何报错。  
**修复**：逐个 import，每个独立处理：

```python
for _module, _attr in [("api.routes.chat", "router"), ...]:
    try:
        mod = importlib.import_module(_module)
        app.include_router(getattr(mod, _attr))
    except (ImportError, AttributeError):
        pass
```

**经验**：吞异常是定位 bug 的最大障碍。测试通过不代表功能正常，要验证实际请求。

---

### 坑2：Mock 不够深，AsyncMock 忘记加

```python
# 测试里的 mock_pipeline
p.retriever.vector_store.add  # 返回的是普通 MagicMock
```

但 `knowledge.py` 里：
```python
await vector_store.add([chunk])  # await 一个普通 Mock → TypeError
```

**症状**：测试报 `TypeError: object MagicMock can't be used in 'await' expression`。  
**修复**：`p.retriever.vector_store.add = AsyncMock()`  
**经验**：所有被 `await` 的 mock 方法必须是 `AsyncMock`，不是 `MagicMock`。

---

### 坑3：私有属性没有公开接口

```python
class RAGPipeline:
    def __init__(self, ...):
        self._retriever = retriever  # 私有
```

API 路由里：
```python
pipeline.retriever.vector_store  # AttributeError: no attribute 'retriever'
```

**修复**：加 `@property`  
**经验**：组件内部用 `_name` 是好习惯，但需要对外暴露的属性要显式加 property。

---

### 坑4：环境变量时序问题

```python
# conftest.py 里设置了 DATABASE_URL
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_api.db"

# 但 db/session.py 在 import 时就读取了 DATABASE_URL 创建 engine
engine = create_async_engine(os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./app.db"))
```

**症状**：设置了测试用 DB，但实际用的是默认路径，导致「表不存在」。  
**修复**：在 `conftest.py` 最顶部设置，比任何 import 都早；或用 `autouse` fixture 在每个测试前 `init_db()`。  
**经验**：环境变量必须在模块 import 之前设置，Python import 是有副作用的。

---

## 架构亮点

### Ports & Adapters（端口适配器）

所有核心组件都依赖接口（Port），不依赖具体实现：

```python
# core/interfaces/reranker.py
class BaseReranker(ABC):
    @abstractmethod
    async def rerank(self, query, candidates, top_k) -> list[dict]: ...

# 测试用
class NoopReranker(BaseReranker): ...  # 直通，不依赖模型文件

# 生产用
class BGEReranker(BaseReranker): ...  # 真实 BGE 模型
```

好处：测试时用 `NoopReranker`，不下载 2.1GB 模型；生产时换 `BGEReranker`，不改任何调用代码。

### 置信度三路信号

不用单一分数决定是否触发 fallback：

```
retrieval_score = reranked[0]["rerank_score"]      # 文档本身的相关度
coverage_score  = jieba token 覆盖率               # 答案是否覆盖查询词
score_gap       = top1.score - top2.score          # 结果的确定性

confidence = 0.6 × retrieval + 0.3 × coverage + 0.1 × gap
```

### RRF 融合

向量检索和 BM25 的分数量纲完全不同（0-1 vs 0-∞），用 RRF 只看排名不看分数：

```python
rrf_score = Σ  1 / (60 + rank_i)   # k=60 是经验最优值
```

---

## 量化结果

| 指标 | 数值 |
|------|------|
| 测试用例 | 179 passed, 0 failed |
| 代码覆盖率 | 93% |
| 核心链路覆盖 | 100%（所有分支都有测试） |
| API 接口数 | 9 个（含认证） |
| 从零到可运行 API | ~2 周 |

---

## 关键工具配置

### CLAUDE.md — 项目级 AI 指令

项目根目录放 `CLAUDE.md`，每次对话自动加载：

```markdown
## 开发规范
- 异步优先：IO 操作全部 async/await
- 新建组件必须实现 core/interfaces/ 中对应的 Port 接口
- LLMFactory 通过注入传入，不在组件内直接构造

## 运行测试
.venv/bin/pytest tests/core/ tests/integration/ -q --no-cov
```

这样 AI 每次都知道项目约定，不用重复解释。

### 测试命令分层

```bash
# 开发时（秒级）
.venv/bin/pytest tests/core/ -q --no-cov

# PR 前（分钟级）
.venv/bin/pytest --no-header -q

# 真实依赖验证（按需）
.venv/bin/pytest tests/smoke/ -m smoke
```

---

## 总结：什么时候 AI 最有用

**AI 最能发挥价值的场景**：
- ✅ 有清晰规格的模板代码（CRUD、路由、测试 fixture）
- ✅ 已知架构，只需填充实现
- ✅ 调试已知类型的 bug（看错误信息直接定位）
- ✅ 跨文件的一致性修改（统一重命名、格式调整）

**人必须主导的环节**：
- ✋ 架构设计决策（什么该做、什么不做）
- ✋ 需求边界判断（这个功能现在有必要吗）
- ✋ 安全审查（认证逻辑、输入验证）
- ✋ 性能权衡（这里用缓存合适吗）

**核心认知**：AI 是极好的「执行层」，但策略层必须是人。计划越清晰，AI 执行越准确，返工越少。

---

*项目持续更新中，下一期：Week 3 前端 Widget JS + Docker 容器化部署*
