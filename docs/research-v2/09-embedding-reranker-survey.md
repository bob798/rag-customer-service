# Embedding / Reranker / 稀疏检索 技术调研（2026-04）

> 初版：2026-04-16 | 更新：2026-04-17 | 定位：客观技术调研
> 文献覆盖范围：2024-01 ~ 2026-04
> 数据来源：MTEB Leaderboard、HuggingFace 官方模型卡片、Qwen 官方博客、Agentset Rerankers Leaderboard

---

## 一、Embedding 模型

### 1.1 开源模型对比

**MTEB Mean(Task)** 综合分（非 Retrieval 子任务分数，下同）：

| 模型 | 参数量 | C-MTEB 中文 | MTEB 多语言 | MTEB 英文 v2 | 上下文 | 输出维度 | 许可证 |
|------|--------|------------|------------|-------------|--------|---------|--------|
| gte-Qwen2-1.5B-instruct | 1.5B | — | 59.45 | 67.20 | 32K | 可变 | Apache 2.0 |
| Qwen3-Embedding-0.6B | 0.6B | 66.33 | 64.33 | 70.70 | 32K | 1024 | Apache 2.0 |
| Qwen3-Embedding-4B | 4B | 72.27 | 69.45 | 74.60 | 32K | 2560 | Apache 2.0 |
| Qwen3-Embedding-8B | 8B | **73.84** | **70.58** (#1 多语言) | 75.22 | 32K | 4096 | Apache 2.0 |
| BGE-M3 | 568M | ~66（历史数据） | 稳定 | — | 8K | 1024 | MIT |
| NV-Llama-Embed-Nemotron-8B | 8B | — | 顶级 | — | — | — | NVIDIA 开源协议 |

> 数据来源：Qwen3 官方模型卡片（截至 2025-06-05 MTEB 多语言 #1）。MTEB 英文 v2 与多语言均为 Mean(Task)，不要直接与具体任务子分数（如 Retrieval）对比。

### 1.2 Qwen3-Embedding 中文检索子任务分数

**C-MTEB Retrieval 子分**（RAG 场景更具参考价值）：

| 模型 | C-MTEB Retrieval |
|------|-----------------|
| Qwen3-Embedding-0.6B | 71.03 |
| Qwen3-Embedding-4B | 77.03 |
| Qwen3-Embedding-8B | **78.21** |

> 来源：Qwen3-Embedding-8B 官方模型卡片。中文 RAG 选型应以此表为主要依据，而非 MTEB 综合分。

### 1.3 API 模型对比

| 模型 | MTEB 英文 v2 | 上下文 | 输出维度 | 发布时间 | 定价模式 |
|------|-------------|--------|---------|---------|---------|
| Gemini Embedding-001 | 68.32 | 2K | 3072 | 2024 | API 按量 |
| Cohere Embed-v4 | 66.3（MTEB 子集，具体版本见官方） | 128K | 1024 | 2024 | API 按量 / VPC 部署 |
| Voyage-3-Large | 未公开 | 32K | 2048 | 2024 | API 按量 |

> Cohere Embed-v4 的确切 MTEB 分数随版本和子集变化，直接引用官方基准页面更稳妥。

### 1.4 Qwen3-Embedding 硬件需求

> ⚠️ 以下"模型体积"为 HuggingFace 权重文件大小（参考官方 safetensors shards），"显存/内存"为 **推理时运行占用估算**（含 KV cache），不等于文件大小。实际数值因 batch size、序列长度、框架（transformers / vLLM / llama.cpp）差异较大，仅供量级判断。

| 模型 | 精度 | 模型体积 | 推理显存（估算） | 推荐硬件 |
|------|------|---------|----------------|---------|
| 0.6B | FP16 | ~1.2 GB | ~2 GB | CPU 可跑 |
| 4B | FP16 | ~8 GB | ~10 GB VRAM | RTX 3080+ |
| 4B | INT4（GGUF） | ~2.5 GB | ~4 GB | CPU 勉强（延迟 2–5s/query，数据来自社区实测） |
| 8B | FP16 | ~15 GB | ~15 GB VRAM | RTX 4090 / A6000 / A100 |
| 8B | INT8（GGUF） | ~8 GB | ~8 GB VRAM | RTX 3080 / 4070 Ti |
| 8B | INT4（GGUF） | ~4.6 GB | ~5 GB | CPU 勉强（数秒/请求） |

### 1.5 Qwen3-Embedding 架构特性

- **MRL（Matryoshka Representation Learning）**：支持 32/64/128/256/512/1024 维度灵活输出
  - 低维度用于粗筛/缓存，高维度用于精排
  - 官方声明支持 MRL 维度裁剪；具体召回率损失因数据集而异，需实测
- **指令感知**：通过 task prompt 区分 query/document，官方博客报告检索场景提升约 1–5%（具体数据集见原文）
- **100+ 语言**：中英文、代码均覆盖
- **32K 上下文**：长文档无需截断

### 1.6 Qwen3-Embedding 依赖要求

| 依赖 | 最低版本 | 说明 |
|------|---------|------|
| transformers | >= 4.51.0 | 低版本报 `KeyError: 'qwen3'` |
| sentence-transformers | >= 2.7.0 | 兼容 Qwen3 架构 |
| tokenizer 设置 | `padding_side='left'` | 与 Qwen2 不同 |

### 1.7 Embedding 选型决策树

```
                    有 GPU？
                   /         \
                 是            否
                /               \
     预算充足？               参数量预算？
     /       \                /         \
   是         否           ≤1B          ≤4B
   /           \            /              \
Qwen3-8B    Qwen3-4B   Qwen3-0.6B    Qwen3-4B (INT4)
(#1 多语言)  (高性价比)  (CPU 友好)    (延迟 2-5s/query)

特殊需求：
├── 需要 dense+sparse 一体化 → BGE-M3
├── 需要超长上下文 (128K) → Cohere Embed-v4 (API)
└── 不想自部署 → Gemini / Cohere / Voyage (API)
```

---

## 二、Reranker 模型

### 2.1 开源模型对比

| 模型 | MTEB-R 英文 | CMTEB-R 中文 | MMTEB-R 多语言 | 参数量 | 架构 | 许可证 |
|------|------------|-------------|---------------|--------|------|--------|
| BGE-Reranker-v2-m3 | 57.03 | — | — | ~568M | Cross-encoder | MIT |
| Qwen3-Reranker-0.6B | 65.80 | 71.31 | 66.36 | 0.6B | LLM decoder | Apache 2.0 |
| Qwen3-Reranker-4B | **69.76** | 75.94 | 72.74 | 4B | LLM decoder | Apache 2.0 |
| Qwen3-Reranker-8B | 69.02 | **77.45** | **72.94** | 8B | LLM decoder | Apache 2.0 |
| Jina Reranker v3 | 61.94 (BEIR nDCG@10) | — | — | ~300M | Cross-encoder | Apache 2.0 |

> **注 1**：Qwen3-Reranker-8B 在英文 MTEB-R 上低于 4B（69.02 vs 69.76，差 0.74 分），但在中文 CMTEB-R 和多语言 MMTEB-R 上反超。8B 更偏向多语言优化。
>
> **注 2**：BGE-Reranker **没有 v3 版本**（截至 2026-04）。最新 BGE 系列为 `bge-reranker-v2-m3` 和 `bge-reranker-v2.5-gemma2-lightweight`（2024-07）。v3 命名的 reranker 仅 Jina 发布。

### 2.2 API Reranker（Agentset Leaderboard，2025-12 ~ 2026）

| 模型 | ELO | 排名 | 发布时间 | 说明 |
|------|-----|------|---------|------|
| ZeroEntropy Zerank-2 | 1638 | #1 | 2025 | API only |
| **Cohere Rerank v4.0 Pro** | 1629 | #2 | 2025-12-11 | API only，替代 v3.5（旧版本） |
| Cohere Rerank v4.0 Fast | — | — | 2025-12 | Pro 的轻量版 |

> 早期版本 Cohere Rerank v3.5 已被 v4 系列（Pro + Fast）替代。选型时不再推荐 v3.5。

### 2.3 架构对比：Cross-encoder vs LLM Decoder

```
Cross-encoder (BGE-v2-m3):
  [CLS] query [SEP] document [SEP] → encoder → sigmoid → score

LLM Decoder (Qwen3-Reranker):
  <instruct> task </instruct> query \n document → decoder → logits → score
```

| 维度 | Cross-encoder (BGE) | LLM Decoder (Qwen3) |
|------|--------------------|--------------------|
| 输入格式 | query + document 拼接 | 需传入 task instruction |
| 输出 | sigmoid 直接出分 | logits 映射到 score |
| tokenizer | `padding_side='right'` | `padding_side='left'` |
| 多语言 | 好 | 更好（100+ 语言） |
| CPU 延迟（参考值） | 约 200ms | 约 300ms |

### 2.4 Reranker 硬件需求

> ⚠️ 下表"CPU 延迟"为参考量级（top-10 候选、序列长度 256、单请求、Intel/AMD 桌面级 CPU）。**未指定 batch size、精度、框架**，实际延迟可在 2–10x 范围波动。生产部署前必须在目标硬件实测。

| 模型 | CPU 可行 | CPU 延迟（参考） | GPU 推荐 |
|------|----------|----------------|---------|
| BGE-Reranker-v2-m3 | 可以 | ~200ms | 无需 |
| Qwen3-Reranker-0.6B | 可以 | ~300ms | 无需 |
| Qwen3-Reranker-4B | 勉强 | ~2s | RTX 3080+ |
| Qwen3-Reranker-8B | 不可行 | — | RTX 4090+ |

---

## 三、稀疏检索

### 3.1 方案对比

| 方案 | 类型 | 原理 | 优势 | 劣势 | GPU 需求 |
|------|------|------|------|------|----------|
| **BM25** | 经典统计 | TF-IDF 变体 | 零延迟、零依赖、可解释 | 无语义扩展，纯词频匹配 | 无 |
| **SPLADE v3** | 学习型稀疏 | Transformer 生成稀疏向量 | 语义扩展，benchmark 优于 BM25 | +100–300ms 延迟 | 需要 |
| **BGE-M3 sparse head** | 学习型稀疏 | dense+sparse+multi-vector 一体化 | 一个模型三种检索模式 | 需换整套 embedding 模型 | 推荐 |
| **BM42** (Qdrant) | 改进 BM25 | 结合浅层语义 | 比 BM25 好，比 SPLADE 快 | Qdrant 向量库绑定 | 无 |

### 3.2 混合检索效果（典型量级）

> ⚠️ 下表为**业界公开 benchmark 的典型量级**（BEIR / MS MARCO 上多篇论文的大致范围），**非某一特定评测**。具体数字在不同数据集、不同 embedding 模型、不同 RRF 参数下差异可达 ±10pp。

| 检索方式 | Recall@10（量级） | NDCG@10（量级） |
|---------|-----------------|---------------|
| BM25 only | 0.70–0.75 | 0.60–0.70 |
| Dense only | 0.75–0.82 | 0.70–0.75 |
| **Hybrid (BM25 + Dense + RRF)** | **0.88–0.92** | **0.82–0.87** |

参考论文：BEIR（arXiv:2104.08663）、Hybrid Retrieval（arXiv:2010.01195）、BGE-M3（arXiv:2402.03216）

### 3.3 BM25 在混合检索中的定位

BM25 作为稀疏信号在 RRF 混合检索中仍具竞争力。升级到 SPLADE 的主要收益来自语义扩展（同义词、近义表达），但需要额外的 GPU 推理开销。在 CPU-only 环境下，BM25 仍是唯一零成本的稀疏检索选项。

---

## 四、选型建议（针对本项目）

### 4.1 当前配置

| 组件 | 当前 | 定位 |
|------|------|------|
| 硬件 | Intel Mac x86_64，无 GPU | CPU-only 推理 |
| Embedding | gte-Qwen2-1.5B-instruct | MTEB 英文 v2 Mean(Task) 67.20 |
| Reranker | bge-reranker-v2-m3 | MTEB-R 57.03 |
| 稀疏 | BM25 | 零成本 |

### 4.2 Embedding 升级路径

| 路径 | 目标模型 | 中文 C-MTEB Mean | Retrieval 子分 | 成本 | 建议 |
|------|---------|-----------------|---------------|------|------|
| **维持** | gte-Qwen2-1.5B | — | — | 0 | 稳定，基线已验证 |
| **推荐升级** | Qwen3-Embedding-0.6B | 66.33 | 71.03 | 换模型 + 重建索引 | **性价比最高**——模型更小（0.6B vs 1.5B）、CPU 友好、C-MTEB 数据公开可验证，支持 MRL 维度裁剪 |
| 中期升级 | Qwen3-Embedding-4B (INT4) | 72.27 | 77.03 | CPU 延迟 2–5s/query | 质量显著提升，但查询延迟不可接受，除非改异步预热 |
| 不推荐 | Qwen3-Embedding-8B | 73.84 | 78.21 | 需 GPU | CPU 不可行 |

**建议**：Phase B 先升 Qwen3-Embedding-0.6B，评估中文 Retrieval 实际提升；Phase C 若质量不够，再考虑 4B INT4 + 异步重建。

### 4.3 Reranker 升级路径

| 路径 | 目标模型 | CMTEB-R | MTEB-R | 延迟变化 | 建议 |
|------|---------|---------|--------|---------|------|
| **维持** | BGE-Reranker-v2-m3 | — | 57.03 | ~200ms | 当前基线 |
| **推荐升级** | Qwen3-Reranker-0.6B | **71.31** | 65.80 | ~300ms（+100ms） | **中文场景显著提升**；代价是 tokenizer `padding_side='left'` + 需 task instruction，需改调用代码 |
| 不推荐 | Qwen3-Reranker-4B/8B | 75.94/77.45 | 69.76/69.02 | ~2s+ | CPU 延迟不可接受 |

**建议**：Phase B 同步升 Qwen3-Reranker-0.6B，评估中文精排效果；改造点是 reranker 调用层（约半天工作量）。

### 4.4 稀疏检索

**维持 BM25**。CPU-only 环境下没有更好的选择：
- SPLADE v3 需 GPU，且 +100–300ms 延迟
- BM42 绑定 Qdrant，换向量库成本高
- BGE-M3 sparse head 需换整套 embedding 模型，与 4.2 的 Qwen3 升级冲突

### 4.5 不做的事

| 方案 | 原因 |
|------|------|
| Qwen3-Embedding-8B / 4B FP16 | 需 GPU，与硬件约束冲突 |
| Qwen3-Reranker-4B/8B | CPU 延迟 ≥ 2s，不可用于在线查询 |
| Cohere Rerank v4 Pro API | 数据外发合规风险 + 成本 + 网络延迟 |
| Jina Reranker v3 | BEIR 分数高但中文 benchmark 无公开数据，收益不明确 |
| SPLADE v3 | 无 GPU |

### 4.6 升级路径总览

```
Phase A（当前）:  gte-Qwen2-1.5B + BGE-Reranker-v2-m3 + BM25
      ↓ Phase B（推荐）
Phase B:         Qwen3-Embedding-0.6B + Qwen3-Reranker-0.6B + BM25
                 预期收益：中文 Retrieval +4~6pp（基于 C-MTEB 数据），中文精排 +14pp
      ↓ Phase C（可选，硬件升级后）
Phase C:         Qwen3-Embedding-4B (GPU) + Qwen3-Reranker-4B (GPU) + BM25
```

---

## 五、关键参考资料

### 官方资源

| 资料 | 价值 |
|------|------|
| [MTEB Leaderboard](https://huggingface.co/spaces/mteb/leaderboard) | 实时 embedding/reranker benchmark 排行 |
| [Qwen3 Embedding 官方博客](https://qwenlm.github.io/blog/qwen3-embedding/) | 发布说明、benchmark 数据、Reranker 对比 |
| [Qwen/Qwen3-Embedding-0.6B](https://huggingface.co/Qwen/Qwen3-Embedding-0.6B) | 模型卡片（含 C-MTEB 详细分数） |
| [Qwen/Qwen3-Embedding-8B](https://huggingface.co/Qwen/Qwen3-Embedding-8B) | 模型卡片（旗舰） |
| [Qwen/Qwen3-Reranker-8B](https://huggingface.co/Qwen/Qwen3-Reranker-8B) | 含 MTEB-R / CMTEB-R / MMTEB-R 完整对比 |
| [BAAI/bge-reranker-v2-m3](https://huggingface.co/BAAI/bge-reranker-v2-m3) | 当前 BGE Reranker 最新版 |
| [BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | BGE-M3 dense+sparse+multi-vector |

### 第三方评测

| 资料 | 价值 |
|------|------|
| [Agentset Rerankers Leaderboard](https://agentset.ai/rerankers) | API Reranker ELO 排名（Zerank-2 / Cohere Rerank 4 Pro） |
| [Cohere Rerank v4 发布博客](https://docs.cohere.com/changelog/rerank-v4.0) | v3.5 → v4 升级说明 |
| [Hybrid Search for RAG (Prem AI)](https://blog.premai.io/hybrid-search-for-rag-bm25-splade-and-vector-search-combined/) | BM25/SPLADE/混合检索对比 |

### 学术论文

| 资料 | 价值 |
|------|------|
| [BEIR (arXiv:2104.08663)](https://arxiv.org/abs/2104.08663) | 零样本信息检索基准 |
| [BGE-M3 (arXiv:2402.03216)](https://arxiv.org/abs/2402.03216) | 混合检索一体化模型 |
| [SPLADE v3 (arXiv:2403.06789)](https://arxiv.org/abs/2403.06789) | 学习型稀疏检索 |
