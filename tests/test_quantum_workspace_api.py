from __future__ import annotations

import atexit
import asyncio

import json
import os
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from tempfile import gettempdir
from uuid import uuid4

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

TEST_DB = Path(gettempdir()) / f"quantum_workspace_test_{os.getpid()}.db"
if TEST_DB.exists():
    TEST_DB.unlink()
atexit.register(lambda: TEST_DB.unlink(missing_ok=True))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ.setdefault("AUTHEN_DEV_MODE", "true")

from backend.main import app  # noqa: E402
import backend.api.quantum_workspace as qws_api  # noqa: E402
from backend.api.auth import require_auth  # noqa: E402
from backend.api.quantum_workspace import (  # noqa: E402
    _apply_taskboard_backfill,
    _enforce_agent_lease_fence,
    _enforce_qws_relation_backfill_contract,
    _parse_backfill_block,
)
from backend.services.workspace_process import instantiate_project_blueprint, persist_process_revision  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.models.workflow import WorkflowDefinition  # noqa: E402
from backend.models.workspace import (  # noqa: E402
    WorkspaceBusinessIntake,
    WorkspaceCardSessionRegistry,
    WorkspaceDeliveryManifest,
    WorkspaceKnowledgeCandidate,
    WorkspaceProcessDraft,
    WorkspaceProject,
    WorkspaceTaskConversation,
    WorkspaceTaskMessage,
)


@pytest.fixture(autouse=True)
def _reset_database():
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a",
        "user_id": "user-a",
        "sub": "user-a",
        "principal_type": "human",
        "amr": ["pwd"], "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_ipd_template_instantiates_one_idempotent_project(_reset_database):
    client = _reset_database

    templates = client.get("/api/v1/project-templates")
    assert templates.status_code == 200
    assert [item["id"] for item in templates.json()] == ["ipd-product-development"]

    payload = {
        "request_id": "idem-project-0001",
        "name": "Quantum Router",
        "goal": "交付可验证的新产品方案",
        "desired_outputs": ["产品包", "验证证据"],
        "inputs": {},
        "truth_mode": "PLANNED",
        "resource_overrides": {},
    }
    first = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json=payload,
    )
    repeated = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json=payload,
    )

    assert first.status_code == 201
    assert repeated.status_code == 200
    assert repeated.json()["project_id"] == first.json()["project_id"]
    assert first.json()["template_version"] == "1.0.0"

    projects = client.get("/api/v1/projects")
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()] == [first.json()["project_id"]]


def test_project_home_supports_update_and_owner_delete(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "home-crud")
    updated = client.patch(
        f"/api/v1/projects/{project_id}",
        json={"name": "新项目名", "goal": "更新后的业务目标", "desired_outputs": ["项目文档"]},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "新项目名"
    assert updated.json()["desired_outputs"] == ["项目文档"]
    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"X-QWS-Confirm-Project-Id": project_id},
    )
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_workspace_bootstrap_returns_project_and_process_in_one_request(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "workspace-bootstrap")
    response = client.get(f"/api/v1/projects/{project_id}/workspace-bootstrap")
    assert response.status_code == 200
    payload = response.json()
    assert payload["project"]["id"] == project_id
    assert payload["process"]["project_id"] == project_id
    assert payload["process"]["process_revision"] == payload["project"]["process_revision"]


def test_project_role_update_persists_revision_and_revalidates(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "role-revision")
    before = client.get(f"/api/v1/projects/{project_id}/workspace-bootstrap").json()
    process = before["process"]
    old_role = next(task["assignee_role"] for task in process["tasks"] if task.get("assignee_role"))
    updated = client.put(
        f"/api/v1/projects/{project_id}/roles/{old_role}",
        json={
            "expected_revision": process["process_revision"],
            "name": "项目总负责人",
            "description": "统筹关键交付与跨角色决策",
            "decision_rights": ["确认关键 Gate"],
            "collaboration_boundaries": ["不替代专业验收人"],
        },
    )
    assert updated.status_code == 200, updated.text
    payload = updated.json()
    assert payload["process_revision"] == process["process_revision"] + 1
    assert payload["role"]["name"] == "项目总负责人"
    assert payload["validation"]["operation"] == "ROLE_UPDATE"

    after = client.get(f"/api/v1/projects/{project_id}/workspace-bootstrap").json()["process"]
    assert after["process_revision"] == payload["process_revision"]
    assert any(task.get("assignee_role") == "项目总负责人" for task in after["tasks"])
    assert after["role_profiles"]["项目总负责人"]["description"] == "统筹关键交付与跨角色决策"
    assert old_role not in after["role_profiles"]

    validation = client.post(
        f"/api/v1/projects/{project_id}/consistency/validate",
        json={"operation": "AUTOMATION_PREFLIGHT"},
    )
    assert validation.status_code == 200
    assert validation.json()["project_id"] == project_id


def test_hermes_blueprint_compiles_dynamic_stages_rich_cards_and_documents():
    process = instantiate_project_blueprint({
        "project_goal": "交付动态项目",
        "stages": [
            {"key": "discover", "name": "发现", "goal": "验证问题", "acceptance_criteria": ["完成访谈"]},
            {"key": "ship", "name": "交付", "goal": "发布成果", "acceptance_criteria": ["验收通过"]},
        ],
        "tasks": [
            {"key": "research", "stage_key": "discover", "title": "用户研究", "description": "访谈目标用户", "role": "研究员", "status": "todo", "priority": "high", "labels": ["需求"], "acceptance_criteria": ["5 份访谈"], "deliverables": ["访谈报告"], "handoff": {"to": "开发负责人", "completion_definition": "报告评审通过"}},
            {"key": "build", "stage_key": "ship", "title": "完成交付", "description": "实现并交付", "role": "开发负责人", "status": "backlog", "priority": "urgent", "parent_key": "research", "relations": [{"type": "blocked_by", "target_key": "research"}], "deliverables": ["发布包"]},
        ],
        "documents": [{"id": "brief", "title": "项目说明", "content": "# 项目说明", "status": "ready"}],
    })
    assert [stage["name"] for stage in process["stages"]] == ["发现", "交付"]
    assert process["tasks"][0]["priority"] == "high"
    assert process["tasks"][1]["status"] == "BACKLOG"
    assert {item["type"] for item in process["tasks"][1]["relations"]} == {"parent", "blocked_by"}
    assert process["documents"][0]["title"] == "项目说明"
    assert any(item.get("id") == "00-project-master" and item.get("canonical") for item in process["documents"])
    assert all(task.get("execution_document_id") for task in process["tasks"])
    assert process["document_policy"]["task_record_required"] is True


def test_hermes_blueprint_default_schedule_follows_dependencies_and_workdays():
    process = instantiate_project_blueprint({
        "project_goal": "按依赖自动排期",
        "stages": [
            {"key": "design", "name": "设计"},
            {"key": "ship", "name": "交付"},
        ],
        "tasks": [
            {
                "key": "design",
                "stage_key": "design",
                "title": "完成设计",
                "estimated_duration_days": 2,
            },
            {
                "key": "ship",
                "stage_key": "ship",
                "title": "完成交付",
                "estimated_duration_days": 1,
                "relations": [{"type": "blocked_by", "target_key": "design"}],
            },
        ],
    }, schedule_anchor=date(2026, 8, 29))
    assert process["tasks"][0]["start_date"] == "2026-08-31"
    assert process["tasks"][0]["due_date"] == "2026-09-01"
    assert process["tasks"][1]["start_date"] == "2026-09-02"
    assert process["tasks"][1]["due_date"] == "2026-09-02"
    assert process["stages"][0]["planned_start_at"] == "2026-08-31"
    assert process["stages"][1]["planned_finish_at"] == "2026-09-02"
    assert process["calendar"]["status"] == "SCHEDULED"
    assert process["calendar"]["schedule_source"] == "SYSTEM_DEFAULT"


def test_process_revision_flushes_fk_targets_before_dependencies():
    class ScalarRows:
        def all(self):
            return []

    class FlushProbe:
        def __init__(self):
            self.added = []
            self.flushes = []

        async def scalar(self, _statement):
            return SimpleNamespace(id="cfgrev_test")

        async def scalars(self, _statement):
            return ScalarRows()

        def add(self, row):
            self.added.append(row)

        async def flush(self):
            self.flushes.append(tuple(type(row).__name__ for row in self.added))

    probe = FlushProbe()
    process = instantiate_project_blueprint({
        "project_goal": "验证外键写入顺序",
        "stages": [{"key": "delivery", "name": "交付", "goal": "完成"}],
        "tasks": [
            {"key": "first", "stage_key": "delivery", "title": "前置任务", "role": "负责人"},
            {"key": "second", "stage_key": "delivery", "title": "后续任务", "role": "负责人", "relations": [{"type": "blocked_by", "target_key": "first"}]},
        ],
    })
    asyncio.run(persist_process_revision(
        probe,
        project=SimpleNamespace(id="project_test", tenant_key="tenant-a"),
        process=process,
        revision=1,
    ))

    dependency_flush = next(index for index, rows in enumerate(probe.flushes) if "WorkspaceTaskDependency" in rows)
    task_revision_flush = next(index for index, rows in enumerate(probe.flushes) if "WorkspaceTaskRevision" in rows)
    assert task_revision_flush < dependency_flush


def test_project_planning_session_dispatches_confirmed_blueprint(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "planning-dispatch")
    opened = client.post("/api/v1/task-conversations", json={
        "project_id": project_id,
        "task_id": "project-intake",
        "workflow_id": None,
        "agent_version": "hermes-project-planning-v1",
        "card_context": {
            "schema_version": 1,
            "project": {"id": project_id, "name": "planning-dispatch", "business_goal": "交付项目"},
            "task": {
                "dashi_task_id": "project-intake", "qws_task_id": "project-intake",
                "title": "项目需求收敛与派发", "descriptions": [{"content": "交付项目"}],
                "status": "in_progress", "assignee": {"id": "main_agent", "name": "Hermes"},
                "qws": {"binding_kind": "project_planning", "stage_id": "project-planning"},
            },
        },
    })
    assert opened.status_code == 201, opened.text
    conversation_id = opened.json()["id"]
    request_id = "project-blueprint-0001"
    blueprint = {
        "project_goal": "交付项目",
        "stages": [{"key": "delivery", "name": "交付", "goal": "完成", "acceptance_criteria": ["通过验收"]}],
        "tasks": [
            {"key": "deliver", "stage_key": "delivery", "title": "完成交付", "description": "完成项目成果", "role": "交付负责人", "status": "todo", "priority": "high", "acceptance_criteria": ["成果可阅读"], "deliverables": ["交付说明"]},
            {"key": "review", "stage_key": "delivery", "title": "验收交付", "description": "验收项目成果", "role": "验收负责人", "status": "backlog", "priority": "medium", "relations": [{"type": "blocked_by", "target_key": "deliver"}]},
        ],
        "documents": [{"id": "brief", "title": "项目说明", "content": "# 项目说明", "status": "ready"}],
    }

    async def insert_blueprint_message():
        async with SessionLocal() as db:
            db.add(WorkspaceTaskMessage(
                id="msg_project_blueprint_0001", tenant_key="tenant-a",
                conversation_id=conversation_id, request_id=request_id, role="assistant",
                content=f"蓝图如下。\n```project_blueprint\n{json.dumps(blueprint, ensure_ascii=False)}\n```",
                event_metadata={"terminal_type": "done"},
            ))
            await db.commit()

    asyncio.run(insert_blueprint_message())
    dispatched = client.post(f"/api/v1/projects/{project_id}/planning/dispatch", json={
        "conversation_id": conversation_id,
        "assistant_request_id": request_id,
        "expected_revision": 0,
    })
    assert dispatched.status_code == 200, dispatched.text
    assert dispatched.json()["stage_count"] == 1
    assert dispatched.json()["task_count"] == 2
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    assert process["tasks"][0]["title"] == "完成交付"
    assert len(process["dependencies"]) == 1
    assert process["documents"][0]["id"] == "brief"

    human_edited = json.loads(json.dumps(blueprint, ensure_ascii=False))
    human_edited["project_goal"] = "按人工修订版交付项目"
    human_edited["tasks"][0]["title"] = "按人工要求完成交付"
    redispatched = client.post(f"/api/v1/projects/{project_id}/planning/dispatch", json={
        "conversation_id": conversation_id,
        "assistant_request_id": request_id,
        "expected_revision": 1,
        "blueprint": human_edited,
    })
    assert redispatched.status_code == 200, redispatched.text
    assert redispatched.json()["blueprint_source"] == "HUMAN_EDITED_CONFIRMATION"
    revised_process = client.get(f"/api/v1/projects/{project_id}/process").json()
    assert revised_process["project_goal"] == "按人工修订版交付项目"
    assert revised_process["tasks"][0]["title"] == "按人工要求完成交付"
    assert revised_process["dispatch_source"]["human_edited"] is True

    async def task_registry_profile():
        async with SessionLocal() as db:
            return await db.scalar(
                select(WorkspaceCardSessionRegistry).where(
                    WorkspaceCardSessionRegistry.project_id == project_id,
                    WorkspaceCardSessionRegistry.task_id == process["tasks"][0]["id"],
                )
            )

    registry = asyncio.run(task_registry_profile())
    assert registry is not None
    assert registry.task_profile["goal"] == "完成项目成果"
    assert registry.task_profile["current_state"] == "TODO"
    assert registry.task_profile["progress"] == 0
    assert registry.task_profile["acceptance_criteria"] == ["成果可阅读"]
    assert registry.task_profile["stage"]["name"] == "交付"

    deleted = client.delete(
        f"/api/v1/projects/{project_id}",
        headers={"X-QWS-Confirm-Project-Id": project_id},
    )
    assert deleted.status_code == 204, deleted.text
    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_project_blueprint_deduplicates_equivalent_dependency_edges():
    process = instantiate_project_blueprint({
        "project_goal": "验证依赖去重",
        "stages": [{"key": "delivery", "name": "交付"}],
        "tasks": [
            {
                "key": "A", "stage_key": "delivery", "title": "前置任务",
                "relations": [
                    {"type": "blocks", "target_key": "B"},
                    {"type": "blocks", "target_key": "B"},
                ],
            },
            {
                "key": "B", "stage_key": "delivery", "title": "后置任务",
                "relations": [{"type": "blocked_by", "target_key": "A"}],
            },
        ],
    })
    assert len(process["dependencies"]) == 1
    assert len(process["graphs"]["workflow"]["edges"]) == 1
    assert len(process["tasks"][0]["relations"]) == 1


