# RAG 多类型内容输出通用方案

> 版本：1.0 | 日期：2026-04-14
> 适用场景：任意 RAG 系统需要输出文本 + 图片 + 表格 + 代码等混合内容

---


## 一、问题

RAG 系统的回答通常是纯文本 string。但知识库中包含图片、表格、代码、公式等多种内容类型。用户提问时，理想的回答应该是**混合内容**——文字说明 + 产品图片 + 参数表格，而不是把所有内容压成一段话。

**核心矛盾**：LLM 生成的是纯文本，但检索到的 chunks 包含多种类型的结构化信息。需要一种机制把两者组合成统一的混合输出。

---

## 二、ContentBlock 协议

### 2.1 设计原则

| 原则 | 说明 |
|------|------|
| **纯文本是特例** | 纯文本回答 = 只包含一个 TextBlock 的数组，不需要两套接口 |
| **渲染无关** | 协议只定义数据结构，不规定前端如何渲染（Web/App/终端都能用） |
| **可扩展** | 新增类型（视频、音频、文件）只需加新 Block，不改已有结构 |
| **流式友好** | 文本可逐 token 流式推送，非文本内容在完成帧一次性给出 |

### 2.2 Block 类型定义

```
ContentBlock = TextBlock | ImageBlock | TableBlock | CodeBlock | FormulaBlock | FileBlock
```

```jsonc
// 文本块 — LLM 生成的回答文本
{
  "type": "text",
  "content": "请按以下步骤操作：\n1. 打开电源开关..."
}

// 图片块 — 从知识库 chunk 中提取
{
  "type": "image",
  "url": "/static/images/doc-001/panel.jpg",   // 图片访问地址
  "caption": "图1：产品前面板",                   // 图片说明
  "source_chunk_id": "chunk-abc-123"            // 可选：溯源到原始 chunk
}

// 表格块 — Markdown 或 HTML 格式的表格
{
  "type": "table",
  "format": "markdown",                          // "markdown" | "html"
  "content": "| 参数 | 值 |\n|---|---|\n| 功率 | 50W |",
  "caption": "表1：技术规格"
}

// 代码块
{
  "type": "code",
  "language": "python",
  "content": "def hello():\n    print('world')"
}

// 公式块 — LaTeX 格式
{
  "type": "formula",
  "content": "E = mc^2",
  "format": "latex"
}

// 文件附件块
{
  "type": "file",
  "url": "/static/files/manual.pdf",
  "filename": "产品手册.pdf",
  "mime_type": "application/pdf"
}
```

### 2.3 完整响应结构

```jsonc
{
  "answer": [
    {"type": "text", "content": "BLV-D1 的技术规格如下："},
    {"type": "table", "format": "markdown", "content": "| 参数 | 值 |\n|---|---|\n| 功率 | 50W |", "caption": "技术规格"},
    {"type": "text", "content": "产品外观如下图所示："},
    {"type": "image", "url": "/static/images/doc-001/panel.jpg", "caption": "前面板"}
  ],
  "sources": [
    {
      "chunk_id": "chunk-001",
      "doc_id": "doc-001",
      "title": "功放说明书.pdf",
      "content_preview": "BLV-D1 输出功率 50W...",
      "content_type": "table",
      "image_url": null
    }
  ],
  "confidence": 0.85,
  "intent": "in_scope"
}
```

**纯文本回答**（向后兼容）：

```json
{
  "answer": [{"type": "text", "content": "退款需要 3-5 个工作日。"}],
  "sources": [],
  "confidence": 0.92
}
```

---

## 三、生成流水线

LLM 只输出文本，非文本内容来自检索到的 chunks。两者在后处理阶段合并。

### 3.1 架构

```
                    ┌─────────────┐
  用户问题 ────────→│  Retriever   │──→ ranked chunks (含 metadata)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  Reranker    │──→ top-k chunks
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐    │     ┌──────▼──────┐
       │ LLM Generator│    │     │ Block Builder │
       │ (纯文本)     │    │     │ (从 chunks   │
       └──────┬──────┘    │     │  提取非文本)  │
              │            │     └──────┬──────┘
              │            │            │
       ┌──────▼────────────▼────────────▼──────┐
       │          Block Assembler               │
       │  合并 LLM 文本 + 非文本 blocks          │
       │  去重、排序、插入位置决策                 │
       └──────────────┬────────────────────────┘
                      │
                      ▼
              list[ContentBlock]
```

