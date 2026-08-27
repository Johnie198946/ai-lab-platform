"""QuantumWorkspace M0 project control-plane API."""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from backend.api.auth import require_auth
from backend.api.chat import StreamRequest, chat_stream
from backend.db import SessionLocal
from backend.models.workspace import (
    WorkspaceBusinessIntake,
    WorkspaceProcessDraft,
    WorkspaceProject,
    WorkspaceTaskConversation,
    WorkspaceTaskMessage,
)
from backend.models.workflow import WorkflowDefinition
from backend.services.workspace_process import (
    compile_ipd_draft,
    instantiate_reviewed_process,
)

router = APIRouter(prefix="/api/v1", tags=["quantum-workspace"])

IPD_TEMPLATE: dict[str, Any] = {
    "id": "ipd-product-development",
    "version": "1.0.0",
    "name": "IPD 产品开发",
    "summary": "按产品形态、创新程度和裁剪级别生成受控 IPD 流程草案。",
    "category": "产品/IPD",
    "stages": ["概念", "计划", "开发", "验证", "发布", "生命周期"],
    "task_count": 12,
    "agents": [],
    "skills_tools": [],
    "deliverables": ["产品包", "架构基线", "验证证据", "发布包"],
    "resource_envelope": {"source_status": "UNCONNECTED"},
    "truth_capability": ["PLANNED", "REPLAY", "SIMULATION"],
    "last_updated": "2026-08-27T00:00:00Z",
}


class InstantiateProjectRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    name: str = Field(min_length=1, max_length=160)
    goal: str = Field(min_length=1, max_length=4000)
    desired_outputs: list[str] = Field(default_factory=list, max_length=40)
    inputs: dict[str, Any] = Field(default_factory=dict)
    truth_mode: Literal["PLANNED", "REPLAY", "SIMULATION"] = "PLANNED"
    resource_overrides: dict[str, Any] = Field(default_factory=dict)


class BusinessIntakeRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    business_goal: str = Field(min_length=1, max_length=4000)
    customers_and_scenarios: str = Field(min_length=1, max_length=4000)
    product_scope: str = Field(min_length=1, max_length=300)
    product_form: Literal["software", "hardware", "integrated", "service"]
    innovation_level: Literal["new_product", "major_upgrade", "routine_update"]
    tailoring_level: Literal["full", "standard", "lite"]
    requirements_and_evidence: str = Field(min_length=1, max_length=8000)
    desired_deliverables: list[str] = Field(min_length=1, max_length=40)
    target_finish_at: datetime


class GenerateDraftRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    business_intake_id: str
    process_template_id: str
    process_template_version: str
    catalog_revision: str = Field(min_length=1, max_length=80)


class ApplyDraftRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=100)
    expected_revision: int = Field(ge=0)
    draft_revision: int = Field(ge=1)


class UpdateTaskRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    status: Literal["TODO", "IN_PROGRESS", "BLOCKED", "PAUSED", "DONE"]
    reason: str | None = Field(default=None, min_length=3, max_length=500)


class CreateProjectTaskRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    stage_id: str = Field(min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=160)
    summary: str = Field(min_length=1, max_length=4000)
    assignee_role: str | None = Field(default=None, max_length=160)


class BindTaskWorkflowRequest(BaseModel):
    expected_revision: int = Field(ge=0)
    workflow_id: str = Field(min_length=1, max_length=48)


class OpenTaskConversationRequest(BaseModel):
    project_id: str
    task_id: str
    workflow_id: str | None = None
    agent_version: str = Field(min_length=1, max_length=80)


class TaskMessageRequest(BaseModel):
    question: str = Field(min_length=1, max_length=12000)
    request_id: str = Field(min_length=8, max_length=100)


TASK_TRANSITIONS: dict[str, set[str]] = {
    "TODO": {"IN_PROGRESS", "BLOCKED", "PAUSED"},
    "IN_PROGRESS": {"BLOCKED", "PAUSED", "DONE"},
    "BLOCKED": {"IN_PROGRESS", "PAUSED"},
    "PAUSED": {"IN_PROGRESS", "BLOCKED"},
    "DONE": set(),
}


def _scope(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or "public"),
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )


def _instantiate_payload(
    template_id: str, body: InstantiateProjectRequest
) -> dict[str, Any]:
    return {
        "template_id": template_id,
        **body.model_dump(mode="json", exclude={"request_id"}),
    }


def _project_matches_instantiate_payload(
    project: WorkspaceProject, request_payload: dict[str, Any]
) -> bool:
    stored = (project.process_snapshot or {}).get("instantiate_request")
    if stored is not None:
        return stored == request_payload
    return request_payload == {
        "template_id": project.template_id,
        "name": project.name,
        "goal": project.goal,
        "desired_outputs": project.desired_outputs or [],
        "inputs": {},
        "truth_mode": project.truth_mode,
        "resource_overrides": {},
    }


def _extract_sse_frames(buffer: str, *, final: bool = False) -> tuple[list[str], str]:
    frames: list[str] = []
    while True:
        matches = [
            (index, separator)
            for separator in ("\r\n\r\n", "\n\n", "\r\r")
            if (index := buffer.find(separator)) >= 0
        ]
        if not matches:
            break
        index, separator = min(matches, key=lambda item: item[0])
        frames.append(buffer[:index])
        buffer = buffer[index + len(separator) :]
    if final and buffer.strip():
        frames.append(buffer)
        buffer = ""
    return frames, buffer


