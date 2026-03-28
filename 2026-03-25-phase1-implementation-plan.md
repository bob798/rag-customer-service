# AI 客服系统 Phase 1 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建企业级独立 AI 客服系统，支持 RAG 全链路问答、文档知识库管理、嵌入式 Widget，单租户，API First。

**Architecture:** FastAPI 后端 + ChromaDB 向量库 + gte-Qwen2-1.5B Embedding + BM25 混合检索，RAG 链路手搓（意图识别→Query改写→混合检索→Reranking→置信度评分→LLM生成）。两级安全模型（Admin API Key vs Widget Token），SSE 流式输出，Docker Compose 一键部署。

**Tech Stack:** Python 3.11, FastAPI, ChromaDB, gte-Qwen2-1.5B, BGE-Reranker, rank_bm25, LiteLLM, SQLite→PostgreSQL, PyMuPDF, python-docx, Docker Compose

**Spec:** `/Users/bob/workspace/pis/项目作品/ai-customer-service/2026-03-25-phase1-design.md`

**Project root:** `~/workspace/ai-customer-service/`（新建独立仓库）

---

## 文件结构

```
ai-customer-service/
├── core/
│   ├── interfaces/               # 所有抽象接口（Ports & Adapters 的 Port 层）
│   │   ├── parser.py             # BaseParser
│   │   ├── chunker.py            # BaseChunker
│   │   ├── embedder.py           # BaseEmbedder
│   │   ├── retriever.py          # BaseRetriever
│   │   ├── reranker.py           # BaseReranker
│   │   ├── confidence.py         # BaseConfidenceEvaluator
│   │   ├── fallback_handler.py   # BaseFallbackHandler
│   │   └── tracer.py             # BaseTracer
│   ├── llm/
│   │   └── factory.py            # LiteLLM 多模型工厂
│   ├── knowledge/
│   │   ├── parsers/
│   │   │   ├── registry.py       # ParserRegistry（Strategy + Plugin）
│   │   │   ├── default.py        # DefaultParser（段落边界文本提取）
│   │   │   └── faq.py            # FAQParser（Q&A对原子分块）
│   │   ├── chunker.py            # SemanticChunker（段落+overlap，默认）
│   │   ├── embedder.py           # Embedder（gte-Qwen2-1.5B）
│   │   ├── vector_store.py       # ChromaDB 接口
│   │   └── bm25_store.py         # rank_bm25 索引
│   └── rag/
│       ├── intent.py              # 意图识别（范围内/外/模糊）
│       ├── query_rewriter.py      # Query 改写
│       ├── retriever.py           # HybridRetriever（向量+BM25+RRF）
│       ├── reranker.py            # BGEReranker + NoopReranker（测试用）
│       ├── confidence.py          # SignalFusionEvaluator（三路信号）
│       ├── tracer.py              # StructuredLogTracer（默认，零依赖）
│       ├── fallback_handler.py    # TellUserHandler（默认兜底）
│       ├── generator.py           # LLM 生成 + 来源引用
│       └── pipeline.py            # RAG 管道编排（注入所有组件）
├── api/
│   ├── main.py                    # FastAPI app + 中间件
│   ├── dependencies.py            # Auth（Admin Key / Widget Token）+ 限速
│   └── routes/
│       ├── chat.py                # POST /chat（SSE 流式）
│       ├── knowledge.py           # 知识库 CRUD
│       ├── sessions.py            # 会话历史
│       ├── config.py              # 系统配置
│       └── health.py              # GET /health
├── db/
│   ├── models.py                  # SQLAlchemy：Document, Chunk, Session, Message, Config
│   └── session.py                 # DB 连接管理
├── widget/
│   ├── widget.js                  # 嵌入式聊天气泡
│   └── widget.css
├── tests/
│   ├── conftest.py                # fixtures: test DB, mock LLM
│   ├── core/
│   │   ├── test_document_processor.py
│   │   ├── test_chunker.py
│   │   ├── test_retriever.py
│   │   ├── test_pipeline.py
│   │   ├── test_confidence.py
│   │   └── test_tracer.py
│   └── api/
│       ├── test_chat.py
│       ├── test_knowledge.py
│       └── test_health.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

---

## Week 1：RAG 核心链路

### Task 1: 项目初始化

**Files:**
- Create: `requirements.txt`
- Create: `.env.example`
- Create: `core/__init__.py`, `api/__init__.py`, `db/__init__.py`

- [ ] 新建目录结构
```bash
mkdir -p ~/workspace/ai-customer-service
cd ~/workspace/ai-customer-service
mkdir -p core/interfaces core/llm core/knowledge/parsers core/rag api/routes db widget tests/core tests/api
touch core/__init__.py core/interfaces/__init__.py
touch core/llm/__init__.py core/knowledge/__init__.py core/knowledge/parsers/__init__.py core/rag/__init__.py
touch api/__init__.py api/routes/__init__.py db/__init__.py tests/__init__.py tests/core/__init__.py tests/api/__init__.py
git init && git add . && git commit -m "chore: init project structure"
```

- [ ] 写 `requirements.txt`
```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.36
aiosqlite==0.20.0
litellm==1.50.0
sentence-transformers==3.3.0
FlagEmbedding==1.3.0
rank_bm25==0.2.2
jieba==0.42.1
chromadb==0.5.20
PyMuPDF==1.24.0
python-docx==1.1.2
python-multipart==0.0.12
pydantic-settings==2.6.0
pytest==8.3.0
pytest-asyncio==0.24.0
httpx==0.27.0
```

- [ ] 写 `.env.example`
```bash
# LLM
ANTHROPIC_API_KEY=sk-ant-xxx
DEEPSEEK_API_KEY=sk-xxx
DEFAULT_MODEL=claude-3-5-sonnet-20241022

# Auth
ADMIN_API_KEY=your-admin-key-here
WIDGET_TOKEN_SECRET=your-secret-here

# DB
DATABASE_URL=sqlite+aiosqlite:///./data/cs.db

# Embedding（本地模型路径或 HF model id）
EMBEDDING_MODEL=Alibaba-NLP/gte-Qwen2-1.5B-instruct
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
```

- [ ] `git commit -m "chore: add requirements and env template"`

---

### Task 2: LLM 工厂

**Files:**
- Create: `core/llm/factory.py`
- Create: `tests/core/test_factory.py`

- [ ] 写失败测试 `tests/core/test_factory.py`
```python
import pytest
from unittest.mock import patch, AsyncMock
from core.llm.factory import LLMFactory

@pytest.mark.asyncio
async def test_factory_returns_response():
    factory = LLMFactory(model="deepseek/deepseek-chat")
    with patch("litellm.acompletion", new_callable=AsyncMock) as mock:
        mock.return_value.choices = [type("C", (), {"message": type("M", (), {"content": "hello"})()})()]
        result = await factory.complete([{"role": "user", "content": "hi"}])
    assert result == "hello"

