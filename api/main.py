"""FastAPI application entry point with lifespan initialization."""
import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from db.session import init_db, AsyncSessionLocal
from db.models import Chunk as ChunkModel, Config as ConfigModel

logger = logging.getLogger(__name__)

DEFAULT_CONFIGS = {
    "llm_model": "claude-haiku-4-5-20251001",
    "bot_name": "AI 客服",
    "fallback_action": "tell_user",
    "top_k": "5",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Initialize DB tables
    await init_db()

    # 2. Seed default configs (skip if already exist)
    async with AsyncSessionLocal() as db:
        for key, value in DEFAULT_CONFIGS.items():
            existing = await db.get(ConfigModel, key)
            if not existing:
                db.add(ConfigModel(key=key, value=value))
        await db.commit()

    # 3. Initialize Pipeline singleton (loads Embedder/Reranker once)
    if not hasattr(app.state, "pipeline") or app.state.pipeline is None:
        from core.rag.pipeline_builder import create_default_pipeline
        llm_model = os.getenv("DEFAULT_MODEL", DEFAULT_CONFIGS["llm_model"])
        use_noop = os.getenv("USE_NOOP_RERANKER", "false").lower() == "true"
        pipeline = create_default_pipeline(
            llm_model=llm_model,
            use_noop_reranker=use_noop,
        )
        app.state.pipeline = pipeline
        logger.info(f"Pipeline initialized with model={llm_model}")

    # 4. Rebuild BM25 index from DB (restores index after restart)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(ChunkModel))
        chunks = [
            {"chunk_id": c.id, "doc_id": c.doc_id, "content": c.content}
            for c in result.scalars().all()
        ]
    if chunks:
        app.state.pipeline.retriever.bm25_store.add(chunks)
        logger.info(f"BM25 rebuilt with {len(chunks)} chunks")

    yield


app = FastAPI(
    title="AI 客服系统",
    description="企业级 RAG 知识库客服系统",
    version="0.2.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["health"])
async def health(request: Request):
    """Component health check."""
    vector_db_status = "ok"
    try:
        _ = request.app.state.pipeline.retriever.vector_store
    except Exception:
        vector_db_status = "error"
    return {"status": "ok", "vector_db": vector_db_status, "llm": "unknown"}


@app.get("/")
async def root():
    return {"message": "AI 客服系统 API", "docs": "/docs"}


# Register routes (imported after app creation to avoid circular imports)
try:
    from api.routes import chat, knowledge, sessions, config
    app.include_router(chat.router)
    app.include_router(knowledge.router)
    app.include_router(sessions.router)
    app.include_router(config.router)
except ImportError:
    pass  # Routes not yet implemented (Tasks 5-7)
