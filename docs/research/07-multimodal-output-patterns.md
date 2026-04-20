# 多模态 RAG 输出技术调研

> 初版：2026-04-16 | 定位：客观技术调研
> 文献覆盖范围：2021 ~ 2026-04

---

## 一、Content Block 协议对比

### 1.1 主流框架输出格式

| 框架/API | 输出格式 | 图片输出 | 特点 |
|---------|---------|---------|------|
| **Anthropic Claude API** | `content: list[Block]`（text/tool_use/thinking） | 模型输出不含 image block（仅输入支持） | 类型安全，可扩展，支持 citations |
| **OpenAI Responses API** (2025-03 GA) | `text.format` + structured output | 模型不直接输出图片（图片生成为独立服务） | `"strict": true` 强制 schema 验证 |
| **Vercel AI SDK v6** (2025-12) | `Output.object()` / `Output.array()` | 无原生多模态输出 block | 抽象 25+ provider，两行切换 |
| **LangChain 1.0** | `AIMessage.content: str \| list[str\|dict]` + `.content_blocks` | provider 透传，无统一 image block | `content_blocks` 跨 provider 标准化 |
| **RAGFlow** | content block 数组 | 支持 image block + MinIO URL | 端到端多模态 RAG |
| **Dify** | Markdown 内联 `![image]({url})` | LLM 输出中嵌入图片 URL | 低门槛，依赖 Markdown 渲染 |

**关键发现**：截至 2026-04，主流 LLM API（Claude、OpenAI）的模型输出均**不含 image block**——图片是输入端能力，不是输出端。多模态 RAG 的图文混排需要**应用层**在 LLM 文本输出后组装 image block，而非由模型直接生成。

### 1.2 三种输出模式对比

| 模式 | 代表 | 优势 | 劣势 | 适用场景 |
|------|------|------|------|---------|
| **Block 数组** | Claude API、RAGFlow | 类型安全、可独立缓存、可扩展 | 需客户端渲染逻辑 | 需结构化处理（流式、引用、缓存） |
| **Markdown 内联** | Dify、大多数 LLM 纯文本输出 | 零门槛，任何 Markdown 渲染器可用 | 无元数据、无结构化 caption | 简单聊天界面 |
| **HTML 内联** | 部分 chat widget | 完全样式控制 | XSS 风险、需消毒、重量级 | 嵌入式 widget |

---

## 二、图片服务模式

### 2.1 方案对比

| 模式 | 延迟 | 缓存 | 带宽 | 安全 | 适用阶段 |
|------|------|------|------|------|---------|
| **本地静态文件** | 低（同主机） | `Cache-Control` 头即可 | 无额外开销 | 路径猜测风险，用 UUID 缓解 | 开发/单机 |
| **CDN URL** | 预热后低 | CDN 处理 | 优化 | 默认公开，需签名 URL 保护私有内容 | 生产 |
| **签名 URL**（S3/MinIO/OSS） | +~10ms 签名 | CDN 可缓存（key 稳定时） | 高效 | 时间有界访问，企业级首选 | 生产多实例 |
| **Base64 内联** | 高（每次解码） | 破坏 HTTP 缓存 | +33% 体积膨胀 | 无独立请求，SSE 流中安全 | 临时/封闭流 |
| **Markdown `![](url)`** | 取决于图片服务器 | URL 稳定则可缓存 | 标准 | 图片服务器需可达 | 简单场景 |

### 2.2 业界共识（2025-2026）

- **Phase 1**：UUID 不可猜测路径 + 本地静态文件
- **生产级**：签名对象存储 URL（S3/MinIO）+ CDN
- **Base64**：仅用于短生命周期的封闭上下文（如内存 pipeline）

---

## 三、多模态检索方案

### 3.1 三种架构

| 方案 | 原理 | 优势 | 劣势 | 代表 |
|------|------|------|------|------|
| **文本提取** | OCR/解析图片→文本 chunk→文本向量检索 | 兼容任何文本 embedder，通用性好 | 丢失布局语义，OCR 错误传播 | MinerU + PaddleOCR |
| **视觉嵌入** | 文档渲染为页面图片→视觉向量检索 | 无需 OCR，保留视觉布局 | 需视觉 embedder，存储大 | ColPali、ColQwen2 |
| **VLM 生成时绑定** | 检索时用文本，生成时将图片传给 Vision LLM | 最高精度（直接看图推理） | 每次查询的 LLM 成本高 | GPT-4o、Claude vision |