@pytest.mark.asyncio
async def test_factory_fallback_on_error():
    factory = LLMFactory(model="claude-3-5-sonnet-20241022", fallback="deepseek/deepseek-chat")
    with patch("litellm.acompletion", side_effect=[Exception("API error"), AsyncMock(
        return_value=type("R", (), {"choices": [type("C", (), {"message": type("M", (), {"content": "fallback"})()})()]})()
    ]):
        result = await factory.complete([{"role": "user", "content": "hi"}])
    assert result == "fallback"
```

- [ ] 运行确认失败: `pytest tests/core/test_factory.py -v`

- [ ] 实现 `core/llm/factory.py`
```python
import litellm
from typing import Optional

class LLMFactory:
    def __init__(self, model: str, fallback: Optional[str] = None):
        self.model = model
        self.fallback = fallback

    async def complete(self, messages: list[dict], stream: bool = False, **kwargs) -> str:
        try:
            response = await litellm.acompletion(
                model=self.model, messages=messages, stream=stream, **kwargs
            )
            if stream:
                return response  # caller handles stream
            return response.choices[0].message.content
        except Exception as e:
            if self.fallback:
                response = await litellm.acompletion(
                    model=self.fallback, messages=messages, stream=stream, **kwargs
                )
                if stream:
                    return response
                return response.choices[0].message.content
            raise

    async def complete_stream(self, messages: list[dict], **kwargs):
        """返回 AsyncGenerator，调用方 async for chunk in stream"""
        return await litellm.acompletion(
            model=self.model, messages=messages, stream=True, **kwargs
        )
```

- [ ] 运行确认通过: `pytest tests/core/test_factory.py -v`
- [ ] `git commit -m "feat: add LLM factory with fallback support"`

---

### Task 2.5: 核心抽象接口层（Ports & Adapters）

**Files:**
- Create: `core/interfaces/parser.py`
- Create: `core/interfaces/chunker.py`
- Create: `core/interfaces/embedder.py`
- Create: `core/interfaces/retriever.py`
- Create: `core/interfaces/reranker.py`
- Create: `core/interfaces/confidence.py`
- Create: `core/interfaces/fallback_handler.py`
- Create: `core/interfaces/tracer.py`

> 所有接口在此集中定义，具体实现依赖这些接口，不反向依赖。

- [ ] 实现 `core/interfaces/parser.py`
```python
from abc import ABC, abstractmethod

class BaseParser(ABC):
    @abstractmethod
    def can_handle(self, file_type: str, content_hint: str = "") -> bool: ...

    @abstractmethod
    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        """返回: [{"chunk_id", "doc_id", "content", "metadata"}]"""
        ...
```

- [ ] 实现 `core/interfaces/chunker.py`
```python
from abc import ABC, abstractmethod

class BaseChunker(ABC):
    @abstractmethod
    def chunk(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        """将文本切分为 chunks，返回: [{"chunk_id", "doc_id", "content", "metadata"}]"""
        ...
```

- [ ] 实现 `core/interfaces/embedder.py`
```python
from abc import ABC, abstractmethod

class BaseEmbedder(ABC):
    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """返回归一化向量列表"""
        ...
```

- [ ] 实现 `core/interfaces/retriever.py`
```python
from abc import ABC, abstractmethod

class BaseRetriever(ABC):
    @abstractmethod
    def retrieve(self, query: str, top_k: int) -> list[dict]:
        """返回: [{"chunk_id", "content", "score", ...}]"""
        ...
```

- [ ] 实现 `core/interfaces/reranker.py`
```python
from abc import ABC, abstractmethod

class BaseReranker(ABC):
    @abstractmethod
    def rerank(self, query: str, chunks: list[dict], top_k: int) -> list[dict]:
        """返回重排后的 chunks，含 rerank_score"""
        ...
```

- [ ] 实现 `core/interfaces/confidence.py`
```python
from abc import ABC, abstractmethod

class BaseConfidenceEvaluator(ABC):
    @abstractmethod
    def evaluate(self, chunks: list[dict], query: str = "") -> tuple[float, str]:
        """返回 (confidence: float, tier: str)，tier ∈ {high, medium, low}"""
        ...
```

- [ ] 实现 `core/interfaces/fallback_handler.py`
```python
from abc import ABC, abstractmethod

class BaseFallbackHandler(ABC):
    @abstractmethod
    def handle(self, question: str, reason: str) -> dict:
        """返回兜底响应 dict，格式与 pipeline.run() 返回一致"""
        ...
```

- [ ] 实现 `core/interfaces/tracer.py`
```python
from abc import ABC, abstractmethod

class BaseTracer(ABC):
    @abstractmethod
    def start_trace(self, trace_id: str, session_id: str) -> dict: ...

    @abstractmethod
    def record_step(self, span: dict, step: str, data: dict): ...

    @abstractmethod
    def end_trace(self, span: dict, result: dict): ...
```

- [ ] `git commit -m "feat: core abstract interfaces (Ports & Adapters)"`

---

### Task 3: 文档解析 + 语义分块（Parser/Chunker 分离）

> Parser 负责"提取文本"，Chunker 负责"如何切"，两者正交组合。

**Files:**
- Create: `core/knowledge/parsers/registry.py`
- Create: `core/knowledge/parsers/default.py`
- Create: `core/knowledge/parsers/faq.py`
- Create: `core/knowledge/chunker.py`
- Create: `tests/core/test_document_processor.py`
- Create: `tests/core/test_chunker.py`

- [ ] 写失败测试 `tests/core/test_document_processor.py`
```python
import pytest
from core.knowledge.parsers.registry import ParserRegistry
from core.knowledge.chunker import SemanticChunker

def test_default_parser_extracts_txt(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("Hello world.\n\nSecond paragraph.")
    registry = ParserRegistry()
    text = registry.get_parser("txt").extract_text(str(f))
    assert "Hello" in text

def test_faq_parser_detected_by_hint():
    registry = ParserRegistry()
    parser = registry.get_parser("txt", content_hint="Q: 退款\nA: 3天")
    assert parser.__class__.__name__ == "FAQParser"

def test_chunker_splits_long_text():
    chunker = SemanticChunker(chunk_size=100, overlap=20)
    chunks = chunker.chunk("A" * 300, doc_id="d1", metadata={})
    assert len(chunks) >= 2
    assert all(k in chunks[0] for k in ["chunk_id", "doc_id", "content", "metadata"])
```

- [ ] 运行确认失败

- [ ] 实现 `core/knowledge/parsers/default.py`（文本提取，不负责分块）
```python
import fitz
import docx
from pathlib import Path
from core.interfaces.parser import BaseParser

class DefaultParser(BaseParser):
    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return True  # 兜底

    def extract_text(self, file_path: str) -> str:
        ext = Path(file_path).suffix.lower().lstrip(".")
        if ext == "pdf":
            return "\n".join(p.get_text() for p in fitz.open(file_path))
        if ext == "docx":
            return "\n".join(p.text for p in docx.Document(file_path).paragraphs)
        return Path(file_path).read_text(encoding="utf-8")

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        # parse = extract_text + chunker（由 Registry 协调）
        raise NotImplementedError("Use ParserRegistry.process_file()")
```

- [ ] 实现 `core/knowledge/parsers/faq.py`（Q&A 对作为原子分块单元）
```python
import re, uuid
from core.interfaces.parser import BaseParser

class FAQParser(BaseParser):
    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return bool(re.search(r"(Q:|问：|^##\s)", content_hint, re.MULTILINE))

    def extract_text(self, file_path: str) -> str:
        return open(file_path, encoding="utf-8").read()

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        text = self.extract_text(file_path)
        return self._extract_qa_chunks(text, doc_id, metadata)

    def _extract_qa_chunks(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        # 匹配 "Q: ...\nA: ..." 或 "问：...\n答：..." 格式
        pattern = re.compile(
            r"(?:Q:|问：)\s*(.+?)\n(?:A:|答：)\s*(.+?)(?=\n(?:Q:|问：)|\Z)",
            re.DOTALL
        )
        chunks = []
        for m in pattern.finditer(text):
            q, a = m.group(1).strip(), m.group(2).strip()
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "content": f"Q: {q}\nA: {a}",
                "metadata": {**metadata, "type": "faq", "question": q}
            })
        return chunks
```

- [ ] 实现 `core/knowledge/parsers/registry.py`
```python
from core.interfaces.parser import BaseParser
from core.knowledge.parsers.faq import FAQParser
from core.knowledge.parsers.default import DefaultParser

class ParserRegistry:
    def __init__(self):
        self._parsers: list[BaseParser] = [FAQParser(), DefaultParser()]

    def register(self, parser: BaseParser):
        """插件扩展入口：insert 在 DefaultParser 之前"""
        self._parsers.insert(-1, parser)

    def get_parser(self, file_type: str, content_hint: str = "") -> BaseParser:
        for p in self._parsers:
            if p.can_handle(file_type, content_hint):
                return p
        return DefaultParser()

    def process_file(self, file_path: str, doc_id: str, metadata: dict,
                     chunker=None) -> list[dict]:
        import os
        ext = os.path.splitext(file_path)[1].lstrip(".")
        content_hint = open(file_path, encoding="utf-8", errors="ignore").read(500)
        parser = self.get_parser(ext, content_hint)
        # FAQParser 自带分块逻辑，其他 Parser 用 Chunker
        if hasattr(parser, "_extract_qa_chunks"):
            return parser.parse(file_path, doc_id, metadata)
        text = parser.extract_text(file_path)
        if chunker:
            return chunker.chunk(text, doc_id, metadata)
        from core.knowledge.chunker import SemanticChunker
        return SemanticChunker().chunk(text, doc_id, metadata)
```

- [ ] 实现 `core/knowledge/chunker.py`
```python
import uuid
from core.interfaces.chunker import BaseChunker

class SemanticChunker(BaseChunker):
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        paragraphs = [s.strip() for s in text.replace("\n\n", "|||").split("|||") if s.strip()]
        chunks, current, current_len = [], [], 0
        for para in paragraphs:
            if current_len + len(para) > self.chunk_size and current:
                chunks.append(self._make_chunk(doc_id, " ".join(current), metadata))
                overlap_text = " ".join(current)[-self.overlap:]
                current = [overlap_text, para]
                current_len = len(overlap_text) + len(para)
            else:
                current.append(para)
                current_len += len(para)
        if current:
            chunks.append(self._make_chunk(doc_id, " ".join(current), metadata))
        return chunks

    def _make_chunk(self, doc_id: str, content: str, metadata: dict) -> dict:
        return {
            "chunk_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "content": content.strip(),
            "metadata": {**metadata, "token_estimate": len(content) // 4}
        }
```

- [ ] 运行确认通过: `pytest tests/core/test_document_processor.py tests/core/test_chunker.py -v`
- [ ] `git commit -m "feat: Parser/Chunker separation, FAQParser, ParserRegistry"`
```python
import fitz  # PyMuPDF
import docx
import uuid
from pathlib import Path

class DocumentProcessor:
    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def process_file(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        ext = Path(file_path).suffix.lower()
        if ext == ".pdf":
            text = self._extract_pdf(file_path)
        elif ext == ".docx":
            text = self._extract_docx(file_path)
        else:
            text = Path(file_path).read_text(encoding="utf-8")
        return self.process_text(text, doc_id, metadata)

    def _extract_pdf(self, path: str) -> str:
        doc = fitz.open(path)
        return "\n".join(page.get_text() for page in doc)

    def _extract_docx(self, path: str) -> str:
        doc = docx.Document(path)
        return "\n".join(p.text for p in doc.paragraphs)

    def process_text(self, text: str, doc_id: str, metadata: dict) -> list[dict]:
        # 按句子边界分块（简单实现：按段落+字符限制）
        sentences = [s.strip() for s in text.replace("\n\n", "|||").split("|||") if s.strip()]
        chunks, current, current_len = [], [], 0
        for sent in sentences:
            if current_len + len(sent) > self.chunk_size and current:
                chunks.append(self._make_chunk(doc_id, " ".join(current), metadata))
                # overlap: 保留最后 N 个字符作为下一块开头
                overlap_text = " ".join(current)[-self.overlap:]
                current = [overlap_text, sent]
                current_len = len(overlap_text) + len(sent)
            else:
                current.append(sent)
                current_len += len(sent)
        if current:
            chunks.append(self._make_chunk(doc_id, " ".join(current), metadata))
        return chunks

    def _make_chunk(self, doc_id: str, content: str, metadata: dict) -> dict:
        return {
            "chunk_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "content": content.strip(),
            "metadata": {**metadata, "token_estimate": len(content) // 4}
        }
```

- [ ] 运行确认通过
- [ ] `git commit -m "feat: document processor with semantic chunking"`

---

### Task 4: Embedding + ChromaDB

**Files:**
- Create: `core/knowledge/embedder.py`
- Create: `core/knowledge/vector_store.py`
- Create: `tests/core/test_vector_store.py`

- [ ] 写失败测试
```python
import pytest
from core.knowledge.embedder import Embedder
from core.knowledge.vector_store import VectorStore

def test_embed_returns_vectors():
    embedder = Embedder(model="Alibaba-NLP/gte-Qwen2-1.5B-instruct")
    vecs = embedder.embed(["hello world", "foo bar"])
    assert len(vecs) == 2
    assert len(vecs[0]) > 100  # gte-Qwen2-1.5B 输出 1536 维

def test_vector_store_add_and_search(tmp_path):
    from core.knowledge.embedder import Embedder
    embedder = Embedder(model="Alibaba-NLP/gte-Qwen2-1.5B-instruct")
    store = VectorStore(persist_dir=str(tmp_path), embedder=embedder)
    store.add_chunks([
        {"chunk_id": "c1", "doc_id": "d1", "content": "退款需要3天", "metadata": {}},
        {"chunk_id": "c2", "doc_id": "d1", "content": "发货时间24小时", "metadata": {}},
    ])
    results = store.search("退款多久", top_k=1)
    assert results[0]["chunk_id"] == "c1"
    assert results[0]["score"] > 0.5
```

- [ ] 运行确认失败

- [ ] 实现 `core/knowledge/embedder.py`
```python
from sentence_transformers import SentenceTransformer

class Embedder:
    def __init__(self, model: str = "Alibaba-NLP/gte-Qwen2-1.5B-instruct"):
        self._model = SentenceTransformer(model, trust_remote_code=True)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return self._model.encode(texts, batch_size=16, normalize_embeddings=True).tolist()
```

- [ ] 实现 `core/knowledge/vector_store.py`
```python
import chromadb
from chromadb.config import Settings

class VectorStore:
    def __init__(self, persist_dir: str, embedder):
        self.client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False)
        )
        self.collection = self.client.get_or_create_collection(
            "knowledge", metadata={"hnsw:space": "cosine"}
        )  # 必须指定 cosine，否则 L2 距离转相似度公式 1-dist 无效
        self.embedder = embedder

    def add_chunks(self, chunks: list[dict]):
        ids = [c["chunk_id"] for c in chunks]
        docs = [c["content"] for c in chunks]
        metas = [c["metadata"] for c in chunks]
        embeddings = self.embedder.embed(docs)
        self.collection.add(ids=ids, documents=docs, metadatas=metas, embeddings=embeddings)

    def search(self, query: str, top_k: int = 5, where: dict = None) -> list[dict]:
        q_emb = self.embedder.embed([query])[0]
        kwargs = {"query_embeddings": [q_emb], "n_results": top_k}
        if where:
            kwargs["where"] = where
        res = self.collection.query(**kwargs)
        results = []
        for i, (cid, doc, meta, dist) in enumerate(zip(
            res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]
        )):
            results.append({
                "chunk_id": cid, "content": doc, "metadata": meta,
                "score": 1 - dist  # ChromaDB 返回 L2 距离，转换为相似度
            })
        return results

    def delete_by_doc(self, doc_id: str):
        results = self.collection.get(where={"doc_id": doc_id})
        if results["ids"]:
            self.collection.delete(ids=results["ids"])
```

- [ ] 运行通过: `pytest tests/core/test_vector_store.py -v`
- [ ] `git commit -m "feat: gte-Qwen2-1.5B embedder and ChromaDB vector store"`

---

### Task 5: BM25 索引

**Files:**
- Create: `core/knowledge/bm25_store.py`

- [ ] 写测试（加入 `tests/core/test_retriever.py`）
```python
from core.knowledge.bm25_store import BM25Store

def test_bm25_search():
    store = BM25Store()
    store.add_chunks([
        {"chunk_id": "c1", "content": "退款需要三个工作日"},
        {"chunk_id": "c2", "content": "发货时间为24小时内"},
    ])
    results = store.search("退款", top_k=1)
    assert results[0]["chunk_id"] == "c1"
```

- [ ] 实现 `core/knowledge/bm25_store.py`
```python
import jieba
from rank_bm25 import BM25Okapi

class BM25Store:
    def __init__(self):
        self._chunks: list[dict] = []
        self._bm25 = None

    def add_chunks(self, chunks: list[dict]):
        self._chunks.extend(chunks)
        tokenized = [list(jieba.cut(c["content"])) for c in self._chunks]
        self._bm25 = BM25Okapi(tokenized)

    def search(self, query: str, top_k: int = 5) -> list[dict]:
        if not self._bm25:
            return []
        tokens = list(jieba.cut(query))
        scores = self._bm25.get_scores(tokens)
        ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            {**self._chunks[i], "bm25_score": score}
            for i, score in ranked if score > 0
        ]

    def delete_by_doc(self, doc_id: str):
        self._chunks = [c for c in self._chunks if c.get("doc_id") != doc_id]
        if self._chunks:
            tokenized = [list(jieba.cut(c["content"])) for c in self._chunks]
            self._bm25 = BM25Okapi(tokenized)
        else:
            self._bm25 = None
```

- [ ] 运行通过，commit: `feat: BM25 keyword search with jieba tokenization`

---

### Task 6: 意图识别 + Query 改写

**Files:**
- Create: `core/rag/intent.py`
- Create: `core/rag/query_rewriter.py`

- [ ] 写测试
```python
import pytest
from unittest.mock import AsyncMock, patch
from core.rag.intent import IntentClassifier
from core.rag.query_rewriter import QueryRewriter

@pytest.mark.asyncio
async def test_intent_in_scope():
    llm = AsyncMock()
    llm.complete.return_value = "IN_SCOPE"
    clf = IntentClassifier(llm=llm)
    result = await clf.classify("退款怎么操作")
    assert result == "in_scope"

@pytest.mark.asyncio
async def test_intent_ambiguous():
    llm = AsyncMock()
    llm.complete.return_value = "AMBIGUOUS"
    clf = IntentClassifier(llm=llm)
    result = await clf.classify("这个怎么弄")
    assert result == "ambiguous"

@pytest.mark.asyncio
async def test_query_rewrite():
    llm = AsyncMock()
    llm.complete.return_value = "如何申请退款？"
    rewriter = QueryRewriter(llm=llm)
    result = await rewriter.rewrite("退款咋整")
    assert "退款" in result
```

- [ ] 实现 `core/rag/intent.py`
```python
INTENT_PROMPT = """判断用户问题是否在客服知识库的服务范围内。
只返回以下三个词之一：IN_SCOPE / OUT_OF_SCOPE / AMBIGUOUS

IN_SCOPE: 可以从知识库找到答案的问题
OUT_OF_SCOPE: 明显不相关的问题
AMBIGUOUS: 问题太模糊，需要澄清

用户问题: {question}"""

class IntentClassifier:
    def __init__(self, llm):
        self.llm = llm

    async def classify(self, question: str) -> str:
        resp = await self.llm.complete([
            {"role": "user", "content": INTENT_PROMPT.format(question=question)}
        ])
        mapping = {"IN_SCOPE": "in_scope", "OUT_OF_SCOPE": "out_of_scope", "AMBIGUOUS": "ambiguous"}
        return mapping.get(resp.strip(), "in_scope")
```

- [ ] 实现 `core/rag/query_rewriter.py`
```python
REWRITE_PROMPT = """将用户的口语化问题改写为更清晰的检索用语。只返回改写后的问题，不要解释。
原问题: {question}"""

class QueryRewriter:
    def __init__(self, llm):
        self.llm = llm

    async def rewrite(self, question: str) -> str:
        return await self.llm.complete([
            {"role": "user", "content": REWRITE_PROMPT.format(question=question)}
        ])
```

- [ ] 运行通过，commit: `feat: intent classifier and query rewriter`

---

### Task 7: 混合检索 + Reranking + 置信度

**Files:**
- Create: `core/rag/retriever.py`
- Create: `core/rag/reranker.py`
- Create: `core/rag/confidence.py`

- [ ] 写测试 (`tests/core/test_retriever.py`)
```python
from unittest.mock import MagicMock
from core.rag.retriever import HybridRetriever

def test_hybrid_retrieval_merges_results():
    vector_store = MagicMock()
    bm25_store = MagicMock()
    vector_store.search.return_value = [
        {"chunk_id": "c1", "content": "退款3天", "score": 0.9},
        {"chunk_id": "c2", "content": "发货24h", "score": 0.6},
    ]
    bm25_store.search.return_value = [
        {"chunk_id": "c1", "content": "退款3天", "bm25_score": 5.0},
        {"chunk_id": "c3", "content": "客服电话", "bm25_score": 2.0},
    ]
    retriever = HybridRetriever(vector_store, bm25_store)
    results = retriever.retrieve("退款", top_k=3)
    ids = [r["chunk_id"] for r in results]
    assert "c1" in ids  # 两路都命中，排名靠前
    assert len(results) <= 3
```

- [ ] 实现 `core/rag/retriever.py`（RRF 融合算法）
```python
class HybridRetriever:
    def __init__(self, vector_store, bm25_store, rrf_k: int = 60):
        self.vector_store = vector_store
        self.bm25_store = bm25_store
        self.rrf_k = rrf_k

    def retrieve(self, query: str, top_k: int = 5) -> list[dict]:
        vec_results = self.vector_store.search(query, top_k=top_k * 2)
        bm25_results = self.bm25_store.search(query, top_k=top_k * 2)

        # RRF 融合
        scores: dict[str, float] = {}
        chunks: dict[str, dict] = {}
        for rank, r in enumerate(vec_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1 / (self.rrf_k + rank + 1)
            chunks[cid] = r
        for rank, r in enumerate(bm25_results):
            cid = r["chunk_id"]
            scores[cid] = scores.get(cid, 0) + 1 / (self.rrf_k + rank + 1)
            chunks[cid] = r

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]
        return [
            {**chunks[cid], "rrf_score": score}
            for cid, score in ranked
        ]
```

- [ ] 实现 `core/rag/reranker.py`
```python
from FlagEmbedding import FlagReranker

class Reranker:
    def __init__(self, model: str = "BAAI/bge-reranker-v2-m3"):
        self._model = FlagReranker(model, use_fp16=True)

    def rerank(self, query: str, chunks: list[dict], top_k: int = 3) -> list[dict]:
        if not chunks:
            return []
        pairs = [[query, c["content"]] for c in chunks]
        scores = self._model.compute_score(pairs, normalize=True)
        ranked = sorted(zip(chunks, scores), key=lambda x: x[1], reverse=True)
        return [{**c, "rerank_score": float(s)} for c, s in ranked[:top_k]]
```

- [ ] 实现 `core/rag/confidence.py`
```python
# 置信度三档（spec 定义）：
#   >= 0.75 → 正常回答
#   0.50–0.75 → 附注"以下内容仅供参考"（uncertain=True, fallback=False）
#   < 0.50 → 触发兜底（fallback=True）

THRESHOLD_HIGH = 0.75
THRESHOLD_LOW = 0.50

def evaluate(chunks: list[dict]) -> tuple[float, str]:
    """返回 (confidence, tier)，tier ∈ {"high", "medium", "low"}"""
    if not chunks:
        return 0.0, "low"
    top_score = chunks[0].get("rerank_score", chunks[0].get("rrf_score", 0.0))
    score = round(float(top_score), 3)
    if score >= THRESHOLD_HIGH:
        tier = "high"
    elif score >= THRESHOLD_LOW:
        tier = "medium"  # 回答但附注不确定
    else:
        tier = "low"     # 触发兜底
    return score, tier

def should_fallback(tier: str) -> bool:
    return tier == "low"
```

- [ ] 运行通过，commit: `feat: hybrid retrieval with RRF fusion, reranker, confidence scoring`

---

### Task 7.5: Tracer + FallbackHandler

**Files:**
- Create: `core/rag/tracer.py`
- Create: `core/rag/fallback_handler.py`
- Create: `tests/core/test_tracer.py`

- [ ] 写失败测试
```python
import json
from core.rag.tracer import StructuredLogTracer
from core.rag.fallback_handler import TellUserHandler

def test_tracer_records_steps(caplog):
    import logging
    tracer = StructuredLogTracer()
    span = tracer.start_trace("t-001", "sess-001")
    tracer.record_step(span, "retrieval", {"top_k": 5, "confidence": 0.87})
    tracer.end_trace(span, {"fallback_triggered": False})
    assert "t-001" in caplog.text or span["trace_id"] == "t-001"

def test_fallback_handler_returns_correct_shape():
    handler = TellUserHandler()
    result = handler.handle("随便问", reason="low_confidence")
    assert result["fallback_triggered"] is True
    assert "answer" in result
    assert result["confidence"] == 0.0
```

- [ ] 运行确认失败

- [ ] 实现 `core/rag/tracer.py`
```python
import json, time, logging
from core.interfaces.tracer import BaseTracer

logger = logging.getLogger("rag.trace")

class StructuredLogTracer(BaseTracer):
    def start_trace(self, trace_id: str, session_id: str) -> dict:
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "start_ts": time.time(),
            "steps": {}
        }

    def record_step(self, span: dict, step: str, data: dict):
        span["steps"][step] = {**data, "ts": round(time.time() - span["start_ts"], 3)}

    def end_trace(self, span: dict, result: dict):
        span["latency_ms"] = round((time.time() - span["start_ts"]) * 1000)
        span.update({k: v for k, v in result.items() if k not in span})
        logger.info(json.dumps(span, ensure_ascii=False, default=str))