### 3.2 Block Builder — 从 chunks 提取非文本块

```python
def build_non_text_blocks(chunks: list[dict], image_url_prefix: str = "/static/images") -> list[dict]:
    """从 reranked chunks 中提取图片、表格等非文本 blocks。
    
    Args:
        chunks: reranker 输出的 top-k chunks，每个含 content + metadata
        image_url_prefix: 图片 URL 前缀
    
    Returns:
        非文本 ContentBlock 列表
    """
    blocks = []
    seen = set()  # 去重

    for chunk in chunks:
        meta = chunk.get("metadata", {})
        content_type = meta.get("content_type", "text")
        content = chunk.get("content", "")

        if content_type == "image":
            image_path = meta.get("image_path")
            if not image_path:
                continue
            url = f"{image_url_prefix}/{image_path}"
            if url in seen:
                continue
            seen.add(url)
            # 去掉 "[图片]" 前缀作为 caption
            caption = content.replace("[图片]", "").strip()
            blocks.append({
                "type": "image",
                "url": url,
                "caption": caption,
                "source_chunk_id": chunk.get("chunk_id"),
            })

        elif content_type == "table":
            # 用内容前 80 字符做去重 key
            dedup_key = f"table:{content[:80]}"
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            blocks.append({
                "type": "table",
                "format": "html" if "<table" in content else "markdown",
                "content": content,
                "caption": meta.get("table_caption", ""),
                "source_chunk_id": chunk.get("chunk_id"),
            })

        elif content_type == "code":
            blocks.append({
                "type": "code",
                "language": meta.get("language", ""),
                "content": content,
            })

        elif content_type == "formula":
            blocks.append({
                "type": "formula",
                "content": content,
                "format": "latex",
            })

    return blocks
```

### 3.3 Block Assembler — 合并策略

LLM 文本和非文本内容如何排列？三种策略：

```
策略 A：文本在前，附件在后（最简单）
  [TextBlock(LLM回答), ImageBlock, TableBlock, ...]

策略 B：按检索顺序交错（最自然）
  [TextBlock(部分回答), ImageBlock, TextBlock(继续回答), TableBlock]

策略 C：LLM 决定插入点（最智能，最复杂）
  LLM 输出标记 {{IMAGE:chunk-id}}，后处理替换为 ImageBlock
```

**推荐策略 A**，原因：
- 实现最简单，LLM 无需感知非文本内容
- 前端可以自由决定如何排列（侧边栏、底部附件、内嵌展示）
- 策略 B/C 需要 LLM prompt engineering 支持，增加复杂度

```python
def assemble_blocks(
    llm_text: str,
    chunks: list[dict],
    strategy: str = "text_first",  # "text_first" | "interleaved" | "llm_directed"
    image_url_prefix: str = "/static/images",
) -> list[dict]:
    """合并 LLM 文本和非文本 blocks。"""
    
    text_block = {"type": "text", "content": llm_text}
    non_text_blocks = build_non_text_blocks(chunks, image_url_prefix)
    
    if strategy == "text_first":
        return [text_block] + non_text_blocks
    
    elif strategy == "interleaved":
        # 按 chunk 在文档中的原始顺序插入
        # 需要 chunks 带有 chunk_index 信息
        result = []
        text_parts = llm_text.split("\n\n")
        block_iter = iter(non_text_blocks)
        
        for i, part in enumerate(text_parts):
            if part.strip():
                result.append({"type": "text", "content": part})
            # 每段文本后尝试插入一个非文本 block
            try:
                result.append(next(block_iter))
            except StopIteration:
                pass
        # 剩余的非文本 blocks 追加到末尾
        result.extend(block_iter)
        return result
    
    elif strategy == "llm_directed":
        # LLM 文本中的 {{IMAGE:chunk-id}} 标记替换为实际 block
        block_map = {b.get("source_chunk_id"): b for b in non_text_blocks if b.get("source_chunk_id")}
        result = []
        import re
        parts = re.split(r'\{\{(IMAGE|TABLE):([^}]+)\}\}', llm_text)
        i = 0
        while i < len(parts):
            text = parts[i].strip()
            if text:
                result.append({"type": "text", "content": text})
            if i + 2 < len(parts):
                block_type = parts[i + 1]
                chunk_id = parts[i + 2]
                if chunk_id in block_map:
                    result.append(block_map[chunk_id])
                i += 3
            else:
                i += 1
        # 未被引用的 blocks 追加到末尾
        used_ids = {b.get("source_chunk_id") for b in result if isinstance(b, dict)}
        for b in non_text_blocks:
            if b.get("source_chunk_id") not in used_ids:
                result.append(b)
        return result
    
    return [text_block] + non_text_blocks
```