def _parse_sse_event(frame: str) -> dict[str, Any] | None:
    data = "\n".join(
        line[5:].lstrip()
        for line in frame.splitlines()
        if line.startswith("data:")
    )
    if not data:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def _project_out(project: WorkspaceProject) -> dict[str, Any]:
    return {
        "id": project.id,
        "tenant_id": project.tenant_key,
        "owner_user_id": project.owner_user_id,
        "name": project.name,
        "goal": project.goal,
        "desired_outputs": project.desired_outputs or [],
        "template_id": project.template_id,
        "template_version": project.template_version,
        "status": project.status,
        "truth_mode": project.truth_mode,
        "process_revision": project.process_revision,
        "current_stage": None,
        "task_count": len((project.process_snapshot or {}).get("tasks") or []),
        "created_at": project.created_at,
        "updated_at": project.updated_at,
    }


def _intake_out(intake: WorkspaceBusinessIntake) -> dict[str, Any]:
    return {
        "id": intake.id,
        "project_id": intake.project_id,
        "revision": intake.revision,
        "status": intake.status,
        **(intake.payload or {}),
    }


def _draft_out(draft: WorkspaceProcessDraft) -> dict[str, Any]:
    return {
        "id": draft.id,
        "project_id": draft.project_id,
        "revision": draft.revision,
        "status": draft.status,
        "truth": "AI_PROPOSED",
        "process": draft.draft_snapshot,
    }


async def _project_for_owner(
    db, project_id: str, tenant_key: str, owner_user_id: str
) -> WorkspaceProject:
    project = await db.scalar(
        select(WorkspaceProject).where(
            WorkspaceProject.id == project_id,
            WorkspaceProject.tenant_key == tenant_key,
            WorkspaceProject.owner_user_id == owner_user_id,
        )
    )
    if project is None:
        raise HTTPException(status_code=404, detail="project not found")
    return project


@router.get("/project-templates")
async def list_project_templates(payload=Depends(require_auth)) -> list[dict[str, Any]]:
    return [IPD_TEMPLATE]


@router.get("/project-templates/{template_id}")
async def get_project_template(template_id: str, payload=Depends(require_auth)) -> dict[str, Any]:
    if template_id != IPD_TEMPLATE["id"]:
        raise HTTPException(status_code=404, detail="project template not found")
    return IPD_TEMPLATE


@router.post("/project-templates/{template_id}/instantiate")
async def instantiate_project(
    template_id: str,
    body: InstantiateProjectRequest,
    payload=Depends(require_auth),
):
    if template_id != IPD_TEMPLATE["id"]:
        raise HTTPException(status_code=404, detail="project template not found")
    tenant_key, user_id = _scope(payload)
    request_payload = _instantiate_payload(template_id, body)
    async with SessionLocal() as db:
        existing = await db.scalar(
            select(WorkspaceProject).where(
                WorkspaceProject.tenant_key == tenant_key,
                WorkspaceProject.owner_user_id == user_id,
                WorkspaceProject.request_id == body.request_id,
            )
        )
        if existing is not None:
            if not _project_matches_instantiate_payload(existing, request_payload):
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different project inputs",
                )
            return JSONResponse(
                status_code=200,
                content={
                    "project_id": existing.id,
                    "task_ids": [item["id"] for item in (existing.process_snapshot or {}).get("tasks", [])],
                    "graph_ids": [],
                    "template_version": existing.template_version,
                    "created_at": existing.created_at.isoformat(),
                },
            )

        project = WorkspaceProject(
            id=f"prj_{uuid4().hex}",
            tenant_key=tenant_key,
            owner_user_id=user_id,
            request_id=body.request_id,
            name=body.name,
            goal=body.goal,
            desired_outputs=body.desired_outputs,
            template_id=template_id,
            template_version=str(IPD_TEMPLATE["version"]),
            status="active",
            truth_mode=body.truth_mode,
            process_revision=0,
            process_snapshot={
                "process_instance_id": None,
                "stages": [],
                "gates": [],
                "tasks": [],
                "dependencies": [],
                "graphs": {},
                "instantiate_request": request_payload,
            },
        )
        db.add(project)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(WorkspaceProject).where(
                    WorkspaceProject.tenant_key == tenant_key,
                    WorkspaceProject.owner_user_id == user_id,
                    WorkspaceProject.request_id == body.request_id,
                )
            )
            if existing is None:
                raise
            if not _project_matches_instantiate_payload(existing, request_payload):
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different project inputs",
                )
            return JSONResponse(
                status_code=200,
                content={
                    "project_id": existing.id,
                    "task_ids": [
                        item["id"]
                        for item in (existing.process_snapshot or {}).get("tasks", [])
                    ],
                    "graph_ids": [],
                    "template_version": existing.template_version,
                    "created_at": existing.created_at.isoformat(),
                },
            )
        await db.refresh(project)
        return JSONResponse(
            status_code=201,
            content={
                "project_id": project.id,
                "task_ids": [],
                "graph_ids": [],
                "template_version": project.template_version,
                "created_at": project.created_at.isoformat(),
            },
        )


