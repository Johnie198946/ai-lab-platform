"""租户技能 API — 真实技能库（挂载目录扫描，非演示数据）。

`GET /api/v1/skills`：返回当前租户专属技能列表（skills/tenants/<tenant>/<name>/SKILL.md
挂载目录扫描，与 /api/v1/topology 的技能 Agent 同源）。多租户隔离由 current_tenant 派生保证。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.api.topology import _sanitize_tenant_id

router = APIRouter(prefix="/api/v1", tags=["skills"])


class TenantSkillOut(BaseModel):
    name: str
    description: str = ""
    category: str = ""
    created_at: Optional[str] = None


class TenantSkillsOut(BaseModel):
    tenant_id: str
    skills: List[TenantSkillOut]


def _scan_tenant_skill_entries(tenant_id: str) -> List[TenantSkillOut]:
    """扫描挂载的租户技能目录（与 topology._scan_tenant_skills 同源）。"""
    safe_tenant = _sanitize_tenant_id(tenant_id)
    skills_root = Path(os.environ.get("HERMES_SKILLS_DIR", "/root/.hermes/skills"))
    tenant_dir = skills_root / "tenants" / safe_tenant

    try:
        tenant_dir_resolved = tenant_dir.resolve()
        skills_root_resolved = skills_root.resolve()
        if not str(tenant_dir_resolved).startswith(str(skills_root_resolved)):
            return []
    except Exception:
        return []

    if not tenant_dir.is_dir():
        return []

    items: List[TenantSkillOut] = []
    for skill_dir in sorted(tenant_dir.iterdir()):
        if not skill_dir.is_dir():
            continue
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.is_file():
            continue
        name = skill_dir.name
        desc = ""
        created = None
        try:
            lines = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines:
                low = line.lower()
                if low.startswith("description:") and not desc:
                    desc = line.split(":", 1)[1].strip()
                if low.startswith("date:") and created is None:
                    created = line.split(":", 1)[1].strip()
        except Exception:
            pass
        items.append(TenantSkillOut(name=name, description=desc[:120], category="", created_at=created))
    return items


@router.get("/skills", response_model=TenantSkillsOut)
async def list_tenant_skills(payload: Dict[str, Any] = Depends(require_auth)) -> TenantSkillsOut:
    """返回当前租户真实技能库（无任何演示数据；空则返回空列表）。"""
    tenant_id = _sanitize_tenant_id(current_tenant.get() or "demo")
    return TenantSkillsOut(tenant_id=tenant_id, skills=_scan_tenant_skill_entries(tenant_id))