class NoopTracer(BaseTracer):
    """测试用，不记录任何东西"""
    def start_trace(self, trace_id, session_id): return {}
    def record_step(self, span, step, data): pass
    def end_trace(self, span, result): pass
```

- [ ] 实现 `core/rag/fallback_handler.py`
```python
from core.interfaces.fallback_handler import BaseFallbackHandler

class TellUserHandler(BaseFallbackHandler):
    """Phase 1 默认：直接告知用户无法回答"""
    MESSAGES = {
        "out_of_scope": "您的问题超出了我的服务范围，建议联系人工客服。",
        "low_confidence": "抱歉，我暂时无法确认这个问题的答案，建议联系人工客服。",
        "default": "抱歉，我暂时无法回答这个问题。",
    }

    def handle(self, question: str, reason: str) -> dict:
        return {
            "answer": self.MESSAGES.get(reason, self.MESSAGES["default"]),
            "sources": [],
            "confidence": 0.0,
            "uncertain": True,
            "fallback_triggered": True,
            "fallback_reason": reason,
        }
```

- [ ] 运行通过，commit: `feat: StructuredLogTracer and TellUserHandler`

---

### Task 8: RAG Pipeline 编排

**Files:**
- Create: `core/rag/pipeline.py`
- Create: `core/rag/generator.py`
- Create: `tests/core/test_pipeline.py`

- [ ] 写集成测试（mock 所有外部依赖）
```python
import pytest
from unittest.mock import AsyncMock, MagicMock
from core.rag.pipeline import RAGPipeline