def test_new_project_session_automatically_assesses_context_and_preserves_system_origin(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id = _create_project(client, "automatic-intake")
    opened = client.post("/api/v1/task-conversations", json={
        "project_id": project_id,
        "task_id": "project-intake",
        "workflow_id": None,
        "agent_version": "hermes-project-planning-v1",
        "card_context": {
            "schema_version": 1,
            "project": {
                "id": project_id,
                "name": "automatic-intake",
                "business_goal": "为制造团队交付可验收的生产管理系统",
                "desired_outputs": ["项目文档"],
            },
            "task": {
                "dashi_task_id": "project-intake",
                "qws_task_id": "project-intake",
                "title": "项目需求收敛与派发",
                "descriptions": [{"content": "为制造团队交付可验收的生产管理系统"}],
                "status": "in_progress",
                "assignee": {"id": "main_agent", "name": "Hermes"},
                "qws": {"binding_kind": "project_planning", "stage_id": "project-planning"},
            },
        },
    })
    assert opened.status_code == 201, opened.text
    captured = {}

    async def fake_chat_stream(req, payload, *, knowledge_query=None, **kwargs):
        captured["question"] = req.question
        captured["knowledge_query"] = knowledge_query
        captured["session_id"] = req.session_id
        captured["context"] = req.client_session_context
        captured["trusted_professional_surface"] = kwargs.get("trusted_professional_surface")

        answer = (
            "```project_blueprint\n"
            f"{json.dumps({'schema_version': '1.0', 'project_goal': '交付可验证的新产品方案', 'stages': [{'key': 'delivery', 'name': '交付'}], 'tasks': [{'key': 'T1', 'stage_key': 'delivery', 'title': '完成交付'}]}, ensure_ascii=False)}\n"
            "```"
        )
        async def event_stream():
            yield f'data: {json.dumps({"type": "clarify", "clarify_id": "clarify-1", "question": "首期必须覆盖哪些生产环节？", "choices": ["排产", "报工"]}, ensure_ascii=False)}\n\n'
            yield f'data: {json.dumps({"type": "done", "answer": answer}, ensure_ascii=False)}\n\n'

        return StreamingResponse(event_stream(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    conversation_id = opened.json()["id"]
    streamed = client.post(
        f"/api/v1/task-conversations/{conversation_id}/messages/stream",
        json={
            "question": "Assess the project context supplied by the application.",
            "request_id": f"project-intake-{project_id}",
            "trigger": "project_created",
        },
    )
    assert streamed.status_code == 200, streamed.text
    assert '"phase": "planning_context"' in streamed.text
    assert '"phase": "blueprint_repair"' not in streamed.text
    assert '"type": "clarify"' in streamed.text
    assert "project_name=Quantum Router" in captured["question"]
    assert "project_goal=交付可验证的新产品方案" in captured["question"]
    assert "不要要求用户重复" in captured["knowledge_query"]
    assert "调用 clarify" in captured["question"]
    assert "持续询问用户至需求收敛" in captured["knowledge_query"]
    assert captured["session_id"] == opened.json()["binding"]["session_id"]
    assert captured["context"] is None
    assert captured["trusted_professional_surface"] is True
    messages = client.get(
        f"/api/v1/task-conversations/{conversation_id}/messages"
    ).json()
    assert [(item["role"], item["event_metadata"].get("kind")) for item in messages] == [
        ("system", "auto_project_intake"),
        ("assistant", None),
    ]


def test_project_planning_repairs_one_missing_blueprint_before_reporting_done(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id = _create_project(client, "blueprint-repair-success")
    opened = client.post("/api/v1/task-conversations", json={
        "project_id": project_id,
        "task_id": "project-intake",
        "workflow_id": None,
        "agent_version": "hermes-project-planning-v1",
        "card_context": {
            "schema_version": 1,
            "project": {"id": project_id, "name": "蓝图修复", "business_goal": "生成可派发计划", "desired_outputs": []},
            "task": {
                "dashi_task_id": "project-intake",
                "qws_task_id": "project-intake",
                "title": "项目需求收敛与派发",
                "descriptions": [{"content": "生成可派发计划"}],
                "status": "in_progress",
                "assignee": {"id": "main_agent", "name": "Hermes"},
                "qws": {"binding_kind": "project_planning", "stage_id": "project-planning"},
            },
        },
    })
    assert opened.status_code == 201, opened.text
    calls = []
    blueprint = {
        "project_goal": "生成可派发计划",
        "stages": [{"key": "delivery", "name": "交付"}],
        "tasks": [{"key": "T1", "stage_key": "delivery", "title": "完成交付", "role": "负责人"}],
        "documents": [],
    }

    async def fake_chat_stream(req, payload, **kwargs):
        calls.append(req)

        async def events():
            if len(calls) == 1:
                invalid = {"project_goal": "生成可派发计划", "stages": [], "tasks": []}
                answer = f"```project_blueprint\n{json.dumps(invalid, ensure_ascii=False)}\n```"
                yield f"data: {json.dumps({'type': 'done', 'answer': answer}, ensure_ascii=False)}\n\n"
            else:
                answer = f"蓝图已补全。\\n```project_blueprint\\n{json.dumps(blueprint, ensure_ascii=False)}\\n```"
                yield f"data: {json.dumps({'type': 'done', 'answer': answer}, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    request_id = f"project-plan-{uuid4().hex}"
    streamed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages/stream",
        json={"question": "现在生成完整蓝图", "request_id": request_id, "trigger": "user"},
    )
    assert streamed.status_code == 200, streamed.text
    assert len(calls) == 2
    assert all(request.client_session_context is None for request in calls)
    assert "[Blueprint repair pass]" in calls[1].question
    assert '"phase": "blueprint_repair"' in streamed.text
    assert '"blueprint_repair_attempted": true' in streamed.text
    assert '"type": "planning_incomplete"' not in streamed.text
    messages = client.get(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages"
    ).json()
    assistant = next(item for item in messages if item["role"] == "assistant")
    assert assistant["event_metadata"]["terminal_type"] == "done"
    assert assistant["event_metadata"]["retry_attempted"] is True
    assert qws_api._project_blueprint_from_text(assistant["content"]) == blueprint


def test_project_planning_persists_and_replays_typed_incomplete_terminal(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id = _create_project(client, "blueprint-repair-incomplete")
    opened = client.post("/api/v1/task-conversations", json={
        "project_id": project_id,
        "task_id": "project-intake",
        "workflow_id": None,
        "agent_version": "hermes-project-planning-v1",
        "card_context": {
            "schema_version": 1,
            "project": {"id": project_id, "name": "蓝图缺口", "business_goal": "生成可派发计划", "desired_outputs": []},
            "task": {
                "dashi_task_id": "project-intake",
                "qws_task_id": "project-intake",
                "title": "项目需求收敛与派发",
                "descriptions": [{"content": "生成可派发计划"}],
                "status": "in_progress",
                "assignee": {"id": "main_agent", "name": "Hermes"},
                "qws": {"binding_kind": "project_planning", "stage_id": "project-planning"},
            },
        },
    })
    assert opened.status_code == 201, opened.text
    calls = []

    async def fake_chat_stream(req, payload, **kwargs):
        calls.append(req)

        async def events():
            answer = "尚缺少不可替代的外部约束。" if len(calls) == 1 else "PLANNING_GAP: 缺少法定审批主体。"
            yield f"data: {json.dumps({'type': 'done', 'answer': answer}, ensure_ascii=False)}\n\n"

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    request_id = f"project-plan-{uuid4().hex}"
    payload = {"question": "现在生成完整蓝图", "request_id": request_id, "trigger": "user"}
    streamed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages/stream",
        json=payload,
    )
    assert streamed.status_code == 200, streamed.text
    assert len(calls) == 2
    assert '"type": "planning_incomplete"' in streamed.text
    assert '"code": "missing_project_blueprint"' in streamed.text
    assert '"retry_attempted": true' in streamed.text
    assert '"type": "done"' not in streamed.text
    messages = client.get(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages"
    ).json()
    assistant = next(item for item in messages if item["role"] == "assistant")
    assert assistant["event_metadata"]["terminal_type"] == "planning_incomplete"
    assert assistant["event_metadata"]["code"] == "missing_project_blueprint"
    assert assistant["event_metadata"]["retry_attempted"] is True
    replayed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages/stream",
        json=payload,
    )
    assert replayed.status_code == 200, replayed.text
    assert '"type": "planning_incomplete"' in replayed.text
    assert '"type": "done"' not in replayed.text


def test_readiness_fails_closed_when_database_initialization_failed(_reset_database):
    client = _reset_database
    app.state.db_ready = False
    degraded = client.get("/ready")
    assert degraded.status_code == 503
    assert degraded.json()["status"] == "degraded"
    app.state.db_ready = True


def test_projects_are_owner_only_even_within_the_same_tenant(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "tenant-isolation")
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a",
        "user_id": "user-b",
        "sub": "user-b",
        "is_super_admin": False,
    }

    assert client.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert client.get("/api/v1/projects").json() == []


def test_idempotency_is_scoped_and_rejects_payload_drift(_reset_database):
    client = _reset_database
    payload = {
        "request_id": "owner-project-key",
        "name": "Owner A",
        "goal": "Goal A",
        "desired_outputs": ["A"],
        "truth_mode": "PLANNED",
    }
    first = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate", json=payload
    )
    assert first.status_code == 201
    input_drift = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json={
            **payload,
            "inputs": {"source": "changed"},
            "resource_overrides": {"gpu": 99},
        },
    )
    assert input_drift.status_code == 409
    drift = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json={**payload, "name": "Different", "goal": "Different"},
    )
    assert drift.status_code == 409

    project_a = first.json()["project_id"]
    project_b = _create_project(client, "idempotency-project-b")
    intake_payload = {
        "request_id": "same-intake-key",
        "business_goal": "目标",
        "customers_and_scenarios": "场景",
        "product_scope": "全新产品",
        "product_form": "software",
        "innovation_level": "new_product",
        "tailoring_level": "standard",
        "requirements_and_evidence": "已有证据",
        "desired_deliverables": ["产品包"],
        "target_finish_at": "2027-08-31T00:00:00Z",
    }
    intake_a = client.post(
        f"/api/v1/projects/{project_a}/business-intakes", json=intake_payload
    )
    intake_b = client.post(
        f"/api/v1/projects/{project_b}/business-intakes", json=intake_payload
    )
    assert intake_a.status_code == intake_b.status_code == 201
    assert intake_a.json()["id"] != intake_b.json()["id"]


