# AI 客服系统 · Phase 1 产品设计文档

> 版本：v1.2 | 日期：2026-03-28 | 状态：已确认
> **本文只记录结论。** 过程文档：[技术选型依据](./tech-selection.md) · [架构设计思想](./architecture-design-principles.md) · [测试验证方案](./test-validation-plan.md) · [面试素材](./interview-prep.md)

---

## 项目背景

基于市场调研，企业 AI 落地诉求集中在客服场景。
本项目目标：独立开发一套企业级 AI 客服系统，可独立部署，也可作为组件接入其他系统（speakeasy 等）。

**三阶段规划：**
- Phase 1（当前）：RAG 核心 + API + Widget，单租户企业级
- Phase 2：评估看板 + 用户反馈机制
- Phase 3：独立 Web 入口 + 多租户扩展

---

## Phase 1 定位

**服务对象：**
- 企业方：直接部署，接待自己的 C 端用户
- 开发者：调用 API，把客服能力集成到自己的产品

**架构原则：**
- API First：所有入口调同一套 `/chat` API，Core 不感知入口类型
- 单租户：每家企业独立部署一套（Phase 3 扩展多租户）
- 企业级标准：API Key 认证、错误处理、流式输出、日志

---

## 核心对话链路

```
用户提问
  ↓
意图识别（范围内 / 范围外 / 模糊）
  ↓ 模糊 → 主动澄清，反问用户
  ↓ 范围外 → 直接兜底
  ↓ 范围内
Query 改写（LLM 优化口语化/模糊表达）
  ↓
混合检索（向量检索 + BM25 关键词检索）+ 元数据过滤
  ↓ 可选：HyDE 增强（生成假设答案再检索）
Reranking（召回结果重排序）
  ↓
幻觉检测 + 置信度评分
  ↓ 低置信度 → 标注"不确定" / 触发兜底
LLM 生成回答（附来源引用）
  ↓
流式输出（SSE）+ 语义缓存命中检查
  ↓ 无答案 → 兜底（告知 / 留资 / 转人工，可配置）
```

---

## Phase 1 功能清单

### 模块 1：知识库管理

| 功能          | 说明                             | 优先级 |
| ----------- | ------------------------------ | --- |
| 文档上传        | 支持 PDF / Word / TXT / Markdown | P0  |
| 文档解析 + 语义分块 | 非固定字符截断，保留语义完整性                | P0  |
| 手动 Q&A 录入   | 问题-答案对，支持增删改                   | P0  |
| 索引状态查看      | 成功 / 失败 / 进行中，失败原因可查           | P0  |
| 文档删除/更新     | 更新后自动重新索引                      | P0  |
| 文档版本标记      | 记录文档时间，用于置信度辅助判断               | P1  |

### 模块 2：对话核心（RAG 全链路）

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 意图识别 | 范围内 / 范围外 / 模糊 三类 | P0 |
| 主动澄清机制 | 模糊问题先反问，不给低质量答案 | P0 |
| Query 改写 | LLM 优化口语化/模糊表达 | P0 |
| 混合检索 | 向量检索 + BM25 关键词检索 | P0 |
| 元数据过滤 | 按文档类型/分类缩小检索范围 | P1 |
| Reranking | 召回结果重排序 | P0 |
| HyDE 检索增强 | 生成假设答案再检索，可配置开关 | P1 |
| 幻觉检测 + 置信度评分 | 低置信度标注"不确定" | P0 |
| 来源引用 | 回答附带文档来源 | P0 |
| 流式输出 | SSE 流式返回 | P0 |
| 高频问题语义缓存 | 降延迟降成本，语义相似命中缓存 | P1 |
| 兜底机制 | 无答案 → 告知 / 留资 / 转人工，可配置 | P0 |
| 敏感词过滤 | 禁止话题拦截，PII 检测 | P1 |

### 模块 3：会话历史

| 功能 | 说明 | 优先级 |
|------|------|--------|
| 会话存储 | 问题 / 回答 / 来源 / 置信度 / 时间 | P0 |
| 历史查询 API | 按会话 ID、时间段查询 | P0 |
| Admin 后台会话浏览 | 管理员可查看所有历史对话 | P0 |

### 模块 4：系统配置

| 功能 | 说明 | 优先级 |
|------|------|--------|
| LLM 选型 | Claude / DeepSeek / 通义，运行时切换 | P0 |
| 兜底动作配置 | 告知 / 留资表单 / 转人工链接 | P0 |
| 机器人人设 | 名字、语气、系统 Prompt | P0 |
| 检索参数 | topK、相似度阈值、缓存开关、HyDE 开关 | P1 |
| 敏感词配置 | 禁止话题词表管理 | P1 |

### 模块 5：系统集成

| 功能 | 说明 | 优先级 |
|------|------|--------|
| `POST /chat` | 问答主接口，支持 SSE 流式 | P0 |
| `POST /knowledge/upload` | 文档上传接口 | P0 |
| `POST /knowledge/qa` | Q&A 录入接口 | P0 |
| `GET /sessions` | 会话历史查询 | P0 |
| `GET/PUT /config` | 配置读取/更新 | P0 |
| API Key 认证 | 企业级安全基础 | P0 |
| Webhook 工单集成 | 无法解决时推送到飞书/钉钉/自定义 URL | P1 |
| 转人工协议 | 携带完整对话上下文移交给真人客服 | P1 |

