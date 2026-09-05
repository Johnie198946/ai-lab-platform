"""Tenant contribution consent and withdrawal control plane."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionOutbox, KnowledgeContributionPolicy,
)
from backend.services.knowledge_contribution import (
    get_contribution_projection,
    set_contribution_policy,
    withdraw_contribution,
)

router = APIRouter(prefix="/api/v1/knowledge-contribution", tags=["knowledge-contribution"])
_ADMIN_ROLES = {"owner", "tenant_owner", "tenant_admin", "admin", "local_owner"}


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool
    agreement_version: str = Field(min_length=1, max_length=96)
    effective_at: datetime | None = None
    historical_backfill: bool = False
    policy_version: str = Field(default="contribution-v4", min_length=1, max_length=96)


class WithdrawalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    event_id: str = Field(min_length=1, max_length=96)
    permanent: bool = True


def _admin(payload: dict[str, Any]) -> None:
    role = str(payload.get("role") or payload.get("user_role") or "").strip().lower()
    if not payload.get("is_super_admin") and role not in _ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="tenant administrator required")


@router.get("/policy")
async def get_policy(payload: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _admin(payload)
    tenant_key = str(payload.get("tenant_key") or "")
    async with SessionLocal() as db:
        policy = await db.scalar(select(KnowledgeContributionPolicy).where(
            KnowledgeContributionPolicy.tenant_key == tenant_key
        ))
    if policy is None:
        return {"tenant_key": tenant_key, "enabled": False, "configured": False}
    return {
        "tenant_key": tenant_key,
        "enabled": policy.enabled,
        "configured": True,
        "agreement_version": policy.agreement_version,
        "effective_at": policy.effective_at,
        "historical_backfill": policy.historical_backfill,
        "policy_version": policy.policy_version,
        "uploaded_file_opt_out_enabled": policy.uploaded_file_opt_out_enabled,
    }


@router.put("/policy")
async def update_policy(body: PolicyUpdate, payload: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _admin(payload)
    effective_at = body.effective_at or datetime.now(timezone.utc)
    if body.historical_backfill:
        raise HTTPException(status_code=422, detail={
            "code": "historical_backfill_forbidden",
            "message": "V4 contribution consent never backfills pre-authorization content",
        })
    try:
        return await set_contribution_policy(
            tenant_key=str(payload.get("tenant_key") or ""),
            enabled=body.enabled,
            agreement_version=body.agreement_version,
            effective_at=effective_at,
            historical_backfill=False,
            policy_version=body.policy_version,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/projections/{projection_id}/source")
async def projection_source(projection_id: str, payload=Depends(require_auth)):
    projection = await get_contribution_projection(
        tenant_key=str(payload.get("tenant_key") or ""),
        user_id=str(payload.get("user_id") or payload.get("sub") or ""),
        projection_id=projection_id,
    )
    if projection is None:
        raise HTTPException(status_code=404, detail="projection not found")
    async with SessionLocal() as db:
        events = []
        for event_id in projection["event_ids"]:
            event = await db.get(KnowledgeContributionOutbox, event_id)
            if event is not None:
                events.append({
                    "surface": event.source_surface,
                    "source_kind": event.source_kind,
                    "source_id": event.source_id,
                    "source_revision": event.source_revision,
                    "status": event.status,
                })
    return {"projection_id": projection_id, "security_level": projection["security_level"],
            "read_only": True, "edit_at_source": True, "sources": events}


@router.post("/withdraw")
async def withdraw(body: WithdrawalRequest, payload: dict[str, Any] = Depends(require_auth)) -> dict[str, Any]:
    _admin(payload)
    try:
        affected = await withdraw_contribution(
            tenant_key=str(payload.get("tenant_key") or ""),
            user_id=str(payload.get("user_id") or payload.get("sub") or ""),
            event_id=body.event_id,
            permanent=body.permanent,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return {"event_id": body.event_id, "affected_event_ids": affected, "status": "withdrawn"}