### 3.2 视觉嵌入模型

| 模型 | 参数量 | 基座 | 特点 | Benchmark |
|------|--------|------|------|-----------|
| **ColPali** | ~3B | PaliGemma-3B | ViT patch → 线性投影 → ColBERT late interaction | ViDoRe (ICLR 2025) |
| **ColQwen2** | 2B | Qwen2-VL 2B | 更小 patch size (768 dim)，存储更低 | ViDoRe SOTA (mid-2025) |
| **CLIP** | 400M | ViT + GPT | 通用图文对齐 | 开放域检索 |

**2025 生产发现**：ColQwen2 在领域微调后优于 OCR-RAG；但 OCR-RAG 对未见过的文档类型和扫描质量波动更鲁棒。

### 3.3 Early-binding vs Late-binding

| | Early-binding | Late-binding |
|---|---|---|
| **定义** | 导入时描述图片（OCR/VLM caption 存为文本） | 查询时才将图片传给 VLM |
| **检索** | 纯文本检索 | 文本检索（图片通过 ID 引用） |
| **生成成本** | 低（图片只描述一次） | 高（每次查询传图给 VLM） |
| **时效性** | caption 可能过期 | 始终使用当前图片 |
| **适用** | 大规模稳定语料 | 小规模、高精度视觉 QA |

---

## 四、业界产品实现

| 产品 | 输出模式 | 图片存储 | 多模态检索 | 说明 |
|------|---------|---------|-----------|------|
| **RAGFlow** | Content block 数组 | MinIO（S3 兼容） | 支持图片/视频解析（2025-10） | 可配置图片/表格上下文窗口 |
| **Dify** | Markdown `![](url)` | 内部对象存储 | v1.11.1 多模态知识库，跨模态检索 | 支持 Bedrock/Vertex/Jina embeddings |
| **LlamaIndex** | 无固定格式，框架级 | 应用层定义 | MultiModal VectorStoreIndex | 框架无关 |
| **Intercom / Zendesk** | 文本回答 + 独立"相关文章"卡片 | CDN | 无跨模态 | 答案和来源分离展示 |
| **Cohere** | Markdown + `[doc]` 引用标签 | Provider CDN | 无公开 block 协议 | 引用导向 |

---

## 五、学术 Benchmark

| Benchmark | 来源 | 任务 | 特点 |
|-----------|------|------|------|
| **MultiModalQA (MMQA)** | Talmor et al., ICLR 2021 | 跨模态 QA（文本+表格+图片） | 29,918 个组合推理问题，子问题跨模态 |
| **MMCoQA** | ACL 2022 | 多轮跨模态对话 QA | 每轮可能需要不同模态 |
| **ViDoRe** | ColPali (2024) | 文档级页面图片检索 | ColPali/ColQwen2 主要 benchmark |
| **OmniDocBench** | CVPR 2025 | 文档解析质量（文本提取/表格/图片描述/版面） | 中英文覆盖 |

---

## 六、参考资料

### 协议与框架