def test_concurrent_intake_and_draft_idempotency_replay_without_500(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id = _create_project(client, "idempotency-race")
    original_commit = AsyncSession.commit
    gate = {"model": WorkspaceBusinessIntake, "count": 0, "release": asyncio.Event()}

    async def synchronized_commit(session):
        if any(isinstance(item, gate["model"]) for item in session.new):
            gate["count"] += 1
            if gate["count"] == 2:
                gate["release"].set()
            else:
                await gate["release"].wait()
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", synchronized_commit)
    intake_payload = {
        "request_id": "idem-intake-race",
        "business_goal": "目标",
        "customers_and_scenarios": "场景",
        "product_scope": "全新产品",
        "product_form": "software",
        "innovation_level": "new_product",
        "tailoring_level": "standard",
        "requirements_and_evidence": "已有证据",
        "desired_deliverables": ["产品包"],
        "target_finish_at": "2027-08-31T00:00:00Z",
    }

    async def race_intakes():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            url = f"/api/v1/projects/{project_id}/business-intakes"
            return await asyncio.gather(
                async_client.post(url, json=intake_payload),
                async_client.post(url, json=intake_payload),
            )

    intake_responses = asyncio.run(race_intakes())
    assert sorted(response.status_code for response in intake_responses) == [200, 201]
    intake_id = intake_responses[0].json()["id"]

    gate.update(
        {"model": WorkspaceProcessDraft, "count": 0, "release": asyncio.Event()}
    )
    draft_payload = {
        "request_id": "idem-draft-race",
        "business_intake_id": intake_id,
        "process_template_id": "ipd-product-development",
        "process_template_version": "1.0.0",
        "catalog_revision": "catalog-current",
    }

    async def race_drafts():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            url = f"/api/v1/projects/{project_id}/process-drafts/generate"
            return await asyncio.gather(
                async_client.post(url, json=draft_payload),
                async_client.post(url, json=draft_payload),
            )

    draft_responses = asyncio.run(race_drafts())
    assert sorted(response.status_code for response in draft_responses) == [200, 201]


def _create_project(client, suffix="draft"):
    response = client.post(
        "/api/v1/project-templates/ipd-product-development/instantiate",
        json={
            "request_id": f"idem-project-{suffix}",
            "name": "Quantum Router",
            "goal": "交付可验证的新产品方案",
            "desired_outputs": ["产品包", "验证证据"],
            "truth_mode": "PLANNED",
        },
    )
    assert response.status_code == 201
    return response.json()["project_id"]


def test_project_documents_assets_and_distillation_are_source_grounded(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "knowledge-p2")
    bootstrap = client.get(f"/api/v1/projects/{project_id}/workspace-bootstrap").json()
    revision = bootstrap["process"]["process_revision"]
    intake = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            "request_id": "idem-intake-knowledge-p2",
            "business_goal": "沉淀可审计项目知识",
            "customers_and_scenarios": "项目成员跨 Session 交接",
            "product_scope": "项目知识闭环",
            "product_form": "software",
            "innovation_level": "major_upgrade",
            "tailoring_level": "standard",
            "requirements_and_evidence": "文档中的事实必须有可验证来源",
            "desired_deliverables": ["项目说明"],
            "target_finish_at": "2027-03-31T00:00:00Z",
        },
    )
    assert intake.status_code == 201
    source_ref = f"intake:{intake.json()['id']}@{intake.json()['revision']}"

    missing_source = client.put(
        f"/api/v1/projects/{project_id}/documents/brief",
        json={
            "expected_revision": revision,
            "title": "项目说明",
            "content": "# 项目说明",
            "status": "PUBLISHED",
        },
    )
    assert missing_source.status_code == 422

    saved = client.put(
        f"/api/v1/projects/{project_id}/documents/brief",
        json={
            "expected_revision": revision,
            "title": "项目说明",
            "content": "# 项目说明\n\n参考 [[交付清单]]。",
            "status": "PUBLISHED",
            "source_refs": [source_ref],
            "tags": ["project/qws"],
        },
    )
    assert saved.status_code == 200
    revision = saved.json()["process_revision"]
    assert saved.json()["document"]["revision"] == 1
    assert saved.json()["document"]["content_hash"]

    listed = client.get(f"/api/v1/projects/{project_id}/documents")
    assert listed.status_code == 200
    assert listed.json()["truth_contract"] == "READABLE_PROJECTION_ONLY"
    assert listed.json()["graph"]["broken_links"][0]["target_title"] == "交付清单"

    exported = client.get(f"/api/v1/projects/{project_id}/documents/brief/obsidian")
    assert exported.status_code == 200
    assert "source_refs:" in exported.json()["content"]
    assert source_ref in exported.json()["content"]

    distilled = client.post(
        f"/api/v1/projects/{project_id}/distillation-runs",
        json={"expected_revision": revision, "max_candidates": 10},
    )
    assert distilled.status_code == 200
    revision = distilled.json()["process_revision"]
    assert len(distilled.json()["candidates"]) == 1
    candidate = distilled.json()["candidates"][0]
    assert candidate["status"] == "CANDIDATE"
    assert candidate["source_refs"] == [source_ref]

    async def _simulate_pre_governance_candidate():
        async with SessionLocal() as db:
            await db.execute(delete(WorkspaceKnowledgeCandidate).where(
                WorkspaceKnowledgeCandidate.id == candidate["id"]
            ))
            project = await db.scalar(select(WorkspaceProject).where(WorkspaceProject.id == project_id))
            assert project is not None
            snapshot = dict(project.process_snapshot or {})
            snapshot["distillation_candidates"] = [
                {
                    **item,
                    **({"title": "旧候选标题", "summary": "旧候选摘要"}
                       if item.get("id") == candidate["id"] else {}),
                }
                for item in snapshot.get("distillation_candidates") or []
            ]
            project.process_snapshot = snapshot
            await db.commit()

    asyncio.run(_simulate_pre_governance_candidate())
    legacy_assets = client.get(f"/api/v1/projects/{project_id}/assets").json()
    legacy_view = next(
        item for item in legacy_assets["distillation_candidates"] if item["id"] == candidate["id"]
    )
    assert legacy_view["title"] == "旧候选标题"

    admitted = client.post(
        f"/api/v1/projects/{project_id}/distillation-candidates/{candidate['id']}/decision",
        json={"expected_revision": revision, "decision": "ADMIT", "note": "来源已核验"},
    )
    assert admitted.status_code == 200
    assert admitted.json()["candidate"]["status"] == "ADMITTED"
    revision = admitted.json()["process_revision"]

    restricted = client.post(
        f"/api/v1/projects/{project_id}/distillation-candidates/{candidate['id']}/govern",
        json={
            "expected_revision": revision, "action": "PERMISSION_CHANGE",
            "reason": "来源权限已收紧", "source_refs": [],
        },
    )
    assert restricted.status_code == 200
    assert restricted.json()["candidate"]["status"] == "RESTRICTED"
    revision = restricted.json()["process_revision"]
    restricted_assets = client.get(f"/api/v1/projects/{project_id}/assets").json()
    restricted_view = next(
        item for item in restricted_assets["distillation_candidates"]
        if item["id"] == candidate["id"]
    )
    assert restricted_view["title"] is None
    assert restricted_view["summary"] is None

    corrected = client.post(
        f"/api/v1/projects/{project_id}/distillation-candidates/{candidate['id']}/govern",
        json={
            "expected_revision": revision, "action": "CORRECT", "reason": "原摘要需纠正",
            "replacement": {"title": "经核验的项目事实", "summary": "修正后的摘要"},
            "source_refs": [source_ref],
        },
    )
    assert corrected.status_code == 200
    replacement = corrected.json()["replacement"]
    assert corrected.json()["candidate"]["status"] == "SUPERSEDED"
    revision = corrected.json()["process_revision"]
    deleted = client.post(
        f"/api/v1/projects/{project_id}/distillation-candidates/{replacement['id']}/govern",
        json={
            "expected_revision": revision, "action": "COMPLIANCE_DELETE",
            "reason": "合规删除请求", "source_refs": [],
        },
    )
    assert deleted.status_code == 200
    assert deleted.json()["candidate"]["status"] == "DELETED"
    assert deleted.json()["governance_receipt"]["snapshot_payload_present"] is False
    revision = deleted.json()["process_revision"]
    governed_assets = client.get(f"/api/v1/projects/{project_id}/assets").json()
    deleted_view = next(
        item for item in governed_assets["distillation_candidates"] if item["id"] == replacement["id"]
    )
    assert deleted_view["title"] is None
    assert deleted_view["summary"] is None

    rule = {
        "version": 1,
        "enabled": True,
        "automation_level": "L1",
        "output_status": "WAITING_CLAIM",
        "cron": "0 9 * * 1",
        "timezone": "Asia/Shanghai",
        "misfire_policy": "RUN_ONCE",
        "concurrency_policy": "FORBID",
        "novelty_threshold": 0.75,
        "budget": {
            "max_candidates_scanned": 100,
            "max_recommendations_per_run": 5,
            "max_catch_up_runs": 1,
        },
        "circuit_breaker": {"noise_ratio": 0.9},
    }
    configured = client.put(
        f"/api/v1/projects/{project_id}/automations/weekly-review",
        json={"expected_revision": revision, "rule": rule},
    )
    assert configured.status_code == 200
    revision = configured.json()["process_revision"]

    denied_run = client.post(
        f"/api/v1/projects/{project_id}/automation-runs",
        json={
            "expected_revision": revision, "rule_id": "weekly-review", "rule_version": 1,
            "scheduled_for": "2026-08-31T01:00:00Z", "candidates": [],
        },
    )
    assert denied_run.status_code == 403

    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "automation-service",
        "principal_type": "service", "amr": ["service_token"],
        "scopes": ["qws:automation-run"], "is_super_admin": False,
    }

    planned = client.post(
        f"/api/v1/projects/{project_id}/automations/weekly-review/plan-due-runs",
        json={
            "rule_version": 1,
            "due_slots": ["2026-08-31T01:00:00Z"],
            "now": "2026-08-31T02:00:00Z",
        },
    )
    assert planned.status_code == 200
    assert planned.json()["planned_slots"] == ["2026-08-31T01:00:00+00:00"]

    automated = client.post(
        f"/api/v1/projects/{project_id}/automation-runs",
        json={
            "expected_revision": revision,
            "rule_id": "weekly-review",
            "rule_version": 1,
            "scheduled_for": "2026-08-31T01:00:00Z",
            "candidates": [{
                "title": "核对项目交付",
                "description": "检查交付证据",
                "source_refs": [source_ref],
            }],
        },
    )
    assert automated.status_code == 200
    revision = automated.json()["process_revision"]
    run = automated.json()["run"]
    recommendation = run["recommendations"][0]
    assert recommendation["status"] == "WAITING_CLAIM"

    replay = client.post(
        f"/api/v1/projects/{project_id}/automation-runs",
        json={
            "expected_revision": revision,
            "rule_id": "weekly-review",
            "rule_version": 1,
            "scheduled_for": "2026-08-31T01:00:00Z",
            "candidates": [{
                "title": "核对项目交付", "description": "检查交付证据",
                "source_refs": [source_ref],
            }],
        },
    )
    assert replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    drifted_replay = client.post(
        f"/api/v1/projects/{project_id}/automation-runs",
        json={
            "expected_revision": revision,
            "rule_id": "weekly-review",
            "rule_version": 1,
            "scheduled_for": "2026-08-31T01:00:00Z",
            "candidates": [{
                "title": "漂移后的建议", "description": "不同负载",
                "source_refs": [source_ref],
            }],
        },
    )
    assert drifted_replay.status_code == 409
    assert drifted_replay.json()["detail"] == "automation_run_replay_payload_drift"

    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "user-a",
        "principal_type": "human", "amr": ["pwd"], "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }

    decided = client.post(
        f"/api/v1/projects/{project_id}/automation-runs/{run['id']}/recommendations/{recommendation['id']}/decision",
        json={"expected_revision": revision, "decision": "ACCEPT", "note": "进入捕获区"},
    )
    assert decided.status_code == 200
    assert decided.json()["run"]["recommendations"][0]["decision"] == "ACCEPTED"
    assert decided.json()["metrics"]["acceptance_rate"] == 1.0
    revision = decided.json()["process_revision"]

    denied_observation = client.post(
        f"/api/v1/projects/{project_id}/telemetry-events",
        json={
            "expected_revision": revision,
            "event": {
                "id": "denied-observation", "event_type": "DUPLICATE_DECISION",
                "correct": True, "user_undid": False,
                "source_refs": [candidate["observation_ref"]],
                "measurement_version": 1, "observed_at": "2026-08-30T00:00:00Z",
            },
        },
    )
    assert denied_observation.status_code == 403

    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "telemetry-service",
        "principal_type": "service", "amr": ["service_token"],
        "scopes": ["qws:telemetry-write"], "is_super_admin": False,
    }

    observation = client.post(
        f"/api/v1/projects/{project_id}/telemetry-events",
        json={
            "expected_revision": revision,
            "event": {
                "id": "duplicate-observation-1",
                "event_type": "DUPLICATE_DECISION",
                "correct": True,
                "user_undid": False,
                "source_refs": [candidate["observation_ref"]],
                "measurement_version": 1,
                "observed_at": "2026-08-30T00:00:00Z",
            },
        },
    )
    assert observation.status_code == 200
    revision = observation.json()["process_revision"]
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "user-a",
        "principal_type": "human", "amr": ["pwd"], "auth_time": int(datetime.now(timezone.utc).timestamp()),
        "is_super_admin": False,
    }
    calibration = client.get(f"/api/v1/projects/{project_id}/calibration")
    assert calibration.status_code == 200
    assert calibration.json()["calibration"]["status"] == "INSUFFICIENT_REAL_DATA"
    assert calibration.json()["calibration"]["applied"] is False

    premature_l2 = client.put(
        f"/api/v1/projects/{project_id}/autonomy-policy",
        json={
            "expected_revision": revision,
            "policy": {"level": "L2", "capabilities": ["recommend_task"]},
        },
    )
    assert premature_l2.status_code == 409
    assert premature_l2.json()["detail"] == "autonomy_upgrade_requires_real_sample"
    l1 = client.put(
        f"/api/v1/projects/{project_id}/autonomy-policy",
        json={
            "expected_revision": revision,
            "policy": {"level": "L1", "capabilities": ["recommend_task"]},
        },
    )
    assert l1.status_code == 200
    assert l1.json()["policy"]["level"] == "L1"

    assets = client.get(f"/api/v1/projects/{project_id}/assets")
    assert assets.status_code == 200
    assert assets.json()["truth_contract"]["documents"] == "readable_projection_only"
    statuses = {item["status"] for item in assets.json()["distillation_candidates"]}
    assert {"SUPERSEDED", "DELETED"}.issubset(statuses)


