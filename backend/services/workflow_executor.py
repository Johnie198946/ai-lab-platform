"""Durable Hermes workflow dispatcher and event projector.

The platform never executes DSL nodes.  It owns the outbox lease, approval and
tenant-safe projection; Hermes Bridge owns DAG progression, agents, tools,
context compression, model routing and exact usage accounting.
"""

from __future__ import annotations

import asyncio
import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.services.knowledge_catalog import compute_catalog
from backend.db import SessionLocal
from backend.models.tenant import TenantMapping
from backend.models.tenant_agent import TenantAgentModel
from backend.models.workflow import (
    WorkflowApproval,
    WorkflowArtifact,
    WorkflowEvent,
    WorkflowExecution,
    WorkflowDefinition,
    WorkflowNodeRun,
    WorkflowPlanVersion,
)
from backend.services.workflow_contract import assert_plan_binding
from backend.services.workflow_artifacts import (
    append_event,
    initialize_run,
    store_artifact,
)
from backend.services.knowledge_policy import mint_capability, resolve_policy
from backend.services.llm_usage import build_llm_usage_record
from backend.services.ipd_scenario_registry import (
    EXECUTABLE_EDGE,
    EXECUTABLE_NODE_IDS,
    SCENARIO_ID,
    is_registered_ipd_plan,
)
from backend.services.process_contract_registry import (
    dependency_lock_digest,
    validate_and_project_process_plan,
)

HERMES_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")
LEASE_SECONDS = 60


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def bridge_base_url() -> str:
    base = HERMES_URL.rstrip("/")
    return base[: -len("/v1/chat")] if base.endswith("/v1/chat") else base


