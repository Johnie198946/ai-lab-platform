"""Tenant-safe subscription center proxy.

iOS never talks to Authen directly. Organization and actor identities are
derived from the verified JWT while Authen remains the entitlement source.
"""

from __future__ import annotations

import os
from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth


router = APIRouter(prefix="/api/v1", tags=["subscriptions"])
AUTHEN_SUBSCRIPTION_URL = os.environ.get(
    "AUTHEN_SUBSCRIPTION_URL", "http://host.docker.internal:8006"
).rstrip("/")
AUTHEN_SERVICE_TOKEN = os.environ.get("AUTHEN_AI_PLATFORM_SERVICE_TOKEN", "")
AUTHEN_APP_ID = os.environ.get("AUTHEN_APP_ID", "ai-lab-platform")


class SubscriptionRequestCreate(BaseModel):
    request_id: str = Field(..., min_length=8, max_length=160)
    plan_id: str = Field(..., min_length=1, max_length=64)
    requested_entitlements: list[str] = Field(default_factory=list)
    reason: str = Field(default="", max_length=1000)


class SubscriptionReview(BaseModel):
    review_note: str = Field(default="", max_length=1000)


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
    org_id = str(payload.get("org_id") or "").strip()
    if not org_id:
        raise _error(
            409,
            code="organization_required",
            message="当前账号尚未加入组织，无法申请组织套餐",
            action="contact_admin",
            retryable=False,
        )
    return org_id


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
    return {
        **center,
        "plans": plans.get("plans") or [],
        "is_super_admin": bool(payload.get("is_super_admin")),
        "pending_count": sum(item.get("status") == "pending" for item in requests),
    }


@router.post("/subscription-requests")
async def create_subscription_request(
    body: SubscriptionRequestCreate, payload=Depends(require_auth)
):
    org_id = _org(payload)
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
