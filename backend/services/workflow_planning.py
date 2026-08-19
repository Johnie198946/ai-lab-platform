"""Durable workflow planning queue and Hermes Bridge projection."""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.db import SessionLocal, init_db
from backend.models.workflow import (
    WorkflowClarificationSession,
    WorkflowDefinition,
    WorkflowLifecycleEvent,
    WorkflowPlanningJob,
)
from backend.services.workflow_planner import (
    HERMES_PLANNING_ENABLED,
    WORKFLOW_TOKEN_BUDGET,
    build_plan,
    persist_raw_plan,
    planning_context,
)

LEASE_SECONDS = 45
POLL_SECONDS = 1.0
HERMES_BRIDGE_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bridge_base_url() -> str:
    base = HERMES_BRIDGE_URL.rstrip("/")
    return base[: -len("/v1/chat")] if base.endswith("/v1/chat") else base


def bridge_headers() -> dict[str, str]:
    return (
        {"X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN}
        if HERMES_BRIDGE_INTERNAL_TOKEN
        else {}
    )


def event_payload(
    step_id: str,
    category: str,
    status: str,
    *,
    tool: str = "",
    detail: str = "",
    source: str = "workflow_platform",
    **extra: Any,
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "category": category,
        "status": status,
        "tool": tool,
        "detail": detail,
        "source": source,
        **extra,
    }


async def append_event(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    session: WorkflowClarificationSession,
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    session.last_event_seq += 1
    db.add(
        WorkflowLifecycleEvent(
            workflow_id=workflow.id,
            session_id=session.id,
            seq=session.last_event_seq,
            event_type=event_type,
            message=message[:500],
            payload=payload,
        )
    )


async def enqueue_planning_job(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    *,
    revision_note: str = "",
    force_new: bool = False,
) -> WorkflowPlanningJob:
    existing = (
        await db.execute(
            select(WorkflowPlanningJob)
            .where(
                WorkflowPlanningJob.workflow_id == workflow.id,
                WorkflowPlanningJob.status.in_(["queued", "running"]),
            )
            .order_by(WorkflowPlanningJob.requirement_version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if existing and not force_new:
        return existing
    version = int(
        (
            await db.execute(
                select(func.coalesce(func.max(WorkflowPlanningJob.requirement_version), 0)).where(
                    WorkflowPlanningJob.workflow_id == workflow.id
                )
            )
        ).scalar_one()
    ) + 1
    job = WorkflowPlanningJob(
        id=f"wfpj_{workflow.id.split('_')[-1][:20]}_{version}",
        workflow_id=workflow.id,
        tenant_key=workflow.tenant_key,
        owner_user_id=workflow.created_by,
        idempotency_key=f"workflow-plan:{workflow.id}:v{version}",
        requirement_version=version,
        requirements_snapshot=dict(workflow.requirements_snapshot or {}),
        revision_note=revision_note,
        status="queued",
    )
    db.add(job)
    return job


async def backfill_orphaned_planning_jobs(db: AsyncSession) -> int:
    """Repair pre-queue or partially migrated workflows stuck without a job."""
    workflows = list(
        (
            await db.execute(
                select(WorkflowDefinition)
                .join(
                    WorkflowClarificationSession,
                    WorkflowClarificationSession.workflow_id == WorkflowDefinition.id,
                )
                .outerjoin(
                    WorkflowPlanningJob,
                    WorkflowPlanningJob.workflow_id == WorkflowDefinition.id,
                )
                .where(
                    WorkflowDefinition.status == "planning",
                    WorkflowClarificationSession.phase == "planning",
                    WorkflowPlanningJob.id.is_(None),
                )
            )
        ).scalars().all()
    )
    for workflow in workflows:
        await enqueue_planning_job(db, workflow)
    if workflows:
        await db.commit()
    return len(workflows)


async def claim_next(db: AsyncSession, owner: str) -> WorkflowPlanningJob | None:
    current = utcnow()
    row = (
        await db.execute(
            select(WorkflowPlanningJob)
            .where(
                WorkflowPlanningJob.status.in_(["queued", "running"]),
                (WorkflowPlanningJob.lease_until.is_(None))
                | (WorkflowPlanningJob.lease_until < current),
            )
            .order_by(WorkflowPlanningJob.created_at)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    row.status = "running"
    row.attempt += 1
    row.lease_owner = owner
    row.lease_until = current + timedelta(seconds=LEASE_SECONDS)
    await db.commit()
    await db.refresh(row)
    return row


async def _fail_job(db: AsyncSession, job: WorkflowPlanningJob, message: str) -> None:
    workflow = await db.get(WorkflowDefinition, job.workflow_id)
    session = (
        await db.get(WorkflowClarificationSession, workflow.clarification_session_id)
        if workflow and workflow.clarification_session_id
        else None
    )
    job.error_message = message[:1000]
    job.lease_owner = None
    job.lease_until = None
    if workflow and session:
        workflow.status = "planning"
        if job.attempt < 3:
            job.status = "queued"
            session.phase = "planning"
            await append_event(
                db,
                workflow,
                session,
                "planning_retry_scheduled",
                "云端规划暂时中断，正在自动恢复",
                event_payload(
                    f"planning-retry-{job.id}-{job.attempt}",
                    "planner",
                    "queued",
                    detail=message[:300],
                    retry_attempt=job.attempt + 1,
                ),
            )
        else:
            job.status = "failed"
            session.phase = "needs_attention"
            await append_event(
                db,
                workflow,
                session,
                "planning_failed",
                "方案生成暂时失败，可安全重试",
                event_payload(
                    f"planning-failed-{job.id}",
                    "planner",
                    "failed",
                    detail=message[:300],
                ),
            )
    elif job.attempt < 3:
        job.status = "queued"
    else:
        job.status = "failed"
    await db.commit()


async def process_job(job_id: str, owner: str) -> None:
    try:
        async with SessionLocal() as db:
            job = await db.get(WorkflowPlanningJob, job_id)
            workflow = await db.get(WorkflowDefinition, job.workflow_id) if job else None
            session = (
                await db.get(WorkflowClarificationSession, workflow.clarification_session_id)
                if workflow and workflow.clarification_session_id
                else None
            )
            if not job or not workflow or not session:
                return
            workflow.status = "planning"
            session.phase = "planning"
            await append_event(
                db,
                workflow,
                session,
                "planning_worker_claimed",
                "云端规划器已接手任务",
                event_payload(
                    f"worker-claimed-{job.id}-{job.attempt}",
                    "planner",
                    "running",
                    tool="planning_worker",
                    detail="离开此页面不会中断",
                ),
            )
            scopes, allowed_agents, analysis_agent = await planning_context(db, workflow)
            await append_event(
                db,
                workflow,
                session,
                "planner_context_loaded",
                "已加载确认需求、技能与可用 Agent",
                event_payload(
                    f"context-{job.id}",
                    "skill_load",
                    "done",
                    tool="workflow_planner_context",
                    detail="确认需求快照、知识权限与 Agent 注册表",
                ),
            )
            await db.commit()
            request_body = {
                "planning_job_id": job.id,
                "idempotency_key": job.idempotency_key,
                "tenant_id": workflow.tenant_key,
                "workflow_id": workflow.id,
                "title": workflow.title,
                "description": workflow.description,
                "deliverable": workflow.desired_output,
                "knowledge_scope": scopes,
                "allowed_agents": allowed_agents,
                "allow_network": True,
                "max_tokens": WORKFLOW_TOKEN_BUDGET,
                "revision_note": job.revision_note,
            }

        if not HERMES_PLANNING_ENABLED:
            async with SessionLocal() as db:
                current_job = await db.get(WorkflowPlanningJob, job_id)
                workflow = await db.get(WorkflowDefinition, current_job.workflow_id)
                session = await db.get(
                    WorkflowClarificationSession, workflow.clarification_session_id
                )
                plan = await build_plan(db, workflow, revision_note=current_job.revision_note)
                current_job.plan_id = plan.id
                current_job.status = "completed"
                current_job.lease_owner = None
                current_job.lease_until = None
                session.phase = "awaiting_approval"
                workflow.status = "awaiting_approval"
                await append_event(
                    db,
                    workflow,
                    session,
                    "plan_ready",
                    "方案已生成，等待你的确认",
                    event_payload(
                        f"ready-{current_job.id}",
                        "planner",
                        "done",
                        plan_id=plan.id,
                    ),
                )
                await db.commit()
            return

        async with httpx.AsyncClient(timeout=httpx.Timeout(20)) as client:
            if not job.bridge_run_id:
                response = await client.post(
                    f"{bridge_base_url()}/v1/workflows/plans",
                    headers=bridge_headers(),
                    json=request_body,
                )
                response.raise_for_status()
                bridge_run_id = str(response.json()["run_id"])
                async with SessionLocal() as db:
                    current_job = await db.get(WorkflowPlanningJob, job_id)
                    current_job.bridge_run_id = bridge_run_id
                    await db.commit()
            else:
                bridge_run_id = job.bridge_run_id

            while True:
                response = await client.get(
                    f"{bridge_base_url()}/v1/workflows/plans/{bridge_run_id}/status",
                    headers=bridge_headers(),
                    params={"after": job.bridge_event_cursor},
                )
                response.raise_for_status()
                state = response.json()
                async with SessionLocal() as db:
                    current_job = await db.get(WorkflowPlanningJob, job_id)
                    workflow = await db.get(WorkflowDefinition, current_job.workflow_id)
                    session = await db.get(
                        WorkflowClarificationSession, workflow.clarification_session_id
                    )
                    for event in state.get("events") or []:
                        event_id = int(event.get("id") or 0)
                        if event_id <= current_job.bridge_event_cursor:
                            continue
                        await append_event(
                            db,
                            workflow,
                            session,
                            "planner_step",
                            str(event.get("message") or "规划步骤已更新"),
                            event_payload(
                                str(event.get("step_id") or f"bridge-{bridge_run_id}-{event_id}"),
                                str(event.get("category") or "planner"),
                                str(event.get("status") or "done"),
                                tool=str(event.get("tool") or ""),
                                detail=str(event.get("detail") or "")[:500],
                                source="hermes_reasoning_plugin",
                                bridge_event_id=event_id,
                            ),
                        )
                        current_job.bridge_event_cursor = event_id
                    current_job.lease_until = utcnow() + timedelta(seconds=LEASE_SECONDS)
                    job.bridge_event_cursor = current_job.bridge_event_cursor
                    status = str(state.get("status") or "running")
                    if status == "completed":
                        raw_plan = state.get("plan")
                        if not isinstance(raw_plan, dict):
                            raise ValueError("Hermes 未返回有效计划")
                        await append_event(
                            db,
                            workflow,
                            session,
                            "plan_compiling",
                            "正在执行 DAG 安全编译",
                            event_payload(
                                f"compile-{current_job.id}",
                                "tool_call",
                                "running",
                                tool="DSLSafetyCompiler",
                            ),
                        )
                        plan = await persist_raw_plan(
                            db,
                            workflow,
                            raw_plan,
                            scopes=scopes,
                            analysis_agent=analysis_agent,
                            revision_note=current_job.revision_note,
                        )
                        current_job.plan_id = plan.id
                        current_job.status = "completed"
                        current_job.lease_owner = None
                        current_job.lease_until = None
                        if plan.validation_errors:
                            session.phase = "needs_attention"
                            await append_event(
                                db,
                                workflow,
                                session,
                                "planning_failed",
                                "方案需要重新生成或调整",
                                event_payload(
                                    f"validation-{current_job.id}",
                                    "tool_call",
                                    "failed",
                                    tool="DSLSafetyCompiler",
                                    detail="；".join(plan.validation_errors)[:500],
                                ),
                            )
                        else:
                            session.phase = "awaiting_approval"
                            await append_event(
                                db,
                                workflow,
                                session,
                                "policy_validated",
                                "方案已通过权限与安全校验",
                                event_payload(
                                    f"policy-{current_job.id}",
                                    "tool_call",
                                    "done",
                                    tool="PlanPolicyValidator",
                                    detail="知识范围、联网权限与 Token 预算已校验",
                                ),
                            )
                            await append_event(
                                db,
                                workflow,
                                session,
                                "plan_ready",
                                "方案已生成，等待你的确认",
                                event_payload(
                                    f"ready-{current_job.id}",
                                    "planner",
                                    "done",
                                    plan_id=plan.id,
                                ),
                            )
                        await db.commit()
                        return
                    if status == "failed":
                        await db.commit()
                        await _fail_job(db, current_job, str(state.get("error") or "Hermes 规划失败"))
                        return
                    await db.commit()
                await asyncio.sleep(POLL_SECONDS)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        async with SessionLocal() as db:
            current_job = await db.get(WorkflowPlanningJob, job_id)
            if current_job:
                await _fail_job(db, current_job, str(exc))


async def worker_loop(poll_seconds: float = 2.0) -> None:
    await init_db()
    owner = f"planning:{socket.gethostname()}:{os.getpid()}"
    while True:
        async with SessionLocal() as db:
            await backfill_orphaned_planning_jobs(db)
            job = await claim_next(db, owner)
        if job:
            await process_job(job.id, owner)
        else:
            await asyncio.sleep(poll_seconds)


async def process_next_once(owner: str = "planning:test") -> bool:
    """Claim and process one job; useful for smoke tests and one-shot maintenance."""
    async with SessionLocal() as db:
        job = await claim_next(db, owner)
    if not job:
        return False
    await process_job(job.id, owner)
    return True