@pytest.mark.asyncio
async def test_pipeline_in_scope_returns_answer():
    pipeline = RAGPipeline(
        llm=AsyncMock(complete=AsyncMock(return_value="退款需要3天")),
        intent_classifier=AsyncMock(classify=AsyncMock(return_value="in_scope")),
        query_rewriter=AsyncMock(rewrite=AsyncMock(return_value="退款时间")),
        retriever=MagicMock(retrieve=MagicMock(return_value=[
            {"chunk_id": "c1", "content": "退款需要3天", "rerank_score": 0.9}
        ])),
        reranker=MagicMock(rerank=MagicMock(return_value=[
            {"chunk_id": "c1", "content": "退款需要3天", "rerank_score": 0.9}
        ])),
    )
    result = await pipeline.run("退款多久")
    assert result["answer"]
    assert result["confidence"] > 0.7
    assert not result["fallback_triggered"]

@pytest.mark.asyncio
async def test_pipeline_low_confidence_triggers_fallback():
    pipeline = RAGPipeline(
        llm=AsyncMock(complete=AsyncMock(return_value="...")),
        intent_classifier=AsyncMock(classify=AsyncMock(return_value="in_scope")),
        query_rewriter=AsyncMock(rewrite=AsyncMock(return_value="query")),
        retriever=MagicMock(retrieve=MagicMock(return_value=[])),
        reranker=MagicMock(rerank=MagicMock(return_value=[])),
    )
    result = await pipeline.run("完全不相关的问题")
    assert result["fallback_triggered"]
