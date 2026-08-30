"""Tenant Skill catalog proxied from the authenticated Hermes sandbox."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.chat import _resolve_chat_policy
from backend.services.hermes_sandbox_catalog import delete_tenant_skill, fetch_skill_catalog
from backend.services.skill_router import build_skill_tree

router = APIRouter(prefix="/api/v1", tags=["skills"])
_SAFE_SKILL_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


class TenantSkillOut(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    created_at: Optional[str] = None
    skill_path: str = "uncategorized/general"
    skill_level: str = "simple"
    trigger_phrases: List[str] = Field(default_factory=list)
    negative_phrases: List[str] = Field(default_factory=list)
    routing_issues: List[str] = Field(default_factory=list)


class TenantSkillsOut(BaseModel):
    tenant_id: str
    skills: List[TenantSkillOut]
    tree: Dict[str, Any]


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
        skill_path=str(item.get("skill_path") or "uncategorized/general"),
        skill_level=str(item.get("skill_level") or "simple"),
        trigger_phrases=[str(value) for value in item.get("trigger_phrases") or []],
        negative_phrases=[str(value) for value in item.get("negative_phrases") or []],
        routing_issues=[str(value) for value in item.get("routing_issues") or []],
    ) for item in items if item.get("name")]


@router.get("/skills", response_model=TenantSkillsOut)
async def list_tenant_skills(
    payload: Dict[str, Any] = Depends(require_auth),
    owned_only: bool = Query(False),
) -> TenantSkillsOut:
    """List the authenticated Hermes skill catalog.

    The default keeps the existing catalog contract for chat/planner callers.
    Settings uses ``owned_only=true`` so template/platform skills are not
    presented as user-configured skills; only the sandbox's tenant scope is
    user-managed.
    """
    tenant_id = str(payload.get("tenant_key") or "public")
    skills = await _bridge_skill_entries(payload)
    if owned_only:
        skills = [skill for skill in skills if skill.category == "tenant"]
    return TenantSkillsOut(
        tenant_id=tenant_id,
        skills=skills,
        tree=build_skill_tree([skill.model_dump() for skill in skills]),
    )


@router.delete("/skills/{name}")
async def delete_owned_tenant_skill(
    name: str,
    payload: Dict[str, Any] = Depends(require_auth),
) -> Dict[str, Any]:
    if not _SAFE_SKILL_NAME.fullmatch(name):
        raise HTTPException(status_code=400, detail="invalid_skill_name")
    policy = await _resolve_chat_policy(payload)
    user_id = str(payload.get("user_id") or payload.get("sub") or "anonymous")
    try:
        result = await delete_tenant_skill(policy, user_id=user_id, name=name)
    except Exception as exc:
        status = getattr(getattr(exc, "response", None), "status_code", 502)
        if status == 404:
            raise HTTPException(status_code=404, detail="tenant_skill_not_found") from exc
        raise HTTPException(status_code=502, detail="Hermes sandbox delete unavailable") from exc
    remaining = await _bridge_skill_entries(payload)
    if any(skill.category == "tenant" and skill.name == name for skill in remaining):
        raise HTTPException(status_code=502, detail="tenant_skill_delete_not_verified")
    return result
