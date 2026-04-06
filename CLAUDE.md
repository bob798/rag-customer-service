# CLAUDE.md — AI 客服系统开发指南

## 项目概述

企业级 RAG 知识库客服系统。Ports & Adapters 架构，RAG 全链路手搓。

- **Python 3.12**（不支持 3.13，PyTorch 无 macOS x86_64 wheel）
- **虚拟环境**：`.venv/`，始终用 `.venv/bin/python` / `.venv/bin/pytest`

## 关键架构

```
API 层 (api/)
  └── RAGPipeline (core/rag/pipeline.py)
        ├── IntentClassifier  → QueryRewriter  → HybridRetriever
        ├── BGEReranker       → ConfidenceEvaluator
        └── LLMGenerator / TellUserFallbackHandler
```

Port 接口在 `core/interfaces/`，所有组件通过依赖注入组装（`core/rag/pipeline_builder.py`）。

## 开发规范

### 测试优先

- 先写测试，再写实现（TDD）
- 单元测试 mock 所有外部依赖（LLM、Embedding 模型）
- 集成测试用 `NoopReranker` + `KeywordEmbedder`，不依赖真实模型
- smoke 测试用真实 jieba/BM25/Chunker，标记 `@pytest.mark.smoke`

### Reranker 说明（重要，新开发者必读）

| | NoopReranker | BGEReranker |
|-|-------------|-------------|
| 用途 | 测试/开发（默认） | 生产 / 检索质量评估 |
| 模型加载 | 无 | bge-reranker-v2-m3（~2.1GB） |
| 切换方式 | `USE_NOOP_RERANKER=true` | `USE_NOOP_RERANKER=false` |
| 效果 | 直通，Top-K 截断 | cross-encoder 精排，质量显著提升 |

**CI 和所有单元/集成测试强制使用 NoopReranker**，避免在无模型的 CI 环境报错。
检索质量实验（`scripts/test_synonym_retrieval.py`）必须切为 BGEReranker。

### 运行测试

```bash
# 快速验证（不生成报告）
.venv/bin/pytest tests/core/ tests/integration/ -q --no-cov

# 全量（生成 HTML 报告 + 覆盖率，约 60s）
.venv/bin/pytest

# 冒烟测试（真实依赖）
.venv/bin/pytest tests/smoke/ -v -m smoke --no-cov

# 单个测试
.venv/bin/pytest tests/core/test_pipeline.py::test_out_of_scope_triggers_fallback -v
```

当前状态：**160 passed，覆盖率 91%**

### 测试文件对应关系

| 核心逻辑 | 单元测试 | 集成测试 |
|---------|---------|---------|
| `core/rag/pipeline.py` | `tests/core/test_pipeline.py` | `tests/integration/test_pipeline_flow.py` |
| `core/rag/retriever.py` | `tests/core/test_hybrid_retriever.py` | `tests/integration/test_hybrid_retriever.py` |
| `core/rag/confidence.py` | `tests/core/test_confidence.py` | — |
| `core/rag/intent.py` | `tests/core/test_intent.py` | — |
| `core/knowledge/` | `tests/core/test_retriever.py` | `tests/integration/test_ingestion_pipeline.py` |

### 代码规范

- 异步优先：IO 操作全部 `async/await`
- 新建组件必须实现 `core/interfaces/` 中对应的 Port 接口
- `LLMFactory` 通过注入传入，不在组件内直接构造
- sources 格式固定：`{doc_id, title, content_preview, chunk_id}`，`title` 来自 `metadata["source_title"]`

## 本地模型（已缓存）

| 模型 | 路径 | 用途 |
|------|------|------|
| `Alibaba-NLP/gte-Qwen2-1.5B-instruct` | `~/.cache/huggingface/` (~3.2GB) | 向量检索 |
| `BAAI/bge-reranker-v2-m3` | `~/.cache/huggingface/` (~2.1GB) | 精排 |

首次下载需 `HF_HUB_DISABLE_XET=1`（磁盘 < 8GB 时必须，避免 2x 临时空间占用）。

## 常用脚本

```bash
# 验证完整 RAG 链路（mock 模式，零依赖）
.venv/bin/python scripts/demo_pipeline.py

# 导入知识库
.venv/bin/python scripts/ingest.py docs/samples/faq_example.txt --dry-run  # 预览
.venv/bin/python scripts/ingest.py docs/samples/faq_example.txt             # 正式导入

# 启动 API
.venv/bin/uvicorn api.main:app --reload --port 8000
```

## 当前开发状态

> **任务列表唯一来源：`TODO.md`**（本文件只记快照，详细任务看 TODO.md）

| 版本 | 里程碑 | 状态 |
|---|---|---|
| v0.1.0 | Phase 1：RAG 核心链路 | ✅ 完成，160 tests，91% 覆盖率 |
| v0.2.0 | Week 2：完整 API 层 | 🔄 PR #3 待合并 |
| v0.3.0 | Week 3：Widget + Docker | 📋 计划中 |

**当前优先级（详见 TODO.md）：**
1. 合并 PR #3，打 tag v0.2.0
2. Widget JS 聊天气泡
3. Docker Compose 容器化
4. 检索质量提升（synonym_expansion 验证）

## 硬件注意事项

- **Intel Mac (x86_64)**，非 Apple Silicon
- Docker 镜像需指定 `--platform linux/amd64`
- Homebrew 路径：`/usr/local/bin/`（非 `/opt/homebrew/`）