---

## 四、流式输出协议

### 4.1 设计约束

- 文本可以逐 token 流式推送（用户体验好）
- 图片/表格**不能流式**（要么有要么没有）
- 前端需要知道"流式还没结束"还是"全部完成"

### 4.2 SSE 帧格式

```
# 1. 文本流（逐 token）
data: {"type": "delta", "content": "请"}
data: {"type": "delta", "content": "按"}
data: {"type": "delta", "content": "以下步骤"}

# 2. 非文本块（完成时一次性推送，可选：也可在流式过程中推送）
data: {"type": "block", "block": {"type": "image", "url": "...", "caption": "..."}}
data: {"type": "block", "block": {"type": "table", "format": "markdown", "content": "..."}}

# 3. 完成帧（包含完整回答）
data: {"type": "done", "answer": [...全部 blocks...], "sources": [...], "confidence": 0.85}

# 4. 错误帧
data: {"type": "error", "message": "服务暂时不可用"}
```

### 4.3 两种推送时序

```
时序 A：先流文本，最后一起给 blocks（简单）
  delta → delta → delta → done(含所有blocks)
  前端：流式渲染文本，done 时追加图片/表格

时序 B：文本和 blocks 交错推送（体验好）
  delta → delta → block(image) → delta → block(table) → done
  前端：按收到的顺序即时渲染
```

**推荐时序 A**，原因：
- 实现简单：LLM 流式完成后，从 chunks 构建 blocks 追加到 done 帧
- 前端逻辑简单：流式阶段只处理文本，done 时处理全量
- 时序 B 需要 LLM 生成过程中实时决定"在这里插入图片"，复杂度高

### 4.4 前端消费示例

```javascript
const eventSource = new EventSource('/api/chat/stream');
let textContent = '';
let blocks = [];

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);
  
  switch (data.type) {
    case 'delta':
      textContent += data.content;
      renderTextStreaming(textContent);
      break;
      
    case 'block':
      // 时序 B：即时渲染非文本块
      renderBlock(data.block);
      break;
      
    case 'done':
      blocks = data.answer;
      renderFinalAnswer(blocks);  // 用完整 blocks 替换流式文本
      renderSources(data.sources);
      eventSource.close();
      break;
      
    case 'error':
      showError(data.message);
      eventSource.close();
      break;
  }
};

function renderFinalAnswer(blocks) {
  const container = document.getElementById('answer');
  container.innerHTML = '';
  
  for (const block of blocks) {
    switch (block.type) {
      case 'text':
        container.appendChild(createMarkdownElement(block.content));
        break;
      case 'image':
        container.appendChild(createImageElement(block.url, block.caption));
        break;
      case 'table':
        container.appendChild(createTableElement(block.content, block.format));
        break;
      case 'code':
        container.appendChild(createCodeElement(block.content, block.language));
        break;
    }
  }
}
```

---

## 五、图片文件服务

### 5.1 生命周期

```
文档上传
  → Parser 解析，提取图片 blob
    → 写入持久目录 data/images/{doc_id}/{hash}.{ext}
      → chunk metadata 存储相对路径 "doc_id/hash.jpg"
        → 检索时 Block Builder 拼接完整 URL "/static/images/doc_id/hash.jpg"
          → Web 服务器直出静态文件

文档删除
  → 删除 data/images/{doc_id}/ 整个目录
    → 无孤立文件
```

### 5.2 三阶段演进

| | Phase 1 开发 | Phase 2 单机生产 | Phase 3 分布式 |
|---|---|---|---|
| 存储 | 本地目录 `data/images/` | + SHA-256 内容去重 | 对象存储（S3/MinIO/OSS） |
| 访问 | Web 框架静态文件中间件 | + 缓存头 `Cache-Control: max-age=86400` | CDN + 签名 URL |
| 鉴权 | 无（路径含 doc_id 不可猜测） | 同左 | 签名 URL 有效期 |
| 清理 | `rm -rf data/images/{doc_id}/` | + DB Image 表级联删除 | 同左 |

### 5.3 接口抽象