@router.get("/projects")
async def list_projects(payload=Depends(require_auth)) -> list[dict[str, Any]]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        rows = (
            await db.scalars(
                select(WorkspaceProject)
                .where(
                    WorkspaceProject.tenant_key == tenant_key,
                    WorkspaceProject.owner_user_id == user_id,
                )
                .order_by(WorkspaceProject.updated_at.desc(), WorkspaceProject.id)
            )
        ).all()
        return [_project_out(row) for row in rows]


@router.get("/projects/{project_id}")
async def get_project(project_id: str, payload=Depends(require_auth)) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        return _project_out(await _project_for_owner(db, project_id, tenant_key, user_id))


@router.get("/projects/{project_id}/process")
async def get_project_process(project_id: str, payload=Depends(require_auth)) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        return {
            "project_id": project.id,
            "process_revision": project.process_revision,
            **(project.process_snapshot or {}),
        }


@router.post("/projects/{project_id}/business-intakes")
async def create_business_intake(
    project_id: str,
    body: BusinessIntakeRequest,
    payload=Depends(require_auth),
):
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        project_record_id = project.id
        intake_payload = body.model_dump(mode="json", exclude={"request_id"})
        existing = await db.scalar(
            select(WorkspaceBusinessIntake).where(
                WorkspaceBusinessIntake.tenant_key == tenant_key,
                WorkspaceBusinessIntake.project_id == project_record_id,
                WorkspaceBusinessIntake.request_id == body.request_id,
            )
        )
        if existing is not None:
            if (existing.payload or {}) != intake_payload:
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different business intake inputs",
                )
            return JSONResponse(
                status_code=200,
                content=_intake_out(existing),
            )
        intake = WorkspaceBusinessIntake(
            id=f"intake_{uuid4().hex}",
            tenant_key=tenant_key,
            project_id=project_id,
            request_id=body.request_id,
            revision=1,
            status="submitted",
            payload=intake_payload,
        )
        db.add(intake)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(WorkspaceBusinessIntake).where(
                    WorkspaceBusinessIntake.tenant_key == tenant_key,
                    WorkspaceBusinessIntake.project_id == project_record_id,
                    WorkspaceBusinessIntake.request_id == body.request_id,
                )
            )
            if existing is None:
                raise
            if (existing.payload or {}) != intake_payload:
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different business intake inputs",
                )
            return JSONResponse(status_code=200, content=_intake_out(existing))
        await db.refresh(intake)
        return JSONResponse(status_code=201, content=_intake_out(intake))


@router.post("/projects/{project_id}/process-drafts/generate")
async def generate_process_draft(
    project_id: str,
    body: GenerateDraftRequest,
    payload=Depends(require_auth),
):
    if (
        body.process_template_id != IPD_TEMPLATE["id"]
        or body.process_template_version != IPD_TEMPLATE["version"]
    ):
        raise HTTPException(status_code=409, detail="project template version changed")
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        project_record_id = project.id
        existing = await db.scalar(
            select(WorkspaceProcessDraft).where(
                WorkspaceProcessDraft.tenant_key == tenant_key,
                WorkspaceProcessDraft.project_id == project_record_id,
                WorkspaceProcessDraft.request_id == body.request_id,
            )
        )
        if existing is not None:
            if (
                existing.business_intake_id != body.business_intake_id
                or existing.template_id != body.process_template_id
                or existing.template_version != body.process_template_version
                or existing.catalog_revision != body.catalog_revision
            ):
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different process draft inputs",
                )
            return JSONResponse(status_code=200, content=_draft_out(existing))
        intake = await db.scalar(
            select(WorkspaceBusinessIntake).where(
                WorkspaceBusinessIntake.id == body.business_intake_id,
                WorkspaceBusinessIntake.project_id == project_id,
                WorkspaceBusinessIntake.tenant_key == tenant_key,
            )
        )
        if intake is None:
            raise HTTPException(status_code=404, detail="business intake not found")
        draft = WorkspaceProcessDraft(
            id=f"draft_{uuid4().hex}",
            tenant_key=tenant_key,
            project_id=project_id,
            business_intake_id=intake.id,
            request_id=body.request_id,
            template_id=body.process_template_id,
            template_version=body.process_template_version,
            catalog_revision=body.catalog_revision,
            revision=1,
            status="READY_FOR_REVIEW",
            draft_snapshot=compile_ipd_draft(intake.payload, body.process_template_version),
        )
        db.add(draft)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(WorkspaceProcessDraft).where(
                    WorkspaceProcessDraft.tenant_key == tenant_key,
                    WorkspaceProcessDraft.project_id == project_record_id,
                    WorkspaceProcessDraft.request_id == body.request_id,
                )
            )
            if existing is None:
                raise
            if (
                existing.business_intake_id != body.business_intake_id
                or existing.template_id != body.process_template_id
                or existing.template_version != body.process_template_version
                or existing.catalog_revision != body.catalog_revision
            ):
                raise HTTPException(
                    status_code=409,
                    detail="request_id already binds different process draft inputs",
                )
            return JSONResponse(status_code=200, content=_draft_out(existing))
        await db.refresh(draft)
        return JSONResponse(status_code=201, content=_draft_out(draft))