```

- [ ] 实现 `core/rag/generator.py`
```python
GENERATE_PROMPT = """你是一个专业的客服助手。根据以下参考资料回答用户问题。
只使用参考资料中的信息。如果参考资料不足以回答，请如实说明。

参考资料:
{context}

用户问题: {question}

回答:"""

class AnswerGenerator:
    def __init__(self, llm):
        self.llm = llm

    async def generate(self, question: str, chunks: list[dict]) -> str:
        context = "\n\n".join(
            f"[{i+1}] {c['content']}" for i, c in enumerate(chunks)
        )
        return await self.llm.complete([
            {"role": "user", "content": GENERATE_PROMPT.format(
                context=context, question=question
            )}
        ])

    async def generate_stream(self, question: str, chunks: list[dict]):
        context = "\n\n".join(f"[{i+1}] {c['content']}" for i, c in enumerate(chunks))
        return await self.llm.complete_stream([
            {"role": "user", "content": GENERATE_PROMPT.format(
                context=context, question=question
            )}
        ])
```

- [ ] 实现 `core/rag/pipeline.py`
```python
import uuid
from core.rag.tracer import StructuredLogTracer, NoopTracer
from core.rag.fallback_handler import TellUserHandler

class RAGPipeline:
    def __init__(self, llm, intent_classifier, query_rewriter,
                 retriever, reranker, confidence_evaluator=None,
                 fallback_handler=None, tracer=None, top_k: int = 5):
        self.llm = llm
        self.intent = intent_classifier
        self.rewriter = query_rewriter
        self.retriever = retriever
        self.reranker = reranker
        self.top_k = top_k
        # 组件默认值（Ports & Adapters：注入接口，默认实现）
        from core.rag.confidence import SignalFusionEvaluator
        from core.rag.generator import AnswerGenerator
        self.confidence_evaluator = confidence_evaluator or SignalFusionEvaluator()
        self.fallback_handler = fallback_handler or TellUserHandler()
        self.tracer = tracer or StructuredLogTracer()
        self.generator = AnswerGenerator(llm)

    async def run(self, question: str, session_id: str = "") -> dict:
        trace_id = str(uuid.uuid4())
        span = self.tracer.start_trace(trace_id, session_id)

        # 1. 意图识别
        intent = await self.intent.classify(question)
        self.tracer.record_step(span, "intent", {"result": intent})
        if intent == "out_of_scope":
            result = self.fallback_handler.handle(question, reason="out_of_scope")
            self.tracer.end_trace(span, result)
            return result
        if intent == "ambiguous":
            result = {"answer": "您的问题不太清晰，能否提供更多信息？",
                      "clarification_needed": True, "fallback_triggered": False,
                      "confidence": 0.0, "sources": []}
            self.tracer.end_trace(span, result)
            return result

        # 2. Query 改写
        rewritten = await self.rewriter.rewrite(question)
        self.tracer.record_step(span, "query_rewrite", {"rewritten": rewritten})

        # 3. 混合检索
        candidates = self.retriever.retrieve(rewritten, top_k=self.top_k * 2)
        self.tracer.record_step(span, "retrieval", {"candidates": len(candidates)})

        # 4. Reranking
        chunks = self.reranker.rerank(rewritten, candidates, top_k=self.top_k)

        # 5. 置信度评估（三档，可替换实现）
        confidence, tier = self.confidence_evaluator.evaluate(chunks, query=rewritten)
        self.tracer.record_step(span, "confidence", {"score": confidence, "tier": tier})
        if tier == "low":
            result = self.fallback_handler.handle(question, reason="low_confidence")
            self.tracer.end_trace(span, result)
            return result

        # 6. 生成回答
        answer = await self.generator.generate(question, chunks)
        sources = [{"chunk_id": c["chunk_id"], "content": c["content"][:100] + "..."}
                   for c in chunks]
        result = {
            "answer": answer,
            "sources": sources,
            "confidence": confidence,
            "uncertain": tier == "medium",
            "fallback_triggered": False,
        }
        self.tracer.end_trace(span, result)
        return result
