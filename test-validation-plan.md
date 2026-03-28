# AI 客服系统 · 测试验证 & 可观测性方案

> **用途**：上线前测试策略、语料来源、评估指标、可观测性架构的执行参考。
> **目标读者**：负责测试和上线验收的开发者。
> **最后更新**：2026-03-28

---

## 语料数据三层来源

```
L1 合成语料  →  快速启动，冷启动阶段
L2 公开数据  →  校准通用能力，对齐行业 Benchmark
L3 真实业务  →  长期驱动优化（上线后）
```

| 层级 | 来源 | 用途 | 说明 |
|------|------|------|------|
| **L1 合成** | RAGAS `generate_testset()` | 快速获得 QA 对，覆盖检索覆盖率测试 | 从知识库文档自动生成，无需人工标注 |
| **L2 公开** | DuReader / CMRC2018 | 校准通用中文理解能力，对齐行业标准 | 可选客服相关子集（退款/物流/账号）|
| **L3 真实** | 用户提问日志（上线后）| 真实分布，发现知识库盲区 | 需脱敏，结合人工/LLM-as-judge 标注 |

---

## 三类测试集

| 类型 | 内容 | 验证目标 |
|------|------|---------|
| **黄金问答集** | 手工挑选 50-100 题，有明确标准答案 + 来源 chunk | 召回率 + 回答准确率 |
| **负例集** | 范围外问题 / 无关问题 / 模糊问题 | 兜底机制是否正确触发 |
| **难例集** | 多文档综合题 / 数字精确查询 / 口语化/错别字 | 鲁棒性 |

---

## 核心评估指标

| 指标 | 目标值 | 对应 RAGAS 指标 | 说明 |
|------|--------|---------------|------|
| Recall@5 | > 90% | `context_recall` | 正确答案在 top-5 召回中 |
| 答案准确率 | > 85% | `answer_relevancy` | 与黄金答案对比 |
| 无幻觉率 | > 95% | `faithfulness` | 答案有知识库依据 |
| 兜底触发率（负例集）| > 95% | 自定义 | 范围外问题被正确兜底 |
| P95 延迟 | < 3s | 自定义 | 全链路端到端 |

### RAGAS 三指标含义

- **faithfulness**：生成答案的每一句是否都有 chunk 支撑，防幻觉核心指标
- **context_recall**：知识库是否充分覆盖问题（需要 ground truth）
- **answer_relevancy**：答案是否切题（用答案反推问题，与原问题相似度衡量）

---

## 可观测性架构

### trace_id 全链路追踪结构

每次请求生成唯一 `trace_id`，记录完整链路数据：

```json
{
  "trace_id": "t-abc123",
  "session_id": "sess_xyz",
  "timestamp": "2026-03-28T10:00:00Z",
  "query": {
    "original": "退款咋整",
    "rewritten": "如何申请退款"
  },
  "retrieval": {
    "top_k_chunks": ["c1", "c2", "c3"],
    "confidence": 0.87,
    "confidence_tier": "high",
    "signals": {
      "retrieval_score": 0.91,
      "coverage_score": 0.80,
      "score_gap": 0.22
    }
  },
  "latency_ms": {
    "intent": 120,
    "query_rewrite": 150,
    "retrieval": 80,
    "rerank": 30,
    "generate": 900,
    "total": 1280
  },
  "fallback_triggered": false,
  "model": "claude-3-5-sonnet-20241022"
}
```

### 用 trace 定位问题

| 现象 | 看哪个字段 | 根因 |
|------|-----------|------|
| 答案不对 | `confidence_tier=high` 但答错 | 生成问题（LLM 幻觉）|
| 总触发兜底 | `retrieval_score` 低 | 召回问题（知识库缺失）|
| 总触发兜底 | `coverage_score` 低 | 知识库盲区 |
| 延迟高 | `latency_ms.generate` 高 | LLM 速度问题 |
| 延迟高 | `latency_ms.retrieval` 高 | Embedding 推理慢 |

---

## 数据飞轮（持续优化闭环）

```
用户提问
  │ trace_id 记录全链路
  ▼
低置信度 / 兜底触发 / 用户反馈差
  │ 标记为"覆盖盲区"
  ▼
每周 review → 汇总 Top 10 盲区问题
  │
  ▼
补充知识库 / 修正 Q&A
  │
  ▼
RAGAS 重跑评测集（faithfulness / context_recall / answer_relevancy）
  │
  ▼
指标提升验证 → 继续收集
```

---

## 阈值校准方法

置信度阈值（0.5 / 0.75）不是拍脑袋，用数据驱动：

1. 用黄金问答集（50-100 题）跑完整 RAG 链路，收集所有 confidence 分值
2. 人工标注每题答案质量（Correct / Partial / Wrong）
3. 画 Precision-Recall 曲线：
   - `high` 阈值：Precision = 0.95 对应的 confidence 值
   - `low` 阈值：Recall = 0.95 对应的 confidence 值
4. 初始值 0.75 / 0.50，实测后调整

---

## 可靠性验证方法

| 方法 | 用途 | 频率 |
|------|------|------|
| **RAGAS 自动评测** | 批量跑 faithfulness / context_recall / answer_relevancy | 每次修改 RAG 参数后 |
| **LLM-as-judge** | Claude 对比生成答案与标准答案，输出 Correct / Partial / Wrong | 周期性抽样 |
| **双盲标注** | 黄金问答集由 2 人独立标注，不一致项讨论 | 建集阶段一次性 |
| **Regression 测试** | 修改 topK / 阈值 / chunking 参数后跑全量测试集 | 每次参数变更 |
