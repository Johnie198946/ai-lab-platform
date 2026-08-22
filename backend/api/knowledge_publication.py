"""One-action Green/Yellow/Red publication approval for super administrators."""

from __future__ import annotations

import hashlib
import hmac
import json
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api import knowledge_policy
from backend.services.knowledge_catalog import clear_manifest_cache
from backend.services.knowledge_color_projection import approve_color, color_approval_candidates, restore_note

router = APIRouter(prefix="/api/v1/admin/knowledge-publication", tags=["knowledge-publication"])
AUTHEN_URL = os.environ.get("AUTHEN_SUBSCRIPTION_URL", "http://host.docker.internal:8006").rstrip("/")
AUTHEN_TOKEN = os.environ.get("AUTHEN_AI_PLATFORM_SERVICE_TOKEN", "")
APPROVAL_SECRET = os.environ.get("AUTHEN_KNOWLEDGE_APPROVAL_SECRET", "")


class PublicationDecision(BaseModel):
    path: str = Field(..., min_length=6, max_length=1200)
    security_level: str = Field(..., pattern="^(green|yellow|red)$")
    entitlement_key: str = Field(default="", max_length=128)
    owner_tenant: str = Field(default="", max_length=64)


def _super(payload: dict) -> None:
    if not payload.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="super administrator required")


def _vault():
    from backend.services.knowledge_catalog import _vault as catalog_vault
    return catalog_vault()


async def _notify_authen(*, path: str, entitlement_key: str, approved_by: str) -> None:
    if not AUTHEN_TOKEN or not APPROVAL_SECRET:
        raise HTTPException(status_code=503, detail={"code": "authen_approval_sync_unconfigured", "message": "Yellow 审批联动尚未配置，文档未发布"})
    event = {
        "event_id": "kpa_" + hashlib.sha256(f"{path}:{entitlement_key}".encode()).hexdigest()[:32],
        "application_id": "ai-lab-platform", "entitlement_key": entitlement_key,
        "approved_by": approved_by, "source_path": path,
    }
    raw = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(APPROVAL_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{AUTHEN_URL}/api/v1/internal/knowledge-pack-approvals",
                content=raw,
                headers={"Authorization": f"Bearer {AUTHEN_TOKEN}", "Content-Type": "application/json", "X-Approval-Signature": f"sha256={signature}"},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail={"code": "authen_approval_sync_failed", "message": "Authen 暂不可达，审批已回滚"}) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "authen_approval_sync_rejected", "message": "Authen 未接受知识包审批，审批已回滚"})


@router.get("")
async def candidates(payload=Depends(require_auth)):
    _super(payload)
    return {"items": color_approval_candidates(_vault())}


@router.post("/approve")
async def approve(body: PublicationDecision, payload=Depends(require_auth)):
    _super(payload)
    actor = str(payload.get("user_id") or payload.get("sub") or "")
    try:
        path, original, metadata = approve_color(
            _vault(), relative_path=body.path, security_level=body.security_level,
            approved_by=actor, entitlement_key=body.entitlement_key,
            owner_tenant=body.owner_tenant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        if body.security_level == "yellow":
            await _notify_authen(
                path=body.path, entitlement_key=body.entitlement_key,
                approved_by=actor,
            )
    except HTTPException:
        restore_note(path, original)
        raise
    except Exception as exc:
        restore_note(path, original)
        raise HTTPException(status_code=500, detail={"code": "approval_transaction_failed", "message": "审批联动失败，文档已回滚"}) from exc
    clear_manifest_cache()
    knowledge_policy._SEARCH_CACHE.clear()
    return {"path": body.path, "security_level": body.security_level, "classification_status": metadata["classification_status"], "gateway_status": "available"}
