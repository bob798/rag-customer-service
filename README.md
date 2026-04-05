# AI 客服系统

企业级 RAG 知识库客服系统。RAG 全链路手搓，Ports & Adapters 架构，可独立部署或作为组件接入。

## 文档导航

### 技术文档（代码同步更新）

| 文档 | 内容 |
|------|------|
| [docs/architecture.md](./docs/architecture.md) | 系统分层架构图、Ports & Adapters 对照表 |
| [docs/rag-query-flow.md](./docs/rag-query-flow.md) | RAG 七步查询流程、置信度三路信号、SSE 时序图、RRF 算法 |
| [docs/data-model.md](./docs/data-model.md) | ER 图、ChromaDB 元数据约定、sources 格式、trace_id 日志 |

### 产品与设计文档

| 文档 | 用途 | 适合读者 |
|------|------|---------|
| [phase1-product-spec.md](./phase1-product-spec.md) | **产品规格**：功能清单、API契约、安全模型、里程碑 | 快速了解做了什么 |
| [architecture-design-principles.md](./architecture-design-principles.md) | **架构设计**：Ports & Adapters、组件化地图、RAG链路、置信度设计 | 理解怎么设计的 |
| [tech-selection.md](./tech-selection.md) | **技术选型**：各组件对比表、决策依据 | 理解为什么这样选 |
| [test-validation-plan.md](./test-validation-plan.md) | **测试方案**：测试集设计、评估指标、可观测性架构 | 了解质量保障 |
| [interview-prep.md](./interview-prep.md) | **面试素材**：30s pitch、技术深度展示、高频问题标准答法 | 面试准备 |
| [客服数据集.md](./客服数据集.md) | 示例数据集 | 测试用 |

## 推荐阅读顺序

1. `docs/architecture.md` — 系统分层架构全景
2. `docs/rag-query-flow.md` — RAG 核心链路详解
3. `phase1-product-spec.md` — 了解整体产品范围
4. `architecture-design-principles.md` — 理解核心设计决策
5. `tech-selection.md` — 看选型依据
6. `test-validation-plan.md` — 了解评测方法

## 技术栈

- **核心**：Python + FastAPI + RAG 全链路手搓
- **检索**：ChromaDB（向量）+ rank_bm25（关键词）+ RRF 融合
- **Embedding**：gte-Qwen2-1.5B（本地，中文 MTEB ~70）
- **Reranker**：BGE-Reranker-v2-m3（本地，零 API 成本）
- **LLM**：Claude / DeepSeek / 通义（LiteLLM 统一接口）
- **部署**：Docker Compose

## 项目状态

Phase 1 实施中（2026-04）

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

### 编码解释模式

本项目采用**混合编码解释模式**：开发者用自然语言描述意图和约束，AI 负责代码生成与自审，开发者保留架构决策权与最终审查权。

参考：Jiang et al., *"混合编码解释模式下的人机协同编程"*，arXiv:2601.20245

### 分工原则

| 开发者负责 | AI 负责 |
|-----------|---------|
| 产品需求定义 | 代码生成与实现 |
| 架构设计决策 | 规格合规审查 |
| 技术选型判断 | 代码质量审查 |
| 计划审批 | TDD 执行 |
| 最终代码审核 | 测试编写 |