def bridge_headers() -> dict[str, str]:
    return (
        {"X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN}
        if HERMES_BRIDGE_INTERNAL_TOKEN
        else {}
    )


async def emit(
    db: AsyncSession,
    execution: WorkflowExecution,
    event_type: str,
    message: str,
    **payload: Any,
) -> None:
    db.add(
        WorkflowEvent(
            execution_id=execution.id,
            event_type=event_type,
            message=message[:500],
            payload=payload,
        )
    )
    append_event(
        execution,
        {
            "type": event_type,
            "message": message,
            "payload": payload,
            "created_at": utcnow().isoformat(),
        },
    )
    await db.flush()


async def claim_next(
    db: AsyncSession, owner: str | None = None
) -> WorkflowExecution | None:
    owner = owner or f"{socket.gethostname()}:{os.getpid()}"
    now = utcnow()
    statement = (
        select(WorkflowExecution)
        .where(
            WorkflowExecution.status.in_(["queued", "running"]),
            (WorkflowExecution.lease_until.is_(None))
            | (WorkflowExecution.lease_until < now),
        )
        .order_by(WorkflowExecution.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    execution = (await db.execute(statement)).scalar_one_or_none()
    if execution is None:
        return None
    execution.lease_owner = owner
    execution.lease_until = now + timedelta(seconds=LEASE_SECONDS)
    await db.commit()
    await db.refresh(execution)
    return execution


async def _plan(db: AsyncSession, execution: WorkflowExecution) -> WorkflowPlanVersion:
    return (
        await db.execute(
            select(WorkflowPlanVersion).where(WorkflowPlanVersion.id == execution.plan_id)
        )
    ).scalar_one()


async def _nodes(db: AsyncSession, execution_id: str) -> dict[str, WorkflowNodeRun]:
    rows = list(
        (
            await db.execute(
                select(WorkflowNodeRun).where(
                    WorkflowNodeRun.execution_id == execution_id
                )
            )
        ).scalars().all()
    )
    return {row.node_id: row for row in rows}


async def _assert_execution_plan_binding(
    db: AsyncSession, execution: WorkflowExecution, plan: WorkflowPlanVersion
) -> None:
    workflow = await db.get(WorkflowDefinition, execution.workflow_id)
    approval = (
        await db.execute(
            select(WorkflowApproval)
            .where(
                WorkflowApproval.workflow_id == execution.workflow_id,
                WorkflowApproval.approval_type == "plan",
                WorkflowApproval.decision == "approved",
            )
            .order_by(WorkflowApproval.created_at.desc(), WorkflowApproval.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    assert_plan_binding(
        active_plan_id=workflow.active_plan_id if workflow else None,
        active_plan_hash=plan.content_hash,
        active_activation_revision=plan.activation_revision,
        approval_plan_id=approval.plan_id if approval else None,
        approval_plan_hash=approval.plan_hash if approval else None,
        approval_activation_revision=approval.activation_revision if approval else None,
    )


def executable_plan_projection(plan: dict[str, Any]) -> dict[str, Any]:
    """Project a registered display plan to only server-approved runtime nodes."""
    if plan.get("process_contract_id"):
        return validate_and_project_process_plan(plan)
    nodes = list(plan.get("nodes") or [])
    has_registered_identity = any(
        (node.get("parameters") or {}).get("scenario_id") == SCENARIO_ID
        for node in nodes
    )
    if has_registered_identity:
        if not is_registered_ipd_plan(plan):
            raise ValueError("注册IPD计划场景合同无效")
        node_map = {str(node.get("id") or ""): node for node in nodes}
        if any(node_id not in node_map for node_id in EXECUTABLE_NODE_IDS):
            raise ValueError("注册IPD计划缺少服务端批准节点")
        return {
            **plan,
            "nodes": [node_map[node_id] for node_id in EXECUTABLE_NODE_IDS],
            "edges": [dict(EXECUTABLE_EDGE)],
        }
    if not any("execution_enabled" in (node.get("parameters") or {}) for node in nodes):
        return plan
    runtime_nodes = [
        node for node in nodes if (node.get("parameters") or {}).get("execution_enabled") is True
    ]
    runtime_ids = {str(node.get("id")) for node in runtime_nodes}
    return {
        **plan,
        "nodes": runtime_nodes,
        "edges": [
            edge
            for edge in (plan.get("edges") or [])
            if str(edge.get("source")) in runtime_ids and str(edge.get("target")) in runtime_ids
        ],
    }


async def dispatch(execution: WorkflowExecution, plan: WorkflowPlanVersion) -> dict[str, Any]:
    async with SessionLocal() as policy_db:
        mapping = (
            await policy_db.execute(
                select(TenantMapping).where(TenantMapping.tenant_key == execution.tenant_key).limit(1)
            )
        ).scalar_one_or_none()
        policy, _ = await resolve_policy(
            policy_db,
            tenant_key=execution.tenant_key,
            org_id=mapping.org_id if mapping else "",
            catalog=compute_catalog(),
            allow_admin_bypass=False,
        )
        allowed_scope = policy.restrict(plan.knowledge_scope or [])
        workflow = await policy_db.get(WorkflowDefinition, execution.workflow_id)
        capability = mint_capability(
            policy,
            subject_id=execution.id,
            entry_point="workflow",
            requested_scopes=allowed_scope,
            user_id=str((workflow and workflow.created_by) or execution.id),
            sources=("tenant_knowledge", "user_notes"),
            ttl_seconds=900,
        )
        task_agent = (
            await policy_db.get(TenantAgentModel, workflow.primary_agent_id)
            if workflow and workflow.primary_agent_id else None
        )
    payload = {
        "tenant_id": execution.tenant_key,
        "execution_id": execution.id,
        "idempotency_key": execution.idempotency_key,
        "command_id": f"workflow-command:{execution.id}",
        "execution_request_id": execution.idempotency_key,
        "goal": plan.goal,
        "deliverable": plan.deliverable,
        "plan": executable_plan_projection(plan.dsl),
        "process_contract_digest": plan.dsl.get("process_contract_digest"),
        "dependency_lock_digest": dependency_lock_digest(plan.dsl),
        "activation_revision": plan.dsl.get("activation_revision"),
        "allow_network": plan.allow_network,
        "knowledge_scope": sorted(allowed_scope),
        "knowledge_capability": capability,
        "knowledge_policy_version": policy.policy_version,
        "max_tokens": plan.max_tokens,
        "agent_config": {
            "id": task_agent.id,
            "prompt": task_agent.private_prompt_delta,
            "composition": task_agent.composition_manifest or {},
        } if task_agent else {},
    }
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.post(
            f"{bridge_base_url()}/v1/workflow-runs",
            headers=bridge_headers(),
            json=payload,
        )
    response.raise_for_status()
    return response.json()


async def read_bridge_run(
    execution: WorkflowExecution,
    *,
    after_seq: int | None = None,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30) as client:
        response = await client.get(
            f"{bridge_base_url()}/v1/workflow-runs/{execution.id}",
            headers=bridge_headers(),
            params={
                "after_seq": (
                    execution.bridge_event_seq if after_seq is None else after_seq
                )
            },
        )
    response.raise_for_status()
    return response.json()


def contiguous_bridge_events(
    events: list[dict[str, Any]], after_seq: int
) -> list[dict[str, Any]]:
    by_seq: dict[int, dict[str, Any]] = {}
    for event in events:
        seq = int(event.get("seq") or 0)
        if seq <= after_seq:
            continue
        previous = by_seq.get(seq)
        if previous and previous.get("event_id") != event.get("event_id"):
            raise RuntimeError(f"Hermes event identity conflict at seq {seq}")
        by_seq[seq] = event
    ordered = [by_seq[seq] for seq in sorted(by_seq)]
    expected = after_seq + 1
    for event in ordered:
        seq = int(event["seq"])
        if seq != expected:
            raise RuntimeError(f"Hermes event gap: expected {expected}, got {seq}")
        expected += 1
    return ordered


def _set_usage(target: Any, usage: dict[str, Any]) -> None:
    target.input_tokens = int(usage.get("input_tokens") or 0)
    target.output_tokens = int(usage.get("output_tokens") or 0)
    target.reasoning_tokens = int(usage.get("reasoning_tokens") or 0)
    target.cache_read_tokens = int(usage.get("cache_read_tokens") or 0)
    target.cache_write_tokens = int(usage.get("cache_write_tokens") or 0)
    target.api_calls = int(usage.get("api_calls") or 0)
    target.estimated_cost_usd = float(usage.get("estimated_cost_usd") or 0)
    target.model_used = str(usage.get("model") or "")
    target.provider_used = str(usage.get("provider") or "")
    target.token_used = int(usage.get("total_tokens") or 0)


def _rollup_usage(execution: WorkflowExecution, nodes: dict[str, WorkflowNodeRun]) -> None:
    """Publish the last exact per-call totals while the overall run is active."""
    fields = (
        "input_tokens", "output_tokens", "reasoning_tokens", "cache_read_tokens",
        "cache_write_tokens", "api_calls", "token_used",
    )
    for field in fields:
        setattr(execution, field, sum(int(getattr(node, field, 0) or 0) for node in nodes.values()))
    execution.estimated_cost_usd = sum(
        float(node.estimated_cost_usd or 0) for node in nodes.values()
    )
    completed = [node for node in nodes.values() if node.status == "succeeded"]
    if completed:
        latest = max(completed, key=lambda item: item.position)
        execution.model_used = latest.model_used
        execution.provider_used = latest.provider_used


async def _add_workflow_usage_record(
    db: AsyncSession,
    execution: WorkflowExecution,
    usage: dict[str, Any] | None,
    *,
    success: bool,
    provider: str = "",
    model: str = "",
) -> None:
    owner = (
        await db.execute(
            select(WorkflowDefinition.created_by).where(
                WorkflowDefinition.id == execution.workflow_id
            )
        )
    ).scalar_one_or_none()
    db.add(
        build_llm_usage_record(
            auth_payload={
                "user_id": str(owner or ""),
                "tenant_key": execution.tenant_key,
            },
            usage_payload=usage,
            latency_ms=0,
            success=success,
            provider=provider,
            model=model,
        )
    )


async def _artifact_exists(db: AsyncSession, execution_id: str, event_id: str) -> bool:
    rows = list(
        (
            await db.execute(
                select(WorkflowArtifact.metadata_json).where(
                    WorkflowArtifact.execution_id == execution_id
                )
            )
        ).scalars().all()
    )
    return any((item or {}).get("bridge_event_id") == event_id for item in rows)


def artifact_storage_contract(
    artifact: dict[str, Any], *, event_id: str, node: WorkflowNodeRun
) -> tuple[str, dict[str, Any]]:
    contracts = {
        "markdown": ("md", "text/markdown"),
        "word": ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        "chart": ("json", "application/json"),
        "topology": ("json", "application/json"),
        "flowchart": ("json", "application/json"),
        "data": ("json", "application/json"),
    }
    aliases = {"md": "markdown", "docx": "word", "flow": "flowchart", "process": "flowchart"}
    declared = str(artifact.get("render_type") or artifact.get("artifact_type") or "").strip().lower()
    render_type = aliases.get(declared, declared)
    extension_hint = str(artifact.get("extension") or "").strip().lower().lstrip(".")
    if render_type not in contracts:
        render_type = {"md": "markdown", "docx": "word", "csv": "data", "json": "data"}.get(extension_hint, "markdown")
    extension, mime_type = contracts[render_type]
    if render_type == "data" and extension_hint == "csv":
        extension, mime_type = "csv", "text/csv"
    metadata = {
        "bridge_event_id": event_id,
        "source_node_id": node.node_id,
        "agent_id": node.agent_id,
        "model": node.model_used,
        "provider": node.provider_used,
        "render_type": render_type,
        "mime_type": mime_type,
    }
    return extension, metadata


async def project_event(
    db: AsyncSession,
    execution: WorkflowExecution,
    node_rows: dict[str, WorkflowNodeRun],
    event: dict[str, Any],
) -> None:
    event_type = str(event.get("type") or "bridge_event")
    node_id = str(event.get("node_id") or "")
    message = str(event.get("message") or event_type)
    node = node_rows.get(node_id)
    if event_type == "run_started":
        execution.status = "running"
        execution.started_at = execution.started_at or utcnow()
    elif event_type == "node_started" and node is not None:
        node.status = "running"
        node.attempt += 1
        node.started_at = utcnow()
        node.error_message = None
    elif event_type == "node_succeeded" and node is not None:
        usage = event.get("usage") or {}
        node.status = "succeeded"
        node.output_summary = str((event.get("artifact") or {}).get("content") or "")[:2000]
        node.finished_at = utcnow()
        _set_usage(node, usage)
        route = event.get("route") or {}
        node.model_used = str(route.get("model") or node.model_used)
        node.provider_used = str(route.get("provider") or node.provider_used)
        await _add_workflow_usage_record(
            db,
            execution,
            usage,
            success=True,
            provider=node.provider_used,
            model=node.model_used,
        )
        execution.progress = int(event.get("progress") or execution.progress)
        artifact = event.get("artifact") or {}
        event_id = str(event.get("event_id") or "")
        if artifact.get("content") and not await _artifact_exists(db, execution.id, event_id):
            extension, artifact_metadata = artifact_storage_contract(
                artifact, event_id=event_id, node=node
            )
            db.add(
                store_artifact(
                    execution,
                    node_run_id=node.id,
                    kind=str(artifact.get("kind") or "draft"),
                    title=str(artifact.get("title") or node.name),
                    content=str(artifact["content"]),
                    source_kind=str(artifact.get("source_kind") or "hermes_output"),
                    metadata=artifact_metadata,
                    extension=extension,
                )
            )
        if route.get("reason"):
            execution.route_reason = str(route["reason"])[:500]
        _rollup_usage(execution, node_rows)
    elif event_type == "run_completed":
        execution.status = "awaiting_review"
        execution.progress = 100
        execution.finished_at = utcnow()
        _set_usage(execution, event.get("usage") or {})
    elif event_type == "run_failed":
        execution.status = "failed"
        execution.error_message = str(event.get("error") or message)[:2000]
        execution.finished_at = utcnow()
        if node is not None:
            node.status = "failed"
            node.error_message = execution.error_message
            node.finished_at = utcnow()
            await _add_workflow_usage_record(
                db,
                execution,
                event.get("usage") if isinstance(event.get("usage"), dict) else None,
                success=False,
                provider=node.provider_used,
                model=node.model_used,
            )
    elif event_type == "run_cancelled":
        execution.status = "cancelled"
        execution.finished_at = utcnow()
    await emit(
        db,
        execution,
        event_type,
        message,
        bridge_event_id=event.get("event_id"),
        bridge_seq=event.get("seq"),
        node_id=node_id or None,
        node_attempt_id=event.get("node_attempt_id"),
        tool_call_id=event.get("tool_call_id"),
        idempotency_key=event.get("idempotency_key"),
        receipt=event.get("receipt") or {},
        resolved_manifest=event.get("resolved_manifest") or {},
        usage=event.get("usage") or {},
        route=event.get("route") or {},
        category=event.get("category") or event_type,
        status=event.get("status") or (
            "running" if event_type in {"run_started", "node_started", "tool_start", "agent_spawn"}
            else "failed" if event_type in {"run_failed", "evaluation_failed"}
            else "done"
        ),
        tool=event.get("tool"),
        detail=event.get("detail") or "",
        source=event.get("source") or "hermes_bridge",
    )
    execution.bridge_event_seq = max(
        execution.bridge_event_seq, int(event.get("seq") or 0)
    )


async def sync_execution(execution_id: str, db: AsyncSession) -> None:
    execution = (
        await db.execute(
            select(WorkflowExecution).where(WorkflowExecution.id == execution_id)
        )
    ).scalar_one()
    plan = await _plan(db, execution)
    await _assert_execution_plan_binding(db, execution, plan)
    initialize_run(execution, executable_plan_projection(plan.dsl))
    try:
        dispatched = await dispatch(execution, plan)
        execution.hermes_session_id = dispatched.get("hermes_session_id")
        # 用户已在平台明确触发 retry/revision 后，本地状态会回到 queued。
        # 若 Bridge 仍保存旧的终态，显式从首个未成功节点恢复，而不是创建第二个 Run。
        if execution.status == "queued" and dispatched.get("status") in {
            "failed",
            "cancelled",
        }:
            current_nodes = await _nodes(db, execution.id)
            restart = next(
                (
                    node
                    for node in sorted(current_nodes.values(), key=lambda item: item.position)
                    if node.status != "succeeded"
                ),
                None,
            )
            await retry_remote(execution.id, restart.node_id if restart else None)
        snapshot = await read_bridge_run(execution)
        if snapshot.get("hermes_session_id"):
            execution.hermes_session_id = str(snapshot["hermes_session_id"])
        node_rows = await _nodes(db, execution.id)
        for event in contiguous_bridge_events(
            list(snapshot.get("events") or []), execution.bridge_event_seq
        ):
            await project_event(db, execution, node_rows, event)
        if not snapshot.get("events") and snapshot.get("status") == "running":
            execution.status = "running"
            execution.started_at = execution.started_at or utcnow()
        execution.lease_owner = None
        execution.lease_until = None
        execution.artifact_count = int(
            (
                await db.execute(
                    select(func.count(WorkflowArtifact.id)).where(
                        WorkflowArtifact.execution_id == execution.id
                    )
                )
            ).scalar_one()
        )
        from backend.services.showroom_insight_execution import project_execution

        await project_execution(db, execution.id)
        await db.commit()
    except Exception as exc:
        # 外部执行器暂不可达不是业务失败；保留队列并释放租约，下轮安全重试同一幂等键。
        execution.lease_owner = None
        execution.lease_until = None
        execution.error_message = f"等待 Hermes 恢复：{str(exc)[:500]}"
        await db.commit()


async def cancel_remote(execution_id: str) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{bridge_base_url()}/v1/workflow-runs/{execution_id}/cancel",
            headers=bridge_headers(),
        )
    response.raise_for_status()


async def retry_remote(execution_id: str, from_node_id: str | None = None) -> None:
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            f"{bridge_base_url()}/v1/workflow-runs/{execution_id}/retry",
            headers=bridge_headers(),
            json={"from_node_id": from_node_id},
        )
    response.raise_for_status()


async def worker_loop(poll_seconds: float = 2.0) -> None:
    from backend.db import SessionLocal, init_db

    await init_db()
    while True:
        async with SessionLocal() as db:
            execution = await claim_next(db)
            if execution is not None:
                await sync_execution(execution.id, db)
                # Hermes 节点可能运行数分钟；投影同步按固定频率轮询，避免在
                # 无新事件时形成数据库/Bridge 紧循环。
                await asyncio.sleep(poll_seconds)
                continue
        await asyncio.sleep(poll_seconds)
