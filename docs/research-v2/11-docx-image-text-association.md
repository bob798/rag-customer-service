# 11 - DOCX 图文关联：RAG 回答中嵌入文档原图

> 日期：2026-04-20 | 定位：通用技术方案设计
> 前置文档：[02-docx-parsing-research.md](./02-docx-parsing-research.md)

## 1. 问题定义

Word 文档中包含图片（产品图、步骤示意图、接口标注图等），用户提问时，RAG 系统的回答需要**把相关图片嵌入到文本中展示**，保持图文的位置关系。

**核心问题**：如何在 DOCX 解析 → 分块 → 检索 → 回答的全链路中，保持图片与上下文文本的关联，使回答能在正确位置展示原图？

### 1.1 示例场景

用户问："怎么连接电源？"

期望的回答：

```
步骤1：连接电源适配器到设备背面的 DC12V 接口。

[产品背面接口示意图]        ← 原文档中的图片

步骤2：将音箱线连接到 SPK L/R 端口。
```

而不是纯文字描述或丢失图片。

### 1.2 挑战

| 挑战 | 说明 |
|------|------|
| 图文位置保持 | DOCX 中图片有 inline（嵌入式）和 floating（浮动式）两种，解析时需保持原始顺序 |
| 分块不破坏关联 | chunker 切分文本时，图片标记需要跟随上下文，不能被切到独立 chunk |
| 检索能命中 | 图片本身没有文字，需依靠周围文本被检索命中后"顺带"带出图片 |
| 图片持久化与访问 | 图片需要从 DOCX 提取并存储，回答时通过 URL 访问 |

## 2. 方案设计

### 2.1 核心思路

图片不单独成 chunk。解析时把图片持久化到磁盘，在文本流中**原位插入 Markdown 图片标记** `![caption](url)`，chunker 把它当普通文本行处理。

```
DOCX body 遍历（按文档顺序）
  ├── 段落文本 → 直接提取
  ├── 图片     → 存文件 + 在原位插入 ![caption](url)
  └── 表格     → 渲染 Markdown
       ↓
  统一文本流 → chunker 分块 → chunks（图片标记自然跟随上下文）
       ↓
  检索命中 → 回答中渲染 Markdown → 用户看到图文混排
```

### 2.2 为什么图片不单独 chunk

| 方案 | 图片单独 chunk | 图片内联到文本 chunk |
|------|---------------|---------------------|
| chunk 数量 | 图片多则 chunk 膨胀 | 不增加 |
| 图文关联 | 需额外逻辑拼接上下文 | 天然保持（在同一个 chunk 内） |
| 检索 | 图片 chunk 无文字，难以被检索命中 | 图片随上下文一起命中 |
| 复杂度 | 需处理 image chunk 类型 | 统一为 text chunk |

### 2.3 Chunk 内容示例

```markdown
步骤1：连接电源适配器到设备背面的 DC12V 接口。

![连接示意图](/static/images/doc-001/img-001.png)

步骤2：将音箱线连接到 SPK L/R 端口，注意左右声道。
```

- 用户搜索"连接电源"→ 命中此 chunk → 回答自动包含图片
- 图文位置由 DOCX 原始文档顺序决定，无需人工干预

## 3. 技术实现要点

### 3.1 DOCX 图片提取

DOCX（OOXML 格式）中图片存储在 `word/media/` 目录下，通过 XML 关系引用。两种图片类型：

| 类型 | XML 标签 | 说明 |
|------|----------|------|
| Inline（嵌入式） | `<wp:inline>` | 在段落文本流中，位置确定 |
| Floating（浮动式） | `<wp:anchor>` | 锚定在段落，有坐标偏移 |

两种类型在 XML 层面都在 `<w:p>`（段落）内，通过 XPath 查找 `pic:pic` 元素即可统一提取。python-docx 的 `doc._element.body` 遍历能保持文档阅读顺序（RAGFlow 已验证此模式可行）。

### 3.2 解析流程

```python
# 伪代码
for paragraph in doc.body:
    text = paragraph.text
    images = extract_images(paragraph)  # XPath 提取 blob + alt_text

    image_marks = []
    for blob, alt_text in images:
        url = save_image(blob, doc_id)   # 哈希去重 + 写磁盘
        image_marks.append(f"![{alt_text or '图片'}]({url})")

    # 段落文本 + 图片标记合并为一个元素，保持原始顺序
    content = "\n\n".join([text] + image_marks)
    elements.append({"type": "text", "content": content})
```

