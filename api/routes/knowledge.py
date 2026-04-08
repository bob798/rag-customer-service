"""Knowledge base management API: upload, Q&A entry, list, delete."""
import json
import os
import uuid
from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi import BackgroundTasks
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_admin_key
from api.schemas import QAEntryRequest
from db.session import get_db, AsyncSessionLocal
from db.models import Document, Chunk as ChunkModel

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.post("/upload", dependencies=[Depends(require_admin_key)])
async def upload_document(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload and asynchronously index a document."""
    doc_id = str(uuid.uuid4())
    upload_dir = "data/uploads"
    os.makedirs(upload_dir, exist_ok=True)
    save_path = f"{upload_dir}/{doc_id}_{file.filename}"
    content = await file.read()
    with open(save_path, "wb") as f:
        f.write(content)

    doc = Document(
        id=doc_id,
        filename=file.filename,
        file_type=file.filename.rsplit(".", 1)[-1] if "." in file.filename else "txt",
        status="indexing",
    )
    db.add(doc)
    await db.commit()

    # Pass components via args to avoid circular import from api.main
    vector_store = request.app.state.pipeline.retriever.vector_store
    bm25_store = request.app.state.pipeline.retriever.bm25_store
    background_tasks.add_task(_index_document, doc_id, save_path, vector_store, bm25_store)
    return {"id": doc_id, "status": "indexing"}


async def _index_document(doc_id: str, file_path: str, vector_store, bm25_store):
    """Background task: parse → chunk → index → update status."""
    from core.knowledge.parsers.faq import FAQParser
    from core.knowledge.parsers.default import DefaultParser
    from core.knowledge.chunker import SemanticChunker
    try:
        ext = file_path.rsplit(".", 1)[-1].lower() if "." in file_path else "txt"
        if ext == "txt":
            parser = FAQParser()
        else:
            parser = DefaultParser(chunker=SemanticChunker())
        chunks = parser.parse(file_path, doc_id)
        await vector_store.add(chunks)
        bm25_store.add(chunks)

        # Save chunks to DB for BM25 rebuild on restart
        async with AsyncSessionLocal() as db:
            for chunk in chunks:
                db.add(ChunkModel(
                    id=chunk["chunk_id"],
                    doc_id=doc_id,
                    content=chunk["content"],
                    metadata_json=json.dumps(chunk.get("metadata", {})),
                ))
            doc = await db.get(Document, doc_id)
            if doc:
                doc.status = "ready"
            await db.commit()
    except Exception as e:
        async with AsyncSessionLocal() as db:
            doc = await db.get(Document, doc_id)
            if doc:
                doc.status = "failed"
            await db.commit()


@router.post("/qa", dependencies=[Depends(require_admin_key)])
async def add_qa(
    req: QAEntryRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Add a Q&A pair directly to the knowledge base."""
    entry_id = str(uuid.uuid4())
    content = f"Q: {req.question}\nA: {req.answer}"
    metadata = {"source_title": "手动Q&A", "type": "qa"}
    chunk = {
        "chunk_id": entry_id,
        "doc_id": "qa_manual",
        "content": content,
        "metadata": metadata,
    }
    await request.app.state.pipeline.retriever.vector_store.add([chunk])
    request.app.state.pipeline.retriever.bm25_store.add([chunk])
    db.add(ChunkModel(
        id=entry_id,
        doc_id="qa_manual",
        content=content,
        metadata_json=json.dumps(metadata),
    ))
    await db.commit()
    return {"id": entry_id, "status": "indexed"}


@router.get("/documents", dependencies=[Depends(require_admin_key)])
async def list_documents(db: AsyncSession = Depends(get_db)):
    """List all documents with their indexing status."""
    result = await db.execute(select(Document))
    return [
        {"id": d.id, "filename": d.filename, "status": d.status}
        for d in result.scalars().all()
    ]


@router.delete("/documents/{doc_id}", dependencies=[Depends(require_admin_key)])
async def delete_document(doc_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a document and its DB record (vector/BM25 cleanup handled separately)."""
    doc = await db.get(Document, doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    await db.delete(doc)
    await db.commit()
    return {"status": "deleted"}
