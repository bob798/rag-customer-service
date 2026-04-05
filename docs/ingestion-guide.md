# 知识库构建指南

## 一、整体流程

```
原始文档（.txt / .pdf / .docx）
      │
      ▼
  ParserRegistry               ← 根据文件类型选择解析器
  ├── FAQParser                ← Q/A 格式 → 每对问答一个 chunk
  └── DefaultParser            ← 普通文档 → SemanticChunker 分段
      └── SemanticChunker      ← 按段落合并，加滑动窗口 overlap
      │
      ▼
  chunks: list[dict]           ← {chunk_id, doc_id, content, metadata}
      │
      ├──▶ ChromaVectorStore   ← 持久化：向量检索（GteQwen2 embedding）
      └──▶ Bm25Store           ← 内存：关键词检索（jieba + BM25Okapi）
```

---

## 二、使用脚本导入文档

### 2.1 快速上手

```bash
# 激活虚拟环境
source .venv/bin/activate

# 先预览解析结果（不写入数据库）
python scripts/ingest.py docs/samples/faq_example.txt --dry-run

# 输出示例：
# 发现 1 个文件
# faq_example.txt  →  6 chunks  (parser: FAQParser)
#   [0] Q: 怎么申请退款？ A: 在订单详情页点击"申请退款"...
#   [1] Q: 发货需要多久？ A: 付款成功后通常 1-2 个工作日...
```

```bash
# 正式导入（需要下载 GteQwen2 embedding 模型，首次约 3GB）
python scripts/ingest.py docs/samples/faq_example.txt
```

### 2.2 批量导入目录

```bash
# 导入整个目录（递归扫描 .txt / .pdf / .docx）
python scripts/ingest.py data/docs/

# 指定 ChromaDB 路径和集合名（默认是 ./data/chroma 和 knowledge）
python scripts/ingest.py data/docs/ --chroma-path ./data/chroma --collection my_kb
```

---

## 三、文档格式说明

### FAQ 格式（推荐，自动识别）

每个问答对变成一个 chunk，检索精度最高：

```
Q: 怎么申请退款？
A: 在订单详情页点击"申请退款"，填写退款原因后提交。审核通过后 3-5 个工作日原路退回。

Q: 发货需要多久？
A: 付款成功后通常 1-2 个工作日内发货。节假日期间可能延迟，以短信通知为准。
```

支持中文格式：

```
问：怎么申请退款？
答：在订单详情页点击申请退款...

问：发货需要多久？
答：通常 1-2 个工作日...
```

**FAQParser 触发条件**（任一满足）：
- 文件扩展名是 `faq`
- 扩展名是 `txt` 且文件名/内容含 `faq`
- 扩展名是 `txt` 且内容含 `问：` 或 `Q:` 格式

### 普通文档（PDF / DOCX / TXT）

使用 `SemanticChunker` 按段落拆分：

- 按 `\n\n` 分段
- 合并短段落，直到接近 `chunk_size=512` token
- 相邻 chunk 加 `overlap=100` token 滑动窗口（避免语义截断）

**适合**：产品手册、政策文件、帮助中心文章等长文本。

---

## 四、在代码中直接调用

### 4.1 解析 FAQ 文件

```python
from core.knowledge.parsers.faq import FAQParser
import uuid

parser = FAQParser()
doc_id = str(uuid.uuid4())

chunks = parser.parse(
    file_path="data/faq.txt",
    doc_id=doc_id,
    metadata={"source_title": "客服 FAQ"}
)

# chunks: [
#   {
#     "chunk_id": "uuid...",
#     "doc_id": "uuid...",
#     "content": "Q: 怎么退款？\nA: 在订单页面...",
#     "metadata": {"source_title": "客服 FAQ", "type": "faq", "question": "怎么退款？"}
#   },
#   ...
# ]
```

### 4.2 解析普通文档

