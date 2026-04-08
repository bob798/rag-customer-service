"""System configuration API: read and update key-value config store."""
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import require_admin_key
from api.schemas import ConfigUpdateRequest
from db.session import get_db
from db.models import Config

router = APIRouter(prefix="/config", tags=["config"], dependencies=[Depends(require_admin_key)])


@router.get("")
async def get_config(db: AsyncSession = Depends(get_db)):
    """Return all config entries as a key-value dict."""
    result = await db.execute(select(Config))
    return {c.key: c.value for c in result.scalars().all()}


@router.put("")
async def update_config(req: ConfigUpdateRequest, db: AsyncSession = Depends(get_db)):
    """Update one or more config values (insert if key doesn't exist)."""
    for key, value in req.updates.items():
        existing = await db.get(Config, key)
        if existing:
            existing.value = value
        else:
            db.add(Config(key=key, value=value))
    await db.commit()
    return {"updated": list(req.updates.keys())}