```python
from abc import ABC, abstractmethod

class ImageStore(ABC):
    @abstractmethod
    def save(self, blob: bytes, doc_id: str, filename: str) -> str:
        """保存图片，返回相对路径（不含 URL 前缀）。"""
        ...

    @abstractmethod
    def delete_doc(self, doc_id: str) -> int:
        """删除文档关联的所有图片，返回删除数量。"""
        ...

    @abstractmethod
    def get_url(self, relative_path: str) -> str:
        """相对路径 → 完整可访问 URL。"""
        ...


class LocalImageStore(ImageStore):
    """Phase 1/2：本地文件系统存储。"""
    
    def __init__(self, base_dir: str = "data/images", url_prefix: str = "/static/images"):
        self.base_dir = Path(base_dir)
        self.url_prefix = url_prefix
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, blob: bytes, doc_id: str, filename: str) -> str:
        doc_dir = self.base_dir / doc_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        path = doc_dir / filename
        path.write_bytes(blob)
        return f"{doc_id}/{filename}"

    def delete_doc(self, doc_id: str) -> int:
        doc_dir = self.base_dir / doc_id
        if not doc_dir.exists():
            return 0
        import shutil
        count = len(list(doc_dir.iterdir()))
        shutil.rmtree(doc_dir)
        return count

    def get_url(self, relative_path: str) -> str:
        return f"{self.url_prefix}/{relative_path}"


class S3ImageStore(ImageStore):
    """Phase 3：对象存储。"""
    
    def __init__(self, bucket: str, prefix: str = "images/", sign_expiry: int = 3600):
        self.bucket = bucket
        self.prefix = prefix
        self.sign_expiry = sign_expiry
        # self.client = boto3.client("s3") / minio.Minio(...)

    def save(self, blob: bytes, doc_id: str, filename: str) -> str:
        key = f"{self.prefix}{doc_id}/{filename}"
        # self.client.put_object(Bucket=self.bucket, Key=key, Body=blob)
        return f"{doc_id}/{filename}"

    def delete_doc(self, doc_id: str) -> int:
        # list_objects + delete_objects
        ...

    def get_url(self, relative_path: str) -> str:
        key = f"{self.prefix}{relative_path}"
        # return self.client.generate_presigned_url('get_object', Params={...}, ExpiresIn=self.sign_expiry)
        ...
```

---

## 六、数据库存储

### 6.1 answer 字段

答案从 `string` 改为 `JSON string`（存储 blocks 数组）：

```sql
-- 不需要改 schema，Text 列存 JSON 字符串即可
-- 写入
INSERT INTO messages (answer) VALUES ('[{"type":"text","content":"..."},{"type":"image","url":"..."}]');

-- 读取时判断格式
```

```python
# 向后兼容：旧数据是纯字符串，新数据是 JSON
def parse_answer(raw: str) -> list[dict]:
    if raw.startswith("["):
        return json.loads(raw)
    return [{"type": "text", "content": raw}]
```

### 6.2 独立 Image 表（Phase 2）

```sql
CREATE TABLE images (
    id          TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    file_hash   TEXT NOT NULL,          -- SHA-256 内容去重
    file_path   TEXT NOT NULL,          -- 相对路径
    file_size   INTEGER,
    mime_type   TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(file_hash)                   -- 相同内容只存一份
);
```

---

## 七、完整数据流

```
用户: "蓝牙怎么连？"
  │
  ▼
Retriever → 5 chunks:
  [0] text   "步骤3：打开电源，长按配对键..."
  [1] image  "[图片] 前面板按钮位置"  metadata.image_path="doc-001/panel.jpg"
  [2] text   "手机蓝牙设置中搜索 BLV-D1..."
  [3] table  "[表格] 指示灯含义"
  [4] text   "配对成功后白色指示灯常亮"
  │
  ▼
Reranker → top 3: [0, 1, 3]
  │
  ├──→ LLM Generator (输入: chunks[0,1,3] 的文本)
  │      输出: "请按以下步骤连接蓝牙：\n1. 打开电源开关\n2. 长按配对键 3 秒..."
  │
  ├──→ Block Builder (输入: chunks[0,1,3])
  │      输出: [ImageBlock(panel.jpg), TableBlock(指示灯)]
  │
  ▼
Block Assembler (strategy=text_first):
  [
    {"type": "text",  "content": "请按以下步骤连接蓝牙：\n1. 打开电源..."},
    {"type": "image", "url": "/static/images/doc-001/panel.jpg", "caption": "前面板按钮位置"},
    {"type": "table", "format": "markdown", "content": "| 指示灯 | 含义 |...", "caption": "指示灯说明"}
  ]
  │
  ▼
SSE 推送:
  data: {"type":"delta","content":"请按以下步骤"}
  data: {"type":"delta","content":"连接蓝牙：\n1."}
  ...
  data: {"type":"done","answer":[...3 blocks...],"sources":[...],"confidence":0.85}
```

