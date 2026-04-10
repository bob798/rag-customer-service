# RAG 多模态输出架构设计

> 调研日期：2026-04-10 | 定位：架构设计方案
> 系列文档 | [① 工具选型](./01-parsing-tools-selection.md) → [② Pipeline 设计](./02-multimodal-pipeline-design.md) → [③ 分块策略](./03-chinese-chunking-strategy.md) → [流程类QA](./procedural-qa-in-rag.md) → 本文

---

## 一、问题定义

当前 RAG 系统回答是纯文本。用户问"蓝牙怎么连"时，应该返回文字步骤 + 产品面板图片。

### 数据流现状

```
解析层 ✅ image_path 完整保留
  → 存储层 ✅ ChromaDB metadata 含 image_path
    → 检索层 ✅ 检索结果含完整 metadata
      → Generator ❌ _build_sources() 只保留 4 个字段，丢弃 image_path
        → API ❌ SourceItem 无图片字段
          → 前端 ❌ 无法展示图片
```

---

## 二、ContentBlock 协议设计

### 统一输出格式

```python
# 所有回答统一用 blocks 数组
ContentBlock = TextBlock | ImageBlock | TableBlock

TextBlock   = {"type": "text",  "content": str}
ImageBlock  = {"type": "image", "url": str, "caption": str}
TableBlock  = {"type": "table", "content": str, "caption": str}

# 纯文本场景（特例）
answer = [{"type": "text", "content": "退款需要3-5个工作日。"}]

# 图文场景
answer = [
    {"type": "text",  "content": "请按以下步骤操作：\n1. 打开电源..."},
    {"type": "image", "url": "/static/images/doc-001/panel.jpg", "caption": "图1：前面板"},
    {"type": "text",  "content": "2. 等待蓝牙指示灯闪烁..."},
]
```

纯文本是 ContentBlock 的特例，不需要两种接口。

### SSE 流式协议

```
# LLM token 流（不变）
data: {"type": "delta", "content": "token"}

# 完成帧（answer 改为 blocks）
data: {
    "type": "done",
    "answer": [
        {"type": "text", "content": "完整回答"},
        {"type": "image", "url": "/static/images/...", "caption": "图1"}
    ],
    "sources": [...],
    "confidence": 0.85
}
```

图片不需要"流式"，在 done 帧中一次性给出。

---

## 三、图片文件服务方案

### 全景图

```
PDF → [MinerU/PaddleOCR] → 提取图片到临时目录
                              ↓
                    [Ingest] 拷贝到 data/images/{doc_id}/
                              ↓
                    [ChromaDB] chunk.metadata.image_path = "{doc_id}/hash.jpg"
                              ↓
                    [Retriever] 检索返回 image chunk
                              ↓
                    [Generator] image_url = "/static/images/{doc_id}/hash.jpg"
                              ↓
                    [FastAPI StaticFiles] 直出图片
                              ↓
                    [前端] <img src="/static/images/...">
```

### 三阶段演进

| | Phase 1 开发阶段 | Phase 2 单机部署 | Phase 3 生产级 |
|---|---|---|---|
| **存储** | 本地 `data/images/{doc_id}/` | + hash 命名去重 | MinIO / S3 / OSS |
| **访问** | FastAPI StaticFiles | + 长期缓存头 | 签名 URL 或 CDN |
| **去重** | 文件名级 | 内容级 SHA-256 | 同 Phase 2 |
| **鉴权** | 无（路径不可猜测） | 无 | 签名 URL |
| **清理** | `rmtree(doc_id/)` | + DB Image 表级联 | 同左 |
| **部署** | 本地目录 | Docker volume | 对象存储 |
| **工作量** | 1 天 | +2 天 | +2 天 |

### 目录结构

```
data/images/
├── {doc_id}/
│   ├── front_panel.jpg     # Phase 1: 原始文件名
│   ├── rear_panel.jpg
│   └── spec_table.png
```

### 关键决策