def test_project_close_generates_final_distillation_and_freezes_regular_writes(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "final-distillation")
    bootstrap = client.get(f"/api/v1/projects/{project_id}/workspace-bootstrap").json()
    revision = bootstrap["process"]["process_revision"]
    generated = instantiate_project_blueprint({
        "project_goal": "完成项目关闭验收",
        "stages": [{
            "key": "delivery", "name": "交付", "goal": "完成交付",
            "acceptance_criteria": ["人工验收通过"],
        }],
        "tasks": [{
            "key": "close-task", "stage_key": "delivery", "title": "完成交付",
            "description": "提交最终交付", "role": "交付负责人", "status": "done",
            "acceptance_criteria": ["交付完成"], "deliverables": ["交付包"],
        }],
    })
    generated["project_id"] = project_id
    generated["process_revision"] = revision
    close_task_id = generated["tasks"][0]["id"]
    generated["tasks"][0]["task_revision"] = 1

    async def _prepare_close_state():
        async with SessionLocal() as db:
            project = await db.scalar(select(WorkspaceProject).where(WorkspaceProject.id == project_id))
            assert project is not None
            project.process_snapshot = generated
            db.add(WorkspaceDeliveryManifest(
                id="manifest-close-1", tenant_key="tenant-a", project_id=project_id,
                task_id=close_task_id, revision=1, task_revision=1, status="ACCEPTED",
                content={"summary": "人工已验收", "acceptance_checklist": [
                    {"criterion": "交付完成", "passed": True}
                ], "artifact_version_refs": []},
                content_hash="manifest-hash-close-1", created_by="user-a",
            ))
            await db.commit()

    asyncio.run(_prepare_close_state())
    closed = client.post(
        f"/api/v1/projects/{project_id}/close",
        json={"expected_revision": revision, "note": "人工确认项目完成"},
    )
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert closed.json()["final_distillation"]["status"] == "ADMITTED"
    closed_revision = closed.json()["process_revision"]
    assets = client.get(f"/api/v1/projects/{project_id}/assets").json()
    final_candidate = next(
        item for item in assets["distillation_candidates"]
        if item["category"] == "FINAL_PROJECT_DISTILLATION"
    )
    assert final_candidate["title"].startswith("Final Project Distillation")
    blocked = client.put(
        f"/api/v1/projects/{project_id}/documents/after-close",
        json={
            "expected_revision": closed_revision, "title": "不应写入", "content": "# blocked",
            "status": "DRAFT",
        },
    )
    assert blocked.status_code == 409
    assert blocked.json()["detail"] == "project_closed_read_only"
    resource_plan = client.get(f"/api/v1/projects/{project_id}/resource-plan")
    assert resource_plan.status_code == 200
    owner_write = client.put(
        f"/api/v1/projects/{project_id}/resource-plan",
        json={"expected_revision": closed_revision, "plan": resource_plan.json()["plan"]},
    )
    assert owner_write.status_code == 409
    assert owner_write.json()["detail"] == "project_closed_read_only"


def test_business_intake_draft_requires_review_and_applies_atomically(_reset_database):
    client = _reset_database
    project_id = _create_project(client)
    intake = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            "request_id": "idem-intake-0001",
            "business_goal": "面向园区交付可审计的网络产品",
            "customers_and_scenarios": "园区网络运维团队",
            "product_scope": "重大升级",
            "product_form": "software",
            "innovation_level": "major_upgrade",
            "tailoring_level": "standard",
            "requirements_and_evidence": "已有需求清单，验证证据待补",
            "desired_deliverables": ["产品包", "架构基线", "验证报告"],
            "target_finish_at": "2027-03-31T00:00:00Z",
        },
    )
    assert intake.status_code == 201

    generated = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/generate",
        json={
            "request_id": "idem-draft-0001",
            "business_intake_id": intake.json()["id"],
            "process_template_id": "ipd-product-development",
            "process_template_version": "1.0.0",
            "catalog_revision": "catalog-current",
        },
    )
    assert generated.status_code == 201
    draft = generated.json()
    assert draft["status"] == "READY_FOR_REVIEW"
    assert draft["truth"] == "AI_PROPOSED"
    assert [stage["name"] for stage in draft["process"]["stages"]] == [
        "概念", "计划", "开发", "验证", "发布", "生命周期"
    ]
    assert {gate["node_type"] for gate in draft["process"]["gates"]} == {"TR", "DCP"}
    assert all(
        candidate["availability"] == "UNAVAILABLE"
        for task in draft["process"]["tasks"]
        for candidate in task["agent_candidates"]
    )

    before = client.get(f"/api/v1/projects/{project_id}/process")
    assert before.status_code == 200
    assert before.json()["tasks"] == []

    applied = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": "idem-apply-0001",
            "expected_revision": 0,
            "draft_revision": draft["revision"],
        },
    )
    assert applied.status_code == 200
    assert applied.json()["process_revision"] == 1
    assert applied.json()["task_ids"]
    assert all(not task_id.startswith("draft_") for task_id in applied.json()["task_ids"])
    active_process = client.get(f"/api/v1/projects/{project_id}/process").json()
    employees = active_process["ai_employees"]
    assert employees
    assert all(employee["is_ai"] for employee in employees)
    assert all(task["assignee_id"] for task in active_process["tasks"])
    assert all(
        task["agent_candidates"][0]["availability"] == "AVAILABLE"
        for task in active_process["tasks"]
    )
    ensured = client.post(f"/api/v1/projects/{project_id}/ai-employees/ensure")
    assert ensured.status_code == 200
    assert {item["employee_id"] for item in ensured.json()["ai_employees"]} == {
        item["employee_id"] for item in employees
    }

    repeated = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": "idem-apply-0001",
            "expected_revision": 0,
            "draft_revision": draft["revision"],
        },
    )
    assert repeated.status_code == 200
    assert repeated.json() == applied.json()

    mismatched_replay = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": "unrelated-apply-request",
            "expected_revision": 999,
            "draft_revision": 999,
        },
    )
    assert mismatched_replay.status_code == 409


def test_intake_revisions_and_artifact_registry_are_immutable_and_versioned(
    _reset_database,
):
    client = _reset_database
    project_id = _create_project(client, "intake-artifacts")
    base_intake = {
        "business_goal": "交付可验收系统",
        "customers_and_scenarios": "项目负责人在任务看板中验收交付",
        "product_scope": "任务闭环",
        "product_form": "software",
        "innovation_level": "major_upgrade",
        "tailoring_level": "standard",
        "requirements_and_evidence": "原始需求与验收记录",
        "desired_deliverables": ["设计文档", "测试报告"],
        "target_finish_at": "2027-03-31T00:00:00Z",
        "raw_input": "用户最初输入的原文",
        "methodology": "先事实合同，再自动化",
        "constraints": ["Hermes 是唯一 Runtime"],
        "source_refs": ["session://initial"],
    }
    initial = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={**base_intake, "request_id": "intake-revision-initial", "revision_type": "INITIAL"},
    )
    clarification = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            **base_intake,
            "request_id": "intake-revision-clarify",
            "revision_type": "CLARIFICATION",
            "requirements_and_evidence": "补充图文反馈验收要求",
        },
    )
    assert initial.status_code == clarification.status_code == 201
    assert initial.json()["revision"] == 1
    assert clarification.json()["revision"] == 2
    revisions = client.get(f"/api/v1/projects/{project_id}/business-intakes").json()
    assert [item["revision_type"] for item in revisions] == ["INITIAL", "CLARIFICATION"]
    duplicate_initial = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={**base_intake, "request_id": "intake-revision-invalid", "revision_type": "INITIAL"},
    )
    assert duplicate_initial.status_code == 409

    created = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        json={
            "artifact_key": "design.qws-loop",
            "title": "QWS 任务闭环设计",
            "artifact_type": "document",
        },
    )
    assert created.status_code == 201, created.text
    artifact_id = created.json()["id"]
    repeated = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        json={
            "artifact_key": "design.qws-loop",
            "title": "QWS 任务闭环设计",
            "artifact_type": "document",
        },
    )
    assert repeated.status_code == 200
    assert repeated.json()["id"] == artifact_id
    version_payload = {
        "storage_ref": "repo://docs/qws-task-operating-loop-v1.md",
        "sha256": "a" * 64,
        "media_type": "text/markdown",
        "size_bytes": 1024,
        "lineage": {"commit": "abc123"},
        "verification": {"verified": True, "test_ref": "test://design-compile"},
    }
    version = client.post(
        f"/api/v1/projects/{project_id}/artifacts/{artifact_id}/versions",
        json=version_payload,
    )
    replay = client.post(
        f"/api/v1/projects/{project_id}/artifacts/{artifact_id}/versions",
        json=version_payload,
    )
    assert version.status_code == 201, version.text
    assert replay.status_code == 200
    assert version.json()["id"] == replay.json()["id"]
    versions = client.get(
        f"/api/v1/projects/{project_id}/artifacts/{artifact_id}/versions"
    ).json()
    assert len(versions) == 1
    assert versions[0]["verification"]["verified"] is True


def test_delivery_manifest_is_the_only_gate_to_done(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "delivery-gate")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task = process["tasks"][0]
    task_id = task["id"]
    started = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    )
    assert started.status_code == 200, started.text
    review = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 2, "status": "ACCEPTANCE_REVIEW"},
    )
    assert review.status_code == 200, review.text
    direct_done = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 3, "status": "DONE"},
    )
    assert direct_done.status_code == 409
    assert direct_done.json()["detail"]["error"] == "delivery_manifest_acceptance_required"

    artifact = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        json={
            "artifact_key": "delivery.final",
            "title": "最终交付物",
            "artifact_type": "document",
            "task_id": task_id,
        },
    ).json()
    version = client.post(
        f"/api/v1/projects/{project_id}/artifacts/{artifact['id']}/versions",
        json={
            "storage_ref": "repo://delivery/final.md",
            "sha256": "b" * 64,
            "media_type": "text/markdown",
            "verification": {"verified": True, "test_ref": "test://delivery"},
        },
    ).json()
    current_task = client.get(
        f"/api/v1/projects/{project_id}/tasks/{task_id}"
    ).json()
    evidence = [
        {"criterion": criterion, "passed": True, "evidence_ref": "test://delivery"}
        for criterion in current_task.get("acceptance_criteria", [])
    ]
    manifest = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task_id}/delivery-manifests",
        json={
            "expected_revision": 3,
            "expected_task_revision": current_task["task_revision"],
            "artifact_version_ids": [version["id"]],
            "acceptance_evidence": evidence,
            "summary": "验收标准通过且交付物已验证",
        },
    )
    assert manifest.status_code == 201, manifest.text
    accepted = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task_id}/delivery-manifests/{manifest.json()['id']}/decision",
        json={"expected_revision": 3, "decision": "ACCEPT", "note": "用户验收通过"},
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["task_status"] == "DONE"
    assert accepted.json()["manifest"]["status"] == "ACCEPTED"
    completed_process = client.get(f"/api/v1/projects/{project_id}/process").json()
    completion_doc = next(
        item for item in completed_process["documents"]
        if item["id"] == (task.get("execution_document_id") or f"task-record-{task_id}")
    )
    assert completion_doc["status"] == "PUBLISHED"
    assert "验收标准通过且交付物已验证" in completion_doc["content"]
    assert version["id"] in completion_doc["content"]
    assert "b" * 64 in completion_doc["content"]


def test_taskboard_backfill_uses_trusted_internal_host(monkeypatch):
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["host"] == "127.0.0.1"
        if request.url.path == "/api/qws/session":
            return httpx.Response(
                200,
                json={"taskboard_project_id": "qws-tenant-project"},
                headers={
                    "set-cookie": "qws-taskboard-session=session-token; Path=/taskboard/; HttpOnly"
                },
            )
        if request.method == "GET":
            return httpx.Response(200, json={"task": {"id": "task-1", "version": 1}})
        if request.method == "PATCH":
            return httpx.Response(
                200,
                json={"task": {"id": "task-1", "version": 2, "description": "新描述"}},
            )
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    transport = httpx.MockTransport(handler)
    original_client = httpx.AsyncClient

    def client_factory(*, base_url, timeout):
        return original_client(base_url=base_url, timeout=timeout, transport=transport)

    monkeypatch.setattr(
        "backend.api.quantum_workspace.httpx.AsyncClient", client_factory
    )
    evidence = asyncio.run(
        _apply_taskboard_backfill(
            project_id="project-1",
            task_id="task-1",
            expected_version=1,
            self_changes={"description": "新描述"},
            authorization="Bearer test-token",
        )
    )
    assert evidence == {"created_issues": [], "attachments": [], "relations": []}
    assert [request.method for request in requests] == ["POST", "GET", "PATCH"]


