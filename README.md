# AI 客服系统

企业级 RAG 知识库客服系统。RAG 全链路手搓，Ports & Adapters 架构，可独立部署或作为组件接入。

## 文档导航

### 技术文档（代码同步更新）

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](./docs/architecture.md) | 系统分层架构图、Ports & Adapters 对照表 |
| [docs/rag-query-flow.md](./docs/rag-query-flow.md) | RAG 七步查询流程、置信度三路信号、SSE 时序图、RRF 算法 |
| [docs/data-model.md](./docs/data-model.md) | ER 图、ChromaDB 元数据约定、sources 格式、trace_id 日志 |
| [docs/llm-guide.md](./docs/llm-guide.md) | LLM 配置指南：LiteLLM 机制、模型切换、Fallback、成本优化 |
| [docs/ingestion-guide.md](./docs/ingestion-guide.md) | 知识库构建：解析文档、写入向量库、BM25 索引、数据结构说明 |

### 产品与设计文档

| 文档 | 用途 | 适合读者 |
|------|------|---------|
| [phase1-product-spec.md](./phase1-product-spec.md) | **产品规格**：功能清单、API契约、安全模型、里程碑 | 快速了解做了什么 |
| [architecture-design-principles.md](./architecture-design-principles.md) | **架构设计**：Ports & Adapters、组件化地图、RAG链路、置信度设计 | 理解怎么设计的 |
| [tech-selection.md](./tech-selection.md) | **技术选型**：各组件对比表、决策依据 | 理解为什么这样选 |
| [test-validation-plan.md](./test-validation-plan.md) | **测试方案**：测试集设计、评估指标、可观测性架构 | 了解质量保障 |
| [interview-prep.md](./interview-prep.md) | **面试素材**：30s pitch、技术深度展示、高频问题标准答法 | 面试准备 |

## 推荐阅读顺序

1. `docs/architecture.md` — 系统分层架构全景
2. `docs/rag-query-flow.md` — RAG 核心链路详解
3. `docs/llm-guide.md` — LLM 配置与使用
4. `phase1-product-spec.md` — 了解整体产品范围

---

## 快速开始

### 1. 环境准备

```bash
# 克隆项目
git clone https://github.com/bob798/rag-customer-service.git
cd rag-customer-service

# 安装依赖（需要 Python 3.12，PyTorch 暂无 Python 3.13 的 macOS x86_64 wheel）
python3.12 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 配置 LLM API Key（三选一）
cp .env.example .env
# 编辑 .env，填入 ANTHROPIC_API_KEY 或 OPENAI_API_KEY 或 DEEPSEEK_API_KEY
```

> **模型配置详情**见 [docs/llm-guide.md](./docs/llm-guide.md)

### 2. 验证配置（无需下载 Embedding 模型）

```bash
# 用 mock 模式跑完整 RAG 链路（零依赖，立即可用）
.venv/bin/python scripts/demo_pipeline.py
```

**输出示例**：

```
📚 正在构建知识库 (mock 模式)...
  已导入 5 条 FAQ

============================================================
❓ 问题: 怎么申请退款？
💬 回答: 退款申请：在订单详情页点击"申请退款"，填写原因提交即可。
   📄 来源: 常见问题FAQ.txt | 退款流程：在订单详情页点击...
   🎯 置信度: 0.85

============================================================
❓ 问题: 帮我写一首诗
💬 回答: 这个问题超出了我的服务范围，请联系人工客服。
   🎯 置信度: 0.00   ← out_of_scope fallback 正常触发
```

设置真实 API Key 后，脚本自动切换到真实 LLM 模式：

```bash
export ANTHROPIC_API_KEY=sk-ant-...
.venv/bin/python scripts/demo_pipeline.py
# 使用 claude-haiku-4-5-20251001，返回真实 AI 回答
```

脚本会验证以下链路节点：意图识别 → Query 改写 → 向量检索+BM25检索+RRF融合 → 置信度评估 → LLM 生成 → sources 溯源 → out_of_scope fallback。