| 决策 | 选择 | 理由 |
|------|------|------|
| base64 vs URL | **URL** | 可缓存、响应体不膨胀 |
| 按 doc_id 分目录 | **是** | 删除/隔离简单 |
| 缩略图 | **不做** | 客服图片需看清细节 |
| Phase 1 去重 | **不做** | 冗余 ~10%，可接受 |
| 持久化位置 | **Phase 1 parser 内，Phase 2 抽 ImageStore 接口** | 快速上线 → 架构对齐 |

---

## 四、改动清单

### 全栈改动（3.5 人天）

| 文件 | 改动 | 工作量 |
|------|------|--------|
| `api/schemas.py` | `ContentBlock` model + `SourceItem` 加 `content_type`/`image_url` | 0.5 天 |
| `core/rag/generator.py` | `_build_content_blocks()` 后处理 + `_build_sources()` 扩展 | 1 天 |
| `core/rag/pipeline.py` | fallback 路径返回 `[TextBlock]` | 0.25 天 |
| `api/routes/chat.py` | SSE done 帧适配 | 0.5 天 |
| `api/main.py` | 挂载 `/static/images` 静态文件 | 0.25 天 |
| `db/models.py` | `Message.answer` 存 JSON | 0.25 天 |
| `core/knowledge/parsers/mineru.py` | 图片拷贝到持久目录 | 0.25 天 |
| 测试（多文件） | 断言适配 + 新增 image block 测试 | 1 天 |

### Phase 2 追加（2 天）

| 文件 | 改动 |
|------|------|
| `core/interfaces/image_store.py` | **新建** BaseImageStore 接口 |
| `core/knowledge/image_store.py` | **新建** LocalImageStore（hash 去重） |
| `db/models.py` | Image 表（file_hash + doc_id） |
| `api/routes/knowledge.py` | 删除文档时级联清理图片 |

### Phase 3 追加（2 天）

| 文件 | 改动 |
|------|------|
| `core/knowledge/s3_image_store.py` | **新建** S3ImageStore |
| `scripts/migrate_images.py` | **新建** 本地→S3 迁移脚本 |

---

## 五、与现有模块的关系

### Generator 改造细节

```python
# 现在
def generate() -> {"answer": str, "sources": list}

# 改后
def generate() -> {"answer": list[ContentBlock], "sources": list}
```

LLM 仍然生成纯文本 string，后处理将其拆为 TextBlock + 从 reranked chunks 中提取 ImageBlock/TableBlock：

```python
def _build_content_blocks(self, llm_text: str, reranked: list[dict]) -> list[dict]:
    blocks = [{"type": "text", "content": llm_text}]
    for chunk in reranked:
        ct = chunk.get("metadata", {}).get("content_type", "text")
        if ct == "image" and chunk["metadata"].get("image_path"):
            blocks.append({
                "type": "image",
                "url": f"/static/images/{chunk['metadata']['image_path']}",
                "caption": chunk["content"].replace("[图片] ", ""),
            })
        elif ct == "table":
            blocks.append({
                "type": "table",
                "content": chunk["content"],
                "caption": chunk.get("metadata", {}).get("table_caption", ""),
            })
    return blocks
```

### 多实例部署架构

```
              ┌─────────┐
              │  Nginx   │
              └────┬─────┘
             ┌─────┼─────┐
          ┌──▼──┐┌─▼──┐┌─▼──┐
          │API 1││API 2││API 3│  ← 无状态
          └──┬──┘└──┬──┘└──┬──┘
             │      │      │
          ┌──▼──────▼──────▼──┐
          │  MinIO / S3 / OSS  │  ← 共享图片
          └───────────────────┘
          ┌───────────────────┐
          │    PostgreSQL      │  ← 替换 SQLite
          └───────────────────┘
```

---

## 六、参考资料

| 产品/框架 | 图文输出模式 |
|---------|-----------|
| RAGFlow | content blocks 数组，图片存 MinIO |
| Dify | Markdown `![](url)` 内嵌图片 |
| LangChain | `AIMessage.content` 支持 `list[str|dict]` |
| Intercom/Zendesk | 回答后附"相关文章"卡片含缩略图 |
