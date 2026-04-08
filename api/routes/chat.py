"""POST /chat — main Q&A endpoint with SSE streaming and DB persistence."""
import json
import uuid
from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_widget_token, get_pipeline
from api.schemas import ChatRequest
from db.session import get_db
from db.models import Session as SessionModel, Message

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(
    req: ChatRequest,
    request: Request,
    _: str = Depends(require_widget_token),
    db: AsyncSession = Depends(get_db),
):
    pipeline = get_pipeline(request)

    # 1. Load or create Session
    session = await db.get(SessionModel, req.session_id)
    if not session:
        session = SessionModel(id=req.session_id)
        db.add(session)
        await db.flush()

    # 2. Load conversation history for multi-turn context (last 10 turns)
    result = await db.execute(
        select(Message)
        .where(Message.session_id == req.session_id)
        .order_by(Message.created_at)
        .limit(10)
    )
    history = [
        {"role": "user", "content": m.question}
        for m in result.scalars().all()
    ]

    # 3. Run RAG pipeline
    rag_result = await pipeline.run(req.question, req.session_id, history)
    message_id = str(uuid.uuid4())

    # 4. Persist message to DB
    msg = Message(
        id=message_id,
        session_id=req.session_id,
        question=req.question,
        answer=rag_result["answer"],
        sources_json=json.dumps(rag_result.get("sources", [])),
        confidence=rag_result.get("confidence"),
        uncertain=rag_result.get("uncertain", False),
    )
    db.add(msg)
    await db.commit()

    if req.stream:
        async def event_stream():
            words = rag_result["answer"].split()
            for word in words:
                yield f'data: {json.dumps({"type": "delta", "content": word + " "})}\n\n'
            done_frame = {
                "type": "done",
                "sources": rag_result.get("sources", []),
                "confidence": rag_result.get("confidence"),
                "uncertain": rag_result.get("uncertain", False),
                "message_id": message_id,
            }
            yield f"data: {json.dumps(done_frame)}\n\n"

        return StreamingResponse(event_stream(), media_type="text/event-stream")
    else:
        return {
            **rag_result,
            "session_id": req.session_id,
            "message_id": message_id,
        }
