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

### 测试规范（必读）

#### 测试金字塔 — 四个层级

```
              ╱╲           E2E 质量评测 — scripts/eval_*.py
             ╱  ╲          真实模型 + 真实 LLM API，手动触发
            ╱────╲
           ╱      ╲        冒烟测试 — tests/smoke/
          ╱ smoke  ╲       真实 jieba/BM25，@pytest.mark.smoke
         ╱──────────╲
        ╱            ╲     集成测试 — tests/integration/
       ╱ integration  ╲    DeterministicEmbedder + NoopReranker，CI 可跑
      ╱────────────────╲
     ╱                  ╲   单元测试 — tests/core/
    ╱    unit tests      ╲  全 mock，最快
   ╱──────────────────────╲
```

| 层级 | 位置 | Embedder | Reranker | LLM | CI 可跑 | 用途 |
|------|------|----------|----------|-----|---------|------|
| **单元测试** | `tests/core/` | mock | mock | mock | ✅ | 验证单个函数/类逻辑 |
| **集成测试** | `tests/integration/` | DeterministicEmbedder | **NoopReranker** | mock | ✅ | 验证组件协作、数据流、回归 |
| **冒烟测试** | `tests/smoke/` | 无/真实 jieba | 无 | 无 | ✅ | 真实依赖不崩溃 |
| **E2E 评测** | `scripts/eval_*.py` | **GteQwen2** | **BGEReranker** | **真实 API** | ❌ | 检索质量、端到端效果 |

#### 核心规则

1. **CI 测试（单元+集成+冒烟）强制 NoopReranker + DeterministicEmbedder**，不加载 GPU 模型
2. **E2E 评测用真实全链路**：GteQwen2Embedder + BGEReranker + LLM API，手动触发
3. **先写测试再写实现（TDD）**
4. **新增 parser/chunker/retriever 必须同时新增对应的单元测试 + 集成测试**
5. **集成测试验证"不破坏"，E2E 评测验证"效果好"**，两者不互相替代
6. **测试结果文件带版本号**，格式 `qa_eval_results_v{版本}.json`

#### Reranker 选型

| | NoopReranker | BGEReranker |
|-|-------------|-------------|
| 用途 | CI 测试 / 开发 | 生产 / E2E 评测 |
| 模型 | 无 | bge-reranker-v2-m3（~2.1GB） |
| 效果 | 直通（score 不变） | cross-encoder 精排 |

#### 运行命令

```bash
# CI 自动化（每次提交必跑）
.venv/bin/pytest tests/core/ tests/integration/ -q --no-cov

# 全量 + 覆盖率报告
.venv/bin/pytest

# 冒烟测试
.venv/bin/pytest tests/smoke/ -v -m smoke --no-cov

# E2E 质量评测（手动，需模型+API）
.venv/bin/python scripts/eval_production_pipeline.py
```

当前状态：**284 passed，覆盖率 91%**

#### 测试目录结构

```
tests/
├── core/                           # 单元测试（165 用例）
│   ├── test_chunker.py             # SemanticChunker 字符计数/中文分块
│   ├── test_mineru_parser.py       # MinerU content_list 分流逻辑
│   ├── test_document_processor.py  # FAQParser/DefaultParser/Registry
│   ├── test_pipeline.py            # RAG Pipeline 流程
│   ├── test_hybrid_retriever.py    # RRF 融合逻辑
│   └── ...
├── integration/                    # 集成测试（78 用例）
│   ├── test_pdf_parsing.py         # PDF 解析回归（10 个场景，68 用例）
│   ├── test_ingestion_pipeline.py  # FAQ 导入端到端
│   ├── test_pipeline_flow.py       # Pipeline 全流程
│   └── test_hybrid_retriever.py    # 混合检索集成
├── smoke/                          # 冒烟测试（6 用例）
├── api/                            # API 接口测试（19 用例）
├── data/                           # 测试数据
│   ├── 功放说明书.pdf               # 测试 PDF
│   ├── golden_amplifier_default.json  # Golden data 基线
│   ├── eval_amplifier_qa.json      # QA 评测集（10 题）
│   └── qa_eval_results_v*.json     # E2E 评测结果（带版本号）
└── conftest.py                     # 全局 fixtures

scripts/
├── eval_production_pipeline.py     # E2E 质量评测（真实全链路）
├── ingest.py                       # 知识库导入
└── demo_pipeline.py                # RAG 链路演示
```

### 文档同步规则

以下文件修改时，必须同步更新 README.md 对应章节：

| 触发变更 | 同步到 README |
|---------|--------------|
| `tests/` 目录结构变化（新增/删除测试文件） | "测试 > 测试结构" 章节 |
| 测试数量变化（新增/删除用例） | "当前状态：N passed" |
| `scripts/eval_*.py` 新增或改动 | "测试 > 运行命令" E2E 评测部分 |
| `.env` 配置项变化 | "快速开始" 环境变量说明 |
| API 接口新增或变更 | "主要接口" 表格 |
| `docs/*.md` 新增文档 | "文档导航" 表格 |

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
| v0.1.0 | Phase 1：RAG 核心链路 | ✅ 完成，284 tests，91% 覆盖率 |
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
