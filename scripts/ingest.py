"""知识库构建脚本 — 解析文档并写入向量数据库 + BM25 索引。

支持的文件格式：
  - .txt (FAQ 格式或普通文本)
  - .pdf
  - .docx

FAQ 格式示例（自动识别）：
  Q: 怎么申请退款？
  A: 在订单页面点击申请退款...

  问：发货需要多久？
  答：通常 1-2 个工作日...

使用方式：
  # 单个文件
  .venv/bin/python scripts/ingest.py data/faq.txt

  # 整个目录
  .venv/bin/python scripts/ingest.py data/docs/

  # 指定 ChromaDB 路径和集合名
  .venv/bin/python scripts/ingest.py data/faq.txt --chroma-path ./data/chroma --collection knowledge

  # 仅解析预览，不写入（dry-run）
  .venv/bin/python scripts/ingest.py data/faq.txt --dry-run
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


async def ingest_file(
    file_path: Path,
    vector_store,
    bm25_store,
    embedder,
    dry_run: bool = False,
) -> int:
    """解析单个文件并写入知识库。返回写入的 chunk 数量。"""
    from core.knowledge.chunker import SemanticChunker
    from core.knowledge.parsers.default import DefaultParser
    from core.knowledge.parsers.docx_parser import DocxParser
    from core.knowledge.parsers.faq import FAQParser
    from core.knowledge.parsers.mineru import MinerUParser
    from core.knowledge.parsers.paddleocr import PaddleOCRParser
    from core.knowledge.parsers.registry import ParserRegistry

    registry = ParserRegistry()
    registry.register(FAQParser())

    # PDF parsers: PaddleOCR > MinerU > Default (first available wins)
    if PaddleOCRParser.is_available():
        registry.register(PaddleOCRParser(chunker=SemanticChunker()))
    elif MinerUParser.is_available():
        registry.register(MinerUParser(chunker=SemanticChunker()))

    # DOCX parser: python-docx + PaddleOCR for image OCR
    registry.register(DocxParser(chunker=SemanticChunker()))

    registry.register(DefaultParser(chunker=SemanticChunker()))

    ext = file_path.suffix.lstrip(".").lower()
    content_hint = file_path.read_text(encoding="utf-8", errors="ignore")[:500]

    try:
        parser = registry.get_parser(ext, content_hint)
    except ValueError:
        print(f"  [跳过] 不支持的格式：{file_path.name}")
        return 0

    doc_id = str(uuid.uuid4())
    metadata = {
        "source_title": file_path.name,
        "source_path": str(file_path),
        "file_type": ext,
    }

    try:
        chunks = parser.parse(str(file_path), doc_id=doc_id, metadata=metadata)
    except Exception as e:
        if type(parser).__name__ == "MinerUParser":
            print(f"  [降级] MinerU 失败，使用 DefaultParser: {e}")
            from core.knowledge.parsers.default import DefaultParser
            from core.knowledge.chunker import SemanticChunker
            fallback = DefaultParser(chunker=SemanticChunker())
            chunks = fallback.parse(str(file_path), doc_id=doc_id, metadata=metadata)
        else:
            raise

    if not chunks:
        print(f"  [空] 未解析出任何 chunk：{file_path.name}")
        return 0

    parser_name = type(parser).__name__
    print(f"  {file_path.name}  →  {len(chunks)} chunks  (parser: {parser_name})")

    if dry_run:
        for i, c in enumerate(chunks[:3]):
            preview = c["content"].replace("\n", " ")[:80]
            print(f"    [{i}] {preview}...")
        if len(chunks) > 3:
            print(f"    ... 还有 {len(chunks) - 3} 个 chunk")
        return len(chunks)

    # 写入向量数据库
    await vector_store.add(chunks)
    # 写入 BM25 索引
    bm25_store.add(chunks)

    return len(chunks)


async def main():
    parser = argparse.ArgumentParser(
        description="将文档解析并写入知识库（ChromaDB + BM25）"
    )
    parser.add_argument("path", help="文件路径或目录路径")
    parser.add_argument(
        "--chroma-path", default="./data/chroma", help="ChromaDB 存储路径（默认 ./data/chroma）"
    )
    parser.add_argument(
        "--collection", default="knowledge", help="ChromaDB 集合名（默认 knowledge）"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="仅解析预览，不写入数据库"
    )
    args = parser.parse_args()

    target = Path(args.path)
    if not target.exists():
        print(f"错误：路径不存在 → {target}")
        sys.exit(1)

    # 收集文件列表
    SUPPORTED_EXTS = {".txt", ".pdf", ".docx"}
    if target.is_file():
        files = [target]
    else:
        files = sorted([f for f in target.rglob("*") if f.suffix.lower() in SUPPORTED_EXTS])

    if not files:
        print(f"未找到支持的文件（{', '.join(SUPPORTED_EXTS)}）in {target}")
        sys.exit(1)

    print(f"发现 {len(files)} 个文件\n")

    if args.dry_run:
        print("=== DRY RUN 模式（不写入数据库）===\n")
        # dry-run 不需要真实 embedder，用轻量替代
        vector_store = None
        bm25_store = None
        embedder = None
    else:
        # 真实模式：需要 GteQwen2Embedder（会下载模型，首次较慢）
        print("正在加载 Embedding 模型（GteQwen2，首次需下载约 3GB）...")
        from core.knowledge.embedder import GteQwen2Embedder
        from core.knowledge.bm25_store import Bm25Store
        from core.knowledge.vector_store import ChromaVectorStore

        embedder = GteQwen2Embedder()
        vector_store = ChromaVectorStore(
            embedder=embedder,
            collection_name=args.collection,
            persist_directory=args.chroma_path,
        )
        bm25_store = Bm25Store()
        print(f"ChromaDB: {args.chroma_path}  集合: {args.collection}\n")

    total_chunks = 0
    for f in files:
        count = await ingest_file(
            file_path=f,
            vector_store=vector_store,
            bm25_store=bm25_store,
            embedder=embedder,
            dry_run=args.dry_run,
        )
        total_chunks += count

    print(f"\n{'='*50}")
    if args.dry_run:
        print(f"DRY RUN 完成：共解析 {total_chunks} 个 chunk（未写入）")
    else:
        print(f"导入完成：{len(files)} 个文件，{total_chunks} 个 chunk")
        print(f"ChromaDB: {args.chroma_path}")
        print(f"\n注意：BM25 索引仅在内存中，服务启动时需要从 ChromaDB 重建。")
        print(f"参考 core/knowledge/bm25_store.py: rebuild_from_chunks()")


if __name__ == "__main__":
    asyncio.run(main())
