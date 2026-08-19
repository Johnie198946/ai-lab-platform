"""Idempotent migration from the legacy card-only ``workflow_runs`` table."""

from __future__ import annotations

from sqlalchemy import inspect, select, text

from backend.db import SessionLocal, engine
from backend.models.workflow import WorkflowDefinition
from backend.services.workflow_planner import build_plan


async def migrate_legacy_workflows() -> int:
    async with engine.begin() as connection:
        has_legacy = await connection.run_sync(
            lambda sync_connection: inspect(sync_connection).has_table("workflow_runs")
        )
    if not has_legacy:
        return 0
    migrated = 0
    async with SessionLocal() as db:
        rows = (
            (
                await db.execute(
                    text(
                        "SELECT id, tenant_key, created_by, title, goal, created_at, "
                        "updated_at FROM workflow_runs"
                    )
                )
            )
            .mappings()
            .all()
        )
        for legacy in rows:
            exists = (
                await db.execute(
                    select(WorkflowDefinition.id).where(
                        WorkflowDefinition.id == legacy["id"]
                    )
                )
            ).scalar_one_or_none()
            if exists:
                continue
            workflow = WorkflowDefinition(
                id=legacy["id"],
                tenant_key=legacy["tenant_key"],
                created_by=legacy.get("created_by") or "",
                title=legacy["title"],
                description=legacy.get("goal") or legacy["title"],
                desired_output="研究报告（Markdown）",
                status="planning",
                created_at=legacy.get("created_at"),
                updated_at=legacy.get("updated_at"),
            )
            db.add(workflow)
            await db.flush()
            await build_plan(db, workflow)
            migrated += 1
        await db.commit()
    return migrated