```python
from core.knowledge.parsers.default import DefaultParser
from core.knowledge.chunker import SemanticChunker
import uuid

parser = DefaultParser(chunker=SemanticChunker(chunk_size=512, overlap=100))
doc_id = str(uuid.uuid4())

# 支持 .pdf / .docx / .txt
chunks = parser.parse(
    file_path="data/manual.pdf",
    doc_id=doc_id,
    metadata={"source_title": "产品手册 v2.0"}
)
```

### 4.3 写入知识库

```python
import asyncio
from core.knowledge.embedder import GteQwen2Embedder
from core.knowledge.vector_store import ChromaVectorStore
from core.knowledge.bm25_store import Bm25Store

async def build_kb(chunks: list[dict]):
    embedder = GteQwen2Embedder()
    vector_store = ChromaVectorStore(
        embedder=embedder,
        collection_name="knowledge",
        persist_directory="./data/chroma",
    )
    bm25_store = Bm25Store()

    # 写入向量数据库（持久化）
    await vector_store.add(chunks)

    # 写入 BM25 内存索引
    bm25_store.add(chunks)

    print(f"已导入 {len(chunks)} 个 chunk")

asyncio.run(build_kb(chunks))
```

### 4.4 使用 ParserRegistry（自动选择解析器）

```python
from core.knowledge.parsers.registry import ParserRegistry
from core.knowledge.parsers.faq import FAQParser
from core.knowledge.parsers.default import DefaultParser
from core.knowledge.chunker import SemanticChunker

registry = ParserRegistry()
registry.register(FAQParser())          # FAQ 优先
registry.register(DefaultParser(chunker=SemanticChunker()))  # 兜底

# 自动根据扩展名和内容选择解析器
parser = registry.get_parser(file_type="txt", content_hint=open("data/faq.txt").read()[:200])
chunks = parser.parse("data/faq.txt", doc_id=..., metadata={...})
```

---

## 五、chunk 数据结构

```python
{
    "chunk_id": "550e8400-e29b-41d4-a716-446655440000",  # UUID，全局唯一
    "doc_id":   "7c9e6679-7425-40de-944b-e07fc1f90ae7",  # 文档 ID，一个文件一个
    "content":  "Q: 怎么申请退款？\nA: 在订单详情页...",   # 送入 LLM 的文本
    "metadata": {
        "source_title": "客服FAQ.txt",      # 用于 sources 展示给用户
        "source_path":  "data/faq.txt",    # 原始文件路径（可选）
        "file_type":    "txt",             # 文件类型
        "chunk_index":  0,                 # 在文档中的位置（DefaultParser）
        "type":         "faq",             # FAQ 类型标记（FAQParser 专有）
        "question":     "怎么申请退款？"   # 原始问题（FAQParser 专有）
    }
}
```

---

## 六、BM25 重启后恢复

BM25Store 是**纯内存**索引，服务重启后数据丢失。需在启动时从 ChromaDB 重建：

```python
# api/main.py（Week 2 实现时加入启动逻辑）
from core.knowledge.bm25_store import Bm25Store
from core.knowledge.vector_store import ChromaVectorStore

async def startup():
    # 从 ChromaDB 拉取所有 chunks，重建 BM25 索引
    all_chunks = await vector_store.get_all()   # TODO: Week 2 实现此方法
    bm25_store.rebuild_from_chunks(all_chunks)
    print(f"BM25 索引重建完成：{bm25_store.count()} 个 chunk")
```

---

## 七、注意事项

| 场景 | 说明 |
|------|------|
| **中文文本** | SemanticChunker 用空格分词估算 token 数，中文会低估。实际 chunk 内容不会被截断，只影响合并策略。 |
| **embedding 模型** | GteQwen2Embedder 首次使用会下载约 3GB 模型文件（`~/.cache/huggingface/`）。下载后本地缓存，无需联网。 |
| **向量维度** | GteQwen2 输出 1536 维向量，ChromaDB 集合创建时自动确定，不可更改。切换 embedding 模型需重建集合。 |
| **重复导入** | ChromaDB 用 chunk_id 去重。重复调用 `add()` 同 chunk_id 会报错，需先 `delete_by_doc_id()` 再重新导入。 |