### 3. 构建知识库

```bash
# 预览解析结果（不写入，快速验证格式）
.venv/bin/python scripts/ingest.py docs/samples/faq_example.txt --dry-run

# 正式导入（首次会下载 GteQwen2 embedding 模型，约 3GB）
.venv/bin/python scripts/ingest.py docs/samples/faq_example.txt

# 批量导入整个目录
.venv/bin/python scripts/ingest.py data/docs/
```

支持格式：`.txt`（FAQ 格式自动识别）、`.pdf`、`.docx`

> **完整说明**见 [docs/ingestion-guide.md](./docs/ingestion-guide.md)

### 4. 启动 API 服务

```bash
# 开发模式（热重载）
.venv/bin/uvicorn api.main:app --reload --port 8000

# 验证服务正常
curl http://localhost:8000/health
# {"status":"ok"}
```

> **注意**：API 路由层（`api/routes/`）为 Week 2 任务，当前仅有 `/health` 和 `/docs`。

---

## 测试

### 运行测试

```bash
# 全量测试（自动生成 HTML 报告 + 覆盖率报告）
.venv/bin/pytest

# 单元 + 集成测试（不生成报告，快速验证）
.venv/bin/pytest tests/core/ tests/integration/ -q --no-cov

# 冒烟测试（真实 jieba + BM25 + Chunker，需要真实依赖）
.venv/bin/pytest tests/smoke/ -v -m smoke --no-cov
```

### 查看 HTML 测试报告

```bash
open test-reports/report.html       # 测试通过/失败详情
open test-reports/coverage/index.html  # 代码覆盖率（哪些行被执行过）
```

