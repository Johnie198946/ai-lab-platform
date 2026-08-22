"""Tenant-scoped executable workflow APIs."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.customer_demand import CustomerDemand
from backend.models.showroom import ShowroomSession
from backend.models.tenant_agent import AgentInvocationRelation, TenantAgentModel
from backend.models.tenant_agent_schema import WorkflowDSLPlan
from backend.models.workflow import (
    WorkflowApproval,
    WorkflowArtifact,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowClarificationSession,
    WorkflowLifecycleEvent,
    WorkflowNodeRun,
    WorkflowPlanningJob,
    WorkflowPlanVersion,
    WorkflowSessionMessage,
)
from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.workflow_artifacts import run_root, vault_root
from backend.services.workflow_executor import (
    cancel_remote,
    executable_plan_projection,
    read_bridge_run,
    retry_remote,
)
from backend.services.workflow_planner import validate_plan_policy
from backend.services.workflow_planning import (
    backfill_orphaned_planning_jobs,
    enqueue_planning_job,
    event_payload as planning_event_payload,
)
from backend.services.clarification_planner import request_bridge_clarification
from backend.services.capability_projection import project_plan_capability
from backend.services.ipd_scenario_registry import (
    is_registered_ipd_plan,
    validate_registered_ipd_execution_contract,
)
from backend.services.showroom_workflow_bridge import (
    build_customer_demand_seed,
    build_showroom_context_snapshot,
    seed_customer_demand_description,
    seed_workflow_description,
)
from backend.services.workflow_insights import (
    build_explain_context_snapshot,
    compile_evidence_bound_report,
)

router = APIRouter(prefix="/api/v1", tags=["workflows"])

def now() -> datetime:
    return datetime.now(timezone.utc)


def tenant() -> str:
    return current_tenant.get()


def uid(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


class WorkflowCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field(..., min_length=3, max_length=12000)
    desired_output: str = Field("研究报告（Markdown）", min_length=1, max_length=300)
    clarification_mode: str = Field("compatibility", pattern="^(compatibility|dynamic)$")
    showroom_session_id: str | None = Field(None, min_length=1, max_length=120)
    customer_demand_id: str | None = Field(None, min_length=1, max_length=48)


class ClarificationResponse(BaseModel):
    response: str = Field("", max_length=4000)
    intent: Literal["confirm", "revise"] | None = None


class PlanEdit(BaseModel):
    dsl: dict[str, Any]
    deliverable: str = Field(..., min_length=1, max_length=300)
    allow_network: bool = True
    max_tokens: int = Field(999999, ge=1000, le=999999)
    knowledge_scope: list[str] = []


class ReplanRequest(BaseModel):
    instruction: str = Field("", max_length=2000)


class ApprovalRequest(BaseModel):
    comment: str = Field("", max_length=2000)
    request_id: str | None = Field(None, min_length=8, max_length=160)


class OutputApprovalRequest(BaseModel):
    artifact_ids: list[str] = []
    comment: str = Field("", max_length=2000)


class RevisionRequest(BaseModel):
    node_id: str = Field(..., min_length=1, max_length=80)
    comment: str = Field(..., min_length=1, max_length=2000)


def plan_out(plan: WorkflowPlanVersion) -> dict[str, Any]:
    # Historical rows and rolling deployments may contain a partial DSL.  Keep
    # the wire contract complete so one missing nested field cannot make the
    # entire plan-review screen undecodable on iOS.
    dsl = dict(plan.dsl or {})
    dsl["plan_id"] = str(dsl.get("plan_id") or plan.id)
    dsl["name"] = str(dsl.get("name") or plan.goal or "执行计划")
    dsl["version"] = str(dsl.get("version") or "1.0.0")
    dsl["nodes"] = dsl.get("nodes") if isinstance(dsl.get("nodes"), list) else []
    dsl["edges"] = dsl.get("edges") if isinstance(dsl.get("edges"), list) else []
    checked_at = now()
    try:
        DSLSafetyCompiler.compile_and_validate(dsl)
        compiler_status = "compiled"
    except Exception:
        compiler_status = "invalid"
    capability = project_plan_capability(
        compiler_status=compiler_status,
        checked_at=checked_at,
        ttl_seconds=300,
        now=checked_at,
    )
    return {
        "id": plan.id,
        "workflow_id": plan.workflow_id,
        "version": plan.version,
        "goal": plan.goal,
        "deliverable": plan.deliverable,
        "allow_network": plan.allow_network,
        "max_tokens": plan.max_tokens,
        "estimated_tokens": plan.estimated_tokens,
        "knowledge_scope": plan.knowledge_scope or [],
        "validation_errors": plan.validation_errors or [],
        "dsl": dsl,
        "frozen_at": plan.frozen_at.isoformat() if plan.frozen_at else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
        "capability": capability,
    }


def workflow_out(row: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "desired_output": row.desired_output,
        "status": row.status,
        "active_plan_id": row.active_plan_id,
        "clarification_session_id": row.clarification_session_id,
        "requirements_snapshot": row.requirements_snapshot or {},
        "primary_agent_id": row.primary_agent_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def current_user(payload: dict[str, Any]) -> str:
    return str(payload.get("user_id") or payload.get("sub") or "")


def clarification_out(row: WorkflowClarificationSession) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "phase": row.phase,
        "round_number": row.round_number,
        "confirmed_spec": row.confirmed_spec or {},
        "last_event_seq": row.last_event_seq,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def session_message_out(row: WorkflowSessionMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "seq": row.seq,
        "role": row.role,
        "message_type": row.message_type,
        "content": row.content,
        "payload": row.payload or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def lifecycle_event_out(row: WorkflowLifecycleEvent) -> dict[str, Any]:
    return {
        "id": row.seq,
        "workflow_id": row.workflow_id,
        "session_id": row.session_id,
        "type": row.event_type,
        "message": row.message,
        "payload": row.payload or {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


async def append_lifecycle_event(
    db,
    workflow: WorkflowDefinition,
    session: WorkflowClarificationSession,
    event_type: str,
    message: str,
    payload: dict[str, Any] | None = None,
) -> WorkflowLifecycleEvent:
    session.last_event_seq += 1
    event = WorkflowLifecycleEvent(
        workflow_id=workflow.id,
        session_id=session.id,
        seq=session.last_event_seq,
        event_type=event_type,
        message=message,
        payload=payload or {},
    )
    db.add(event)
    return event


async def append_session_message(
    db,
    session: WorkflowClarificationSession,
    *,
    role: str,
    content: str,
    message_type: str = "text",
    payload: dict[str, Any] | None = None,
) -> WorkflowSessionMessage:
    next_seq = int(
        (
            await db.execute(
                select(func.coalesce(func.max(WorkflowSessionMessage.seq), 0)).where(
                    WorkflowSessionMessage.session_id == session.id
                )
            )
        ).scalar_one()
    ) + 1
    row = WorkflowSessionMessage(
        id=uid("wfm"),
        session_id=session.id,
        seq=next_seq,
        role=role,
        message_type=message_type,
        content=content,
        payload=payload or {},
    )
    db.add(row)
    return row


def execution_out(
    row: WorkflowExecution, nodes: list[WorkflowNodeRun] | None = None
) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "plan_id": row.plan_id,
        "status": row.status,
        "truth": "LIVE",
        "progress": row.progress,
        "token_budget": row.token_budget,
        "token_used": row.token_used,
        "input_tokens": row.input_tokens,
        "output_tokens": row.output_tokens,
        "reasoning_tokens": row.reasoning_tokens,
        "cache_read_tokens": row.cache_read_tokens,
        "cache_write_tokens": row.cache_write_tokens,
        "api_calls": row.api_calls,
        "estimated_cost_usd": row.estimated_cost_usd,
        "model_used": row.model_used,
        "provider_used": row.provider_used,
        "route_reason": row.route_reason,
        "hermes_session_id": row.hermes_session_id,
        "artifact_count": row.artifact_count,
        "error_message": row.error_message,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "nodes": [
            {
                "id": node.id,
                "node_id": node.node_id,
                "node_type": node.node_type,
                "name": node.name,
                "agent_id": node.agent_id,
                "status": node.status,
                "position": node.position,
                "attempt": node.attempt,
                "max_tokens": node.max_tokens,
                "token_used": node.token_used,
                "input_tokens": node.input_tokens,
                "output_tokens": node.output_tokens,
                "reasoning_tokens": node.reasoning_tokens,
                "cache_read_tokens": node.cache_read_tokens,
                "cache_write_tokens": node.cache_write_tokens,
                "api_calls": node.api_calls,
                "estimated_cost_usd": node.estimated_cost_usd,
                "model_used": node.model_used,
                "provider_used": node.provider_used,
                "output_summary": node.output_summary,
                "error_message": node.error_message,
            }
            for node in (nodes or [])
        ],
    }


async def owned_workflow(
    db, workflow_id: str, payload: dict[str, Any]
) -> WorkflowDefinition:
    row = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                WorkflowDefinition.tenant_key == tenant(),
                WorkflowDefinition.archived_at.is_(None),
            )
        )
    ).scalar_one_or_none()
    if row is None or (
        row.clarification_session_id
        and row.created_by != current_user(payload)
    ):
        raise HTTPException(status_code=404, detail="工作流不存在")
    return row


async def owned_clarification(
    db, workflow: WorkflowDefinition, payload: dict[str, Any]
) -> WorkflowClarificationSession:
    row = (
        await db.execute(
            select(WorkflowClarificationSession).where(
                WorkflowClarificationSession.workflow_id == workflow.id,
                WorkflowClarificationSession.tenant_key == tenant(),
                WorkflowClarificationSession.owner_user_id == current_user(payload),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="任务澄清会话不存在")
    return row


CLARIFICATION_STEPS: tuple[dict[str, Any], ...] = (
    {
        "dimension": "目标用户与场景",
        "question": "这项任务主要服务谁，最核心的使用场景是什么？",
        "choices": ["单个学习者/个人使用", "团队或班级协作", "组织级规模化使用"],
    },
    {
        "dimension": "MVP 范围",
        "question": "第一阶段最需要优先保证什么？",
        "choices": ["先完成可验证的核心闭环", "优先覆盖完整功能", "优先保证自动化与规模化"],
    },
    {
        "dimension": "约束与验收",
        "question": "你希望用什么标准判断这项任务已经成功？",
        "choices": ["交付物完整且可直接使用", "关键指标有明确提升", "通过人工复核与安全检查"],
    },
)


def clarification_payload(index: int) -> dict[str, Any]:
    step = CLARIFICATION_STEPS[index]
    return {
        "question": step["question"],
        "choices": step["choices"],
        "multi_select": False,
        "dimension": step["dimension"],
        "submit_label": "确认并继续",
        "source": "fallback",
        "truth": "UNCONNECTED",
        "simulation": True,
    }


async def dynamic_clarification_payload(
    goal: str,
    transcript: list[dict[str, Any]],
    *,
    tenant_id: str,
    workflow_id: str,
) -> dict[str, Any]:
    result = await request_bridge_clarification(
        goal,
        transcript,
        tenant_id=tenant_id,
        workflow_id=workflow_id,
    )
    return {
        "question": result.get("question", ""),
        "choices": [],
        "multi_select": False,
        "dimension": result.get("dimension", "missing requirement"),
        "submit_label": "确认并继续",
        "source": result.get("source", "fallback"),
        "truth": result.get("truth", "UNCONNECTED"),
        "simulation": bool(result.get("simulation", False)),
        "status": result.get("status", "question"),
        "usage": result.get("usage", {}),
    }


def requirement_is_explicit(description: str) -> bool:
    """Conservatively skip questions only when the request covers key dimensions."""
    text = description.lower()
    signals = (
        any(word in text for word in ("用户", "使用者", "场景", "对象", "audience")),
        any(word in text for word in ("范围", "第一阶段", "mvp", "包含", "不包含", "scope")),
        any(word in text for word in ("约束", "必须", "不能", "预算", "时间", "平台", "constraint")),
        any(word in text for word in ("验收", "成功标准", "完成标准", "指标", "acceptance")),
        any(word in text for word in ("数据", "知识库", "接口", "集成", "integration")),
    )
    return len(description.strip()) >= 120 and sum(signals) >= 4


def requirement_confirmation_payload(
    workflow: WorkflowDefinition, answers: list[str]
) -> dict[str, Any]:
    details = [
        f"目标：{workflow.description.split('已确认需求：', 1)[0].strip()}",
        f"交付物：{workflow.desired_output}",
    ]
    core_answers = answers[:3] if len(answers) >= 3 else []
    for index, step in enumerate(CLARIFICATION_STEPS):
        answer = core_answers[index] if index < len(core_answers) else "按当前描述与平台默认建议"
        details.append(f"{step['dimension']}：{answer}")
    revision_source = answers[3:] if core_answers else answers
    revisions = [answer for answer in revision_source if answer != "需要修改"]
    if revisions:
        details.append(f"补充修改：{'；'.join(revisions)}")
    return {
        "question": "请确认需求单：\n" + "\n".join(details),
        "choices": ["确认，进入方案设计", "需要修改"],
        "multi_select": False,
        "dimension": "最终确认",
        "submit_label": "确认选择",
    }


def confirmation_intent(response: str, explicit: str | None = None) -> str:
    """Resolve the two-value confirmation gate; explicit UI intent always wins."""
    if explicit:
        return explicit
    normalized = re.sub(r"[\s，。！!？?、]", "", response.lower())
    if any(term in normalized for term in (
        "修改", "需要改", "不确认", "不可以", "不要", "不能", "先别", "暂不",
        "不进入", "不开始", "暂停", "拒绝",
    )):
        return "revise"
    if normalized in {"是的", "可以", "开始", "没有了开始后面流程"}:
        return "confirm"
    if response.startswith("确认") or "进入方案" in response:
        return "confirm"
    return "revise"


async def resume_pending_planning() -> None:
    """Backfill a durable job for pre-queue deployments; workers own execution."""
    async with SessionLocal() as db:
        await backfill_orphaned_planning_jobs(db)


async def owned_execution(
    db, execution_id: str, payload: dict[str, Any]
) -> WorkflowExecution:
    row = (
        await db.execute(
            select(WorkflowExecution).where(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.tenant_key == tenant(),
            )
        )
    ).scalar_one_or_none()
    workflow = await db.get(WorkflowDefinition, row.workflow_id) if row else None
    if row is None or workflow is None or (
        workflow.clarification_session_id
        and workflow.created_by != current_user(payload)
    ):
        raise HTTPException(status_code=404, detail="工作流执行不存在")
    return row


@router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowCreate, payload: dict = Depends(require_auth)):
    workflow_id = uid("wf")
    session_id = uid("wfs")
    async with SessionLocal() as db:
        description = body.description.strip()
        requirements_snapshot: dict[str, Any] = {
            "clarification_mode": body.clarification_mode
        }
        if body.showroom_session_id and body.customer_demand_id:
            raise HTTPException(status_code=422, detail="只能续接一个客户上下文")
        if body.showroom_session_id:
            showroom = (
                await db.execute(
                    select(ShowroomSession).where(
                        ShowroomSession.session_id == body.showroom_session_id,
                        ShowroomSession.tenant_key == tenant(),
                        ShowroomSession.slot == "main",
                    )
                )
            ).scalar_one_or_none()
            if showroom is None:
                raise HTTPException(status_code=404, detail="体验会话不存在")
            showroom_context = build_showroom_context_snapshot(
                showroom.session_id, showroom.data or {}
            )
            requirements_snapshot["showroom_context"] = showroom_context
            description = seed_workflow_description(
                description, showroom_context
            )[:12_000]
        elif body.customer_demand_id:
            demand = (
                await db.execute(
                    select(CustomerDemand).where(
                        CustomerDemand.demand_id == body.customer_demand_id,
                        CustomerDemand.tenant_key == tenant(),
                    )
                )
            ).scalar_one_or_none()
            if demand is None:
                raise HTTPException(status_code=404, detail="客户需求不存在")
            if demand.status != "confirmed":
                raise HTTPException(status_code=409, detail="客户需求尚未人工确认")
            demand_context = build_customer_demand_seed(demand)
            requirements_snapshot["customer_demand"] = demand_context
            description = seed_customer_demand_description(
                description, demand_context
            )[:12_000]

        explicit = requirement_is_explicit(description)
        row = WorkflowDefinition(
            id=workflow_id,
            tenant_key=tenant(),
            created_by=current_user(payload),
            title=body.title.strip(),
            description=description,
            desired_output=body.desired_output.strip(),
            status="clarifying",
            clarification_session_id=session_id,
            requirements_snapshot=requirements_snapshot,
        )
        clarification = WorkflowClarificationSession(
            id=session_id,
            workflow_id=workflow_id,
            tenant_key=tenant(),
            owner_user_id=current_user(payload),
            phase="awaiting_requirement_confirmation" if explicit else "clarifying",
            round_number=3 if explicit else 1,
        )
        db.add(row)
        # The session references workflows.id but there is no ORM relationship
        # between these two independently constructed rows.  Flush the parent
        # explicitly so PostgreSQL cannot order the child INSERT first.
        await db.flush()
        db.add(clarification)
        await db.flush()
        await append_session_message(
            db,
            clarification,
            role="user",
            content=description,
        )
        if not explicit and body.clarification_mode == "dynamic":
            clarification.phase = "clarifying_pending"
            row.status = "clarifying_pending"
            await db.commit()
            first = await dynamic_clarification_payload(
                description,
                [{"role": "user", "content": description}],
                tenant_id=row.tenant_key,
                workflow_id=row.id,
            )
            await db.refresh(row)
            await db.refresh(clarification)
            if first["status"] == "READY":
                first = requirement_confirmation_payload(row, [])
                first.update({"source": "hermes", "truth": "LIVE", "status": "READY", "simulation": False})
                clarification.phase = "awaiting_requirement_confirmation"
                row.status = "clarifying"
                first_message_type = "requirement_confirmation"
                first_event_type = "requirement_summary_ready"
            elif first["status"] == "ERROR":
                clarification.phase = "needs_attention"
                row.status = "needs_attention"
                first_message_type = "status"
                first_event_type = "clarification_unavailable"
            else:
                clarification.phase = "clarifying"
                row.status = "clarifying"
                first_message_type = "clarify"
                first_event_type = "clarify_requested"
        else:
            first = (
                requirement_confirmation_payload(row, [])
                if explicit
                else clarification_payload(0)
            )
            first_message_type = "requirement_confirmation" if explicit else "clarify"
            first_event_type = "requirement_summary_ready" if explicit else "clarify_requested"
        await append_session_message(
            db,
            clarification,
            role="assistant",
            content=first["question"],
            message_type=first_message_type,
            payload=first,
        )
        await append_lifecycle_event(
            db,
            row,
            clarification,
            "clarification_started",
            "已创建任务草稿，开始澄清需求",
        )
        await append_lifecycle_event(
            db,
            row,
            clarification,
            first_event_type,
            "需求描述已足够明确，请确认需求单" if explicit else first["question"],
            first,
        )
        await db.commit()
        await db.refresh(row)
        await db.refresh(clarification)
        return {
            "workflow": workflow_out(row),
            "clarification_session": clarification_out(clarification),
        }


@router.get("/workflows/{workflow_id}/clarification")
async def get_clarification(
    workflow_id: str, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        session = await owned_clarification(db, workflow, payload)
        messages = list(
            (
                await db.execute(
                    select(WorkflowSessionMessage)
                    .where(WorkflowSessionMessage.session_id == session.id)
                    .order_by(WorkflowSessionMessage.seq)
                )
            ).scalars().all()
        )
        events = list(
            (
                await db.execute(
                    select(WorkflowLifecycleEvent)
                    .where(WorkflowLifecycleEvent.workflow_id == workflow.id)
                    .order_by(WorkflowLifecycleEvent.seq)
                )
            ).scalars().all()
        )
        return {
            "workflow": workflow_out(workflow),
            "session": clarification_out(session),
            "messages": [session_message_out(item) for item in messages],
            "events": [lifecycle_event_out(item) for item in events],
        }


@router.post("/workflows/{workflow_id}/clarification/respond")
async def respond_to_clarification(
    workflow_id: str,
    body: ClarificationResponse,
    payload: dict = Depends(require_auth),
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        session = await owned_clarification(db, workflow, payload)
        session = (
            await db.execute(
                select(WorkflowClarificationSession)
                .where(WorkflowClarificationSession.id == session.id)
                .with_for_update()
                .execution_options(populate_existing=True)
            )
        ).scalar_one()
        response = body.response.strip()
        resolved_intent = confirmation_intent(response, body.intent)
        if session.phase == "planning" and resolved_intent == "confirm":
            return clarification_out(session)
        if session.phase not in {"clarifying", "awaiting_requirement_confirmation"}:
            raise HTTPException(status_code=409, detail="当前阶段不接受澄清回复")
        if not response and body.intent is None:
            raise HTTPException(status_code=422, detail="澄清回复不能为空")
        await append_session_message(db, session, role="user", content=response)

        dynamic_mode = (workflow.requirements_snapshot or {}).get("clarification_mode") == "dynamic"
        if dynamic_mode and session.phase == "clarifying":
            session.phase = "clarifying_pending"
            workflow.status = "clarifying_pending"
            await db.commit()
            transcript_rows = list((await db.execute(
                select(WorkflowSessionMessage)
                .where(WorkflowSessionMessage.session_id == session.id)
                .order_by(WorkflowSessionMessage.seq)
            )).scalars().all())
            decision = await dynamic_clarification_payload(
                workflow.description,
                [{"role": item.role, "content": item.content} for item in transcript_rows],
                tenant_id=workflow.tenant_key,
                workflow_id=workflow.id,
            )
            await db.refresh(workflow)
            await db.refresh(session)
            if decision["status"] == "READY":
                session.phase = "awaiting_requirement_confirmation"
                workflow.status = "clarifying"
                decision = requirement_confirmation_payload(workflow, [item.content for item in transcript_rows if item.role == "user"][1:])
                decision.update({"source": "hermes", "truth": "LIVE", "status": "READY", "simulation": False})
                message_type = "requirement_confirmation"
                event_type = "requirement_summary_ready"
            elif decision["status"] == "ERROR":
                session.phase = "needs_attention"
                workflow.status = "needs_attention"
                message_type = "status"
                event_type = "clarification_unavailable"
            else:
                session.phase = "clarifying"
                workflow.status = "clarifying"
                session.round_number += 1
                message_type = "clarify"
                event_type = "clarify_requested"
            await append_session_message(db, session, role="assistant", content=decision["question"], message_type=message_type, payload=decision)
            await append_lifecycle_event(db, workflow, session, event_type, decision["question"], decision)
            await db.commit()
            await db.refresh(session)
            return clarification_out(session)

        if session.phase == "awaiting_requirement_confirmation":
            if resolved_intent == "confirm":
                answer_rows = list(
                    (
                        await db.execute(
                            select(WorkflowSessionMessage)
                            .where(
                                WorkflowSessionMessage.session_id == session.id,
                                WorkflowSessionMessage.role == "user",
                            )
                            .order_by(WorkflowSessionMessage.seq)
                        )
                    ).scalars().all()
                )
                answers = [item.content for item in answer_rows[1:-1]][:5]
                core_answers = answers[:3] if len(answers) >= 3 else []
                revision_source = answers[3:] if core_answers else answers
                revision_answers = [
                    answer for answer in revision_source if answer != "需要修改"
                ]
                spec = {
                    "goal": workflow.description,
                    "deliverable": workflow.desired_output,
                    "dimensions": [
                        {
                            "name": step["dimension"],
                            "answer": core_answers[index] if index < len(core_answers) else "按默认建议",
                        }
                        for index, step in enumerate(CLARIFICATION_STEPS)
                    ],
                    "revision_notes": revision_answers,
                }
                session.confirmed_spec = spec
                session.phase = "planning"
                workflow.requirements_snapshot = spec
                workflow.description = workflow.description + "\n\n已确认需求：\n" + "\n".join(
                    f"- {item['name']}：{item['answer']}" for item in spec["dimensions"]
                )
                workflow.status = "planning"
                await append_session_message(
                    db,
                    session,
                    role="assistant",
                    content="需求已确认，正在生成可审阅方案。",
                    message_type="status",
                    payload={"phase": "planning"},
                )
                await append_lifecycle_event(
                    db,
                    workflow,
                    session,
                    "requirements_confirmed",
                    "需求确认单已锁定",
                    planning_event_payload(
                        f"requirements-{workflow.id}",
                        "requirements",
                        "done",
                        detail="结构化需求快照已冻结",
                        spec=spec,
                    ),
                )
                job = await enqueue_planning_job(db, workflow)
                await append_lifecycle_event(
                    db,
                    workflow,
                    session,
                    "planning_queued",
                    "规划请求已提交到云端",
                    planning_event_payload(
                        f"queued-{job.id}",
                        "planner",
                        "queued",
                        tool="planning_queue",
                        detail="离开此页面不会中断",
                        planning_job_id=job.id,
                    ),
                )
            else:
                session.phase = "clarifying"
                session.round_number = 3
                workflow.status = "clarifying"
                payload_out = {
                    "question": "请说明需要修改的具体内容。",
                    "choices": [],
                    "multi_select": False,
                    "dimension": "修改项",
                    "submit_label": "提交修改",
                }
                await append_session_message(
                    db,
                    session,
                    role="assistant",
                    content=payload_out["question"],
                    message_type="clarify",
                    payload=payload_out,
                )
                await append_lifecycle_event(
                    db, workflow, session, "clarify_requested", payload_out["question"], payload_out
                )
        elif session.round_number < len(CLARIFICATION_STEPS):
            session.round_number += 1
            question = clarification_payload(session.round_number - 1)
            await append_session_message(
                db,
                session,
                role="assistant",
                content=question["question"],
                message_type="clarify",
                payload=question,
            )
            await append_lifecycle_event(
                db, workflow, session, "clarify_requested", question["question"], question
            )
        else:
            session.phase = "awaiting_requirement_confirmation"
            answer_rows = list(
                (
                    await db.execute(
                        select(WorkflowSessionMessage)
                        .where(
                            WorkflowSessionMessage.session_id == session.id,
                            WorkflowSessionMessage.role == "user",
                        )
                        .order_by(WorkflowSessionMessage.seq)
                    )
                ).scalars().all()
            )
            summary = requirement_confirmation_payload(
                workflow, [item.content for item in answer_rows[1:]]
            )
            await append_session_message(
                db,
                session,
                role="assistant",
                content=summary["question"],
                message_type="requirement_confirmation",
                payload=summary,
            )
            await append_lifecycle_event(
                db,
                workflow,
                session,
                "requirement_summary_ready",
                "需求确认单已生成",
                summary,
            )
        await db.commit()
        await db.refresh(session)
        result = clarification_out(session)
    return result


@router.get("/workflows/{workflow_id}/lifecycle-events")
async def workflow_lifecycle_events(
    workflow_id: str,
    after: int = Query(0, ge=0),
    format: str = Query("sse", pattern="^(sse|json)$"),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    payload: dict = Depends(require_auth),
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        await owned_clarification(db, workflow, payload)
    cursor = max(after, int(last_event_id or 0) if str(last_event_id or "").isdigit() else 0)

    if format == "json":
        async with SessionLocal() as db:
            rows = list((await db.execute(select(WorkflowLifecycleEvent).where(WorkflowLifecycleEvent.workflow_id == workflow_id, WorkflowLifecycleEvent.seq > max(after, int(last_event_id or 0) if str(last_event_id or "").isdigit() else 0)).order_by(WorkflowLifecycleEvent.seq))).scalars().all())
            return [lifecycle_event_out(row) for row in rows]

    async def stream():
        nonlocal cursor
        idle_ticks = 0
        while idle_ticks < 600:
            async with SessionLocal() as db:
                rows = list(
                    (
                        await db.execute(
                            select(WorkflowLifecycleEvent)
                            .where(
                                WorkflowLifecycleEvent.workflow_id == workflow_id,
                                WorkflowLifecycleEvent.seq > cursor,
                            )
                            .order_by(WorkflowLifecycleEvent.seq)
                        )
                    ).scalars().all()
                )
                session = (
                    await db.execute(
                        select(WorkflowClarificationSession).where(
                            WorkflowClarificationSession.workflow_id == workflow_id
                        )
                    )
                ).scalar_one_or_none()
            if rows:
                idle_ticks = 0
                for row in rows:
                    cursor = row.seq
                    yield f"id: {row.seq}\ndata: {json.dumps(lifecycle_event_out(row), ensure_ascii=False)}\n\n"
            else:
                idle_ticks += 1
                if idle_ticks % 15 == 0:
                    yield ": keepalive\n\n"
            if session and session.phase in {"awaiting_approval", "agent_ready", "needs_attention"} and not rows:
                return
            await asyncio.sleep(1)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.get("/workflow-activities/active")
async def active_workflow_activities(payload: dict = Depends(require_auth)):
    """Bootstrap resumable planning/building activities for an app foreground."""
    async with SessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(WorkflowDefinition, WorkflowClarificationSession)
                    .join(
                        WorkflowClarificationSession,
                        WorkflowClarificationSession.workflow_id == WorkflowDefinition.id,
                    )
                    .where(
                        WorkflowDefinition.tenant_key == tenant(),
                        WorkflowDefinition.created_by == current_user(payload),
                        WorkflowDefinition.archived_at.is_(None),
                        WorkflowClarificationSession.phase.in_(
                            ["planning", "building_agent", "awaiting_approval", "needs_attention"]
                        ),
                    )
                    .order_by(WorkflowDefinition.updated_at.desc())
                )
            ).all()
        )
        result = []
        for workflow, session in rows:
            latest = (
                await db.execute(
                    select(WorkflowLifecycleEvent)
                    .where(WorkflowLifecycleEvent.workflow_id == workflow.id)
                    .order_by(WorkflowLifecycleEvent.seq.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            result.append(
                {
                    "workflow": workflow_out(workflow),
                    "session": clarification_out(session),
                    "latest_event": lifecycle_event_out(latest) if latest else None,
                }
            )
        return result


@router.get("/workflows")
async def list_workflows(payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        rows = list(
            (
                await db.execute(
                    select(WorkflowDefinition)
                    .where(
                        WorkflowDefinition.tenant_key == tenant(),
                        WorkflowDefinition.archived_at.is_(None),
                    )
                    .order_by(WorkflowDefinition.updated_at.desc())
                )
            )
            .scalars()
            .all()
        )
        result = []
        for row in rows:
            if (
                row.clarification_session_id
                and row.created_by != current_user(payload)
            ):
                continue
            latest = (
                await db.execute(
                    select(WorkflowExecution)
                    .where(WorkflowExecution.workflow_id == row.id)
                    .order_by(WorkflowExecution.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            item = workflow_out(row)
            item["latest_execution"] = execution_out(latest) if latest else None
            if row.primary_agent_id:
                agent = await db.get(TenantAgentModel, row.primary_agent_id)
                if agent and (
                    agent.visibility != "private"
                    or agent.owner_user_id == current_user(payload)
                ):
                    item["agent"] = task_agent_out(agent)
            result.append(item)
        return result


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        row = await owned_workflow(db, workflow_id, payload)
        latest = (
            await db.execute(
                select(WorkflowExecution)
                .where(WorkflowExecution.workflow_id == row.id)
                .order_by(WorkflowExecution.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        result = workflow_out(row)
        result["latest_execution"] = execution_out(latest) if latest else None
        if row.primary_agent_id:
            agent = await db.get(TenantAgentModel, row.primary_agent_id)
            if agent and (
                agent.visibility != "private"
                or agent.owner_user_id == current_user(payload)
            ):
                result["agent"] = task_agent_out(agent)
        return result


@router.delete("/workflows/{workflow_id}", status_code=204)
async def delete_workflow(
    workflow_id: str,
    payload: dict = Depends(require_auth),
) -> Response:
    """Soft-delete a user-owned workflow while retaining its audit trail."""
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        if workflow.created_by != current_user(payload):
            raise HTTPException(status_code=404, detail="工作流不存在")
        executions = list(
            (
                await db.execute(
                    select(WorkflowExecution).where(
                        WorkflowExecution.workflow_id == workflow.id,
                        WorkflowExecution.status.in_(
                            ["queued", "running", "awaiting_review"]
                        ),
                    )
                )
            )
            .scalars()
            .all()
        )
        for execution in executions:
            if execution.status == "running":
                try:
                    await cancel_remote(execution.id)
                except Exception:
                    pass
            execution.status = "cancelled"
            execution.finished_at = now()
            execution.lease_owner = None
            execution.lease_until = None

        planning_jobs = list(
            (
                await db.execute(
                    select(WorkflowPlanningJob).where(
                        WorkflowPlanningJob.workflow_id == workflow.id,
                        WorkflowPlanningJob.status.in_(["queued", "running"]),
                    )
                )
            )
            .scalars()
            .all()
        )
        for job in planning_jobs:
            job.status = "cancelled"
            job.lease_owner = None
            job.lease_until = None

        session = (
            await db.execute(
                select(WorkflowClarificationSession).where(
                    WorkflowClarificationSession.workflow_id == workflow.id
                )
            )
        ).scalar_one_or_none()
        if session is not None:
            session.phase = "archived"

        workflow.status = "archived"
        workflow.archived_at = now()
        await db.commit()
    return Response(status_code=204)


@router.get("/workflows/{workflow_id}/plan")
async def get_plan(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        if not workflow.active_plan_id:
            raise HTTPException(status_code=404, detail="执行计划尚未生成")
        plan = (
            await db.execute(
                select(WorkflowPlanVersion).where(
                    WorkflowPlanVersion.id == workflow.active_plan_id
                )
            )
        ).scalar_one()
        return plan_out(plan)


@router.patch("/workflows/{workflow_id}/plan")
async def edit_plan(
    workflow_id: str, body: PlanEdit, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        if workflow.status not in {"awaiting_approval", "draft", "planning"}:
            raise HTTPException(
                status_code=409, detail="已确认计划不能直接修改，请创建新版本"
            )
        try:
            compiled: WorkflowDSLPlan = DSLSafetyCompiler.compile_and_validate(body.dsl)
            current_plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
            if current_plan is not None and is_registered_ipd_plan(current_plan.dsl or {}):
                validate_registered_ipd_execution_contract(compiled.model_dump(mode="json"))
            await validate_plan_policy(
                db,
                tenant(),
                compiled,
                allow_network=body.allow_network,
                max_tokens=body.max_tokens,
                knowledge_scope=body.knowledge_scope,
                owner_user_id=current_user(payload),
            )
        except Exception as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        version = (
            int(
                (
                    await db.execute(
                        select(func.count(WorkflowPlanVersion.id)).where(
                            WorkflowPlanVersion.workflow_id == workflow.id
                        )
                    )
                ).scalar_one()
            )
            + 1
        )
        plan = WorkflowPlanVersion(
            id=uid("wfp"),
            workflow_id=workflow.id,
            version=version,
            dsl=compiled.model_dump(mode="json"),
            goal=workflow.description,
            deliverable=body.deliverable,
            allow_network=body.allow_network,
            max_tokens=body.max_tokens,
            estimated_tokens=sum(
                int(node.parameters.get("max_tokens", 0)) for node in compiled.nodes
            ),
            knowledge_scope=body.knowledge_scope,
            validation_errors=[],
        )
        db.add(plan)
        workflow.active_plan_id = plan.id
        workflow.desired_output = body.deliverable
        workflow.status = "awaiting_approval"
        await db.commit()
        await db.refresh(plan)
        return plan_out(plan)


@router.post("/workflows/{workflow_id}/replan")
async def replan(
    workflow_id: str, body: ReplanRequest, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        session = await owned_clarification(db, workflow, payload)
        if workflow.status in {"archived"}:
            raise HTTPException(status_code=409, detail="已归档工作流不能重新规划")
        if session.phase == "planning":
            raise HTTPException(status_code=409, detail="同一规划任务已经在运行")
        instruction = body.instruction.strip()
        snapshot = dict(workflow.requirements_snapshot or {})
        snapshot["revision_instruction"] = instruction or "按现有确认需求重新生成"
        workflow.requirements_snapshot = snapshot
        workflow.status = "planning"
        session.phase = "planning"
        await append_lifecycle_event(
            db,
            workflow,
            session,
            "replan_requested",
            "已收到修改意见，准备重新生成方案",
            {"instruction": instruction},
        )
        await enqueue_planning_job(
            db, workflow, revision_note=instruction or "按现有确认需求重新生成", force_new=True
        )
        await db.commit()
        await db.refresh(session)
        result = clarification_out(session)
    return result


@router.post("/workflows/{workflow_id}/planning/retry")
async def retry_planning(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        session = await owned_clarification(db, workflow, payload)
        if session.phase != "needs_attention":
            raise HTTPException(status_code=409, detail="当前阶段不需要重试规划")
        instruction = str(
            (workflow.requirements_snapshot or {}).get("revision_instruction")
            or "规划失败后安全重试"
        )
        snapshot = dict(workflow.requirements_snapshot or {})
        snapshot["revision_instruction"] = instruction
        workflow.requirements_snapshot = snapshot
        workflow.status = "planning"
        session.phase = "planning"
        await append_lifecycle_event(
            db,
            workflow,
            session,
            "planning_retry_scheduled",
            "已安排同一规划任务重试",
            planning_event_payload(
                f"retry-{workflow.id}-{session.last_event_seq + 1}",
                "planner",
                "queued",
                tool="planning_queue",
                detail="将从已确认需求重新生成，不重复提交执行任务",
            ),
        )
        await enqueue_planning_job(
            db, workflow, revision_note=instruction, force_new=True
        )
        await db.commit()
        await db.refresh(session)
        result = clarification_out(session)
    return result


@router.post("/workflows/{workflow_id}/clarification/reopen")
async def reopen_clarification(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        session = await owned_clarification(db, workflow, payload)
        if session.phase not in {"needs_attention", "clarifying_pending"}:
            raise HTTPException(status_code=409, detail="当前阶段不能继续澄清")
        session.phase = "clarifying"
        session.round_number = len(CLARIFICATION_STEPS)
        workflow.status = "clarifying"
        question = {
            "question": "方案生成未完成。请补充或修正需求，我们会据此重新生成需求确认单。",
            "choices": [],
            "multi_select": False,
            "dimension": "补充澄清",
            "submit_label": "提交补充",
        }
        await append_session_message(
            db,
            session,
            role="assistant",
            content=question["question"],
            message_type="clarify",
            payload=question,
        )
        await append_lifecycle_event(
            db, workflow, session, "clarification_reopened", "已返回需求澄清阶段"
        )
        await db.commit()
        await db.refresh(session)
        return clarification_out(session)


def task_agent_out(row: TenantAgentModel) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "owner_user_id": row.owner_user_id,
        "origin_workflow_id": row.origin_workflow_id,
        "base_agent_id": row.base_agent_id,
        "custom_name": row.custom_name,
        "private_prompt_delta": row.private_prompt_delta,
        "subscribed_knowledge_packs": row.subscribed_knowledge_packs or [],
        "visibility": row.visibility,
        "composition_manifest": row.composition_manifest or {},
        "is_active": row.is_active,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def bounded_platform_int(name: str, default: int, lower: int, upper: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)))
    except ValueError:
        value = default
    return max(lower, min(upper, value))


def compose_task_agent(workflow: WorkflowDefinition, plan: WorkflowPlanVersion) -> dict[str, Any]:
    nodes = list((plan.dsl or {}).get("nodes") or [])
    node_types = {str(item.get("node_type") or "") for item in nodes}
    goal = f"{workflow.description} {workflow.desired_output}".lower()
    capabilities = ["main_agent"]
    if "KNOWLEDGE_RETRIEVAL" in node_types:
        capabilities.append("knowledge")
    if any(word in goal for word in ("代码", "开发", "编程", "测试", "app", "ios", "网站")):
        capabilities.append("coder")
    if "FILTER_PASS" in node_types or any(
        word in goal for word in ("审核", "风控", "安全", "合规")
    ):
        capabilities.append("supervision")
    baseline = {"main_agent", "knowledge", "coder", "supervision"}
    referenced = {
        str((item.get("parameters") or {}).get("agent_id") or "") for item in nodes
    }
    for agent_id in ("knowledge", "coder", "supervision"):
        if agent_id in referenced and agent_id not in capabilities:
            capabilities.append(agent_id)
    invoked_agents = sorted(
        referenced
        - baseline
        - {""}
    )
    max_concurrent_children = bounded_platform_int(
        "WORKFLOW_DELEGATION_MAX_CONCURRENT", 3, 1, 8
    )
    max_spawn_depth = bounded_platform_int(
        "WORKFLOW_DELEGATION_MAX_DEPTH", 1, 0, 3
    )
    return {
        "capability_agent_ids": capabilities,
        "invoked_agent_ids": invoked_agents,
        "delegation": {
            "max_concurrent_children": max_concurrent_children,
            "max_spawn_depth": max_spawn_depth,
        },
        "knowledge_scope": plan.knowledge_scope or [],
        "plan_id": plan.id,
    }


@router.post("/workflows/{workflow_id}/approve-plan", status_code=201)
async def approve_plan(
    workflow_id: str, body: ApprovalRequest, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        if not workflow.active_plan_id:
            raise HTTPException(status_code=409, detail="当前没有待确认的计划")
        if workflow.status not in {"awaiting_approval", "agent_ready"}:
            raise HTTPException(status_code=409, detail="当前没有待确认的计划")
        plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
        if plan is None or plan.validation_errors:
            raise HTTPException(status_code=409, detail="计划校验未通过，不能构建 Agent")
        existing = (
            await db.execute(
                select(TenantAgentModel).where(
                    TenantAgentModel.origin_workflow_id == workflow.id,
                    TenantAgentModel.owner_user_id == current_user(payload),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            return {"workflow": workflow_out(workflow), "agent": task_agent_out(existing)}

        compiled = DSLSafetyCompiler.compile_and_validate(plan.dsl)
        try:
            await validate_plan_policy(
                db,
                tenant(),
                compiled,
                allow_network=plan.allow_network,
                max_tokens=plan.max_tokens,
                knowledge_scope=plan.knowledge_scope or [],
                owner_user_id=current_user(payload),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        workflow.status = "building_agent"
        manifest = compose_task_agent(workflow, plan)
        for target_id in manifest["invoked_agent_ids"]:
            if target_id.startswith("skill_"):
                continue
            target_agent = await db.get(TenantAgentModel, target_id)
            if (
                target_agent is None
                or target_agent.tenant_id != tenant()
                or (
                    target_agent.visibility == "private"
                    and target_agent.owner_user_id != current_user(payload)
                )
            ):
                raise HTTPException(
                    status_code=422,
                    detail=f"计划引用了当前用户不可用的 Agent：{target_id}",
                )
        agent = TenantAgentModel(
            id=uuid.uuid4().hex,
            tenant_id=tenant(),
            owner_user_id=current_user(payload),
            origin_workflow_id=workflow.id,
            visibility="private",
            base_agent_id="main_agent",
            custom_name=f"{workflow.title} · 专属 Agent",
            private_prompt_delta=(
                "你是该用户的任务专用编排 Agent。严格依据已确认需求和批准计划工作；"
                "仅调用 composition_manifest 中列出的基线能力，并遵守知识范围、联网与 Token 边界。\n"
                + json.dumps(workflow.requirements_snapshot or {}, ensure_ascii=False)
            )[:6000],
            subscribed_knowledge_packs=plan.knowledge_scope or [],
            composition_manifest=manifest,
            is_active=True,
        )
        db.add(agent)
        await db.flush()
        baseline = {"main_agent", "knowledge", "coder", "supervision"}
        plan_nodes = list((plan.dsl or {}).get("nodes") or [])
        for node in plan_nodes:
            params = node.get("parameters") or {}
            target = str(params.get("agent_id") or "")
            if not target or target in baseline or target == agent.id:
                continue
            db.add(
                AgentInvocationRelation(
                    id=uid("air"),
                    tenant_id=tenant(),
                    owner_user_id=current_user(payload),
                    source_agent_id=agent.id,
                    target_agent_id=target,
                    workflow_id=workflow.id,
                    description=str(
                        params.get("instruction") or params.get("query") or node.get("name") or "调用任务能力"
                    )[:300],
                )
            )
        plan.frozen_at = now()
        workflow.primary_agent_id = agent.id
        workflow.status = "agent_ready"
        db.add(
            WorkflowApproval(
                id=uid("wfa"),
                workflow_id=workflow.id,
                execution_id=None,
                approval_type="plan",
                decision="approved",
                actor_id=current_user(payload),
                comment=body.comment,
            )
        )
        if workflow.clarification_session_id:
            session = await db.get(
                WorkflowClarificationSession, workflow.clarification_session_id
            )
            if session:
                session.phase = "agent_ready"
                await append_lifecycle_event(
                    db,
                    workflow,
                    session,
                    "agent_built",
                    "专属 Agent 已构建，等待你启动任务",
                    {"agent_id": agent.id, "composition": manifest},
                )
        await db.commit()
        await db.refresh(agent)
        await db.refresh(workflow)
        return {"workflow": workflow_out(workflow), "agent": task_agent_out(agent)}


@router.post("/workflows/{workflow_id}/start", status_code=201)
async def start_workflow(
    workflow_id: str, body: ApprovalRequest, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id, payload)
        if workflow.status not in {"agent_ready", "ready"} or not workflow.active_plan_id:
            raise HTTPException(status_code=409, detail="专属 Agent 尚未就绪")
        plan = await db.get(WorkflowPlanVersion, workflow.active_plan_id)
        request_key = body.request_id or f"start:{workflow.id}:{uuid.uuid4().hex}"
        existing = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.idempotency_key == request_key,
                    WorkflowExecution.tenant_key == tenant(),
                )
            )
        ).scalar_one_or_none()
        if existing:
            nodes = list(
                (
                    await db.execute(
                        select(WorkflowNodeRun)
                        .where(WorkflowNodeRun.execution_id == existing.id)
                        .order_by(WorkflowNodeRun.position)
                    )
                ).scalars().all()
            )
            return execution_out(existing, nodes)
        active = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.workflow_id == workflow.id,
                    WorkflowExecution.tenant_key == tenant(),
                    WorkflowExecution.status.in_(["queued", "running", "awaiting_review"]),
                ).limit(1)
            )
        ).scalar_one_or_none()
        if active:
            raise HTTPException(status_code=409, detail="该工作流已有活动执行，请先恢复或完成现有任务")
        compiled = DSLSafetyCompiler.compile_and_validate(
            executable_plan_projection(plan.dsl)
        )
        execution = WorkflowExecution(
            id=uid("wfr"), workflow_id=workflow.id, plan_id=plan.id,
            tenant_key=tenant(), status="queued", token_budget=plan.max_tokens,
            idempotency_key=request_key,
        )
        db.add(execution)
        order = DSLSafetyCompiler.check_dag_cycle_kahn(compiled)
        node_map = {node.id: node for node in compiled.nodes}
        for position, node_id in enumerate(order):
            node = node_map[node_id]
            db.add(
                WorkflowNodeRun(
                    id=uid("wfn"), execution_id=execution.id, node_id=node.id,
                    node_type=node.node_type.value, name=node.name or node.id,
                    agent_id=str(node.parameters.get("agent_id") or "main_agent"),
                    position=position,
                    max_tokens=int(node.parameters.get("max_tokens", 4000)),
                    input_refs=[edge.source for edge in compiled.edges if edge.target == node.id],
                )
            )
        workflow.status = "ready"
        await db.commit()
        nodes = list(
            (
                await db.execute(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.execution_id == execution.id)
                    .order_by(WorkflowNodeRun.position)
                )
            ).scalars().all()
        )
        return execution_out(execution, nodes)


@router.get("/workflow-executions/active")
async def active_workflow_executions(payload: dict = Depends(require_auth)):
    """Return resumable executions owned by the current user.

    This is the authority used after foregrounding or a cold app launch; an SSE
    connection is never treated as the task's lifetime.
    """
    async with SessionLocal() as db:
        rows = list((await db.execute(
            select(WorkflowExecution, WorkflowDefinition)
            .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowExecution.workflow_id)
            .where(
                WorkflowExecution.tenant_key == tenant(),
                WorkflowDefinition.created_by == current_user(payload),
                WorkflowDefinition.archived_at.is_(None),
                WorkflowExecution.status.in_(["queued", "running", "awaiting_review", "failed"]),
            )
            .order_by(WorkflowExecution.created_at.desc())
        )).all())
        result = []
        for execution, workflow in rows:
            nodes = list((await db.execute(
                select(WorkflowNodeRun)
                .where(WorkflowNodeRun.execution_id == execution.id)
                .order_by(WorkflowNodeRun.position)
            )).scalars().all())
            result.append({
                "workflow": workflow_out(workflow),
                "execution": execution_out(execution, nodes),
            })
        return result


@router.get("/workflow-executions/{execution_id}")
async def get_execution(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        nodes = list(
            (
                await db.execute(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.execution_id == execution.id)
                    .order_by(WorkflowNodeRun.position)
                )
            )
            .scalars()
            .all()
        )
        return execution_out(execution, nodes)


@router.get("/workflow-executions/{execution_id}/events")
async def stream_events(
    execution_id: str,
    after: int = Query(0, ge=0),
    format: str = Query("sse", pattern="^(sse|json)$"),
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
    payload: dict = Depends(require_auth),
):
    requested_tenant = tenant()
    async with SessionLocal() as db:
        await owned_execution(db, execution_id, payload)

    cursor = max(after, int(last_event_id or 0) if str(last_event_id or "").isdigit() else 0)
    if format == "json":
        async with SessionLocal() as db:
            rows = list((await db.execute(select(WorkflowEvent).where(WorkflowEvent.execution_id == execution_id, WorkflowEvent.id > cursor).order_by(WorkflowEvent.id))).scalars().all())
            return [{"id": row.id, "type": row.event_type, "message": row.message, "payload": row.payload, "created_at": row.created_at.isoformat() if row.created_at else None} for row in rows]

    async def generate():
        nonlocal cursor
        while True:
            async with SessionLocal() as db:
                execution = (
                    await db.execute(
                        select(WorkflowExecution).where(
                            WorkflowExecution.id == execution_id,
                            WorkflowExecution.tenant_key == requested_tenant,
                        )
                    )
                ).scalar_one_or_none()
                if execution is None:
                    yield 'event: error\ndata: {"message":"not found"}\n\n'
                    return
                events = list(
                    (
                        await db.execute(
                            select(WorkflowEvent)
                            .where(
                                WorkflowEvent.execution_id == execution_id,
                                WorkflowEvent.id > cursor,
                            )
                            .order_by(WorkflowEvent.id)
                        )
                    )
                    .scalars()
                    .all()
                )
                for event in events:
                    cursor = event.id
                    data = json.dumps(
                        {
                            "id": event.id,
                            "type": event.event_type,
                            "message": event.message,
                            "payload": event.payload,
                            "created_at": event.created_at.isoformat() if event.created_at else None,
                        },
                        ensure_ascii=False,
                    )
                    yield f"id: {event.id}\nevent: {event.event_type}\ndata: {data}\n\n"
                if execution.status in {
                    "awaiting_review",
                    "completed",
                    "failed",
                    "cancelled",
                }:
                    return
            yield ": keepalive\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/workflow-executions/{execution_id}/artifacts")
async def list_artifacts(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        await owned_execution(db, execution_id, payload)
        rows = list(
            (
                await db.execute(
                    select(WorkflowArtifact)
                    .where(WorkflowArtifact.execution_id == execution_id)
                    .order_by(WorkflowArtifact.created_at)
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": row.id,
                "kind": row.kind,
                "title": row.title,
                "relative_path": row.relative_path,
                "content_hash": row.content_hash,
                "source_url": row.source_url,
                "source_kind": row.source_kind,
                "selected_for_publish": row.selected_for_publish,
                "published_path": row.published_path,
                "metadata": row.metadata_json or {},
            }
            for row in rows
        ]


@router.get("/workflow-executions/{execution_id}/explain-context")
async def get_explain_context(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        workflow = await db.get(WorkflowDefinition, execution.workflow_id)
        plan = await db.get(WorkflowPlanVersion, execution.plan_id)
        run_started = (
            await db.execute(
                select(WorkflowEvent)
                .where(
                    WorkflowEvent.execution_id == execution_id,
                    WorkflowEvent.event_type == "run_started",
                )
                .order_by(WorkflowEvent.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if run_started is None:
            raise HTTPException(status_code=409, detail="Hermes Run尚未返回版本回执")
        nodes = list(
            (
                await db.execute(
                    select(WorkflowNodeRun)
                    .where(WorkflowNodeRun.execution_id == execution_id)
                    .order_by(WorkflowNodeRun.position)
                )
            ).scalars().all()
        )
        current = nodes[0] if nodes else None
        dsl = dict(plan.dsl or {}) if plan else {}
        manifest = (run_started.payload or {}).get("resolved_manifest") or {}
        return build_explain_context_snapshot({
            "workflow_id": execution.workflow_id,
            "execution_id": execution.id,
            "customer_goal": workflow.description if workflow else "",
            "current_stage": current.name if current else execution.status,
            "next_action": "按批准计划执行，并由人工复核成果与证据",
            "process_contract_id": dsl.get("process_contract_id"),
            "process_contract_digest": dsl.get("process_contract_digest"),
            "activation_revision": dsl.get("activation_revision"),
            "resolved_manifest": manifest or {},
        })


@router.get("/workflow-executions/{execution_id}/evidence-report")
async def get_evidence_report(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        workflow = await db.get(WorkflowDefinition, execution.workflow_id)
        plan = await db.get(WorkflowPlanVersion, execution.plan_id)
        events = list((await db.execute(
            select(WorkflowEvent)
            .where(WorkflowEvent.execution_id == execution_id)
            .order_by(WorkflowEvent.id)
        )).scalars().all())
        artifacts = list((await db.execute(
            select(WorkflowArtifact)
            .where(WorkflowArtifact.execution_id == execution_id)
            .order_by(WorkflowArtifact.created_at)
        )).scalars().all())
        root = run_root(execution).resolve()
        evidence: list[dict[str, Any]] = []
        claims: list[dict[str, Any]] = []
        for event in events:
            bridge_id = str((event.payload or {}).get("bridge_event_id") or f"event:{event.id}")
            evidence.append({
                "evidence_id": bridge_id,
                "kind": "event",
                "title": event.event_type,
                "content": event.message,
            })
        for artifact in artifacts:
            path = (root / artifact.relative_path).resolve()
            content = path.read_text(encoding="utf-8") if path.is_relative_to(root) and path.exists() else ""
            evidence.append({
                "evidence_id": artifact.id,
                "kind": artifact.kind,
                "title": artifact.title,
                "content": content,
            })
            claims.append({
                "statement": f"已生成工件：{artifact.title}",
                "evidence_ids": [artifact.id],
            })
        dsl = dict(plan.dsl or {}) if plan else {}
        return compile_evidence_bound_report(
            execution_id=execution.id,
            customer_goal=workflow.description if workflow else "",
            process_contract_digest=dsl.get("process_contract_digest"),
            evidence=evidence,
            claims=claims,
            usage={
                "input_tokens": execution.input_tokens,
                "output_tokens": execution.output_tokens,
                "reasoning_tokens": execution.reasoning_tokens,
                "estimated_cost_usd": float(execution.estimated_cost_usd or 0),
            },
        )


@router.get("/workflow-executions/{execution_id}/artifacts/{artifact_id}/content")
async def get_artifact_content(
    execution_id: str,
    artifact_id: str,
    payload: dict = Depends(require_auth),
):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        artifact = (
            await db.execute(
                select(WorkflowArtifact).where(
                    WorkflowArtifact.id == artifact_id,
                    WorkflowArtifact.execution_id == execution.id,
                )
            )
        ).scalar_one_or_none()
        if artifact is None:
            raise HTTPException(status_code=404, detail="工作流素材不存在")
        root = run_root(execution)
        path = (root / artifact.relative_path).resolve()
        if root not in path.parents:
            raise HTTPException(status_code=404, detail="工作流素材文件不存在")
        if not path.is_file():
            content = await _recover_artifact_content(execution, artifact)
            if content is None:
                raise HTTPException(status_code=404, detail="工作流素材文件不存在")
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
            try:
                temporary.write_text(content, encoding="utf-8")
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
        return {
            "id": artifact.id,
            "title": artifact.title,
            "kind": artifact.kind,
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }


async def _recover_artifact_content(
    execution: WorkflowExecution,
    artifact: WorkflowArtifact,
) -> str | None:
    """Recover a missing file from the append-only Hermes run projection."""
    bridge_event_id = str((artifact.metadata_json or {}).get("bridge_event_id") or "")
    if not bridge_event_id:
        return None
    try:
        snapshot = await read_bridge_run(execution, after_seq=0)
    except Exception:
        return None
    for event in snapshot.get("events") or []:
        if str(event.get("event_id") or "") != bridge_event_id:
            continue
        content = str((event.get("artifact") or {}).get("content") or "")
        if not content:
            return None
        digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
        return content if digest == artifact.content_hash else None
    return None


@router.post("/workflow-executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        if execution.status not in {"queued", "running"}:
            raise HTTPException(status_code=409, detail="当前执行不能取消")
        if execution.status == "running":
            try:
                await cancel_remote(execution.id)
            except Exception as exc:
                # 平台仍记录取消意图，Hermes 恢复后相同 run 不会被重新派发执行。
                execution.error_message = f"Hermes 取消回执待同步：{str(exc)[:300]}"
        execution.status = "cancelled"
        execution.finished_at = now()
        execution.lease_owner = None
        execution.lease_until = None
        await db.commit()
        return execution_out(execution)


async def _reset_from_node(
    db, execution: WorkflowExecution, node_id: str | None = None
) -> None:
    nodes = list(
        (
            await db.execute(
                select(WorkflowNodeRun)
                .where(WorkflowNodeRun.execution_id == execution.id)
                .order_by(WorkflowNodeRun.position)
            )
        )
        .scalars()
        .all()
    )
    target = (
        next((node for node in nodes if node.node_id == node_id), None)
        if node_id
        else next((node for node in nodes if node.status == "failed"), None)
    )
    if target is None:
        target = next((node for node in nodes if node.status != "succeeded"), None)
    if target is None:
        raise HTTPException(status_code=409, detail="没有可重试的节点")
    for node in nodes:
        if node.position >= target.position:
            node.status = "pending"
            node.error_message = None
            node.output_summary = ""
            node.token_used = 0
            node.started_at = None
            node.finished_at = None
    execution.status = "queued"
    execution.progress = int((target.position / max(1, len(nodes))) * 100)
    execution.error_message = None
    execution.token_used = sum(
        node.token_used for node in nodes if node.status == "succeeded"
    )
    execution.finished_at = None
    execution.lease_owner = None
    execution.lease_until = None


@router.post("/workflow-executions/{execution_id}/retry")
async def retry_execution(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        if execution.status not in {"failed", "cancelled"}:
            raise HTTPException(status_code=409, detail="只有失败或取消的执行可以重试")
        failed_node = (
            await db.execute(
                select(WorkflowNodeRun)
                .where(
                    WorkflowNodeRun.execution_id == execution.id,
                    WorkflowNodeRun.status == "failed",
                )
                .order_by(WorkflowNodeRun.position)
                .limit(1)
            )
        ).scalar_one_or_none()
        from_node_id = failed_node.node_id if failed_node else None
        await _reset_from_node(db, execution, from_node_id)
        try:
            await retry_remote(execution.id, from_node_id)
        except Exception:
            # 持久 Worker 会在 Bridge 恢复后用同一 execution/idempotency key 续跑。
            pass
        await db.commit()
        return execution_out(execution)


@router.post("/workflow-executions/{execution_id}/request-revision")
async def request_revision(
    execution_id: str, body: RevisionRequest, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        if execution.status != "awaiting_review":
            raise HTTPException(status_code=409, detail="只有待复核成果可以退回修改")
        await _reset_from_node(db, execution, body.node_id)
        try:
            await retry_remote(execution.id, body.node_id)
        except Exception:
            pass
        db.add(
            WorkflowApproval(
                id=uid("wfa"),
                workflow_id=execution.workflow_id,
                execution_id=execution.id,
                approval_type="output",
                decision="revision_requested",
                actor_id=str(payload.get("user_id") or payload.get("sub") or ""),
                comment=body.comment,
            )
        )
        await db.commit()
        return execution_out(execution)


def _publish_name(title: str, artifact_id: str) -> str:
    clean = (
        re.sub(r"[^\w\u4e00-\u9fff-]+", "-", title).strip("-")[:80]
        or "workflow-artifact"
    )
    return f"{clean}-{artifact_id[-8:]}.md"


@router.post("/workflow-executions/{execution_id}/approve-output")
async def approve_output(
    execution_id: str,
    body: OutputApprovalRequest,
    payload: dict = Depends(require_auth),
):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id, payload)
        if execution.status != "awaiting_review":
            raise HTTPException(status_code=409, detail="当前没有待复核成果")
        query = select(WorkflowArtifact).where(
            WorkflowArtifact.execution_id == execution.id
        )
        if body.artifact_ids:
            query = query.where(WorkflowArtifact.id.in_(body.artifact_ids))
        else:
            query = query.where(WorkflowArtifact.selected_for_publish.is_(True))
        artifacts = list((await db.execute(query)).scalars().all())
        raw_dir = (
            vault_root() / "raw" / "workflows" / execution.workflow_id / execution.id
        )
        raw_dir.mkdir(parents=True, exist_ok=True)
        source_root = run_root(execution)
        for artifact in artifacts:
            source = (source_root / artifact.relative_path).resolve()
            if not source.is_file() or source_root not in source.parents:
                continue
            destination = raw_dir / _publish_name(artifact.title, artifact.id)
            if not destination.exists():
                shutil.copy2(source, destination)
            artifact.published_path = str(destination.relative_to(vault_root()))
        try:
            from scripts.build_knowledge_matrix import build_matrix

            matrix = build_matrix(vault_root())
            matrix_path = vault_root() / "knowledge_matrix.json"
            temporary = matrix_path.with_suffix(".json.tmp")
            temporary.write_text(
                json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temporary, matrix_path)
        except Exception as exc:
            raise HTTPException(
                status_code=500, detail=f"素材已落盘，但知识矩阵重建失败：{exc}"
            ) from exc
        execution.status = "completed"
        execution.finished_at = now()
        workflow = await owned_workflow(db, execution.workflow_id, payload)
        workflow.status = "ready"
        db.add(
            WorkflowApproval(
                id=uid("wfa"),
                workflow_id=workflow.id,
                execution_id=execution.id,
                approval_type="output",
                decision="approved",
                actor_id=str(payload.get("user_id") or payload.get("sub") or ""),
                comment=body.comment,
            )
        )
        await db.commit()
        return {
            "execution": execution_out(execution),
            "published": [
                item.published_path for item in artifacts if item.published_path
            ],
        }
