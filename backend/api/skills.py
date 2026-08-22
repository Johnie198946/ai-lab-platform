"""Tenant Skill catalog proxied from the authenticated Hermes sandbox."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from backend.api.auth import require_auth
from backend.api.chat import _resolve_chat_policy
from backend.services.hermes_sandbox_catalog import fetch_skill_catalog

router = APIRouter(prefix="/api/v1", tags=["skills"])


class TenantSkillOut(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    created_at: Optional[str] = None


class TenantSkillsOut(BaseModel):
    tenant_id: str
    skills: List[TenantSkillOut]


async def _bridge_skill_entries(payload: Dict[str, Any]) -> List[TenantSkillOut]:
    policy = await _resolve_chat_policy(payload)
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    try:
        items = await fetch_skill_catalog(policy, user_id=user_id)
    except Exception:
        raise HTTPException(status_code=502, detail="Hermes sandbox catalog unavailable")
    return [TenantSkillOut(
        name=str(item.get("name") or ""),
        description=str(item.get("description") or "")[:120],
        category=str(item.get("scope") or ""),
        created_at=item.get("created_at"),
    ) for item in items if item.get("name")]


@router.get("/skills", response_model=TenantSkillsOut)
async def list_tenant_skills(payload: Dict[str, Any] = Depends(require_auth)) -> TenantSkillsOut:
    tenant_id = str(payload.get("tenant_key") or "public")
    return TenantSkillsOut(
        tenant_id=tenant_id, skills=await _bridge_skill_entries(payload)
    )