def test_apply_rejects_stale_project_revision(_reset_database):
    client = _reset_database
    project_id = _create_project(client, "conflict")
    intake = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            "request_id": "idem-intake-conflict",
            "business_goal": "交付硬件产品",
            "customers_and_scenarios": "数据中心团队",
            "product_scope": "全新产品",
            "product_form": "hardware",
            "innovation_level": "new_product",
            "tailoring_level": "full",
            "requirements_and_evidence": "已有市场证据",
            "desired_deliverables": ["样机", "验证报告"],
            "target_finish_at": "2027-06-30T00:00:00Z",
        },
    ).json()
    draft = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/generate",
        json={
            "request_id": "idem-draft-conflict",
            "business_intake_id": intake["id"],
            "process_template_id": "ipd-product-development",
            "process_template_version": "1.0.0",
            "catalog_revision": "catalog-current",
        },
    ).json()

    conflict = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": "idem-apply-conflict",
            "expected_revision": 9,
            "draft_revision": draft["revision"],
        },
    )
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["server_revision"] == 0


def _create_applied_process(client, suffix="views"):
    project_id = _create_project(client, suffix)
    intake = client.post(
        f"/api/v1/projects/{project_id}/business-intakes",
        json={
            "request_id": f"idem-intake-{suffix}",
            "business_goal": "交付可审计的产品",
            "customers_and_scenarios": "产品与研发团队",
            "product_scope": "全新产品",
            "product_form": "integrated",
            "innovation_level": "new_product",
            "tailoring_level": "full",
            "requirements_and_evidence": "已有需求证据",
            "desired_deliverables": ["产品包", "验证证据"],
            "target_finish_at": "2027-08-31T00:00:00Z",
        },
    ).json()
    draft = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/generate",
        json={
            "request_id": f"idem-draft-{suffix}",
            "business_intake_id": intake["id"],
            "process_template_id": "ipd-product-development",
            "process_template_version": "1.0.0",
            "catalog_revision": "catalog-current",
        },
    ).json()
    result = client.post(
        f"/api/v1/projects/{project_id}/process-drafts/{draft['id']}/apply",
        json={
            "request_id": f"idem-apply-{suffix}",
            "expected_revision": 0,
            "draft_revision": draft["revision"],
        },
    ).json()
    return project_id, result


def test_taskboard_schedule_and_graph_share_one_revision(_reset_database):
    client = _reset_database
    project_id, applied = _create_applied_process(client)
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task = process["tasks"][0]

    schedule = client.get(f"/api/v1/projects/{project_id}/schedule")
    workflow_graph = client.get(
        f"/api/v1/projects/{project_id}/graphs/workflow"
    )
    resource_graph = client.get(
        f"/api/v1/projects/{project_id}/graphs/ai-resource"
    )
    assert schedule.status_code == workflow_graph.status_code == resource_graph.status_code == 200
    assert {
        schedule.json()["process_revision"],
        workflow_graph.json()["process_revision"],
        resource_graph.json()["process_revision"],
    } == {applied["process_revision"]}
    assert schedule.json()["tasks"][0]["schedule_status"] == "UNSCHEDULED"
    assert schedule.json()["tasks"][0]["planned_start_at"] is None
    assert workflow_graph.json()["source_status"] == "PLANNED"
    assert resource_graph.json()["source_status"] == "UNCONNECTED"

    updated = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    )
    assert updated.status_code == 200
    assert updated.json()["process_revision"] == 2
    assert updated.json()["task"]["status"] == "IN_PROGRESS"
    assert updated.json()["stage"]["status"] == "IN_PROGRESS"

    graph_after_update = client.get(
        f"/api/v1/projects/{project_id}/graphs/workflow"
    ).json()
    updated_node = next(node for node in graph_after_update["nodes"] if node["id"] == task["id"])
    assert updated_node["status"] == "UNCONNECTED"
    assert updated_node["task_status"] == "IN_PROGRESS"
    assert len(resource_graph.json()["edges"]) == len(process["tasks"])

    stale = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}",
        json={"expected_revision": 1, "status": "DONE"},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["server_revision"] == 2


def test_workflow_designer_persists_configured_nodes_edges_and_rejects_stale_revision(
    _reset_database,
):
    client = _reset_database
    project_id, applied = _create_applied_process(client, "workflow-designer")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    stage = process["stages"][0]
    trigger_id = f"workflow_start_{stage['id']}"
    action_id = "workflow_node_define_requirements"
    payload = {
        "expected_revision": applied["process_revision"],
        "nodes": [
            {
                "id": trigger_id,
                "type": "workflow_step",
                "stage_id": stage["id"],
                "position": {"x": 60, "y": 220},
                "data": {
                    "kind": "trigger",
                    "label": f"{stage['name']}开始",
                    "description": "业务需求进入已确认状态",
                    "execution_mode": "human_ai",
                    "participants": ["产品负责人"],
                    "tools": [],
                    "data_sources": ["需求池"],
                    "devices": [],
                    "deliverables": [],
                    "acceptance_criteria": ["需求编号存在"],
                },
            },
            {
                "id": action_id,
                "type": "workflow_step",
                "stage_id": stage["id"],
                "position": {"x": 380, "y": 220},
                "data": {
                    "kind": "action",
                    "label": "定义需求与验收边界",
                    "description": "梳理目标、范围和成功标准",
                    "execution_mode": "human_ai",
                    "participants": ["产品负责人", "业务代表"],
                    "tools": ["访谈模板", "需求评审清单"],
                    "data_sources": ["客户档案", "历史访谈"],
                    "devices": ["会议室", "浏览器"],
                    "deliverables": ["需求定义", "评审结论"],
                    "acceptance_criteria": ["业务负责人确认"],
                },
            },
        ],
        "edges": [
            {
                "id": "workflow_edge_start_define",
                "source": trigger_id,
                "target": action_id,
            }
        ],
    }

    saved = client.put(
        f"/api/v1/projects/{project_id}/graphs/workflow",
        json=payload,
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["process_revision"] == applied["process_revision"] + 1
    assert saved.json()["source_status"] == "USER_CONFIGURED"
    configured = next(node for node in saved.json()["nodes"] if node["id"] == action_id)
    assert configured["data"]["participants"] == ["产品负责人", "业务代表"]
    assert configured["data"]["tools"] == ["访谈模板", "需求评审清单"]
    assert configured["data"]["data_sources"] == ["客户档案", "历史访谈"]
    assert configured["data"]["devices"] == ["会议室", "浏览器"]
    assert configured["data"]["deliverables"] == ["需求定义", "评审结论"]
    assert {ref["kind"] for refs in configured["data"]["resource_refs"].values() for ref in refs} == {"tool", "data", "environment"}
    persisted_process = client.get(f"/api/v1/projects/{project_id}/process").json()
    resource_ids = {item["id"] for item in persisted_process["resource_entities"]}
    assert all(
        ref["resource_id"] in resource_ids
        for refs in configured["data"]["resource_refs"].values()
        for ref in refs
    )

    reloaded = client.get(f"/api/v1/projects/{project_id}/graphs/workflow")
    assert reloaded.status_code == 200
    assert reloaded.json()["nodes"] == saved.json()["nodes"]
    assert reloaded.json()["edges"] == saved.json()["edges"]

    stale = client.put(
        f"/api/v1/projects/{project_id}/graphs/workflow",
        json=payload,
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["server_revision"] == saved.json()["process_revision"]


def test_ai_resource_plan_is_versioned_recommended_and_user_configurable(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "resource-workbench")

    initial = client.get(f"/api/v1/projects/{project_id}/resource-plan")
    assert initial.status_code == 200
    assert initial.json()["plan"]["source_status"] == "UNCONFIGURED"
    assert initial.json()["plan"]["scenario_twin"]["systems"][0]["id"] == "erp-order-simulator"
    assert initial.json()["plan"]["scenario_twin"]["systems"][0]["methodology"]["agent_design"]["guardrails"]
    assert initial.json()["monitoring"]["source_status"] == "UNCONNECTED"

    async def fake_chat_stream(req, payload, *, allow_agent_invocation=True):
        assert allow_agent_invocation is False
        assert "企业 AI 基础设施解决方案架构师" in req.question
        assert "token_factory.status 必须为 UNCONNECTED" in req.question

        async def events():
            answer = {
                "systems": [{"id": "gateway", "name": "业务网关", "role": "接入", "deployment": "容器", "replicas": 2}],
                "infrastructure": {
                    "ecs": {"count": 2, "v_cpu": 16, "memory_gb": 64},
                    "storage": {"system_disk_gb": 200, "data_disk_gb": 500, "object_storage_gb": 1024},
                    "hyperconverged_nodes": {"count": 3, "profile": "通用计算"},
                    "gpu": {"model": "L20", "count": 1, "memory_gb": 48},
                    "network": {"bandwidth_mbps": 1000},
                },
                "runtime": {
                    "microservices": 6, "containers": 10, "queues": 1, "ontology": "用户与任务本体",
                    "agents": {"count": 4, "concurrency": 8},
                    "inference": {"service": "vLLM", "provider": "自部署", "model": "Qwen", "replicas": 1},
                },
                "sla": {"p95_latency_ms": 1500, "throughput_rps": 12, "availability": "99.9%", "target_monthly_cost_cny": 30000, "acceleration": "连续批处理"},
                "token_factory": {"status": "CONNECTED", "product_mapping": "Token Factory 推理单元", "token_peak_per_minute": 50000, "monthly_token_estimate": 50000000, "capacity_unit": "待接口确认", "evidence": "需压测"},
                "topology": {"nodes": [{"id": "gateway", "label": "业务网关", "type": "system", "status": "PLANNED"}], "edges": []},
                "assumptions": ["按首期 100 并发用户估算"],
            }
            yield f'data: {json.dumps({"type": "done", "answer": json.dumps(answer, ensure_ascii=False)}, ensure_ascii=False)}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    recommended = client.post(
        f"/api/v1/projects/{project_id}/resource-plan/recommend",
        json={"request_id": "resource-recommend-0001", "expected_revision": 1, "constraints": "成本优先"},
    )
    assert recommended.status_code == 200, recommended.text
    proposal = recommended.json()["plan"]
    assert recommended.json()["process_revision"] == 2
    assert proposal["source_status"] == "AI_PROPOSED"
    assert proposal["infrastructure"]["gpu"]["model"] == "L20"
    assert proposal["token_factory"]["status"] == "UNCONNECTED"

    proposal["sla"]["p95_latency_ms"] = 1200
    saved = client.put(
        f"/api/v1/projects/{project_id}/resource-plan",
        json={"expected_revision": 2, "plan": proposal},
    )
    assert saved.status_code == 200
    assert saved.json()["process_revision"] == 3
    assert saved.json()["plan"]["source_status"] == "USER_CONFIGURED"
    assert saved.json()["plan"]["sla"]["p95_latency_ms"] == 1200

    generated = client.post(
        f"/api/v1/projects/{project_id}/resource-plan/simulations/erp-order-simulator/datasets",
        json={"expected_revision": 3, "row_count": 2500, "seed": 20260828},
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["process_revision"] == 4
    dataset = generated.json()["dataset"]
    assert dataset["truth"] == "SYNTHETIC"
    assert dataset["row_count"] == 2500
    assert dataset["sample_rows"][0]["order_id"].startswith("SIM-SO-")
    assert dataset["quality"]["pii_safety"] == 100
    assert "未读取生产数据" in dataset["lineage"]

    async def fake_context_chat(req, payload, *, allow_agent_invocation=True):
        assert allow_agent_invocation is False
        assert "AI Resource 工作台的上下文助手" in req.question
        assert "ERP 模拟器如何设计" in req.question
        assert "不得把规划或模拟数据描述成生产事实" in req.question
        assert "Web 当前草案模型" in req.question

        async def events():
            yield 'data: {"type":"done","answer":"应按订单状态机与接口契约模拟，并保留 seed 和 lineage。"}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_context_chat)
    chat = client.post(
        f"/api/v1/projects/{project_id}/resource-plan/chat",
        json={
            "request_id": "resource-chat-0001",
            "context_id": "runtime",
            "context_title": "AI 运行时与本体",
            "question": "ERP 模拟器如何设计？",
            "resource_plan": {
                **proposal,
                "runtime": {
                    **proposal["runtime"],
                    "inference": {
                        **proposal["runtime"]["inference"],
                        "model": "Web 当前草案模型",
                    },
                },
            },
        },
    )
    assert chat.status_code == 200, chat.text
    assert chat.json()["truth"] == "AI_GENERATED"
    assert "seed" in chat.json()["answer"]

    stale = client.put(
        f"/api/v1/projects/{project_id}/resource-plan",
        json={"expected_revision": 3, "plan": proposal},
    )
    assert stale.status_code == 409
    assert stale.json()["detail"]["server_revision"] == 4


def test_taskboard_can_create_tasks_and_bind_owned_canonical_workflows(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "dashi-parity")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    stage = process["stages"][0]

    created_task = client.post(
        f"/api/v1/projects/{project_id}/tasks",
        json={
            "expected_revision": 1,
            "stage_id": stage["id"],
            "title": "客户证据复核",
            "summary": "核验真实客户证据并形成可审阅结论",
            "assignee_role": "研究负责人",
        },
    )
    assert created_task.status_code == 201
    assert created_task.json()["process_revision"] == 2
    task = created_task.json()["task"]
    assert task["status"] == "WAITING_CLAIM"
    assert task["workflow_status"] == "UNCONNECTED"

    process_after_create = client.get(
        f"/api/v1/projects/{project_id}/process"
    )
    assert process_after_create.status_code == 200, process_after_create.text
    assert process_after_create.json()["process_revision"] == 2

    schedule = client.get(f"/api/v1/projects/{project_id}/schedule").json()
    assert next(item for item in schedule["tasks"] if item["id"] == task["id"])["schedule_status"] == "UNSCHEDULED"
    graph = client.get(f"/api/v1/projects/{project_id}/graphs/workflow").json()
    assert next(node for node in graph["nodes"] if node["id"] == task["id"])["status"] == "UNCONNECTED"

    conversation = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "workflow_id": None,
            "agent_version": "hermes-current",
        },
    )
    assert conversation.status_code == 201

    workflow = {
        "id": "wf_qws_dashi_parity",
        "title": task["title"],
        "description": task["summary"],
        "status": "clarifying",
    }

    async def create_owned_workflow():
        async with SessionLocal() as db:
            db.add(
                WorkflowDefinition(
                    tenant_key="tenant-a",
                    created_by="user-a",
                    desired_output="可审阅证据结论",
                    **workflow,
                )
            )
            await db.commit()

    asyncio.run(create_owned_workflow())

    bound = client.put(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/workflow",
        json={"expected_revision": 2, "workflow_id": workflow["id"]},
    )
    assert bound.status_code == 200, bound.text
    assert bound.json()["process_revision"] == 3
    assert bound.json()["task"]["workflow_id"] == workflow["id"]
    assert bound.json()["task"]["workflow_status"] == workflow["status"]

    process_after_bind = client.get(
        f"/api/v1/projects/{project_id}/process"
    )
    assert process_after_bind.status_code == 200, process_after_bind.text
    assert process_after_bind.json()["process_revision"] == 3

    reopened = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "workflow_id": workflow["id"],
            "agent_version": "hermes-current",
        },
    )
    assert reopened.status_code == 200
    assert reopened.json()["binding"]["workflow_id"] == workflow["id"]
    assert reopened.json()["binding"]["process_revision"] == 3

    duplicate = client.put(
        f"/api/v1/projects/{project_id}/tasks/{process['tasks'][0]['id']}/workflow",
        json={"expected_revision": 3, "workflow_id": workflow["id"]},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["detail"] == "workflow already binds another project task"


def test_task_merge_preview_apply_redirect_and_revert(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "merge-loop")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    primary, secondary = process["tasks"][:2]
    source_artifact = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        json={
            "artifact_key": "merge.source.evidence",
            "title": "来源任务证据",
            "artifact_type": "document",
            "task_id": secondary["id"],
        },
    )
    assert source_artifact.status_code == 201

    preview_response = client.post(
        f"/api/v1/projects/{project_id}/tasks/{primary['id']}/merge-previews",
        json={
            "request_id": "merge-preview-0001",
            "expected_revision": 1,
            "secondary_task_id": secondary["id"],
            "expected_primary_revision": 1,
            "expected_secondary_revision": 1,
        },
    )
    assert preview_response.status_code == 201, preview_response.text
    preview = preview_response.json()["merge"]
    preview_replay = client.post(
        f"/api/v1/projects/{project_id}/tasks/{primary['id']}/merge-previews",
        json={
            "request_id": "merge-preview-0001",
            "expected_revision": 1,
            "secondary_task_id": secondary["id"],
            "expected_primary_revision": 1,
            "expected_secondary_revision": 1,
        },
    )
    assert preview_replay.status_code == 200
    assert preview_replay.json()["merge"]["id"] == preview["id"]
    choices = {
        item["field"]: ("union" if "union" in item["allowed_choices"] else "primary")
        for item in preview["conflicts"]
    }
    applied = client.post(
        f"/api/v1/projects/{project_id}/task-merges/{preview['id']}/apply",
        json={"request_id": "merge-apply-0001", "expected_revision": 2, "field_choices": choices},
    )
    assert applied.status_code == 200, applied.text
    assert applied.json()["merge"]["status"] == "APPLIED"
    assert applied.json()["secondary_task"]["status"] == "MERGED"
    assert applied.json()["secondary_task"]["redirect_to_task_id"] == primary["id"]
    merged_task = client.get(
        f"/api/v1/projects/{project_id}/tasks/{secondary['id']}"
    )
    assert merged_task.status_code == 200
    assert merged_task.json()["redirect"]["task_id"] == primary["id"]
    workflow_graph = client.get(
        f"/api/v1/projects/{project_id}/graphs/workflow"
    ).json()
    merged_node = next(node for node in workflow_graph["nodes"] if node["id"] == secondary["id"])
    assert merged_node["task_status"] == "MERGED"
    blocked_update = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{secondary['id']}/card-summary",
        json={"expected_revision": 3, "progress": "不应写入"},
    )
    assert blocked_update.status_code == 409
    assert blocked_update.json()["detail"]["error"] == "merged_task_is_read_only"
    blocked_artifact = client.post(
        f"/api/v1/projects/{project_id}/artifacts",
        json={
            "artifact_key": "merge.source.after",
            "title": "不应写入来源任务",
            "artifact_type": "document",
            "task_id": secondary["id"],
        },
    )
    assert blocked_artifact.status_code == 409
    blocked_version = client.post(
        f"/api/v1/projects/{project_id}/artifacts/{source_artifact.json()['id']}/versions",
        json={
            "storage_ref": "repo://merge/blocked.md",
            "sha256": "c" * 64,
            "media_type": "text/markdown",
            "verification": {"verified": True},
        },
    )
    assert blocked_version.status_code == 409
    blocked_conversation = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": secondary["id"],
            "workflow_id": secondary.get("workflow_id"),
            "agent_version": "hermes-current",
        },
    )
    assert blocked_conversation.status_code == 409
    assert blocked_conversation.json()["detail"]["error"] == "merged_task_is_read_only"
    artifacts = client.get(f"/api/v1/projects/{project_id}/artifacts").json()
    merged_artifact = next(item for item in artifacts if item["artifact_key"] == "merge.source.evidence")
    assert merged_artifact["source_task_id"] == secondary["id"]
    assert merged_artifact["effective_task_id"] == primary["id"]
    manifests = client.get(
        f"/api/v1/projects/{project_id}/tasks/{primary['id']}/delivery-manifests"
    )
    assert manifests.status_code == 200
    assert manifests.json() == []
    replayed = client.post(
        f"/api/v1/projects/{project_id}/task-merges/{preview['id']}/apply",
        json={"request_id": "merge-apply-0001", "expected_revision": 2, "field_choices": choices},
    )
    assert replayed.status_code == 200
    assert replayed.json()["process_revision"] == 3
    drifted_apply = client.post(
        f"/api/v1/projects/{project_id}/task-merges/{preview['id']}/apply",
        json={"request_id": "merge-apply-drift", "expected_revision": 2, "field_choices": choices},
    )
    assert drifted_apply.status_code == 409

    reverted = client.post(
        f"/api/v1/projects/{project_id}/task-merges/{preview['id']}/revert",
        json={"request_id": "merge-revert-0001", "expected_revision": 3},
    )
    assert reverted.status_code == 200, reverted.text
    assert reverted.json()["merge"]["status"] == "REVERTED"
    assert reverted.json()["secondary_task"]["status"] == secondary["status"]
    assert "redirect_to_task_id" not in reverted.json()["secondary_task"]
    restored_task = client.get(
        f"/api/v1/projects/{project_id}/tasks/{secondary['id']}"
    ).json()
    assert "redirect" not in restored_task
    replayed_revert = client.post(
        f"/api/v1/projects/{project_id}/task-merges/{preview['id']}/revert",
        json={"request_id": "merge-revert-0001", "expected_revision": 3},
    )
    assert replayed_revert.status_code == 200
    assert replayed_revert.json()["process_revision"] == 4


