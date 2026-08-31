"""Idempotent capability migration for all persisted QWS AI employees."""

from __future__ import annotations

from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.tenant_agent import TenantAgentModel
from backend.services.agent_capabilities import SAFE_GLOBAL_TOOLS


async def migrate_qws_ai_employee_capabilities() -> int:
    """Grant every QWS employee the platform-safe baseline capability set."""
    updated = 0
    baseline_tools = list(SAFE_GLOBAL_TOOLS)
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(TenantAgentModel).where(TenantAgentModel.is_active.is_(True))
            )
        ).all()
        for row in rows:
            manifest = dict(row.composition_manifest or {})
            if not isinstance(manifest.get("qws_employee"), dict):
                continue
            if (
                manifest.get("allowed_tools") == baseline_tools
                and manifest.get("allow_network") is True
            ):
                continue
            row.composition_manifest = {
                **manifest,
                "allowed_tools": baseline_tools,
                "allow_network": True,
            }
            updated += 1
        if updated:
            await db.commit()
    return updated
