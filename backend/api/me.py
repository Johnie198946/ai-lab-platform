"""当前用户 / 会话历史 / 用量（租户维数据，逻辑隔离落点）。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from backend.api.auth import require_auth
from backend.api.catalog import compute_catalog

router = APIRouter(prefix="/api/v1", tags=["me"])


class ProfileUpdate(BaseModel):
    """PATCH /me 请求体：可更新字段（None = 不修改）。"""

    username: Optional[str] = None
    avatar_url: Optional[str] = None


async def _build_profile(
    payload: dict,
    username_override: Optional[str] = None,
    avatar_override: Optional[str] = None,
) -> dict:
    """组装当前用户完整 Profile（GET /me 与 PATCH /me 共用）。

    DB 可读时 username / avatar_url 优先取 TenantMapping 持久化值；
    DB 不可用时回退 JWT username 与 override 值（本地 Mock 兼容）。
    """
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import (
        KnowledgeSubscription,
        TenantMapping,
        TenantSession,
        TenantUsage,
    )

    tenant_key = payload["tenant_key"]
    user_id = payload.get("user_id", "")
    subs: list[str] = []
    usage = None
    session_count = None
    username = (
        username_override
        if username_override is not None
        else payload.get("username", "")
    )
    avatar_url = avatar_override
    try:
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
            if user_id:
                mapping = (
                    await db.execute(
                        select(TenantMapping).where(
                            TenantMapping.user_id == user_id
                        )
                    )
                ).scalar_one_or_none()
                if mapping is not None:
                    if mapping.username:
                        username = mapping.username
                    avatar_url = mapping.avatar_url
    except Exception:
        # 本地未连 DB 时仍返回最小会话信息，避免前端真实登录态恢复失败。
        pass
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
        "user_id": user_id,
        "username": username,
        "avatar_url": avatar_url,
        "is_super_admin": payload.get("is_super_admin", False),
        "tenant_key": tenant_key,
        "subscriptions": sorted(subs),
        "visible_docs": visible_count,
        "chat_calls": usage.chat_calls if usage else 0,
        "token_used": usage.token_used if usage else 0,
        "has_sessions": session_count is not None,
    }


@router.get("/me")
async def me(payload=Depends(require_auth)):
    """当前用户信息 + 租户 + 订阅 + 可见知识统计。"""
    return await _build_profile(payload)


@router.get("/me/session")
async def me_session(payload=Depends(require_auth)):
    """登录关键路径使用的轻量身份快照；不扫描知识目录或聚合用量。"""
    return {
        "user_id": payload.get("user_id", ""),
        "username": payload.get("username", ""),
        "avatar_url": payload.get("avatar_url"),
        "is_super_admin": payload.get("is_super_admin", False),
        "tenant_key": payload["tenant_key"],
    }


@router.patch("/me")
async def patch_me(body: ProfileUpdate, payload=Depends(require_auth)):
    """更新当前用户 username / avatar_url，返回更新后的完整 Profile。

    零破坏性：不改变 GET /me 返回结构（仅新增 avatar_url 字段）；
    未配置 DB 时降级为本地 Mock（不持久化，仍返回更新后 profile）。
    """
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import TenantMapping

    if body.username is not None or body.avatar_url is not None:
        tenant_key = payload["tenant_key"]
        user_id = payload.get("user_id", "")
        try:
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        select(TenantMapping).where(
                            TenantMapping.user_id == user_id
                        )
                    )
                ).scalar_one_or_none()
                if row is None:
                    row = TenantMapping(
                        user_id=user_id,
                        tenant_key=tenant_key,
                    )
                    db.add(row)
                if body.username is not None:
                    row.username = body.username
                if body.avatar_url is not None:
                    row.avatar_url = body.avatar_url
                await db.commit()
        except Exception:
            # 未配置 DB → 本地 Mock 兼容（不持久化）
            pass
    return await _build_profile(payload, body.username, body.avatar_url)


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


@router.get("/usage/summary")
async def my_usage_summary(
    days: int = Query(30), payload=Depends(require_auth)
):
    """Return exact, post-launch LLM usage for the authenticated user."""
    if days not in {7, 30, 90}:
        raise HTTPException(status_code=400, detail="days 仅支持 7、30 或 90")
    from backend.services.llm_usage import usage_summary

    return await usage_summary(payload, days)
