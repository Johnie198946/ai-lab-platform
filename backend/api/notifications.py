"""通知 API — 站内通知中心(Agent 汇报落点; 后续飞书 webhook 同源)。"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.api.auth import require_auth

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(
    limit: int = Query(50, ge=1, le=200),
    unread_only: bool = Query(False),
    payload=Depends(require_auth),
) -> Dict[str, Any]:
    from sqlalchemy import func, select

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        total = (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.tenant_key == tenant_key
                )
            )
        ).scalar_one()
        unread = (
            await db.execute(
                select(func.count(Notification.id)).where(
                    Notification.tenant_key == tenant_key,
                    Notification.read.is_(False),
                )
            )
        ).scalar_one()
        q = (
            select(Notification)
            .where(Notification.tenant_key == tenant_key)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        if unread_only:
            q = q.where(Notification.read.is_(False))
        rows = (await db.execute(q)).scalars().all()
    return {
        "total": total,
        "unread": unread,
        "items": [
            {
                "id": n.id,
                "agent_id": n.agent_id,
                "title": n.title,
                "content": n.content or "",
                "channel": n.channel,
                "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
    }


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: int, payload=Depends(require_auth)
) -> Dict[str, Any]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    async with SessionLocal() as db:
        n = (
            await db.execute(
                select(Notification).where(
                    Notification.id == notification_id,
                    Notification.tenant_key == payload["tenant_key"],
                )
            )
        ).scalar_one_or_none()
        if n is None:
            raise HTTPException(status_code=404, detail="通知不存在")
        n.read = True
        await db.commit()
    return {"ok": True, "id": notification_id}


@router.post("/read-all")
async def mark_all_read(payload=Depends(require_auth)) -> Dict[str, Any]:
    from sqlalchemy import update

    from backend.db import SessionLocal
    from backend.models.notification import Notification

    async with SessionLocal() as db:
        await db.execute(
            update(Notification)
            .where(
                Notification.tenant_key == payload["tenant_key"],
                Notification.read.is_(False),
            )
            .values(read=True)
        )
        await db.commit()
    return {"ok": True}