```

- [ ] 运行所有 core 测试通过: `pytest tests/core/ -v`
- [ ] commit: `feat: complete RAG pipeline orchestrator`

---

## Week 2：API + 数据库 + 安全

### Task 8.5: conftest.py（测试基础设施）

**Files:**
- Create: `tests/conftest.py`

- [ ] 实现 `tests/conftest.py`
```python
import pytest, pytest_asyncio, os
from unittest.mock import AsyncMock, MagicMock

os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["WIDGET_TOKEN_SECRET"] = "test-token"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test.db"

@pytest.fixture
def mock_pipeline():
    pipeline = MagicMock()
    pipeline.run = AsyncMock(return_value={
        "answer": "退款需要3个工作日",
        "sources": [{"chunk_id": "c1", "content": "退款3天..."}],
        "confidence": 0.88,
        "uncertain": False,
        "fallback_triggered": False,
    })
    return pipeline

@pytest.fixture(autouse=True)
def inject_pipeline(mock_pipeline, monkeypatch):
    """自动将 mock pipeline 注入 app.state，仅在 api 测试中生效"""
    try:
        from api.main import app
        app.state.pipeline = mock_pipeline
    except Exception:
        pass
```

- [ ] commit: `test: add conftest with mock_pipeline fixture`

---

### Task 9: 数据库模型

**Files:**
- Create: `db/models.py`
- Create: `db/session.py`

- [ ] 实现 `db/models.py`
```python
from sqlalchemy import Column, String, Float, Boolean, DateTime, Text, JSON, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class Document(Base):
    __tablename__ = "documents"
    doc_id = Column(String, primary_key=True)
    filename = Column(String)
    file_type = Column(String)
    status = Column(String, default="pending")  # pending/indexing/done/failed
    error_msg = Column(Text, nullable=True)
    chunk_count = Column(Integer, default=0)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, onupdate=func.now())

class QAEntry(Base):
    __tablename__ = "qa_entries"
    qa_id = Column(String, primary_key=True)
    question = Column(Text)
    answer = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class Session(Base):
    __tablename__ = "sessions"
    session_id = Column(String, primary_key=True)
    created_at = Column(DateTime, server_default=func.now())

class Message(Base):
    __tablename__ = "messages"
    message_id = Column(String, primary_key=True)
    session_id = Column(String)
    question = Column(Text)
    answer = Column(Text)
    sources = Column(JSON)
    confidence = Column(Float)
    uncertain = Column(Boolean, default=False)
    fallback_triggered = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.now())

class Chunk(Base):
    __tablename__ = "chunks"
    chunk_id = Column(String, primary_key=True)
    doc_id = Column(String)
    content = Column(Text)
    metadata_ = Column("metadata", JSON)

class Config(Base):
    __tablename__ = "config"
    key = Column(String, primary_key=True)
    value = Column(Text)
```

- [ ] 实现 `db/session.py`
```python
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from db.models import Base
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./data/cs.db")
engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
```

- [ ] commit: `feat: SQLAlchemy async models for documents, sessions, config`

---

### Task 10: Auth + FastAPI 主应用

**Files:**
- Create: `api/dependencies.py`
- Create: `api/main.py`
- Create: `api/routes/health.py`
- Create: `tests/api/test_health.py`

- [ ] 写测试
```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_health_ok():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"

@pytest.mark.asyncio
async def test_chat_requires_auth():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat", json={"question": "test", "session_id": "s1"})
    assert resp.status_code == 401
```

- [ ] 实现 `api/dependencies.py`
```python
from fastapi import Header, HTTPException, Request
from fastapi.responses import JSONResponse
import os, time
from collections import defaultdict

ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", "")
WIDGET_TOKEN_SECRET = os.getenv("WIDGET_TOKEN_SECRET", "")