### 模块 6：嵌入式 Widget

| 功能 | 说明 | 优先级 |
|------|------|--------|
| JS 聊天气泡 | `<script>` 一行嵌入任意网页 | P0 |
| 流式消息渲染 | 打字机效果，与 SSE 对应 | P0 |
| Token 认证 | Widget 与后端安全通信 | P0 |

---

## 技术选型

| 组件 | 选型 | 理由 |
|------|------|------|
| 语言/框架 | Python + FastAPI | 与 speakeasy 一致，复用经验；AI 生态最完整 |
| 向量数据库 | ChromaDB | Phase 1 本地部署零依赖；Phase 3 迁移 Milvus |
| BM25 | rank_bm25 | 纯 Python，无外部服务依赖，轻量 |
| Reranker | BGE-Reranker-v2-m3（本地） | 无 API 成本，中文效果好；Cohere Rerank 作为可选 |
| Embedding | gte-Qwen2-1.5B（本地）| 中文 MTEB 优于 BGE-M3，3GB 本地可接受；备选 Qwen API |
| LLM | 工厂模式（Claude / DeepSeek / 通义） | 复用 speakeasy 多模型架构，切换成本零 |
| LLM SDK 代理 | LiteLLM | 统一接口，屏蔽各家 SDK 差异 |
| 文档解析 | PyMuPDF（PDF）+ python-docx（Word）| 轻量，无需外部服务 |
| 会话/配置持久化 | SQLite（Phase 1）→ PostgreSQL（生产） | 开发简单，生产可升级 |
| 语义缓存 | 内存 + 向量相似度（Phase 1）| 简单实现，Phase 2 升级 Redis |
| 部署 | Docker Compose | 企业一键部署，开发环境一致 |

> 详细对比与决策依据见 [tech-selection.md](./tech-selection.md)。

---

## API 契约 & 数据结构

### POST /chat（主问答接口）

**Request:**
```json
{
  "question": "退款需要几个工作日？",
  "session_id": "sess_abc123",
  "stream": true
}
```

**Response（非流式）:**
```json
{
  "answer": "退款通常需要 3-5 个工作日到账。",
  "sources": [
    { "doc_id": "doc_001", "title": "退款政策.pdf", "chunk": "退款处理时间为..." }
  ],
  "confidence": 0.87,
  "uncertain": false,
  "session_id": "sess_abc123",
  "message_id": "msg_xyz789"
}
```

**Response（流式 SSE）:**

```
# 中间帧（每个 token）
data: {"type": "delta", "content": "退款"}

# 最终帧（携带完整元数据）
data: {"type": "done", "sources": [...], "confidence": 0.87, "uncertain": false, "message_id": "msg_xyz789"}

# 错误帧
data: {"type": "error", "code": 503, "message": "LLM 暂时不可用"}
```

### 置信度定义（三档）

```
confidence = 0.6 * retrieval_score   # BGE-Reranker 语义相关度
           + 0.3 * coverage_score    # 关键词覆盖率（jieba 分词）
           + 0.1 * score_gap         # top-1 与 top-2 分差

>= 0.75 → 正常回答
0.50–0.75 → 附注"以下回答仅供参考"（uncertain=True）
< 0.50 → 触发兜底（fallback_triggered=True）
```

阈值初始值 0.5/0.75，用黄金问答集 PR 曲线校准后调整。Phase 2 引入 LLM-as-judge 替换 coverage_score。

> 多信号置信度的设计原理见 [architecture-design-principles.md](./architecture-design-principles.md)。

### 核心数据模型

**Chunk（知识库切片）:**
```
chunk_id, doc_id, content, token_count,
embedding_vector, metadata(doc_type, category, created_at),
bm25_indexed: bool
```

**Session / Message:**
```
session_id, message_id, question, answer,
sources(list), confidence(float), uncertain(bool),
fallback_triggered(bool), created_at
```

**Document:**
```
doc_id, filename, file_type, status(pending/indexing/done/failed),
error_msg, version, chunk_count, created_at, updated_at
```

---

## 安全模型

**两级认证（防止 Widget 暴露 Admin 权限）：**

| 凭证类型 | 作用域 | 传输方式 | 颁发方式 |
|---------|--------|---------|---------|
| Admin API Key | 全部接口（知识库、配置、会话历史） | 服务端 Header，禁止前端持有 | 环境变量配置 |
| Widget Token | 仅 `/chat` 接口，只读 | 浏览器 `<script data-token="">` | Admin 后台生成，可撤销 |

**其他安全措施：**
- Widget Token 限速：默认 60 req/min/token，可配置
- HTTPS 强制（Docker Compose 提供 Nginx TLS 模板）
- CORS 白名单：Widget Token 绑定允许来源域名

---

## 可观测性 & 错误处理

### 标准错误码

