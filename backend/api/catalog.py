"""知识分类目录 + 订阅管理（订阅制逻辑多租户）。

- GET    /api/v1/catalog                      可订阅分类目录（登录即可）
- GET    /api/v1/me/subscriptions             我的订阅
- POST   /api/v1/me/subscriptions             订阅 {"category": "wiki"}
- DELETE /api/v1/me/subscriptions/{category}  退订
"""

from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.auth import require_auth
from backend.api import knowledge

router = APIRouter(prefix="/api/v1", tags=["catalog"])

# 不可订阅的系统目录（不进入知识分类）
SYSTEM_DIRS = {
    ".obsidian",
    ".claudian",
    ".git",
    ".DS_Store",
    "00_Inbox",   # 私人收件箱（已从同步排除，天然不上云）
    "模板",
    "_archive",
}

CATEGORY_TITLES = {
    "研究系统": "研究报告与来源卡片",
    "wiki": "编译知识条目",
    "产品设计": "产品文档",
    "raw": "原始资料",
    "AI情报雷达": "情报日报",
    "竞品情报": "竞品分析",
    "客户画像": "客户资料",
    "任务记录": "项目任务记录",
    "决策记录": "决策记录",
}


def compute_catalog() -> list[dict]:
    """从 vault 顶层目录实时计算分类目录（含文档数）。"""
    vault = knowledge._vault()
    if not vault.exists():
        return []
    catalog = []
    for child in sorted(vault.iterdir()):
        if not child.is_dir() or child.name in SYSTEM_DIRS:
            continue
        doc_count = sum(1 for _ in child.rglob("*.md"))
        catalog.append(
            {
                "category": child.name,
                "path_prefix": f"{child.name}/",
                "title": CATEGORY_TITLES.get(child.name, child.name),
                "doc_count": doc_count,
                "open": True,
            }
        )
    return catalog


@router.get("/catalog")
async def get_catalog(payload=Depends(require_auth)):
    """可订阅分类目录（登录即可见）。"""
    return {"catalog": compute_catalog()}


@router.get("/me/subscriptions")
async def my_subscriptions(payload=Depends(require_auth)):
    """我的订阅列表。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeSubscription.category).where(
                    KnowledgeSubscription.tenant_key == tenant_key
                )
            )
        ).scalars().all()
    return {"tenant_key": tenant_key, "categories": sorted(rows)}


class SubscribeRequest(BaseModel):
    category: str


@router.post("/me/subscriptions")
async def subscribe(body: SubscribeRequest, payload=Depends(require_auth)):
    """订阅一个分类（分类必须在 catalog 中）。"""
    catalog = {c["category"] for c in compute_catalog()}
    if body.category not in catalog:
        raise HTTPException(
            status_code=404, detail=f"分类不存在: {body.category}"
        )
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        exists = (
            await db.execute(
                select(KnowledgeSubscription).where(
                    KnowledgeSubscription.tenant_key == tenant_key,
                    KnowledgeSubscription.category == body.category,
                )
            )
        ).scalar_one_or_none()
        if exists is None:
            db.add(
                KnowledgeSubscription(
                    tenant_key=tenant_key, category=body.category
                )
            )
            await db.commit()
    return {"tenant_key": tenant_key, "categories": await _subs(tenant_key)}


@router.delete("/me/subscriptions/{category}")
async def unsubscribe(category: str, payload=Depends(require_auth)):
    """退订（该分类知识立即不可见）。"""
    from sqlalchemy import delete

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    tenant_key = payload["tenant_key"]
    async with SessionLocal() as db:
        await db.execute(
            delete(KnowledgeSubscription).where(
                KnowledgeSubscription.tenant_key == tenant_key,
                KnowledgeSubscription.category == category,
            )
        )
        await db.commit()
    return {"tenant_key": tenant_key, "categories": await _subs(tenant_key)}


async def _subs(tenant_key: str) -> list[str]:
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.tenant import KnowledgeSubscription

    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeSubscription.category).where(
                    KnowledgeSubscription.tenant_key == tenant_key
                )
            )
        ).scalars().all()
    return sorted(rows)
