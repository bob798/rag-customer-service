"""Pydantic request/response models for the API layer."""
from pydantic import BaseModel
from typing import Optional


class ChatRequest(BaseModel):
    question: str
    session_id: str
    stream: bool = True


class SourceItem(BaseModel):
    chunk_id: str
    doc_id: str
    title: str
    content_preview: str


class ChatResponse(BaseModel):
    answer: str
    sources: list[SourceItem]
    confidence: float
    uncertain: bool
    session_id: str
    message_id: str


class QAEntryRequest(BaseModel):
    question: str
    answer: str


class ConfigUpdateRequest(BaseModel):
    updates: dict[str, str]  # {key: value}


class SessionOut(BaseModel):
    id: str
    created_at: str


class MessageOut(BaseModel):
    id: str
    question: str
    answer: str
    confidence: Optional[float]
    uncertain: bool
    created_at: str
