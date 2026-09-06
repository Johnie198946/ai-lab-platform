"""Tenant-safe subscription center proxy.

iOS never talks to Authen directly. Organization identity and requester identity
are derived from the verified JWT, while Authen remains the entitlement source.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select

from backend.api.auth import PERSONAL_PUBLIC_ORG_ID, require_auth
from backend.api import knowledge
from backend.db import SessionLocal
from backend.models.tenant import KnowledgeBookSubscription
from backend.services.knowledge_catalog import (
    base_knowledge_status,
    bookshelf_catalog,
    document_index,
    filter_database_live_documents,
    tenant_private_knowledge_status,
)


router = APIRouter(prefix="/api/v1", tags=["subscriptions"])
AUTHEN_SUBSCRIPTION_URL = os.environ.get(
    "AUTHEN_SUBSCRIPTION_URL", "http://host.docker.internal:8006"
).rstrip("/")
AUTHEN_SERVICE_TOKEN = os.environ.get("AUTHEN_AI_PLATFORM_SERVICE_TOKEN", "")
AUTHEN_APP_ID = os.environ.get("AUTHEN_APP_ID", "ai-lab-platform")
KNOWLEDGE_PACK_SUBSCRIPTION_ENABLED = os.environ.get(
    "KNOWLEDGE_PACK_SUBSCRIPTION_V1", "true"
).lower() == "true"


class SubscriptionRequestCreate(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=160)
    plan_id: str = Field(..., min_length=1, max_length=64)
    requested_entitlements: list[str] = Field(default_factory=list)
    requested_pack_ids: list[str] = Field(default_factory=list, max_length=20)
    reason: str = Field(default="", max_length=1000)


class SubscriptionReview(BaseModel):
    review_note: str = Field(default="", max_length=1000)
    approved_pack_ids: list[str] | None = Field(default=None, max_length=20)


class BookSubscriptionWrite(BaseModel):
    book_id: str = Field(..., min_length=1, max_length=384)
    edition: int = Field(default=1, ge=1)


class BookProgressWrite(BaseModel):
    book_id: str = Field(..., min_length=1, max_length=384)
    progress: float = Field(..., ge=0, le=1)


def _error(
    status: int, *, code: str, message: str, action: str, retryable: bool
) -> HTTPException:
    return HTTPException(
        status_code=status,
        detail={
            "code": code,
            "message": message,
            "action": action,
            "retryable": retryable,
        },
    )


def _org(payload: dict[str, Any]) -> str:
    org_id = str(payload.get("org_id") or PERSONAL_PUBLIC_ORG_ID).strip()
    if not org_id:
        raise _error(
            409,
            code="organization_required",
            message="当前账号尚未加入组织，无法申请组织套餐",
            action="contact_admin",
            retryable=False,
        )
    return org_id


def _is_base_plan(plan: dict[str, Any]) -> bool:
    """Recognize the base tier without coupling to one Authen seed UUID."""
    return (
        str(plan.get("tier") or "").lower() == "base"
        or str(plan.get("slug") or "").lower() in {
            "team-knowledge-basic",
            "knowledge-basic",
        }
        or "基础" in str(plan.get("name") or "")
    )


def _decorate_plan_availability(
    plan: dict[str, Any], base_knowledge: dict[str, Any]
) -> dict[str, Any]:
    if _is_base_plan(plan) and base_knowledge["status"] != "ready":
        return {
            **plan,
            "availability": "content_building",
            "is_available": False,
        }
    return {**plan, "availability": "available", "is_available": True}


async def _authen_request(
    method: str, path: str, *, params: dict | None = None, json: dict | None = None
) -> Any:
    if not AUTHEN_SERVICE_TOKEN:
        raise _error(
            503,
            code="subscription_service_unconfigured",
            message="套餐服务尚未配置，请联系平台管理员",
            action="contact_admin",
            retryable=False,
        )
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.request(
                method,
                f"{AUTHEN_SUBSCRIPTION_URL}{path}",
                params=params,
                json=json,
                headers={"Authorization": f"Bearer {AUTHEN_SERVICE_TOKEN}"},
            )
    except httpx.RequestError as exc:
        raise _error(
            503,
            code="subscription_service_unavailable",
            message="套餐服务暂时不可用，请稍后重试",
            action="retry",
            retryable=True,
        ) from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except Exception:
            detail = None
        if isinstance(detail, dict) and detail.get("code") == "request_pending":
            raise _error(
                409,
                code="request_pending",
                message="当前组织已有待审批申请",
                action="view_request",
                retryable=False,
            )
        detail_text = detail if isinstance(detail, str) else ""
        if "allowance exceeded" in detail_text:
            raise _error(
                422,
                code="knowledge_pack_allowance_exceeded",
                message="所选知识包超过当前套餐额度",
                action="edit_selection",
                retryable=False,
            )
        if "not published" in detail_text or "governance" in detail_text:
            raise _error(
                409,
                code="knowledge_pack_governance_pending",
                message="该知识包仍在治理建设中，暂不能申请",
                action="dismiss",
                retryable=False,
            )
        if "custom plan" in detail_text:
            raise _error(
                422,
                code="contact_admin_required",
                message="企业知识专属版需要由管理员按合同配置",
                action="contact_admin",
                retryable=False,
            )
        message = detail if isinstance(detail, str) else "套餐服务拒绝了该操作"
        raise _error(
            response.status_code,
            code="subscription_service_rejected",
            message=message,
            action="retry" if response.status_code >= 500 else "contact_admin",
            retryable=response.status_code >= 500,
        )
    return response.json()


@router.get("/subscription-center")
async def subscription_center(payload=Depends(require_auth)):
    org_id = _org(payload)
    plans = await _authen_request(
        "GET", "/api/v1/internal/plans", params={"app_id": AUTHEN_APP_ID}
    )
    center = await _authen_request(
        "GET",
        f"/api/v1/internal/organizations/{org_id}/subscription-center",
        params={"app_id": AUTHEN_APP_ID},
    )
    requests = center.get("requests") or []
    vault = knowledge._vault()
    base_status = base_knowledge_status(vault)
    private_status = tenant_private_knowledge_status(payload["tenant_key"], vault)
    plan_items = [
        _decorate_plan_availability(item, base_status)
        for item in (plans.get("plans") or [])
    ]
    if not KNOWLEDGE_PACK_SUBSCRIPTION_ENABLED:
        plan_items = [
            {**item, "pack_allowance": 0, "selectable_pack_ids": []}
            for item in plan_items
        ]
        center["knowledge_packs"] = []
        center["active_pack_grants"] = []
        center["pack_allowance"] = 0
    # The member settings surface is an entitlement summary, not a marketplace.
    # Minimize data server-side so hidden candidate/ungranted packs cannot be
    # enumerated by bypassing the iOS view.
    if not payload.get("is_super_admin"):
        grants = center.get("active_pack_grants") or (
            (center.get("subscription") or {}).get("active_pack_grants")
        ) or []
        active_ids = {
            str(item.get("knowledge_pack_id") or item.get("id") or "")
            for item in grants
            if item.get("status") == "active"
        }
        center["knowledge_packs"] = [
            item for item in (center.get("knowledge_packs") or [])
            if str(item.get("id") or "") in active_ids
        ]
    return {
        **center,
        "plans": plan_items,
        "base_knowledge": base_status,
        "bookshelves": await _visible_bookshelves(payload),
        "tenant_private_knowledge": private_status,
        "knowledge_pack_subscription_enabled": KNOWLEDGE_PACK_SUBSCRIPTION_ENABLED,
        "is_super_admin": bool(payload.get("is_super_admin")),
        "pending_count": sum(item.get("status") == "pending" for item in requests),
    }


@router.get("/knowledge-bookshelves")
async def knowledge_bookshelves(payload=Depends(require_auth)):
    """Reader catalog independent of organization subscription state."""
    return {"bookshelves": await _visible_bookshelves(payload)}


def _reader_identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or ""),
        str(payload.get("user_id") or payload.get("sub") or payload.get("username") or "dev"),
    )


async def _visible_bookshelves(payload: dict[str, Any]) -> list[dict[str, Any]]:
    vault = knowledge._vault()
    documents = await filter_database_live_documents(list(document_index(vault).values()), vault)
    return bookshelf_catalog(
        payload["tenant_key"], vault, payload.get("visible_categories"), documents
    )


async def _available_books(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    shelves = await _visible_bookshelves(payload)
    return {book["id"]: book for shelf in shelves for book in shelf["books"]}


def _book_subscription(row: KnowledgeBookSubscription, book: dict[str, Any]) -> dict[str, Any]:
    return {
        "book": book,
        "edition": row.edition,
        "progress": row.progress,
        "subscribed_at": row.subscribed_at,
        "last_read_at": row.last_read_at,
    }


@router.get("/me/book-subscriptions")
async def my_book_subscriptions(payload=Depends(require_auth)):
    tenant_key, user_id = _reader_identity(payload)
    available = await _available_books(payload)
    async with SessionLocal() as db:
        rows = (
            await db.execute(
                select(KnowledgeBookSubscription)
                .where(
                    KnowledgeBookSubscription.tenant_key == tenant_key,
                    KnowledgeBookSubscription.owner_user_id == user_id,
                )
                .order_by(KnowledgeBookSubscription.last_read_at.desc())
            )
        ).scalars().all()
    return {
        "subscriptions": [
            _book_subscription(row, available[row.book_id])
            for row in rows
            if row.book_id in available
        ]
    }


@router.put("/me/book-subscriptions")
async def subscribe_book(body: BookSubscriptionWrite, payload=Depends(require_auth)):
    tenant_key, user_id = _reader_identity(payload)
    book = (await _available_books(payload)).get(body.book_id)
    if book is None:
        raise _error(
            404, code="book_not_found", message="这本书已下架或当前无权阅读",
            action="refresh_catalog", retryable=True,
        )
    async with SessionLocal() as db:
        row = await db.scalar(
            select(KnowledgeBookSubscription).where(
                KnowledgeBookSubscription.tenant_key == tenant_key,
                KnowledgeBookSubscription.owner_user_id == user_id,
                KnowledgeBookSubscription.book_id == body.book_id,
            )
        )
        if row is None:
            row = KnowledgeBookSubscription(
                tenant_key=tenant_key, owner_user_id=user_id,
                book_id=body.book_id, edition=body.edition,
            )
            db.add(row)
        else:
            row.edition = body.edition
            row.last_read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
    return _book_subscription(row, book)


@router.patch("/me/book-subscriptions/progress")
async def update_book_progress(body: BookProgressWrite, payload=Depends(require_auth)):
    tenant_key, user_id = _reader_identity(payload)
    book = (await _available_books(payload)).get(body.book_id)
    if book is None:
        raise _error(
            404, code="book_not_found", message="这本书已下架或当前无权阅读",
            action="refresh_catalog", retryable=True,
        )
    async with SessionLocal() as db:
        row = await db.scalar(
            select(KnowledgeBookSubscription).where(
                KnowledgeBookSubscription.tenant_key == tenant_key,
                KnowledgeBookSubscription.owner_user_id == user_id,
                KnowledgeBookSubscription.book_id == body.book_id,
            )
        )
        if row is None:
            raise _error(
                404, code="book_not_subscribed", message="请先订阅这本书",
                action="subscribe", retryable=False,
            )
        row.progress = body.progress
        row.last_read_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(row)
    return _book_subscription(row, book)


@router.delete("/me/book-subscriptions")
async def unsubscribe_book(body: BookSubscriptionWrite, payload=Depends(require_auth)):
    tenant_key, user_id = _reader_identity(payload)
    async with SessionLocal() as db:
        result = await db.execute(
            delete(KnowledgeBookSubscription).where(
                KnowledgeBookSubscription.tenant_key == tenant_key,
                KnowledgeBookSubscription.owner_user_id == user_id,
                KnowledgeBookSubscription.book_id == body.book_id,
            )
        )
        await db.commit()
    return {"book_id": body.book_id, "deleted": bool(result.rowcount)}


@router.post("/subscription-requests")
async def create_subscription_request(
    body: SubscriptionRequestCreate, payload=Depends(require_auth)
):
    org_id = _org(payload)
    if body.requested_pack_ids and not KNOWLEDGE_PACK_SUBSCRIPTION_ENABLED:
        raise _error(
            503,
            code="knowledge_pack_subscription_disabled",
            message="知识包申请正在灰度开放中",
            action="retry_later",
            retryable=True,
        )
    plans = await _authen_request(
        "GET", "/api/v1/internal/plans", params={"app_id": AUTHEN_APP_ID}
    )
    target_plan = next(
        (item for item in plans.get("plans") or [] if str(item.get("id")) == body.plan_id),
        None,
    )
    if target_plan and _is_base_plan(target_plan):
        base_status = base_knowledge_status(knowledge._vault())
        if base_status["status"] != "ready":
            raise _error(
                409,
                code="base_knowledge_building",
                message=(
                    "基础公共知识正在完成来源与权限复核"
                    f"（{base_status['document_count']}/"
                    f"{base_status['minimum_document_count']}），开放后无需再次申请"
                ),
                action="retry_later",
                retryable=True,
            )
    return await _authen_request(
        "POST",
        f"/api/v1/internal/organizations/{org_id}/subscription-requests",
        params={"app_id": AUTHEN_APP_ID},
        json={
            **body.model_dump(),
            "requested_by": str(payload.get("user_id") or payload.get("sub") or ""),
        },
    )


@router.delete("/subscription-requests/{request_id}")
async def cancel_subscription_request(request_id: str, payload=Depends(require_auth)):
    org_id = _org(payload)
    return await _authen_request(
        "DELETE",
        f"/api/v1/internal/organizations/{org_id}/subscription-requests/{request_id}",
        params={"app_id": AUTHEN_APP_ID},
    )


@router.get("/admin/subscription-requests")
async def list_subscription_requests(
    status: str = "pending", payload=Depends(require_auth)
):
    if not payload.get("is_super_admin"):
        raise _error(
            403, code="admin_required", message="需要超级管理员权限",
            action="dismiss", retryable=False,
        )
    return await _authen_request(
        "GET",
        "/api/v1/internal/admin/subscription-requests",
        params={"app_id": AUTHEN_APP_ID, "status": status},
    )


async def _review(
    request_id: str, action: str, body: SubscriptionReview, payload: dict[str, Any]
):
    if not payload.get("is_super_admin"):
        raise _error(
            403, code="admin_required", message="需要超级管理员权限",
            action="dismiss", retryable=False,
        )
    return await _authen_request(
        "POST",
        f"/api/v1/internal/admin/subscription-requests/{request_id}/{action}",
        params={"app_id": AUTHEN_APP_ID},
        json={
            "reviewed_by": str(payload.get("user_id") or payload.get("sub") or ""),
            "review_note": body.review_note,
            "approved_pack_ids": body.approved_pack_ids,
        },
    )


@router.post("/admin/subscription-requests/{request_id}/approve")
async def approve_subscription_request(
    request_id: str, body: SubscriptionReview, payload=Depends(require_auth)
):
    return await _review(request_id, "approve", body, payload)


@router.post("/admin/subscription-requests/{request_id}/reject")
async def reject_subscription_request(
    request_id: str, body: SubscriptionReview, payload=Depends(require_auth)
):
    return await _review(request_id, "reject", body, payload)
