"""FastAPI application entry point.

Routes (api/routes/) are Week 2 tasks and not yet implemented.
This file provides a minimal runnable app for startup verification.
"""
import logging

from fastapi import FastAPI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="AI 客服系统",
    description="企业级 RAG 知识库客服系统",
    version="0.1.0",
)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/")
async def root():
    return {"message": "AI 客服系统 API", "docs": "/docs"}