def test_task_operating_loop_api_claims_lease_builds_context_and_proposes_relation(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "operating-loop")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    source = process["tasks"][0]
    target = process["tasks"][1]

    lease = client.post(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/execution-lease",
        json={
            "expected_revision": 1,
            "expected_task_revision": 1,
            "session_id": "session-primary",
            "actor_id": "hermes-agent",
            "ttl_seconds": 900,
        },
    )
    assert lease.status_code == 200, lease.text
    assert lease.json()["process_revision"] == 2
    assert lease.json()["task_revision"] == 2
    assert lease.json()["lease"]["session_id"] == "session-primary"

    context = client.get(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/context-pack"
    )
    assert context.status_code == 200, context.text
    context_payload = context.json()
    assert context_payload["identity"]["execution_lease"]["session_id"] == "session-primary"
    assert "full_chat_history" in context_payload["exclusions"]
    assert "relations" not in context_payload
    assert context_payload["relation_digest"]["schema_version"] == "qws.relation-digest.v1"
    digest = client.get(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/relation-digest"
    )
    assert digest.status_code == 200, digest.text
    digest_payload = digest.json()
    assert digest_payload["entries"] == context_payload["relation_digest"]["entries"]
    assert digest_payload["exclusions"] == context_payload["relation_digest"]["exclusions"]

    proposal = client.post(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/relation-proposals",
        json={
            "expected_revision": 2,
            "expected_task_revision": 2,
            "target_task_id": target["id"],
            "relation_type": "related",
            "reason": "共享同一验收证据",
            "evidence_refs": ["artifact://evidence"],
            "confidence": 0.91,
            "impact": {"execution": "continue", "scope": "none"},
        },
    )
    assert proposal.status_code == 201, proposal.text
    assert proposal.json()["process_revision"] == 3
    assert proposal.json()["task_revision"] == 3
    assert proposal.json()["proposal"]["status"] == "PROPOSED"
    assert proposal.json()["proposal"]["requires_user_confirmation"] is True

    conflicting_lease = client.post(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/execution-lease",
        json={
            "expected_revision": 3,
            "expected_task_revision": 3,
            "session_id": "session-other",
            "actor_id": "other-agent",
            "ttl_seconds": 900,
        },
    )
    assert conflicting_lease.status_code == 409
    assert conflicting_lease.json()["detail"]["error"] == "execution_lease_conflict"

    confirmed = client.post(
        f"/api/v1/projects/{project_id}/relation-proposals/{proposal.json()['proposal']['id']}/decision",
        json={
            "request_id": "relation-confirm-0001",
            "expected_revision": 3,
            "expected_task_revision": 3,
            "decision": "CONFIRM",
            "reason": "用户确认关联",
        },
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["process_revision"] == 4
    assert confirmed.json()["task_revision"] == 4
    assert confirmed.json()["proposal"]["status"] == "CONFIRMED"
    replayed_confirmation = client.post(
        f"/api/v1/projects/{project_id}/relation-proposals/{proposal.json()['proposal']['id']}/decision",
        json={
            "request_id": "relation-confirm-0001",
            "expected_revision": 3,
            "expected_task_revision": 3,
            "decision": "CONFIRM",
            "reason": "用户确认关联",
        },
    )
    assert replayed_confirmation.status_code == 200
    assert replayed_confirmation.json()["process_revision"] == 4
    confirmed_digest = client.get(
        f"/api/v1/projects/{project_id}/tasks/{source['id']}/relation-digest"
    )
    assert confirmed_digest.status_code == 200
    assert any(
        item.get("effective_task_id") == target["id"] and item.get("relation_type") == "related"
        for item in confirmed_digest.json()["entries"]
    )


def test_execution_lease_heartbeat_requires_same_session_and_epoch(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "lease-heartbeat")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    acquired = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/execution-lease",
        json={
            "expected_revision": 1, "expected_task_revision": 1,
            "session_id": "session-a", "actor_id": "agent-a", "ttl_seconds": 900,
        },
    )
    assert acquired.status_code == 200, acquired.text
    epoch = acquired.json()["lease"]["lease_epoch"]
    renewed = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/execution-lease/heartbeat",
        json={
            "expected_revision": 2, "expected_task_revision": 2,
            "session_id": "session-a", "lease_epoch": epoch, "ttl_seconds": 900,
        },
    )
    assert renewed.status_code == 200, renewed.text
    assert renewed.json()["process_revision"] == 3
    assert renewed.json()["lease"]["lease_epoch"] == epoch
    wrong_epoch = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/execution-lease/heartbeat",
        json={
            "expected_revision": 3, "expected_task_revision": 3,
            "session_id": "session-a", "lease_epoch": epoch + 1, "ttl_seconds": 900,
        },
    )
    assert wrong_epoch.status_code == 409
    assert wrong_epoch.json()["detail"]["error"] == "execution_lease_epoch_conflict"