| 资料 | 价值 |
|------|------|
| [Anthropic Messages API](https://platform.claude.com/docs/en/api/messages) | Content block 类型定义 |
| [OpenAI Responses API](https://developers.openai.com/api/docs/guides/migrate-to-responses) | Structured output + Responses 迁移 |
| [Vercel AI SDK v6](https://vercel.com/blog/ai-sdk-6) | 多 provider 抽象层 |
| [LangChain Standard Message Content](https://www.langchain.com/blog/standard-message-content) | `.content_blocks` 跨 provider 标准化 |

### 产品与实现

| 资料 | 价值 |
|------|------|
| [RAGFlow Changelog](https://ragflow.io/changelog) | 多模态输出演进 |
| [Dify 多模态知识库](https://dify.ai/blog/multimodal-retrieval-is-now-available-in-the-knowledge-base) | 跨模态检索实现 |
| [RAGFlow GitHub](https://github.com/infiniflow/ragflow) | 开源多模态 RAG 参考 |

### 视觉检索

| 资料 | 价值 |
|------|------|
| [ColPali (arXiv:2407.01449)](https://arxiv.org/abs/2407.01449) | 视觉文档检索，ViDoRe benchmark |
| [ColQwen2 HuggingFace Cookbook](https://huggingface.co/learn/cookbook/multimodal_rag_using_document_retrieval_and_reranker_and_vlms) | 多模态 RAG 实战 |
| [Weaviate Late Interaction Overview](https://weaviate.io/blog/late-interaction-overview) | ColBERT/ColPali 检索原理 |

### 学术

| 资料 | 价值 |
|------|------|
| [MultiModalQA (arXiv:2104.06039)](https://arxiv.org/abs/2104.06039) | 跨模态 QA 基准 |
| [OmniDocBench (arXiv:2412.07626)](https://arxiv.org/abs/2412.07626) | 文档解析质量 benchmark |


## 七、最佳实践

> 基于前文（一～六节）的业界方案调研和本项目约束，总结以下实践原则。

### 7.1 输出协议

1. **用 Block 数组，不用 Markdown 内联**
   - Block 数组类型安全、可独立缓存、可扩展（未来加 audio/video block 零成本）
   - Markdown `![](url)` 看似简单，但无法携带 caption 元数据、无法区分 block 类型、渲染器依赖
   - 业界验证：RAGFlow（生产级多模态 RAG）采用 block 数组；Anthropic Claude API 也是 content blocks 架构

2. **LLM 不负责输出图片——应用层组装**
   - 截至 2026-04，Claude/OpenAI 模型输出均不含 image block，图片是输入端能力
   - 正确做法：LLM 生成纯文本 → 应用层从检索结果 metadata 中提取 image/table → 组装为 content blocks
   - 不要让 LLM 在输出中"猜"图片 URL

3. **始终保留纯文本回退**
   - `answer`（str）和 `content_blocks`（list）双字段并存
   - 任何客户端都能降级到纯文本，不因多模态升级而不可用

### 7.2 图片服务

4. **开发阶段用本地 + UUID 路径，生产用签名 URL**
   - Phase 1：`data/images/{doc_id}/{hash}.jpg` + FastAPI `StaticFiles`——零依赖快速上线
   - 生产：MinIO/S3 签名 URL——时间有界、可缓存、多实例共享
   - 不要用 base64 内联（+33% 体积、破坏 HTTP 缓存），除非是封闭的短生命周期流

5. **按 doc_id 分目录存储**
   - 删除文档时 `rmtree(doc_id/)` 一步清理
   - 未来加 Image 表后改为级联删除

### 7.3 多模态检索

6. **先走文本提取路线（Early-binding），后续按需加 VLM**
   - 文本提取（OCR → 文本 chunk → 向量检索）兼容现有全链路，无额外模型依赖
   - ColPali/ColQwen2 视觉嵌入精度更高，但需要 GPU + 新的索引管道
   - VLM 生成时绑定精度最高但成本最高（每次查询传图给 Vision LLM）
   - 本项目 Intel Mac 无 GPU → 文本提取是唯一可行方案

7. **image chunk 的 metadata 必须完整**
   - 解析时就写入 `content_type`、`image_path`、`caption`、`page`、`section`
   - Generator 后处理只做"读取 + 组装"，不做"推断"——数据完整性在导入时保证

### 7.4 兼容性

8. **新增字段，不改旧字段（Additive-only schema evolution）**
   - API：新增 `content_blocks`，保留 `answer`
   - DB：新增 `content_blocks_json`，保留 `answer`
   - SSE done 帧：新增字段，已有字段不动
   - 结果：现有 284 测试无需修改，旧客户端无感知

9. **功能开关兜底**
   - `enable_content_blocks` 配置开关，关闭时 blocks 返回 `[]`
   - 客户端逻辑：`blocks.length > 0 ? renderBlocks(blocks) : renderText(answer)`
   - 出问题秒级回滚，无需代码变更

---