# 简单内存限速（生产用 Redis）
_rate_buckets: dict = defaultdict(list)

def rate_limit(token: str, limit: int = 60, window: int = 60):
    now = time.time()
    bucket = _rate_buckets[token]
    _rate_buckets[token] = [t for t in bucket if now - t < window]
    if len(_rate_buckets[token]) >= limit:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    _rate_buckets[token].append(now)

async def require_admin_key(x_api_key: str = Header(...)):
    if x_api_key != ADMIN_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

async def require_widget_token(x_widget_token: str = Header(...)):
    # Phase 1：单一静态 Token（env 配置），Phase 2 升级为 DB 存储+可撤销多 Token
    if x_widget_token != WIDGET_TOKEN_SECRET:
        raise HTTPException(status_code=401, detail="Invalid widget token")
    rate_limit(x_widget_token)
```

- [ ] 实现 `api/main.py`
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from db.session import init_db
from api.routes import chat, knowledge, sessions, config, health

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    # 从 DB 重建 BM25 索引（防止重启后 BM25 为空）
    from db.session import AsyncSessionLocal
    from db.models import Chunk as ChunkModel
    from sqlalchemy import select
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(ChunkModel))
        all_chunks = [{"chunk_id": c.chunk_id, "doc_id": c.doc_id, "content": c.content}
                      for c in result.scalars().all()]
    if all_chunks:
        app.state.bm25_store.add_chunks(all_chunks)
    yield

app = FastAPI(title="AI Customer Service", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境收紧为 Widget Token 绑定域名
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(chat.router)
app.include_router(knowledge.router)
app.include_router(sessions.router)
app.include_router(config.router)

# --- 全局单例（Embedder/Reranker 加载慢，只初始化一次）---
# 在 lifespan 中初始化后挂到 app.state，路由通过 request.app.state 访问
# lifespan 完整实现：
# app.state.embedder = Embedder()
# app.state.vector_store = VectorStore(persist_dir="chroma_data", embedder=app.state.embedder)
# app.state.bm25_store = BM25Store()
# app.state.reranker = Reranker()
# app.state.llm = LLMFactory(model=os.getenv("DEFAULT_MODEL"), fallback="deepseek/deepseek-chat")
# app.state.pipeline = RAGPipeline(llm=..., intent_classifier=..., ...)
# 路由中：pipeline = request.app.state.pipeline（通过 Depends 注入）
```

- [ ] 运行测试通过，commit: `feat: FastAPI app with two-tier auth and rate limiting`

---

### Task 11: /chat 接口（SSE 流式）

**Files:**
- Create: `api/routes/chat.py`
- Create: `tests/api/test_chat.py`

- [ ] 写测试
```python
@pytest.mark.asyncio
async def test_chat_returns_answer(mock_pipeline):
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat",
            json={"question": "退款多久", "session_id": "s1", "stream": False},
            headers={"x-widget-token": "test-token"}
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "confidence" in data
    assert "sources" in data
```

- [ ] 实现 `api/routes/chat.py`
```python
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from api.dependencies import require_widget_token
import json, uuid

router = APIRouter(dependencies=[Depends(require_widget_token)])

class ChatRequest(BaseModel):
    question: str
    session_id: str
    stream: bool = True

@router.post("/chat")
async def chat(req: ChatRequest, request: Request):
    pipeline = request.app.state.pipeline  # 从 app.state 获取单例

    if req.stream:
        async def event_stream():
            result = await pipeline.run(req.question)
            words = result["answer"].split()
            for word in words:
                yield f'data: {json.dumps({"type": "delta", "content": word + " "})}\n\n'
            done_frame = {
                "type": "done",
                "sources": result["sources"],
                "confidence": result["confidence"],
                "uncertain": result["uncertain"],
                "message_id": str(uuid.uuid4())
            }
            yield f'data: {json.dumps(done_frame)}\n\n'
        return StreamingResponse(event_stream(), media_type="text/event-stream")
    else:
        result = await pipeline.run(req.question)
        result["message_id"] = str(uuid.uuid4())
        return result
```

- [ ] 运行通过，commit: `feat: /chat endpoint with SSE streaming`

---

### Task 12: 知识库管理 API

**Files:**
- Create: `api/routes/knowledge.py`
- Create: `tests/api/test_knowledge.py`

- [ ] 写失败测试 `tests/api/test_knowledge.py`
```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_upload_returns_doc_id():
    import io
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/upload",
            files={"file": ("test.txt", io.BytesIO(b"退款需要3天"), "text/plain")},
            headers={"x-api-key": "test-admin-key"}
        )
    assert resp.status_code == 200
    assert "doc_id" in resp.json()
    assert resp.json()["status"] == "indexing"

@pytest.mark.asyncio
async def test_upload_requires_admin_key():
    import io
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/upload",
            files={"file": ("test.txt", io.BytesIO(b"test"), "text/plain")},
        )
    assert resp.status_code == 422  # missing header

@pytest.mark.asyncio
async def test_qa_entry_created():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            "/knowledge/qa",
            json={"question": "退款多久", "answer": "3个工作日"},
            headers={"x-api-key": "test-admin-key"}
        )
    assert resp.status_code == 200
    assert "qa_id" in resp.json()
```

- [ ] 运行确认失败

- [ ] 实现 `api/routes/knowledge.py`（核心逻辑）
```python
from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks
from pydantic import BaseModel
from api.dependencies import require_admin_key
import uuid, shutil, os
from db.session import get_db
from db.models import Document, QAEntry
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

router = APIRouter(prefix="/knowledge", dependencies=[Depends(require_admin_key)])

class QARequest(BaseModel):
    question: str
    answer: str

@router.post("/upload")
async def upload_document(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    request=None  # inject via middleware
):
    doc_id = str(uuid.uuid4())
    save_path = f"data/uploads/{doc_id}_{file.filename}"
    os.makedirs("data/uploads", exist_ok=True)
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    doc = Document(doc_id=doc_id, filename=file.filename,
                   file_type=file.filename.split(".")[-1], status="indexing")
    db.add(doc)
    await db.commit()

    # 异步后台索引（不阻塞响应）
    background_tasks.add_task(_index_document, doc_id, save_path)
    return {"doc_id": doc_id, "status": "indexing"}

async def _index_document(doc_id: str, file_path: str):
    """后台任务：解析→分块→向量化→更新状态"""
    from api.main import app
    try:
        processor = app.state.processor
        vector_store = app.state.vector_store
        bm25_store = app.state.bm25_store
        chunks = processor.process_file(file_path, doc_id, {"doc_id": doc_id})
        vector_store.add_chunks(chunks)
        bm25_store.add_chunks(chunks)
        # 更新 DB 状态
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, doc_id)
            doc.status = "done"
            doc.chunk_count = len(chunks)
            await db.commit()
    except Exception as e:
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, doc_id)
            doc.status = "failed"
            doc.error_msg = str(e)
            await db.commit()

@router.post("/qa")
async def add_qa(req: QARequest, db: AsyncSession = Depends(get_db)):
    qa_id = str(uuid.uuid4())
    entry = QAEntry(qa_id=qa_id, question=req.question, answer=req.answer)
    db.add(entry)
    await db.commit()
    # 即时索引 Q&A
    chunk = {"chunk_id": qa_id, "doc_id": "qa", "content": f"Q: {req.question}\nA: {req.answer}", "metadata": {"type": "qa"}}
    # app.state.vector_store.add_chunks([chunk])  # 在真实 request context 中用 request.app.state
    return {"qa_id": qa_id, "status": "indexed"}

@router.get("/documents")
async def list_documents(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Document))
    return [{"doc_id": d.doc_id, "filename": d.filename, "status": d.status,
             "chunk_count": d.chunk_count, "error_msg": d.error_msg}
            for d in result.scalars().all()]

@router.delete("/documents/{doc_id}")
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    # 删除向量 + BM25
    # request.app.state.vector_store.delete_by_doc(doc_id)
    # request.app.state.bm25_store.delete_by_doc(doc_id)
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
```

