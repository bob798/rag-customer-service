"""Session history API: list sessions and retrieve messages."""
import json
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_admin_key
from db.session import get_db
from db.models import Session as SessionModel, Message

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_admin_key)])


@router.get("")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    """List all sessions (most recent first, limit 50)."""
    result = await db.execute(
        select(SessionModel).order_by(SessionModel.created_at.desc()).limit(50)
    )
    return [
        {"id": s.id, "created_at": s.created_at.isoformat()}
        for s in result.scalars().all()
    ]


@router.get("/{session_id}/messages")
async def get_messages(session_id: str, db: AsyncSession = Depends(get_db)):
    """Get all messages for a session in chronological order."""
    result = await db.execute(
        select(Message)
        .where(Message.session_id == session_id)
        .order_by(Message.created_at)
    )
    return [
        {
            "id": m.id,
            "question": m.question,
            "answer": m.answer,
            "confidence": m.confidence,
            "uncertain": m.uncertain,
            "sources": json.loads(m.sources_json or "[]"),
            "created_at": m.created_at.isoformat(),
        }
        for m in result.scalars().all()
    ]