@router.get("/projects/{project_id}/process-drafts/{draft_id}")
async def get_process_draft(
    project_id: str,
    draft_id: str,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        await _project_for_owner(db, project_id, tenant_key, user_id)
        draft = await db.scalar(
            select(WorkspaceProcessDraft).where(
                WorkspaceProcessDraft.id == draft_id,
                WorkspaceProcessDraft.project_id == project_id,
                WorkspaceProcessDraft.tenant_key == tenant_key,
            )
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="process draft not found")
        return {
            "id": draft.id,
            "project_id": project_id,
            "revision": draft.revision,
            "status": draft.status,
            "truth": "AI_PROPOSED",
            "process": draft.draft_snapshot,
            "apply_result": draft.apply_result,
        }


@router.post("/projects/{project_id}/process-drafts/{draft_id}/apply")
async def apply_process_draft(
    project_id: str,
    draft_id: str,
    body: ApplyDraftRequest,
    payload=Depends(require_auth),
):
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        draft = await db.scalar(
            select(WorkspaceProcessDraft).where(
                WorkspaceProcessDraft.id == draft_id,
                WorkspaceProcessDraft.project_id == project_id,
                WorkspaceProcessDraft.tenant_key == tenant_key,
            )
        )
        if draft is None:
            raise HTTPException(status_code=404, detail="process draft not found")
        if draft.status == "APPLIED" and draft.apply_result:
            applied_from_revision = int(draft.apply_result["process_revision"]) - 1
            if (
                draft.apply_request_id != body.request_id
                or draft.revision != body.draft_revision
                or applied_from_revision != body.expected_revision
            ):
                raise HTTPException(
                    status_code=409,
                    detail="applied draft already binds different apply inputs",
                )
            return draft.apply_result
        if draft.revision != body.draft_revision:
            raise HTTPException(
                status_code=409,
                detail={"error": "draft_revision_conflict", "server_revision": draft.revision},
            )
        if project.process_revision != body.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": project.process_revision,
                },
            )

        project_record_id = project.id
        draft_record_id = draft.id
        process = instantiate_reviewed_process(draft.draft_snapshot)
        instantiate_request = (project.process_snapshot or {}).get("instantiate_request")
        if instantiate_request is not None:
            process["instantiate_request"] = instantiate_request
        next_revision = body.expected_revision + 1
        apply_result = {
            "project_id": project_record_id,
            "process_instance_id": process["process_instance_id"],
            "process_revision": next_revision,
            "task_ids": [item["id"] for item in process["tasks"]],
            "graph_ids": [item["id"] for item in process["graphs"].values()],
            "conversation_ids": [],
            "template_version": draft.template_version,
        }
        project_cas = await db.execute(
            update(WorkspaceProject)
            .where(
                WorkspaceProject.id == project_record_id,
                WorkspaceProject.tenant_key == tenant_key,
                WorkspaceProject.owner_user_id == user_id,
                WorkspaceProject.process_revision == body.expected_revision,
            )
            .values(
                process_snapshot=process,
                process_revision=next_revision,
                updated_at=datetime.now().astimezone(),
            )
            .execution_options(synchronize_session=False)
        )
        if project_cas.rowcount != 1:
            await db.rollback()
            server_revision = await db.scalar(
                select(WorkspaceProject.process_revision).where(
                    WorkspaceProject.id == project_record_id,
                    WorkspaceProject.tenant_key == tenant_key,
                    WorkspaceProject.owner_user_id == user_id,
                )
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": server_revision,
                },
            )
        draft_cas = await db.execute(
            update(WorkspaceProcessDraft)
            .where(
                WorkspaceProcessDraft.id == draft_record_id,
                WorkspaceProcessDraft.project_id == project_record_id,
                WorkspaceProcessDraft.tenant_key == tenant_key,
                WorkspaceProcessDraft.revision == body.draft_revision,
                WorkspaceProcessDraft.status == "READY_FOR_REVIEW",
            )
            .values(
                status="APPLIED",
                apply_request_id=body.request_id,
                apply_result=apply_result,
                updated_at=datetime.now().astimezone(),
            )
            .execution_options(synchronize_session=False)
        )
        if draft_cas.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="process draft changed")
        await db.commit()
        return apply_result


def _aggregate_stage(stage: dict[str, Any], tasks: list[dict[str, Any]]) -> None:
    if not tasks:
        stage["status"] = "NOT_STARTED"
        stage["progress"] = 0
        return
    statuses = {task["status"] for task in tasks}
    if statuses == {"DONE"}:
        stage["status"] = "DONE"
    elif "BLOCKED" in statuses:
        stage["status"] = "BLOCKED"
    elif "IN_PROGRESS" in statuses or "DONE" in statuses:
        stage["status"] = "IN_PROGRESS"
    elif "PAUSED" in statuses:
        stage["status"] = "PAUSED"
    else:
        stage["status"] = "NOT_STARTED"
    stage["progress"] = round(
        sum(1 for task in tasks if task["status"] == "DONE") / len(tasks) * 100
    )


