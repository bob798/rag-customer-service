# AI 客服系统

企业级 RAG 知识库客服系统。RAG 全链路手搓，Ports & Adapters 架构，可独立部署或作为组件接入。

## 文档导航

| 文档 | 用途 | 适合读者 |
|------|------|---------|
| [phase1-product-spec.md](./phase1-product-spec.md) | **产品规格**：功能清单、API契约、安全模型、里程碑 | 快速了解做了什么 |
| [architecture-design-principles.md](./architecture-design-principles.md) | **架构设计**：Ports & Adapters、组件化地图、RAG链路、置信度设计 | 理解怎么设计的 |
| [tech-selection.md](./tech-selection.md) | **技术选型**：各组件对比表、决策依据 | 理解为什么这样选 |
| [test-validation-plan.md](./test-validation-plan.md) | **测试方案**：测试集设计、评估指标、可观测性架构 | 了解质量保障 |
| [interview-prep.md](./interview-prep.md) | **面试素材**：30s pitch、技术深度展示、高频问题标准答法 | 面试准备 |
| [客服数据集.md](./客服数据集.md) | 示例数据集 | 测试用 |

## 推荐阅读顺序

1. `phase1-product-spec.md` — 了解整体范围
2. `architecture-design-principles.md` — 理解核心设计
3. `tech-selection.md` — 看选型依据
4. `test-validation-plan.md` — 了解评测方法

## 技术栈

- **核心**：Python + FastAPI + RAG 全链路手搓
- **检索**：ChromaDB（向量）+ rank_bm25（关键词）+ RRF 融合
- **Embedding**：gte-Qwen2-1.5B（本地，中文 MTEB ~70）
- **Reranker**：BGE-Reranker-v2-m3（本地，零 API 成本）
- **LLM**：Claude / DeepSeek / 通义（LiteLLM 统一接口）
- **部署**：Docker Compose

## 项目状态

Phase 1 设计完成，待执行（2026-03）