- [ ] 运行通过: `pytest tests/api/test_knowledge.py -v`
- [ ] commit: `feat: knowledge management API with async background indexing`

---

### Task 13: 会话历史 + 配置 + 健康检查

**Files:**
- Create: `api/routes/sessions.py`
- Create: `api/routes/config.py`
- Create: `api/routes/health.py`
- Create: `tests/api/test_sessions.py`

- [ ] 写测试 `tests/api/test_sessions.py`
```python
import pytest
from httpx import AsyncClient, ASGITransport
from api.main import app

@pytest.mark.asyncio
async def test_sessions_requires_admin():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/sessions")
    assert resp.status_code in (401, 422)

@pytest.mark.asyncio
async def test_health_shows_components():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    data = resp.json()
    assert data["status"] == "ok"
    assert "vector_db" in data
    assert "llm" in data
```

- [ ] 运行确认失败

- [ ] 实现三个路由（CRUD 模式，无额外复杂逻辑）
  - `GET /sessions` → 列出所有 Session（Admin Key 保护）
  - `GET /sessions/{session_id}/messages` → 单会话消息列表
  - `GET /config` + `PUT /config` → Key-Value 配置读写
  - `GET /health` → 探测 ChromaDB + LLM 可用性，返回各组件状态

- [ ] 运行所有测试通过: `pytest tests/ -v`
- [ ] commit: `feat: sessions, config, health endpoints`

---

## Week 3：Widget + 部署

### Task 14: 嵌入式 Widget

**Files:**
- Create: `widget/widget.js`
- Create: `widget/widget.css`

- [ ] 实现聊天气泡（原生 JS，无依赖）
```javascript
// widget.js - 通过 <script data-token="xxx" data-api="http://..." src="widget.js"> 嵌入
(function() {
  const script = document.currentScript;
  const API = script.dataset.api || '';
  const TOKEN = script.dataset.token || '';

  // 注入 CSS
  const style = document.createElement('link');
  style.rel = 'stylesheet';
  style.href = API + '/widget/widget.css';
  document.head.appendChild(style);

  // 创建气泡按钮 + 对话框
  const btn = document.createElement('div');
  btn.id = 'cs-bubble';
  btn.innerHTML = '💬';
  document.body.appendChild(btn);

  const box = document.createElement('div');
  box.id = 'cs-box';
  box.style.display = 'none';
  box.innerHTML = `
    <div id="cs-messages"></div>
    <div id="cs-input-row">
      <input id="cs-input" placeholder="请输入问题..." />
      <button id="cs-send">发送</button>
    </div>`;
  document.body.appendChild(box);

  btn.onclick = () => box.style.display = box.style.display === 'none' ? 'flex' : 'none';

  // SSE 流式接收
  async function sendMessage(question) {
    const sessionId = localStorage.getItem('cs-session') || Math.random().toString(36).slice(2);
    localStorage.setItem('cs-session', sessionId);

    const msgEl = appendMessage('assistant', '');
    const resp = await fetch(API + '/chat', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'x-widget-token': TOKEN},
      body: JSON.stringify({question, session_id: sessionId, stream: true})
    });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';
    while (true) {
      const {done, value} = await reader.read();
      if (done) break;
      buffer += decoder.decode(value);
      const lines = buffer.split('\n\n');
      buffer = lines.pop();
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue;
        const data = JSON.parse(line.slice(6));
        if (data.type === 'delta') msgEl.textContent += data.content;
        if (data.type === 'done' && data.uncertain) {
          msgEl.textContent += '\n（以上内容仅供参考）';
        }
      }
    }
  }

  function appendMessage(role, text) {
    const el = document.createElement('div');
    el.className = 'cs-msg cs-' + role;
    el.textContent = text;
    document.getElementById('cs-messages').appendChild(el);
    return el;
  }

  document.getElementById('cs-send').onclick = () => {
    const input = document.getElementById('cs-input');
    if (!input.value.trim()) return;
    appendMessage('user', input.value);
    sendMessage(input.value);
    input.value = '';
  };
})();
```

- [ ] commit: `feat: embeddable JS widget with SSE streaming`

---

### Task 15: Docker Compose + 部署

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`

- [ ] 实现 `Dockerfile`
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p data
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] 实现 `docker-compose.yml`
```yaml
version: "3.9"
services:
  api:
    build: .
    ports:
      - "8000:8000"
    volumes:
      - ./data:/app/data
      - ./chroma_data:/app/chroma_data
      - hf_cache:/root/.cache/huggingface   # gte-Qwen2-1.5B/Reranker 模型缓存，避免每次重启重下
    env_file:
      - .env
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

volumes:
  hf_cache:
```

> **首次启动说明：** gte-Qwen2-1.5B 约 3GB，首次 `docker-compose up` 时会自动下载，需要等待。
> 可提前在宿主机运行 `python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('Alibaba-NLP/gte-Qwen2-1.5B-instruct', trust_remote_code=True)"` 预缓存模型。

- [ ] 本地验证: `docker-compose up --build`
- [ ] 访问 `http://localhost:8000/health` 确认返回 `{"status": "ok"}`
- [ ] commit: `feat: Docker Compose one-click deployment`

---

### Task 16: 端到端验证

- [ ] 上传测试文档，确认索引成功
```bash
curl -X POST http://localhost:8000/knowledge/upload \
  -H "x-api-key: $ADMIN_API_KEY" \
  -F "file=@test_docs/faq.pdf"
# 期望: {"doc_id": "...", "status": "indexing"}
```

- [ ] 调用 `/chat` 验证 RAG 回答
```bash
curl -X POST http://localhost:8000/chat \
  -H "x-widget-token: $WIDGET_TOKEN_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"question": "退款需要多久", "session_id": "test-01", "stream": false}'
# 期望: {"answer": "...", "confidence": > 0.5, "sources": [...]}
```

- [ ] 在测试 HTML 页面嵌入 Widget，验证聊天气泡正常弹出并显示流式回答

- [ ] 运行完整测试套件: `pytest tests/ -v --tb=short`

- [ ] 最终 commit + tag
```bash
git tag v0.1.0
git push origin main --tags
```

---

## 验证清单（演示就绪标准）

| 验证项 | 命令 / 操作 |
|--------|------------|
| 单元测试全绿 | `pytest tests/ -v` |
| RAG 链路端到端 | `/chat` 接口返回有来源引用的答案 |
| 置信度阈值生效 | 询问知识库外问题，`fallback_triggered: true` |
| SSE 流式输出 | Widget 界面看到打字机效果 |
| 安全：Widget Token 无法调用 Admin 接口 | `curl -H "x-widget-token:xxx" /knowledge/upload` → 401 |
| 健康检查 | `GET /health` → `{"status": "ok"}` |
| 一键部署 | `docker-compose up` 后所有功能正常 |