### 3.3 图片持久化

```python
# 伪代码
def save_image(blob: bytes, doc_id: str) -> str:
    content_hash = md5(blob)[:12]        # 内容哈希，避免重复存储
    ext = detect_format(blob)            # PNG 签名 / JPEG 签名
    path = f"images/{doc_id}/{content_hash}.{ext}"
    write_if_not_exists(path, blob)
    return f"/static/{path}"
```

### 3.4 图片存储演进路线

| 阶段 | 存储方案 | 访问方式 | 适用场景 |
|------|---------|----------|---------|
| **P0** | 本地文件系统 `static/images/{doc_id}/` | Web 框架静态文件挂载 | 开发 / 单机部署 |
| P1 | MinIO / S3 对象存储 | 预签名 URL | 生产多实例 |
| P2 | CDN 分发 | 公开 URL + 缓存 | 大规模访问 |

## 4. 输出层渲染

前端渲染 chunk 内容时，识别 Markdown 图片语法 `![caption](url)` 并渲染为图片。

| 方式 | 说明 | 适用场景 |
|------|------|---------|
| **Markdown 渲染器直出** | 前端用 markdown-it / react-markdown 渲染，`![](url)` 自动变 `<img>` | 已有 Markdown 渲染的项目 |
| **ContentBlock 组装** | API 层解析 chunk 内容，拆分为 TextBlock + ImageBlock 数组 | 需要结构化输出的场景 |

两种方式不冲突：P0 用 Markdown 直出，P1 按需升级为 ContentBlock。

## 5. 业界参考

| 项目 | 图片处理方式 | 与本方案的关系 |
|------|-------------|---------------|
| **RAGFlow** | 图片发给 Vision LLM 生成描述文本 | body 遍历保序的模式被本方案采用；图片处理方式不同（LLM 描述 vs 原图展示） |
| **MinerU** | 提取图片 blob + base64 编码，不做 OCR | 图片提取方式类似，但 MinerU 不解决"回答中展示图片"的问题 |
| **Dify** | 知识库支持图片存储，回答中可引用 | 类似思路，但 Dify 是平台级方案 |

## 6. 测试策略

| 测试类型 | 验证目标 |
|---------|---------|
| 图片持久化 | blob 写入正确、内容哈希去重、格式检测（PNG/JPEG） |
| 图文位置保序 | chunk 内 `![](...)` 标记在文档原始位置 |
| 图片提取失败降级 | blob 提取异常时跳过图片，不影响文本解析 |
| 端到端检索 | 包含图片标记的 chunk 能被上下文文本检索命中 |

## 7. 收益

| 维度 | 效果 |
|------|------|
| **用户体验** | 回答中直接看到产品图片、步骤示意图，比纯文字描述更直观 |
| **图文关联** | 图片在 chunk 内与上下文文本绑定，检索命中即带出图片 |
| **架构简化** | 图片不产生独立 chunk，统一为 text chunk，下游无需处理多种类型 |
| **部署轻量** | 无需 OCR 引擎和深度学习框架依赖 |

## 8. 决策记录

| 被否决的方案 | 原因 |
|-------------|------|
| 图片单独 chunk + metadata 关联 | 增加 chunk 数量，图片 chunk 无文字难以检索命中，需额外关联逻辑 |
| 图片 base64 内联到 chunk | chunk 体积膨胀，向量化时 base64 字符串是噪音 |
| 图片 OCR 后丢弃原图 | 丢失视觉信息，OCR 有误差，用户体验差 |
| Vision LLM 生成图片描述 | 依赖 LLM API，增加成本和延迟，且描述替代不了原图展示 |

## 9. 适用边界

| 适用 | 不适用 |
|------|--------|
| 图片用于展示（产品图、示意图、步骤截图） | 图片中包含关键文字且无其他文本覆盖 |
| 文档以文本/表格为主，图片为辅 | 扫描件文档（图片是唯一内容载体） |
| 上下文文本足以命中检索 | 图片内文字是唯一的检索关键词来源 |

当图片中文字是唯一检索入口时，需补充 OCR 能力。可按文档类型路由：结构化 DOCX 走内联方案，扫描件走 OCR 方案。
