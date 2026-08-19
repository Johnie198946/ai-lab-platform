"""Tenant-scoped executable workflow APIs."""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from backend.api.auth import require_auth
from backend.api.tenant import current_tenant
from backend.db import SessionLocal
from backend.models.tenant_agent_schema import WorkflowDSLPlan
from backend.models.workflow import (
    WorkflowApproval,
    WorkflowArtifact,
    WorkflowDefinition,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowNodeRun,
    WorkflowPlanVersion,
)
from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.workflow_artifacts import run_root, vault_root
from backend.services.workflow_executor import cancel_remote, retry_remote
from backend.services.workflow_planner import build_plan, validate_plan_policy

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


class PlanEdit(BaseModel):
    dsl: dict[str, Any]
    deliverable: str = Field(..., min_length=1, max_length=300)
    allow_network: bool = True
    max_tokens: int = Field(24000, ge=1000, le=128000)
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
        "dsl": plan.dsl,
        "frozen_at": plan.frozen_at.isoformat() if plan.frozen_at else None,
        "created_at": plan.created_at.isoformat() if plan.created_at else None,
    }


def workflow_out(row: WorkflowDefinition) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "description": row.description,
        "desired_output": row.desired_output,
        "status": row.status,
        "active_plan_id": row.active_plan_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def execution_out(
    row: WorkflowExecution, nodes: list[WorkflowNodeRun] | None = None
) -> dict[str, Any]:
    return {
        "id": row.id,
        "workflow_id": row.workflow_id,
        "plan_id": row.plan_id,
        "status": row.status,
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


async def owned_workflow(db, workflow_id: str) -> WorkflowDefinition:
    row = (
        await db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                WorkflowDefinition.tenant_key == tenant(),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="工作流不存在")
    return row


async def owned_execution(db, execution_id: str) -> WorkflowExecution:
    row = (
        await db.execute(
            select(WorkflowExecution).where(
                WorkflowExecution.id == execution_id,
                WorkflowExecution.tenant_key == tenant(),
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="工作流执行不存在")
    return row


@router.post("/workflows", status_code=201)
async def create_workflow(body: WorkflowCreate, payload: dict = Depends(require_auth)):
    row = WorkflowDefinition(
        id=uid("wf"),
        tenant_key=tenant(),
        created_by=str(payload.get("user_id") or payload.get("sub") or ""),
        title=body.title.strip(),
        description=body.description.strip(),
        desired_output=body.desired_output.strip(),
        status="planning",
    )
    async with SessionLocal() as db:
        db.add(row)
        await db.flush()
        plan = await build_plan(db, row)
        await db.commit()
        await db.refresh(row)
        return {**workflow_out(row), "plan": plan_out(plan)}


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
            result.append(item)
        return result


@router.get("/workflows/{workflow_id}")
async def get_workflow(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        row = await owned_workflow(db, workflow_id)
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
        return result


@router.get("/workflows/{workflow_id}/plan")
async def get_plan(workflow_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id)
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
        workflow = await owned_workflow(db, workflow_id)
        if workflow.status not in {"awaiting_approval", "draft", "planning"}:
            raise HTTPException(
                status_code=409, detail="已确认计划不能直接修改，请创建新版本"
            )
        try:
            compiled: WorkflowDSLPlan = DSLSafetyCompiler.compile_and_validate(body.dsl)
            await validate_plan_policy(
                db,
                tenant(),
                compiled,
                allow_network=body.allow_network,
                max_tokens=body.max_tokens,
                knowledge_scope=body.knowledge_scope,
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
        workflow = await owned_workflow(db, workflow_id)
        if workflow.status in {"archived"}:
            raise HTTPException(status_code=409, detail="已归档工作流不能重新规划")
        workflow.status = "planning"
        plan = await build_plan(db, workflow, revision_note=body.instruction)
        await db.commit()
        await db.refresh(plan)
        return plan_out(plan)


@router.post("/workflows/{workflow_id}/approve-plan", status_code=201)
async def approve_plan(
    workflow_id: str, body: ApprovalRequest, payload: dict = Depends(require_auth)
):
    async with SessionLocal() as db:
        workflow = await owned_workflow(db, workflow_id)
        if not workflow.active_plan_id:
            raise HTTPException(status_code=409, detail="当前没有待确认的计划")
        plan = (
            await db.execute(
                select(WorkflowPlanVersion).where(
                    WorkflowPlanVersion.id == workflow.active_plan_id
                )
            )
        ).scalar_one()
        request_key = body.request_id or f"approve:{workflow.id}:{plan.id}"
        existing = (
            await db.execute(
                select(WorkflowExecution).where(
                    WorkflowExecution.idempotency_key == request_key,
                    WorkflowExecution.tenant_key == tenant(),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing_nodes = list(
                (
                    await db.execute(
                        select(WorkflowNodeRun)
                        .where(WorkflowNodeRun.execution_id == existing.id)
                        .order_by(WorkflowNodeRun.position)
                    )
                ).scalars().all()
            )
            return execution_out(existing, existing_nodes)
        if workflow.status != "awaiting_approval":
            raise HTTPException(status_code=409, detail="当前没有待确认的计划")
        if plan.validation_errors:
            raise HTTPException(status_code=409, detail="计划校验未通过，不能执行")
        compiled = DSLSafetyCompiler.compile_and_validate(plan.dsl)
        try:
            await validate_plan_policy(
                db,
                tenant(),
                compiled,
                allow_network=plan.allow_network,
                max_tokens=plan.max_tokens,
                knowledge_scope=plan.knowledge_scope or [],
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        execution = WorkflowExecution(
            id=uid("wfr"),
            workflow_id=workflow.id,
            plan_id=plan.id,
            tenant_key=tenant(),
            status="queued",
            token_budget=plan.max_tokens,
            idempotency_key=request_key,
        )
        db.add(execution)
        order = DSLSafetyCompiler.check_dag_cycle_kahn(compiled)
        node_map = {node.id: node for node in compiled.nodes}
        for position, node_id in enumerate(order):
            node = node_map[node_id]
            db.add(
                WorkflowNodeRun(
                    id=uid("wfn"),
                    execution_id=execution.id,
                    node_id=node.id,
                    node_type=node.node_type.value,
                    name=node.name or node.id,
                    agent_id=str(node.parameters.get("agent_id") or "main_agent"),
                    position=position,
                    max_tokens=int(node.parameters.get("max_tokens", 4000)),
                    input_refs=[
                        edge.source for edge in compiled.edges if edge.target == node.id
                    ],
                )
            )
        plan.frozen_at = now()
        workflow.status = "ready"
        db.add(
            WorkflowApproval(
                id=uid("wfa"),
                workflow_id=workflow.id,
                execution_id=execution.id,
                approval_type="plan",
                decision="approved",
                actor_id=str(payload.get("user_id") or payload.get("sub") or ""),
                comment=body.comment,
            )
        )
        await db.commit()
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


@router.get("/workflow-executions/{execution_id}")
async def get_execution(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id)
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
async def stream_events(execution_id: str, payload: dict = Depends(require_auth)):
    requested_tenant = tenant()
    async with SessionLocal() as db:
        await owned_execution(db, execution_id)

    async def generate():
        cursor = 0
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
        await owned_execution(db, execution_id)
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


@router.get("/workflow-executions/{execution_id}/artifacts/{artifact_id}/content")
async def get_artifact_content(
    execution_id: str,
    artifact_id: str,
    payload: dict = Depends(require_auth),
):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id)
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
        if not path.is_file() or root not in path.parents:
            raise HTTPException(status_code=404, detail="工作流素材文件不存在")
        return {
            "id": artifact.id,
            "title": artifact.title,
            "kind": artifact.kind,
            "content": path.read_text(encoding="utf-8", errors="replace"),
        }


@router.post("/workflow-executions/{execution_id}/cancel")
async def cancel_execution(execution_id: str, payload: dict = Depends(require_auth)):
    async with SessionLocal() as db:
        execution = await owned_execution(db, execution_id)
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
        execution = await owned_execution(db, execution_id)
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
        execution = await owned_execution(db, execution_id)
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
        execution = await owned_execution(db, execution_id)
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
        workflow = await owned_workflow(db, execution.workflow_id)
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