| 错误码 | 含义 |
|--------|------|
| 401 | API Key 或 Widget Token 无效 |
| 429 | 超出限速 |
| 422 | 请求参数格式错误 |
| 503 | LLM API 不可用（触发备用模型） |
| 500 | 内部错误（附 request_id 便于排查） |

### LLM 故障策略
- 主模型失败 → 自动切换备用模型（工厂模式已支持）
- 备用模型也失败 → 返回 503 + 触发兜底动作

### 健康检查
```
GET /health
→ { "status": "ok", "vector_db": "ok", "llm": "ok" }
```

> 可观测性架构（trace_id / 数据飞轮 / RAGAS 评测）见 [test-validation-plan.md](./test-validation-plan.md)。

---

## 关键技术难点与解决方案

| 难点 | 本质问题 | 解决方案 |
|------|---------|---------|
| **召回质量**（最核心）| 用户口语化提问 vs 知识库正式文档，语义 gap | Query 改写 + 混合检索 RRF + Reranking 三层保底 |
| **幻觉控制** | LLM 生成"看似合理但错误"的回答 | 置信度三档（rerank score）+ 低置信度附注/兜底 |
| **知识库更新一致性** | 更新后旧向量仍在索引，新旧知识并存 | 更新前删旧 chunks，状态机（pending→indexing→done/failed）防中间态 |
| **BM25 重启丢失** | BM25 内存索引重启后为空，混合检索退化 | lifespan 启动时从 DB 重建 BM25 |
| **流式输出 vs 置信度** | 流式要边输出，置信度要全链路跑完才有 | 先跑完 RAG 得到 confidence，再流式推 tokens，最终帧携带元数据 |
| **Chunking 语义完整性** | 固定截断破坏语义，单 chunk 答案不完整 | 按段落边界分块 + overlap，保证语义单元完整 |

---

## 里程碑计划（Phase 1，3 周）

| 周次 | 目标 | 交付物 |
|------|------|--------|
| Week 1 | RAG 核心跑通 | 知识库管理（模块1）+ 完整 RAG 链路（模块2 P0）+ 基础 API |
| Week 2 | 系统完善 | 会话历史（模块3）+ 配置管理（模块4）+ 安全认证 + 日志 |
| Week 3 | 集成交付 | Widget（模块6）+ Webhook + Docker Compose 一键部署 + README |

> Widget 调整到 Week 3，确保 RAG 核心质量优先。P1 功能（HyDE、缓存、元数据过滤）在 Week 1-2 有余量时穿插完成。

---

## Phase 1 不做（留后续）

| 功能 | 规划阶段 |
|------|---------|
| 数据看板 / 解决率统计 | Phase 2 |
| 用户满意度反馈（点赞/踩） | Phase 2 |
| 独立 Web 入口页面 | Phase 3 |
| 多租户架构 | Phase 3 |
| CRM 上下文注入 | Phase 3 |
| 语音输入/输出 | 暂不计划 |

---

## 竞品差异化定位

| 竞品 | 定位 | 我们的差异 |
|------|------|-----------|
| Dify / FastGPT | 低代码，拖拽搭建 | API First，深度定制，技术可展示 |
| 智齿 / 环信 | 全渠道客服平台 | 轻量，RAG 是核心非附加 |
| Zendesk AI | 锁定生态 | 开放接口，可嵌入任意系统 |

---

## 产品设计取舍

### 舍弃的

| 内容 | 原因 |
|------|------|
| 多租户（Phase 1）| 增加隔离/权限复杂度，先单租户验证核心 RAG 价值 |
| 语音输入/输出 | 非客服核心；speakeasy 已有，避免重复建设 |
| CRM 上下文注入 | 需对接外部系统，接口标准不统一 |
| 用户满意度反馈 | 初期数据量不够，统计无意义 |
| 数据看板 | 先保证问答正确，再优化可见性 |

### 保留的（本可以砍）

| 内容 | 保留原因 |
|------|---------|
| Webhook 工单集成 | 企业落地关键连接点，没有它客服系统是孤岛 |
| 两级安全模型 | Admin Key vs Widget Token 是企业基本要求 |
| 置信度三档 | 直接影响用户信任，二档太粗糙 |
| 结构化日志 | 上线后没有日志等于黑盒 |

---

## 功能设计取舍

### 降为 P1 的功能

| 功能 | 原因 |
|------|------|
| HyDE 检索增强 | 多一次 LLM 调用 +300ms 延迟，先验证基础召回质量 |
| 语义缓存 | 先保证正确再优化成本，初期命中率未必高 |
| 元数据过滤 | 小规模知识库无必要，大规模分品类时才有价值 |
| 敏感词过滤 | 初期人工运营兜底，自动化 Phase 2 |

### 有意不做的功能陷阱

| 功能 | 不做原因 |
|------|---------|
| 网页爬取建库 | 内容质量不可控，企业倾向管控知识库 |
| 知识图谱 | 工程复杂度 ×5，RAG 已覆盖 90% 客服场景 |
| Fine-tuning | 数据量通常不足；且知识无法实时更新，RAG 更灵活 |
| 多语言 | 国内客服 95% 中文，over-engineering |
