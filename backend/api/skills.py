"""Tenant Skill catalog proxied from the authenticated Hermes sandbox."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
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
    scope_model: str = "user_private+tenant_shared+platform_template"
    skills: List[TenantSkillOut]


async def _bridge_skill_entries(
    payload: Dict[str, Any], scope: Optional[str] = None
) -> List[TenantSkillOut]:
    policy = await _resolve_chat_policy(payload)
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    try:
        items = await fetch_skill_catalog(policy, user_id=user_id, scope=scope)
    except Exception:
        raise HTTPException(status_code=502, detail="Hermes sandbox catalog unavailable")
    return [TenantSkillOut(
        name=str(item.get("name") or ""),
        description=str(item.get("description") or "")[:120],
        category=str(item.get("scope") or ""),
        created_at=item.get("created_at"),
    ) for item in items if item.get("name")]


@router.get("/skills", response_model=TenantSkillsOut)
async def list_tenant_skills(
    payload: Dict[str, Any] = Depends(require_auth),
    owned_only: bool = Query(False),
    scope: Optional[str] = Query(None, pattern="^(user|tenant|all)$"),
) -> TenantSkillsOut:
    """List the authenticated Hermes skill catalog.

    The default keeps the existing catalog contract for chat/planner callers.
    Settings uses ``scope=user``. The default remains the effective runtime
    catalog; ``owned_only=true`` is retained as a compatibility alias.
    """
    tenant_id = str(payload.get("tenant_key") or "public")
    requested_scope = "user" if owned_only or scope == "user" else scope
    skills = await _bridge_skill_entries(payload, requested_scope)
    if requested_scope in {"user", "tenant"}:
        # Keep a server-side guard even if an older Bridge ignores the query.
        skills = [skill for skill in skills if skill.category == requested_scope]
    return TenantSkillsOut(
        tenant_id=tenant_id, skills=skills
    )
