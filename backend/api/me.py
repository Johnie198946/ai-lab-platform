"""当前用户 / 会话历史 / 用量（租户维数据，逻辑隔离落点）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.api.auth import require_auth
from backend.api.catalog import compute_catalog

router = APIRouter(prefix="/api/v1", tags=["me"])


@router.get("/me")
async def me(payload=Depends(require_auth)):
    """当前用户信息 + 租户 + 订阅 + 可见知识统计。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import (
        KnowledgeSubscription,
        TenantSession,
        TenantUsage,
    )

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        subs = (
            await db.execute(
                select(KnowledgeSubscription.category).where(
                    KnowledgeSubscription.tenant_key == tenant_key
                )
            )
        ).scalars().all()
        usage = (
            await db.execute(
                select(TenantUsage).where(TenantUsage.tenant_key == tenant_key)
            )
        ).scalar_one_or_none()
        session_count = (
            await db.execute(
                select(TenantSession.id)
                .where(TenantSession.tenant_key == tenant_key)
                .limit(1)
            )
        ).first()
    catalog = compute_catalog()
    visible_count = 0
    if payload.get("visible_categories") is None:
        visible_count = sum(c["doc_count"] for c in catalog)
    else:
        visible_count = sum(
            c["doc_count"]
            for c in catalog
            if c["category"] in payload["visible_categories"]
        )
    return {
        "user_id": payload.get("user_id", ""),
        "username": payload.get("username", ""),
        "is_super_admin": payload.get("is_super_admin", False),
        "tenant_key": tenant_key,
        "subscriptions": sorted(subs),
        "visible_docs": visible_count,
        "chat_calls": usage.chat_calls if usage else 0,
        "token_used": usage.token_used if usage else 0,
        "has_sessions": session_count is not None,
    }


@router.get("/me/sessions")
async def my_sessions(
    payload=Depends(require_auth),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """我的问答历史（按租户隔离）。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import TenantSession

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(TenantSession)
                .where(TenantSession.tenant_key == tenant_key)
                .order_by(TenantSession.id.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
    return {
        "tenant_key": tenant_key,
        "sessions": [
            {
                "id": s.id,
                "question": s.question,
                "answer": s.answer,
                "sources": s.sources,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in rows
        ],
    }


@router.get("/me/usage")
async def my_usage(payload=Depends(require_auth)):
    """我的 API 用量。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import TenantUsage

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        usage = (
            await db.execute(
                select(TenantUsage).where(TenantUsage.tenant_key == tenant_key)
            )
        ).scalar_one_or_none()
    return {
        "tenant_key": tenant_key,
        "chat_calls": usage.chat_calls if usage else 0,
        "token_used": usage.token_used if usage else 0,
    }