---

## 八、扩展点

### 8.1 新增 Block 类型

只需三步：
1. 定义新的 Block schema（如 `VideoBlock`）
2. 在 Block Builder 中添加 `elif content_type == "video":` 分支
3. 前端 `renderBlock()` 添加 `case 'video':` 分支

不需要改协议、改数据库、改 SSE 格式。

### 8.2 LLM 感知多模态

当前方案中 LLM **不感知**图片/表格的存在，只根据 chunks 文本内容生成回答。进阶方案：

```
Level 0（当前）: LLM 只看文本，非文本块后处理追加
Level 1: LLM prompt 中注明"检索到了 1 张图片和 1 个表格"，让它在回答中引用
Level 2: LLM 输出 {{IMAGE:chunk-id}} 标记，后处理替换（策略 C）
Level 3: 多模态 LLM 直接看图片，生成描述性回答
```

每级增加复杂度，按需选择。

### 8.3 前端渲染适配

协议不规定渲染方式，前端可以灵活选择：

| 渲染模式 | 适用场景 |
|----------|----------|
| 内嵌模式 | 文本中间插入图片/表格（文章风格） |
| 附件模式 | 文本在上，图片/表格在下方卡片区（客服风格） |
| 侧边栏模式 | 文本在左，图片/表格在右侧面板（知识库风格） |
| Markdown 降级 | 不支持 blocks 的终端，拼接为 `text + ![](url) + table` |

降级输出（给不支持 blocks 的消费者）：

```python
def blocks_to_markdown(blocks: list[dict]) -> str:
    """ContentBlocks → 纯 Markdown 降级输出。"""
    parts = []
    for block in blocks:
        if block["type"] == "text":
            parts.append(block["content"])
        elif block["type"] == "image":
            parts.append(f"![{block.get('caption', '')}]({block['url']})")
        elif block["type"] == "table":
            parts.append(block["content"])
        elif block["type"] == "code":
            lang = block.get("language", "")
            parts.append(f"```{lang}\n{block['content']}\n```")
        elif block["type"] == "formula":
            parts.append(f"$${block['content']}$$")
    return "\n\n".join(parts)


def blocks_to_plain_text(blocks: list[dict]) -> str:
    """ContentBlocks → 纯文本（无格式）。"""
    return "\n\n".join(
        block["content"] for block in blocks
        if block["type"] in ("text", "table", "code")
    )
```

---

## 九、参考实现对比

| 系统 | 输出格式 | 图片处理 | 流式 |
|------|----------|----------|------|
| **本方案** | `list[ContentBlock]` | URL（静态文件/对象存储） | delta + done(blocks) |
| RAGFlow | `content_blocks` 数组 | MinIO URL | 支持 |
| Dify | Markdown string `![](url)` | 内嵌 Markdown | 支持 |
| LangChain | `AIMessage.content: list[str\|dict]` | base64 或 URL | 支持 |
| Intercom | 回答 + "相关文章"卡片 | 缩略图 URL | 不支持 |
| ChatGPT | Markdown + 沙盒渲染 | 内嵌 `sandbox:/path` | 支持 |

---

## 十、快速接入检查清单

```
□ 定义 ContentBlock 类型（至少 text + image + table）
□ 解析层：chunks 的 metadata 包含 content_type 和 image_path
□ 存储层：图片持久化到可访问的存储（本地目录 / 对象存储）
□ 检索层：metadata 随 chunk 传递到 Generator
□ Generator：LLM 文本 + Block Builder 非文本 → Block Assembler 合并
□ API：answer 字段从 string 改为 list[ContentBlock]
□ SSE：done 帧包含完整 blocks 数组
□ DB：answer 列存 JSON，读取时兼容旧格式
□ 前端：按 block.type 分发渲染
□ 降级：提供 blocks_to_markdown() 给不支持的消费者
```