async def _cas_project_process(
    db,
    *,
    project_id: str,
    tenant_key: str,
    user_id: str,
    expected_revision: int,
    process: dict[str, Any],
    commit: bool = True,
) -> int:
    next_revision = expected_revision + 1
    result = await db.execute(
        update(WorkspaceProject)
        .where(
            WorkspaceProject.id == project_id,
            WorkspaceProject.tenant_key == tenant_key,
            WorkspaceProject.owner_user_id == user_id,
            WorkspaceProject.process_revision == expected_revision,
        )
        .values(
            process_snapshot=process,
            process_revision=next_revision,
            updated_at=datetime.now().astimezone(),
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        await db.rollback()
        server_revision = await db.scalar(
            select(WorkspaceProject.process_revision).where(
                WorkspaceProject.id == project_id,
                WorkspaceProject.tenant_key == tenant_key,
                WorkspaceProject.owner_user_id == user_id,
            )
        )
        raise HTTPException(
            status_code=409,
            detail={
                "error": "project_revision_conflict",
                "server_revision": server_revision,
            },
        )
    if commit:
        await db.commit()
    return next_revision


@router.get("/projects/{project_id}/schedule")
async def get_project_schedule(
    project_id: str,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        process = project.process_snapshot or {}
        return {
            "project_id": project.id,
            "process_instance_id": process.get("process_instance_id"),
            "process_revision": project.process_revision,
            "calendar": process.get("calendar") or {},
            "stages": process.get("stages") or [],
            "tasks": [
                {
                    **task,
                    "schedule_status": (
                        "SCHEDULED"
                        if task.get("planned_start_at") and task.get("planned_finish_at")
                        else "UNSCHEDULED"
                    ),
                }
                for task in (process.get("tasks") or [])
            ],
            "dependencies": process.get("dependencies") or [],
            "critical_path": [],
        }


@router.get("/projects/{project_id}/graphs/{view_type}")
async def get_project_graph(
    project_id: str,
    view_type: Literal["workflow", "ai-resource"],
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        process = project.process_snapshot or {}
        graph = (process.get("graphs") or {}).get(view_type)
        if graph is None:
            raise HTTPException(status_code=404, detail="project graph not available")
        return {
            "project_id": project.id,
            "process_instance_id": process.get("process_instance_id"),
            "process_revision": project.process_revision,
            **graph,
        }


@router.post("/projects/{project_id}/tasks", status_code=201)
async def create_project_task(
    project_id: str,
    body: CreateProjectTaskRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        if project.process_revision != body.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": project.process_revision,
                },
            )
        process = dict(project.process_snapshot or {})
        if not process.get("process_instance_id"):
            raise HTTPException(status_code=409, detail="project process is not instantiated")
        stages = [dict(item) for item in process.get("stages", [])]
        stage = next((item for item in stages if item["id"] == body.stage_id), None)
        if stage is None:
            raise HTTPException(status_code=404, detail="project stage not found")
        task = {
            "id": f"tsk_{uuid4().hex}",
            "stage_id": stage["id"],
            "title": body.title.strip(),
            "summary": body.summary.strip(),
            "status": "TODO",
            "status_source": "PLANNED",
            "assignee_id": None,
            "assignee_role": (body.assignee_role or "").strip() or None,
            "agent_candidates": [],
            "workflow_id": None,
            "workflow_status": "UNCONNECTED",
            "planned_start_at": None,
            "planned_finish_at": None,
            "actual_start_at": None,
            "actual_finish_at": None,
            "estimated_duration_days": 5,
            "unscheduled_reason": "missing_planned_dates",
            "deliverables": [],
            "evidence_refs": [],
            "risk": "LOW",
            "created_by": user_id,
        }
        tasks = [dict(item) for item in process.get("tasks", [])]
        tasks.append(task)
        _aggregate_stage(stage, [item for item in tasks if item["stage_id"] == stage["id"]])
        graphs = dict(process.get("graphs") or {})
        workflow_graph = dict(graphs.get("workflow") or {})
        workflow_graph["nodes"] = [
            *(workflow_graph.get("nodes") or []),
            {
                "id": task["id"],
                "type": "task",
                "label": task["title"],
                "status": "UNCONNECTED",
                "task_status": "TODO",
                "stage_id": stage["id"],
            },
        ]
        resource_graph = dict(graphs.get("ai-resource") or {})
        resource_graph["nodes"] = [
            *(resource_graph.get("nodes") or []),
            {
                "id": task["id"],
                "type": "task",
                "label": task["title"],
                "task_status": "TODO",
            },
        ]
        graphs["workflow"] = workflow_graph
        graphs["ai-resource"] = resource_graph
        process["tasks"] = tasks
        process["stages"] = stages
        process["graphs"] = graphs
        next_revision = await _cas_project_process(
            db,
            project_id=project.id,
            tenant_key=tenant_key,
            user_id=user_id,
            expected_revision=body.expected_revision,
            process=process,
        )
        return {
            "project_id": project.id,
            "process_revision": next_revision,
            "task": task,
            "stage": stage,
        }


@router.put("/projects/{project_id}/tasks/{task_id}/workflow")
async def bind_project_task_workflow(
    project_id: str,
    task_id: str,
    body: BindTaskWorkflowRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        if project.process_revision != body.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": project.process_revision,
                },
            )
        workflow = await db.scalar(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == body.workflow_id,
                WorkflowDefinition.tenant_key == tenant_key,
                WorkflowDefinition.created_by == user_id,
                WorkflowDefinition.archived_at.is_(None),
            )
        )
        if workflow is None:
            raise HTTPException(status_code=404, detail="workflow not found")
        process = dict(project.process_snapshot or {})
        tasks = [dict(item) for item in process.get("tasks", [])]
        task = next((item for item in tasks if item["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="project task not found")
        bound_elsewhere = next(
            (
                item
                for item in tasks
                if item["id"] != task_id and item.get("workflow_id") == workflow.id
            ),
            None,
        )
        if bound_elsewhere is not None:
            raise HTTPException(status_code=409, detail="workflow already binds another project task")
        if task.get("workflow_id") == workflow.id:
            return {
                "project_id": project.id,
                "process_revision": project.process_revision,
                "task": task,
            }
        task["workflow_id"] = workflow.id
        task["workflow_status"] = workflow.status
        task["workflow_bound_at"] = datetime.now().astimezone().isoformat()
        task["workflow_bound_by"] = user_id
        graphs = dict(process.get("graphs") or {})
        workflow_graph = dict(graphs.get("workflow") or {})
        workflow_graph["nodes"] = [
            {
                **node,
                "status": workflow.status,
                "workflow_id": workflow.id,
            }
            if node["id"] == task_id
            else node
            for node in workflow_graph.get("nodes", [])
        ]
        graphs["workflow"] = workflow_graph
        process["tasks"] = tasks
        process["graphs"] = graphs
        next_revision = await _cas_project_process(
            db,
            project_id=project.id,
            tenant_key=tenant_key,
            user_id=user_id,
            expected_revision=body.expected_revision,
            process=process,
            commit=False,
        )
        conversations = list(
            (
                await db.execute(
                    select(WorkspaceTaskConversation).where(
                        WorkspaceTaskConversation.tenant_key == tenant_key,
                        WorkspaceTaskConversation.user_id == user_id,
                        WorkspaceTaskConversation.project_id == project.id,
                        WorkspaceTaskConversation.task_id == task_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        for conversation in conversations:
            conversation.workflow_id = workflow.id
            conversation.binding = {
                **(conversation.binding or {}),
                "workflow_id": workflow.id,
                "process_revision": next_revision,
            }
        await db.commit()
        return {
            "project_id": project.id,
            "process_revision": next_revision,
            "task": task,
        }


@router.get("/projects/{project_id}/tasks/{task_id}")
async def get_project_task(
    project_id: str,
    task_id: str,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        task = next(
            (item for item in (project.process_snapshot or {}).get("tasks", []) if item["id"] == task_id),
            None,
        )
        if task is None:
            raise HTTPException(status_code=404, detail="project task not found")
        return {"project_id": project.id, "process_revision": project.process_revision, **task}


@router.patch("/projects/{project_id}/tasks/{task_id}")
async def update_project_task(
    project_id: str,
    task_id: str,
    body: UpdateTaskRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, project_id, tenant_key, user_id)
        project_record_id = project.id
        if project.process_revision != body.expected_revision:
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": project.process_revision,
                },
            )
        process = dict(project.process_snapshot or {})
        tasks = [dict(item) for item in process.get("tasks", [])]
        task = next((item for item in tasks if item["id"] == task_id), None)
        if task is None:
            raise HTTPException(status_code=404, detail="project task not found")
        current_status = str(task.get("status") or "TODO")
        stages = [dict(item) for item in process.get("stages", [])]
        stage = next(item for item in stages if item["id"] == task["stage_id"])
        if body.status == current_status:
            return {
                "project_id": project_record_id,
                "process_revision": project.process_revision,
                "task": task,
                "stage": stage,
            }
        if body.status not in TASK_TRANSITIONS.get(current_status, set()):
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "illegal_task_transition",
                    "from": current_status,
                    "to": body.status,
                },
            )
        if body.status in {"BLOCKED", "PAUSED"} and not body.reason:
            raise HTTPException(
                status_code=422,
                detail="reason is required when blocking or pausing a task",
            )
        task["status"] = body.status
        task["status_source"] = "PLANNED"
        task["status_history"] = [
            *(task.get("status_history") or []),
            {
                "from": current_status,
                "to": body.status,
                "reason": body.reason or "explicit taskboard action",
                "actor_user_id": user_id,
                "at": datetime.now().astimezone().isoformat(),
            },
        ]
        _aggregate_stage(stage, [item for item in tasks if item["stage_id"] == stage["id"]])
        graphs = dict(process.get("graphs") or {})
        workflow_graph = dict(graphs.get("workflow") or {})
        workflow_graph["nodes"] = [
            {**node, "task_status": task["status"]} if node["id"] == task_id else node
            for node in workflow_graph.get("nodes", [])
        ]
        graphs["workflow"] = workflow_graph
        process["tasks"] = tasks
        process["stages"] = stages
        process["graphs"] = graphs
        next_revision = body.expected_revision + 1
        cas = await db.execute(
            update(WorkspaceProject)
            .where(
                WorkspaceProject.id == project_record_id,
                WorkspaceProject.tenant_key == tenant_key,
                WorkspaceProject.owner_user_id == user_id,
                WorkspaceProject.process_revision == body.expected_revision,
            )
            .values(
                process_snapshot=process,
                process_revision=next_revision,
                updated_at=datetime.now().astimezone(),
            )
            .execution_options(synchronize_session=False)
        )
        if cas.rowcount != 1:
            await db.rollback()
            server_revision = await db.scalar(
                select(WorkspaceProject.process_revision).where(
                    WorkspaceProject.id == project_record_id,
                    WorkspaceProject.tenant_key == tenant_key,
                    WorkspaceProject.owner_user_id == user_id,
                )
            )
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "project_revision_conflict",
                    "server_revision": server_revision,
                },
            )
        await db.commit()
        return {
            "project_id": project_record_id,
            "process_revision": next_revision,
            "task": task,
            "stage": stage,
        }


@router.post("/task-conversations")
async def open_task_conversation(
    body: OpenTaskConversationRequest,
    payload=Depends(require_auth),
):
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        project = await _project_for_owner(db, body.project_id, tenant_key, user_id)
        project_record_id = project.id
        process = project.process_snapshot or {}
        task = next(
            (item for item in process.get("tasks", []) if item["id"] == body.task_id),
            None,
        )
        if task is None:
            raise HTTPException(status_code=404, detail="project task not found")
        if body.workflow_id != task.get("workflow_id"):
            raise HTTPException(status_code=409, detail="task workflow binding changed")
        existing = await db.scalar(
            select(WorkspaceTaskConversation).where(
                WorkspaceTaskConversation.tenant_key == tenant_key,
                WorkspaceTaskConversation.user_id == user_id,
                WorkspaceTaskConversation.project_id == project_record_id,
                WorkspaceTaskConversation.task_id == task["id"],
                WorkspaceTaskConversation.agent_version == body.agent_version,
            )
        )
        if existing is not None:
            return JSONResponse(
                status_code=200,
                content={"id": existing.id, "binding": existing.binding, "messages": []},
            )
        conversation_id = f"conv_{uuid4().hex}"
        session_id = f"qw-{uuid4().hex}"
        binding = {
            "tenant_id": tenant_key,
            "workspace_id": "quantum-workspace",
            "user_id": user_id,
            "project_id": project_record_id,
            "process_instance_id": process.get("process_instance_id"),
            "process_revision": project.process_revision,
            "stage_id": task["stage_id"],
            "task_id": task["id"],
            "workflow_id": task.get("workflow_id"),
            "execution_id": None,
            "session_id": session_id,
            "agent_version": body.agent_version,
        }
        conversation = WorkspaceTaskConversation(
            id=conversation_id,
            tenant_key=tenant_key,
            user_id=user_id,
            project_id=project_record_id,
            task_id=task["id"],
            workflow_id=task.get("workflow_id"),
            execution_id=None,
            session_id=session_id,
            agent_version=body.agent_version,
            binding=binding,
        )
        db.add(conversation)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(WorkspaceTaskConversation).where(
                    WorkspaceTaskConversation.tenant_key == tenant_key,
                    WorkspaceTaskConversation.user_id == user_id,
                    WorkspaceTaskConversation.project_id == project_record_id,
                    WorkspaceTaskConversation.task_id == task["id"],
                    WorkspaceTaskConversation.agent_version == body.agent_version,
                )
            )
            if existing is None:
                raise
            return JSONResponse(
                status_code=200,
                content={"id": existing.id, "binding": existing.binding, "messages": []},
            )
        return JSONResponse(
            status_code=201,
            content={"id": conversation.id, "binding": binding, "messages": []},
        )


async def _conversation_for_tenant(
    db, conversation_id: str, tenant_key: str, user_id: str
) -> WorkspaceTaskConversation:
    conversation = await db.scalar(
        select(WorkspaceTaskConversation).where(
            WorkspaceTaskConversation.id == conversation_id,
            WorkspaceTaskConversation.tenant_key == tenant_key,
            WorkspaceTaskConversation.user_id == user_id,
        )
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="task conversation not found")
    return conversation


@router.get("/task-conversations/{conversation_id}/messages")
async def list_task_messages(
    conversation_id: str,
    payload=Depends(require_auth),
) -> list[dict[str, Any]]:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        await _conversation_for_tenant(db, conversation_id, tenant_key, user_id)
        rows = (
            await db.scalars(
                select(WorkspaceTaskMessage)
                .where(
                    WorkspaceTaskMessage.tenant_key == tenant_key,
                    WorkspaceTaskMessage.conversation_id == conversation_id,
                )
                .order_by(WorkspaceTaskMessage.created_at, WorkspaceTaskMessage.id)
            )
        ).all()
        return [
            {
                "id": row.id,
                "role": row.role,
                "content": row.content,
                "request_id": row.request_id,
                "event_metadata": row.event_metadata,
                "created_at": row.created_at,
            }
            for row in rows
        ]


@router.post("/task-conversations/{conversation_id}/messages/stream")
async def stream_task_message(
    conversation_id: str,
    body: TaskMessageRequest,
    payload=Depends(require_auth),
) -> StreamingResponse:
    tenant_key, user_id = _scope(payload)
    async with SessionLocal() as db:
        conversation = await _conversation_for_tenant(db, conversation_id, tenant_key, user_id)
        project = await _project_for_owner(
            db, conversation.project_id, tenant_key, user_id
        )
        task = next(
            (
                item
                for item in (project.process_snapshot or {}).get("tasks", [])
                if item["id"] == conversation.task_id
            ),
            None,
        )
        if task is None:
            raise HTTPException(status_code=409, detail="bound task no longer exists")
        existing_assistant = await db.scalar(
            select(WorkspaceTaskMessage).where(
                WorkspaceTaskMessage.tenant_key == tenant_key,
                WorkspaceTaskMessage.conversation_id == conversation.id,
                WorkspaceTaskMessage.request_id == body.request_id,
                WorkspaceTaskMessage.role == "assistant",
            )
        )
        if existing_assistant is not None:
            async def replay_events():
                yield f"data: {json.dumps({'type': 'status', 'phase': 'replay'}, ensure_ascii=False)}\n\n"
                terminal_type = (existing_assistant.event_metadata or {}).get(
                    "terminal_type", "done"
                )
                if terminal_type == "error":
                    yield f"data: {json.dumps({'type': 'error', 'detail': existing_assistant.content}, ensure_ascii=False)}\n\n"
                else:
                    yield f"data: {json.dumps({'type': 'done', 'answer': existing_assistant.content}, ensure_ascii=False)}\n\n"

            return StreamingResponse(replay_events(), media_type="text/event-stream")
        existing_user = await db.scalar(
            select(WorkspaceTaskMessage).where(
                WorkspaceTaskMessage.tenant_key == tenant_key,
                WorkspaceTaskMessage.conversation_id == conversation.id,
                WorkspaceTaskMessage.request_id == body.request_id,
                WorkspaceTaskMessage.role == "user",
            )
        )
        if existing_user is not None and existing_user.content != body.question:
            raise HTTPException(status_code=409, detail="request_id already binds another message")
        if existing_user is not None:
            raise HTTPException(status_code=409, detail="request is already in progress")
        if existing_user is None:
            db.add(
                WorkspaceTaskMessage(
                    id=f"msg_{uuid4().hex}",
                    tenant_key=tenant_key,
                    conversation_id=conversation.id,
                    request_id=body.request_id,
                    role="user",
                    content=body.question,
                    event_metadata={"source": "quantum-workspace"},
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()
                raise HTTPException(status_code=409, detail="request is already in progress")

    server_goal = "\n".join(
        [
            "[QuantumWorkspace server-resolved binding]",
            f"project_id={project.id}",
            f"project_name={project.name}",
            f"process_instance_id={(project.process_snapshot or {}).get('process_instance_id')}",
            f"process_revision={project.process_revision}",
            f"stage_id={task['stage_id']}",
            f"task_id={task['id']}",
            f"task_title={task['title']}",
            f"task_status={task['status']}",
            f"workflow_id={task.get('workflow_id') or 'UNCONNECTED'}",
            "Do not claim an execution is live unless the canonical workflow endpoint confirms it.",
            "Any task mutation, workflow execution or resource change requires explicit user confirmation.",
            "[User message]",
            body.question,
        ]
    )
    upstream = await chat_stream(
        StreamRequest(
            question=server_goal,
            request_id=body.request_id,
            session_id=conversation.session_id,
            agent_id=None,
            skill_id=None,
            quoted_context=None,
        ),
        payload,
    )

    async def relay_and_record():
        answer: str | None = None
        failure: str | None = None
        deltas: list[str] = []
        terminal_done = False
        buffer = ""

        def consume(frames: list[str]) -> None:
            nonlocal answer, failure, terminal_done
            for frame in frames:
                event = _parse_sse_event(frame)
                if event is None:
                    continue
                if event.get("type") == "delta" and event.get("content"):
                    deltas.append(str(event["content"]))
                if event.get("type") == "done":
                    terminal_done = True
                    answer = str(event.get("answer") or "".join(deltas))
                if event.get("type") == "error":
                    failure = str(
                        event.get("detail")
                        or event.get("message")
                        or "Hermes stream failed"
                    )

        try:
            async for chunk in upstream.body_iterator:
                text = chunk.decode("utf-8") if isinstance(chunk, bytes) else str(chunk)
                buffer += text
                frames, buffer = _extract_sse_frames(buffer)
                consume(frames)
                yield chunk
            frames, buffer = _extract_sse_frames(buffer, final=True)
            consume(frames)
            if not terminal_done and failure is None:
                failure = "Hermes stream ended without a terminal event"
                yield f"data: {json.dumps({'type': 'error', 'detail': failure}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            failure = f"Hermes stream interrupted: {exc}"
            yield f"data: {json.dumps({'type': 'error', 'detail': failure}, ensure_ascii=False)}\n\n"
        recorded_answer = (
            failure
            or answer
            or "Hermes stream ended without a terminal event"
        )
        terminal_type = "error" if failure or not terminal_done else "done"
        async with SessionLocal() as db:
            db.add(
                WorkspaceTaskMessage(
                    id=f"msg_{uuid4().hex}",
                    tenant_key=tenant_key,
                    conversation_id=conversation_id,
                    request_id=body.request_id,
                    role="assistant",
                    content=recorded_answer,
                    event_metadata={
                        "source": "hermes-sse",
                        "terminal_type": terminal_type,
                    },
                )
            )
            try:
                await db.commit()
            except IntegrityError:
                await db.rollback()

    return StreamingResponse(
        relay_and_record(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