def test_challenge_review_hard_gate_decision_brief_and_idempotent_resolution(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "challenge-review")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task = process["tasks"][0]
    request = {
        "request_id": "challenge-create-0001", "expected_revision": 1,
        "expected_task_revision": 1, "agreed": ["目标合理"],
        "challenges": ["未经授权将直接发布生产"],
        "impacts": {"security": "可能泄露数据", "no_action": "继续阻断发布"},
        "evidence": [{"kind": "FACT", "statement": "没有部署授权", "source_refs": [f"task:{task['id']}@1"]}],
        "alternatives": [
            {"id": "keep", "label": "保留原方案", "cost": "高风险", "resolution": "PROCEED"},
            {"id": "experiment", "label": "先做沙盒实验", "cost": "增加一天", "resolution": "EXPERIMENT"},
        ],
        "conclusion": "EXPERIMENT", "decision_key": "production_release_strategy",
        "question": "是否先做沙盒实验？",
        "risk_categories": ["security", "production_publish"], "reversible": False,
    }
    created = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews", json=request
    )
    assert created.status_code == 201, created.text
    review = created.json()["challenge_review"]
    assert review["gate_level"] == "HARD"
    assert review["decision_brief"]["status"] == "OPEN"
    assert created.json()["process_revision"] == 2
    assert created.json()["task_revision"] == 2
    assert client.get(f"/api/v1/projects/{project_id}/tasks/{task['id']}").json()["status"] == "DECISION_REQUIRED"
    replayed_create = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews", json=request
    )
    assert replayed_create.status_code == 200
    assert replayed_create.json()["challenge_review"]["id"] == review["id"]
    drifted_create = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews",
        json={**request, "question": "另一个问题"},
    )
    assert drifted_create.status_code == 409
    blocked_lease = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/execution-lease",
        json={"expected_revision": 2, "expected_task_revision": 2, "session_id": "blocked", "actor_id": "agent", "ttl_seconds": 60},
    )
    assert blocked_lease.status_code == 409
    bypass = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}",
        json={"expected_revision": 2, "status": "TODO", "reason": "尝试绕过 Challenge"},
    )
    assert bypass.status_code == 409
    assert bypass.json()["detail"]["error"] == "open_challenge_decision_required"
    decision_request = {
        "request_id": "challenge-decision-0001", "expected_revision": 2,
        "expected_task_revision": 2, "selected_option_id": "experiment",
        "resolution": "EXPERIMENT", "rationale": "先验证再申请发布授权",
    }
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "user-a",
        "principal_type": "agent", "is_super_admin": False,
    }
    agent_resolution = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews/{review['id']}/decision",
        json=decision_request,
    )
    assert agent_resolution.status_code == 403
    assert agent_resolution.json()["detail"] == "authenticated human principal required"
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a", "user_id": "user-a", "sub": "user-a",
        "principal_type": "human", "amr": ["pwd"], "auth_time": int(datetime.now(timezone.utc).timestamp()), "is_super_admin": False,
    }
    resolved = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews/{review['id']}/decision",
        json=decision_request,
    )
    assert resolved.status_code == 200, resolved.text
    assert resolved.json()["process_revision"] == 3
    assert resolved.json()["task_revision"] == 3
    assert resolved.json()["decision"]["status"] == "CONFIRMED"
    replayed_resolution = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews/{review['id']}/decision",
        json=decision_request,
    )
    assert replayed_resolution.status_code == 200
    assert replayed_resolution.json()["process_revision"] == 3
    drifted_resolution = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews/{review['id']}/decision",
        json={**decision_request, "rationale": "不同理由"},
    )
    assert drifted_resolution.status_code == 409
    restored = client.get(f"/api/v1/projects/{project_id}/tasks/{task['id']}").json()
    assert restored["status"] == "TODO"
    assert restored["challenge_reviews"][0]["decision_brief"]["status"] == "RESOLVED"
    late_create_replay = client.post(
        f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews", json=request
    )
    assert late_create_replay.status_code == 200
    assert late_create_replay.json()["process_revision"] == 2
    assert late_create_replay.json()["task_revision"] == 2
    assert late_create_replay.json()["challenge_review"]["status"] == "OPEN"
    assert late_create_replay.json()["challenge_review"]["decision_brief"]["status"] == "OPEN"


def test_challenge_cas_conflict_rereads_identical_committed_request(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "challenge-race")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    request = {
        "request_id": "challenge-race-0001", "expected_revision": 1,
        "expected_task_revision": 1, "agreed": ["目标合理"],
        "challenges": ["直接发布生产缺少授权"], "impacts": {"security": "发布风险"},
        "evidence": [{"kind": "FACT", "statement": "无发布授权", "source_refs": [f"task:{task['id']}@1"]}],
        "alternatives": [
            {"id": "keep", "label": "保留", "cost": "高风险", "resolution": "PROCEED"},
            {"id": "sandbox", "label": "沙盒", "cost": "一天", "resolution": "EXPERIMENT"},
        ],
        "conclusion": "EXPERIMENT", "decision_key": "production_release_strategy",
        "question": "是否先做沙盒？",
        "risk_categories": ["production_publish"], "reversible": False,
    }
    original = qws_api._cas_project_process

    async def committed_winner_then_conflict(*args, **kwargs):
        await original(*args, **kwargs)
        raise HTTPException(status_code=409, detail="simulated concurrent winner")

    monkeypatch.setattr(qws_api, "_cas_project_process", committed_winner_then_conflict)
    url = f"/api/v1/projects/{project_id}/tasks/{task['id']}/challenge-reviews"
    response = client.post(url, json=request)
    assert response.status_code == 200
    assert response.json()["process_revision"] == 2
    assert response.json()["challenge_review"]["request_id"] == request["request_id"]



def test_task_state_machine_rejects_terminal_rollback_and_missing_reason(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "state-machine")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task_id = process["tasks"][0]["id"]

    direct_done = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "DONE"},
    )
    assert direct_done.status_code == 409

    blocked_without_reason = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "BLOCKED"},
    )
    assert blocked_without_reason.status_code == 422

    started = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 1, "status": "IN_PROGRESS"},
    )
    assert started.status_code == 200
    done = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 2, "status": "DONE"},
    )
    assert done.status_code == 409
    assert done.json()["detail"]["error"] == "delivery_manifest_acceptance_required"
    review = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 2, "status": "ACCEPTANCE_REVIEW"},
    )
    assert review.status_code == 200
    reopened = client.patch(
        f"/api/v1/projects/{project_id}/tasks/{task_id}",
        json={"expected_revision": 3, "status": "TODO"},
    )
    assert reopened.status_code == 409


def test_concurrent_task_updates_use_database_compare_and_swap(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "concurrent-cas")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task_id = process["tasks"][0]["id"]

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            return await asyncio.gather(
                async_client.patch(
                    f"/api/v1/projects/{project_id}/tasks/{task_id}",
                    json={"expected_revision": 1, "status": "IN_PROGRESS"},
                ),
                async_client.patch(
                    f"/api/v1/projects/{project_id}/tasks/{task_id}",
                    json={
                        "expected_revision": 1,
                        "status": "BLOCKED",
                        "reason": "并发验收",
                    },
                ),
            )

    responses = asyncio.run(race())
    assert sorted(response.status_code for response in responses) == [200, 409]
    latest = client.get(f"/api/v1/projects/{project_id}/process").json()
    assert latest["process_revision"] == 2


def test_concurrent_task_conversation_open_replays_without_500(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "conversation-race")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    original_commit = AsyncSession.commit
    reached = 0
    release = asyncio.Event()

    async def synchronized_commit(session):
        nonlocal reached
        if any(isinstance(item, WorkspaceTaskConversation) for item in session.new):
            reached += 1
            if reached == 2:
                release.set()
            else:
                await release.wait()
        return await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", synchronized_commit)
    request = {
        "project_id": project_id,
        "task_id": task["id"],
        "workflow_id": task["workflow_id"],
        "agent_version": "hermes-current",
    }

    async def race():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://test"
        ) as async_client:
            return await asyncio.gather(
                async_client.post("/api/v1/task-conversations", json=request),
                async_client.post("/api/v1/task-conversations", json=request),
            )

    responses = asyncio.run(race())
    assert sorted(response.status_code for response in responses) == [200, 201]
    assert len({response.json()["id"] for response in responses}) == 1


def test_task_conversation_card_context_is_full_then_incremental(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "card-context")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    base_context = {
        "schema_version": 1,
        "project": {"id": project_id, "name": "Card Context", "business_goal": "Ship"},
        "task": {
            "qws_task_id": task["id"],
            "dashi_task_id": "card-1",
            "title": task["title"],
            "descriptions": [{"id": "taskboard-description", "content": "first"}],
            "sub_issues": [],
            "comments": [],
        },
    }
    request = {
        "project_id": project_id,
        "task_id": task["id"],
        "workflow_id": task["workflow_id"],
        "agent_version": "hermes-current",
        "card_context": base_context,
    }

    first = client.post("/api/v1/task-conversations", json=request)
    assert first.status_code == 201
    assert first.json()["context_sync"] == {
        **first.json()["context_sync"],
        "mode": "full",
        "revision": 1,
        "changes_count": 0,
    }

    unchanged = client.post("/api/v1/task-conversations", json=request)
    assert unchanged.status_code == 200
    assert unchanged.json()["context_sync"]["mode"] == "unchanged"
    assert unchanged.json()["context_sync"]["revision"] == 1

    changed_context = json.loads(json.dumps(base_context))
    changed_context["task"]["comments"].append({"id": "comment-1", "body": "new"})
    request["card_context"] = changed_context
    incremental = client.post("/api/v1/task-conversations", json=request)
    assert incremental.status_code == 200
    assert incremental.json()["context_sync"]["mode"] == "incremental"
    assert incremental.json()["context_sync"]["revision"] == 2
    assert incremental.json()["context_sync"]["changes_count"] == 1

    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-b",
        "user_id": "user-b",
        "sub": "user-b",
        "is_super_admin": False,
    }
    cross_tenant = client.get(
        f"/api/v1/task-conversations/{first.json()['id']}/messages"
    )
    assert cross_tenant.status_code == 404


def test_structured_card_backfill_normalizes_field_issue_attachment_and_relation_ops():
    payload = {
        "summary": "把访谈结论写入卡片字段",
        "self_changes": {
            "description": "## 目标\n完成门禁场景的人脸识别需求梳理。",
            "status": "in_progress",
            "priority": "high",
            "labels": ["人脸识别", "需求"],
            "assigneeTarget": "current-user",
            "developmentContext": {"type": "branch", "branch": "feature/face-id"},
            "startDate": "2026-09-01",
            "dueDate": "2026-09-15",
            "recurrence": None,
            "createIssues": [
                {
                    "title": "补充活体检测验收标准",
                    "description": "明确攻击样本与误拒率指标。",
                    "priority": "urgent",
                    "relation": "sub_issue",
                }
            ],
            "addAttachments": [
                {
                    "filename": "需求访谈纪要.md",
                    "contentType": "text/markdown",
                    "content": "# 需求访谈纪要\n首要场景：园区门禁。",
                }
            ],
            "relationChanges": {
                "add": [{"type": "blocked_by", "target_task_id": "card-risk"}],
                "remove": [{"type": "related", "target_task_id": "card-old"}],
            },
        },
        "routes": [],
    }
    parsed = _parse_backfill_block(
        "完成。\n```task_backfill\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```"
    )
    assert parsed == payload


def test_taskboard_only_card_opens_and_streams_without_creating_process_task(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "taskboard-only-card")
    card_id = "b685c17a-8b34-4a9e-b311-000000000001"
    context = {
        "schema_version": 1,
        "project": {"id": project_id, "name": "Card only", "business_goal": "Discuss"},
        "task": {
            "qws_task_id": card_id,
            "dashi_task_id": card_id,
            "title": "需求梳理",
            "descriptions": [{"id": "taskboard-description", "content": "梳理需求"}],
            "comments": [],
            "sub_issues": [],
            "status": "todo",
            "assignee": {"name": "johnie"},
            "qws": {"binding_kind": "taskboard_card", "workflow_id": None},
        },
    }
    opened = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": card_id,
            "workflow_id": None,
            "agent_version": "hermes-current",
            "card_context": context,
        },
    )
    assert opened.status_code == 201, opened.text
    assert opened.json()["binding"]["binding_kind"] == "taskboard_card"
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    assert all(task["id"] != card_id for task in process["tasks"])

    captured = {}

    async def fake_chat_stream(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        captured["question"] = req.question
        captured["context"] = req.client_session_context
        captured["trusted_professional_surface"] = kwargs.get(
            "trusted_professional_surface"
        )
        captured["first_activity_timeout_seconds"] = kwargs.get(
            "first_activity_timeout_seconds"
        )

        async def events():
            yield 'data: {"type":"done","answer":"已读取纯卡片会话"}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    streamed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages/stream",
        json={
            "question": "调用相关技能总结此卡片",
            "request_id": "card-only-stream-0001",
        },
    )
    assert streamed.status_code == 200
    assert "已读取纯卡片会话" in streamed.text
    assert card_id in captured["question"]
    assert "TASK_SESSION_SKILL_REQUESTED=true" in captured["question"]
    assert "READ_ONLY_TASK_CARD_CONTEXT" in captured["context"].messages[0].content
    assert captured["trusted_professional_surface"] is True
    assert captured["first_activity_timeout_seconds"] == 60