当前状态：**160 passed，覆盖率 91%**（已知缺口见 [test-validation-plan.md §Phase1现状](./test-validation-plan.md#phase-1-测试现状与已知缺口2026-04-05)）

---

## 如何阅读测试报告

### report.html — 测试用例报告

打开后看到三列：

| 列 | 含义 |
|----|------|
| **Test** | 测试用例名，格式 `文件::类::方法` |
| **Result** | `Passed` / `Failed` / `Error` |
| **Duration** | 执行时长（ms） |

**如何找到关键测试**：

```
tests/core/test_pipeline.py         ← RAGPipeline 编排逻辑（最核心）
tests/integration/test_pipeline_flow.py  ← 端到端集成流程
tests/core/test_confidence.py       ← 置信度三路信号
tests/core/test_intent.py           ← 意图识别
tests/core/test_hybrid_retriever.py ← RRF 混合检索
```

点击任意失败测试 → 展开看 `AssertionError` 详情，精确定位哪行代码出问题。

### coverage/index.html — 覆盖率报告（含测试溯源）

> 覆盖率数字（91%）只说明"代码被执行过"，不等于"逻辑被验证过"。

**如何真正判断核心逻辑是否被测试覆盖**：

打开 `coverage/index.html` → 点击 `core/rag/pipeline.py` → 查看每行颜色：

- **绿色** — 该行被测试执行过。**点击该行**可展开看是哪些测试覆盖了它。
- **红色** — 该行从未执行（测试盲区）
- **黄色** — 分支只走了一半（如 `if` 只测了 True，没测 False）

**测试溯源（核心功能）**：点击任意绿色行右侧的展开按钮，弹出覆盖该行的测试列表：

```
core/rag/intent.py 第 47 行  ← 点击展开
  ✓ test_intent.py::test_in_scope_classification
  ✓ test_intent.py::test_ambiguous_returns_clarification_question
  ✓ test_pipeline_flow.py::test_out_of_scope_triggers_fallback
  ... 共 15 个测试
```

这样可以回答："IntentClassifier 的 classify() 方法被哪些测试覆盖了？" 直接在 HTML 里点击对应行查看，零额外操作。

**核心逻辑对应的测试位置**：

| 要验证的逻辑 | 看这个文件 | 关键测试方法 |
|------------|-----------|------------|
| `out_of_scope` 走 fallback，不调用 LLM | `test_pipeline_flow.py` | `test_out_of_scope_triggers_fallback` |
| 低置信度走 fallback | `test_pipeline_flow.py` | `test_low_confidence_triggers_fallback` |
| medium 置信度加"仅供参考"前缀 | `test_generator.py` | `test_generate_medium_confidence_adds_disclaimer` |
| ambiguous 意图返回澄清问题 | `test_pipeline_flow.py` | `test_ambiguous_returns_clarification` |
| RRF 融合排序正确 | `test_hybrid_retriever.py` | `test_rrf_score_combines_both_sources` |
| 置信度三路信号权重 | `test_confidence.py` | `test_high_confidence_...` / `test_low_confidence_...` |
| trace_id 每次唯一 | `test_pipeline_flow.py` | `test_trace_id_present_in_result` |

**实际操作**：如果想验证"低置信度触发 fallback"这条核心逻辑确实被覆盖：

```bash
# 1. 运行单个测试，确认它通过
.venv/bin/pytest tests/integration/test_pipeline_flow.py::test_low_confidence_triggers_fallback -v

# 2. 在覆盖率报告里查看 pipeline.py 第 121-131 行是否绿色
#    （那是 if tier == "low": return fallback 的代码）
open test-reports/coverage/index.html
```

**覆盖率 91% 意味着什么**：

```
被覆盖的内容：
✓ RAGPipeline 所有分支（in_scope/out_of_scope/ambiguous/low_confidence/medium）
✓ HybridRetriever RRF 算法
✓ SignalFusionConfidenceEvaluator 三路信号计算
✓ LLMGenerator 流式 + 非流式
✓ StructuredLogTracer ContextVar 并发安全
✓ 数据库 CRUD 操作

未覆盖的 9%：
✗ BGEReranker（需要下载真实模型，smoke 测试不运行）
✗ GteQwen2Embedder（同上）
✗ ChromaDB 错误路径（空集合边界条件）
```

---

## 技术栈

- **核心**：Python 3.12 + FastAPI + RAG 全链路手搓
- **检索**：ChromaDB（向量）+ rank_bm25（关键词）+ RRF 融合
- **Embedding**：gte-Qwen2-1.5B（本地，中文 MTEB ~70）
- **Reranker**：BGE-Reranker-v2-m3（本地，零 API 成本）
- **LLM**：Claude / DeepSeek / 通义（LiteLLM 统一接口，见 [docs/llm-guide.md](./docs/llm-guide.md)）
- **部署**：Docker Compose

## 项目状态

Phase 1 完成（2026-04）：RAG 核心链路 + 基础组件，160 tests passing，覆盖率 91%

---

## 开发方式：AI 协作编程

本项目采用 **人机协作编程（Human-AI Collaborative Programming）** 模式开发。

### 工作流程

```
开发者碰撞产品需求
    ↓
根据需求制定技术方案 + 架构设计
    ↓
编写实施计划（Claude Code Plan Mode）
    ↓
Subagent 驱动执行（自动 TDD + 双轮代码审查）
    ↓
开发者审核合并
```

### 使用的工具

- **Claude Code**：主 AI 编程助手（claude.ai/code）
- **[Superpowers Skills](https://github.com/obra/superpowers)**：Claude Code 技能扩展套件
  - `subagent-driven-development`：每个任务派发独立 subagent 实现，实现后自动规格合规 + 代码质量双轮审查
  - `writing-plans`：结构化实施计划制定
  - `test-driven-development`：TDD 纪律执行
  - `using-git-worktrees`：git worktree 隔离工作空间

### 分工原则

| 开发者负责 | AI 负责 |
|-----------|---------|
| 产品需求定义 | 代码生成与实现 |
| 架构设计决策 | 规格合规审查 |
| 技术选型判断 | 代码质量审查 |
| 计划审批 | TDD 执行 |
| 最终代码审核 | 测试编写 |