def test_card_backfill_applies_only_self_and_routes_overflow_to_target_session(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "card-backfill")
    source_id = "b685c17a-8b34-4a9e-b311-000000000011"
    target_id = "b685c17a-8b34-4a9e-b311-000000000012"

    def context(task_id, title, description, version=1):
        return {
            "schema_version": 1,
            "project": {"id": project_id, "name": "Backfill", "business_goal": "Ship"},
            "session_registry": [
                {
                    "task_id": source_id,
                    "identifier": "QWS-11",
                    "title": "需求梳理",
                    "responsibility": "梳理建设需求",
                    "status": "todo",
                    "card_version": version if task_id == source_id else 1,
                },
                {
                    "task_id": target_id,
                    "identifier": "QWS-12",
                    "title": "接口开发",
                    "responsibility": "实现识别接口",
                    "status": "todo",
                    "card_version": 1,
                },
            ],
            "task": {
                "qws_task_id": task_id,
                "dashi_task_id": task_id,
                "title": title,
                "descriptions": [
                    {
                        "id": "taskboard-description",
                        "source": "taskboard_description",
                        "content": description,
                    }
                ],
                "comments": [],
                "sub_issues": [],
                "status": "todo",
                "version": version,
                "qws": {"binding_kind": "taskboard_card", "workflow_id": None},
            },
        }

    opened = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": source_id,
            "workflow_id": None,
            "agent_version": "hermes-current",
            "card_context": context(source_id, "需求梳理", "旧描述"),
        },
    )
    assert opened.status_code == 201, opened.text

    async def fake_chat_stream(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        async def events():
            answer = (
                "已形成回填方案。\n\n```task_backfill\n"
                + json.dumps(
                    {
                        "summary": "更新需求，并把接口工作交给接口卡片",
                        "self_changes": {"description": "新需求描述"},
                        "routes": [
                            {"target_task_id": target_id, "content": "实现新增的人脸识别接口"}
                        ],
                    },
                    ensure_ascii=False,
                )
                + "\n```"
            )
            yield f'data: {json.dumps({"type": "done", "answer": answer}, ensure_ascii=False)}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", fake_chat_stream)
    request_id = "card-backfill-message-0001"
    streamed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/messages/stream",
        json={"question": "生成回填方案", "request_id": request_id},
    )
    assert streamed.status_code == 200
    proposal_response = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/backfill-proposals",
        json={"assistant_request_id": request_id},
    )
    assert proposal_response.status_code == 201, proposal_response.text
    proposal = proposal_response.json()
    assert proposal["self_changes"] == {"description": "新需求描述"}
    assert proposal["routed_items"][0]["target_task_id"] == target_id

    applied_call = {}

    async def fake_apply_taskboard_backfill(**kwargs):
        applied_call.update(kwargs)
        return {"created_issues": [], "attachments": [], "relations": []}

    monkeypatch.setattr(
        "backend.api.quantum_workspace._apply_taskboard_backfill",
        fake_apply_taskboard_backfill,
    )
    applied = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/backfill-proposals/{proposal['id']}/apply",
        headers={"Authorization": "Bearer test-token"},
    )
    assert applied.status_code == 200, applied.text
    assert applied_call["task_id"] == source_id
    assert applied_call["self_changes"] == {"description": "新需求描述"}
    assert applied_call["authorization"] == "Bearer test-token"

    updated_context = context(source_id, "需求梳理", "新需求描述", version=2)
    completed = client.post(
        f"/api/v1/task-conversations/{opened.json()['id']}/backfill-proposals/{proposal['id']}/complete",
        json={"card_context": updated_context},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "applied"
    assert completed.json()["context_sync"]["mode"] == "incremental"

    target = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": target_id,
            "workflow_id": None,
            "agent_version": "hermes-current",
            "card_context": context(target_id, "接口开发", "实现接口"),
        },
    )
    assert target.status_code == 201, target.text
    captured = {}

    async def capture_target(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        captured["context"] = req.client_session_context

        async def events():
            yield 'data: {"type":"done","answer":"已接收跨卡工作"}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr("backend.api.quantum_workspace.stream_chat", capture_target)
    delivered = client.post(
        f"/api/v1/task-conversations/{target.json()['id']}/messages/stream",
        json={"question": "读取新工作", "request_id": "target-inbox-message-0001"},
    )
    assert delivered.status_code == 200
    transferred = "\n".join(message.content for message in captured["context"].messages)
    assert "实现新增的人脸识别接口" in transferred
    assert source_id in transferred
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    assert all(task["id"] not in {source_id, target_id} for task in process["tasks"])


def test_card_session_keeps_legacy_canonical_conversation_history(_reset_database):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "card-session-identity")
    canonical = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    legacy = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": canonical["id"],
            "workflow_id": canonical["workflow_id"],
            "agent_version": "hermes-current",
        },
    )
    assert legacy.status_code == 201
    card_id = "b685c17a-8b34-4a9e-b311-000000000013"
    rebound = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": card_id,
            "workflow_id": canonical["workflow_id"],
            "agent_version": "hermes-current",
            "card_context": {
                "schema_version": 1,
                "project": {"id": project_id, "name": "Identity", "business_goal": "Ship"},
                "session_registry": [
                    {
                        "task_id": card_id,
                        "title": canonical["title"],
                        "responsibility": canonical["summary"],
                        "status": "todo",
                        "card_version": 1,
                    }
                ],
                "task": {
                    "qws_task_id": card_id,
                    "dashi_task_id": card_id,
                    "title": canonical["title"],
                    "descriptions": [
                        {"id": "taskboard-description", "source": "taskboard_description", "content": canonical["summary"]}
                    ],
                    "comments": [],
                    "sub_issues": [],
                    "status": "todo",
                    "version": 1,
                    "qws": {
                        "binding_kind": "taskboard_card",
                        "canonical_task_id": canonical["id"],
                        "stage_id": canonical["stage_id"],
                        "workflow_id": canonical["workflow_id"],
                    },
                },
            },
        },
    )
    assert rebound.status_code == 200, rebound.text
    assert rebound.json()["id"] == legacy.json()["id"]
    assert rebound.json()["binding"]["task_id"] == card_id
    assert rebound.json()["binding"]["canonical_task_id"] == canonical["id"]


def test_task_chat_is_server_bound_and_persists_real_stream_messages(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "chat")
    process = client.get(f"/api/v1/projects/{project_id}/process").json()
    task = process["tasks"][0]

    opened = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "workflow_id": task["workflow_id"],
            "agent_version": "hermes-current",
        },
    )
    assert opened.status_code == 201
    conversation = opened.json()
    assert conversation["binding"]["project_id"] == project_id
    assert conversation["binding"]["task_id"] == task["id"]
    assert conversation["binding"]["tenant_id"] == "tenant-a"

    captured = {}

    async def fake_chat_stream(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["question"] = req.question
        captured["knowledge_query"] = knowledge_query
        captured["session_id"] = req.session_id
        captured["client_session_context"] = req.client_session_context
        captured["allow_agent_invocation"] = allow_agent_invocation
        captured["allow_agency"] = kwargs.get("allow_agency")
        captured["trusted_professional_surface"] = kwargs.get(
            "trusted_professional_surface"
        )

        async def events():
            yield 'data: {"type":"delta","content":"已读取"}\n\n'
            yield 'data: {"type":"done","answer":"已读取任务上下文"}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr(
        "backend.api.quantum_workspace.stream_chat", fake_chat_stream
    )
    streamed = client.post(
        f"/api/v1/task-conversations/{conversation['id']}/messages/stream",
        json={"question": "下一步做什么？", "request_id": "chat-request-0001"},
    )
    assert streamed.status_code == 200
    assert "已读取任务上下文" in streamed.text
    assert project_id in captured["question"]
    assert task["id"] in captured["question"]
    assert "下一步做什么" in captured["question"]
    assert captured["knowledge_query"] == "下一步做什么？"
    assert captured["session_id"] == conversation["binding"]["session_id"]
    assert captured["client_session_context"].session_id == captured["session_id"]
    assert "READ_ONLY_TASK_CARD_CONTEXT" in captured["client_session_context"].messages[0].content
    assert captured["allow_agent_invocation"] is False
    assert captured["allow_agency"] is False
    assert captured["trusted_professional_surface"] is True

    messages = client.get(
        f"/api/v1/task-conversations/{conversation['id']}/messages"
    )
    assert messages.status_code == 200
    assert [(item["role"], item["content"]) for item in messages.json()] == [
        ("user", "下一步做什么？"),
        ("assistant", "已读取任务上下文"),
    ]

    replayed = client.post(
        f"/api/v1/task-conversations/{conversation['id']}/messages/stream",
        json={"question": "下一步做什么？", "request_id": "chat-request-0001"},
    )
    assert replayed.status_code == 200
    assert "已读取任务上下文" in replayed.text
    assert captured["calls"] == 1

    replay_messages = client.get(
        f"/api/v1/task-conversations/{conversation['id']}/messages"
    ).json()
    assert len(replay_messages) == 2


def test_task_chat_persists_and_replays_terminal_stream_failure(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "chat-failure")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    conversation = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "workflow_id": task["workflow_id"],
            "agent_version": "hermes-current",
        },
    ).json()
    calls = {"count": 0}

    async def failing_chat_stream(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        calls["count"] += 1

        async def events():
            yield 'data: {"type":"error","detail":"HTTP 502: bridge un'
            yield 'available"}\n\n'

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr(
        "backend.api.quantum_workspace.stream_chat", failing_chat_stream
    )
    url = f"/api/v1/task-conversations/{conversation['id']}/messages/stream"
    request = {"question": "继续", "request_id": "chat-failure-request"}
    first = client.post(url, json=request)
    replay = client.post(url, json=request)
    assert first.status_code == replay.status_code == 200
    assert "bridge unavailable" in first.text
    assert "bridge unavailable" in replay.text
    assert calls["count"] == 1
    messages = client.get(
        f"/api/v1/task-conversations/{conversation['id']}/messages"
    ).json()
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert "bridge unavailable" in messages[1]["content"]


def test_task_chat_records_and_replays_abrupt_upstream_disconnect(
    _reset_database, monkeypatch
):
    client = _reset_database
    project_id, _ = _create_applied_process(client, "chat-disconnect")
    task = client.get(f"/api/v1/projects/{project_id}/process").json()["tasks"][0]
    conversation = client.post(
        "/api/v1/task-conversations",
        json={
            "project_id": project_id,
            "task_id": task["id"],
            "workflow_id": task["workflow_id"],
            "agent_version": "hermes-current",
        },
    ).json()
    calls = {"count": 0}

    async def disconnected_chat_stream(
        req, payload, *, knowledge_query=None, allow_agent_invocation=True, **kwargs
    ):
        calls["count"] += 1

        async def events():
            yield 'data: {"type":"delta","content":"partial"}\n\n'
            raise RuntimeError("upstream disconnected")

        return StreamingResponse(events(), media_type="text/event-stream")

    monkeypatch.setattr(
        "backend.api.quantum_workspace.stream_chat", disconnected_chat_stream
    )
    url = f"/api/v1/task-conversations/{conversation['id']}/messages/stream"
    request = {"question": "继续", "request_id": "chat-disconnect-request"}
    first = client.post(url, json=request)
    replay = client.post(url, json=request)

    assert first.status_code == replay.status_code == 200
    assert "upstream disconnected" in first.text
    assert "upstream disconnected" in replay.text
    assert calls["count"] == 1
    messages = client.get(
        f"/api/v1/task-conversations/{conversation['id']}/messages"
    ).json()
    assert messages[-1]["event_metadata"]["terminal_type"] == "error"


def test_qws_canonical_relation_backfill_is_fail_closed() -> None:
    snapshot = {
        "task": {
            "relation_projection": {
                "canonical_source": "QWS_PROCESS_SNAPSHOT",
                "taskboard_mode": "READ_ONLY_CONSUMER_REQUIRED",
            }
        }
    }
    _enforce_qws_relation_backfill_contract(snapshot, {"description": "safe"})
    with pytest.raises(HTTPException, match="QWS canonical relations") as relation_error:
        _enforce_qws_relation_backfill_contract(
            snapshot,
            {"relationChanges": {"add": [{"type": "blocks", "target_task_id": "t2"}]}},
        )
    assert relation_error.value.status_code == 409
    with pytest.raises(HTTPException, match="QWS canonical relations"):
        _enforce_qws_relation_backfill_contract(
            snapshot,
            {"createIssues": [{"title": "child", "relation": "sub_issue"}]},
        )


def test_agent_task_writes_require_current_lease_epoch() -> None:
    task = {
        "execution_lease": {
            "status": "ACTIVE",
            "session_id": "session-new",
            "lease_epoch": 4,
            "actor_id": "agent:agent-a",
            "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        }
    }
    payload = {"principal_type": "agent", "sub": "agent-a"}
    _enforce_agent_lease_fence(task, payload, session_id="session-new", lease_epoch=4)
    with pytest.raises(HTTPException, match="execution_lease_fence_required"):
        _enforce_agent_lease_fence(task, payload, session_id="session-old", lease_epoch=3)
    with pytest.raises(HTTPException, match="execution_lease_fence_required"):
        _enforce_agent_lease_fence(task, {}, session_id="session-new", lease_epoch=4)
    with pytest.raises(HTTPException, match="execution_lease_fence_required"):
        _enforce_agent_lease_fence(
            task, {"principal_type": "agent", "sub": "agent-b"},
            session_id="session-new", lease_epoch=4,
        )
    _enforce_agent_lease_fence(
        task,
        {"principal_type": "human", "sub": "user-a", "amr": ["pwd"]},
        session_id=None,
        lease_epoch=None,
    )
