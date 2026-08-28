from __future__ import annotations

import atexit
import asyncio
import os
from pathlib import Path
from tempfile import gettempdir

import httpx
import pytest
from fastapi.testclient import TestClient
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

TEST_DB = Path(gettempdir()) / f"quantum_workspace_test_{os.getpid()}.db"
if TEST_DB.exists():
    TEST_DB.unlink()
atexit.register(lambda: TEST_DB.unlink(missing_ok=True))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{TEST_DB}"
os.environ.setdefault("AUTHEN_DEV_MODE", "true")

from backend.main import app  # noqa: E402
from backend.api.auth import require_auth  # noqa: E402
from backend.db import SessionLocal  # noqa: E402
from backend.models.workflow import WorkflowDefinition  # noqa: E402
from backend.models.workspace import (  # noqa: E402
    WorkspaceBusinessIntake,
    WorkspaceProcessDraft,
    WorkspaceTaskConversation,
)


@pytest.fixture(autouse=True)
def _reset_database():
    app.dependency_overrides[require_auth] = lambda: {
        "tenant_key": "tenant-a",
        "user_id": "user-a",
        "sub": "user-a",
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
    assert task["status"] == "TODO"
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
    assert done.status_code == 200
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

    async def fake_chat_stream(req, payload, *, knowledge_query=None):
        captured["calls"] = captured.get("calls", 0) + 1
        captured["question"] = req.question
        captured["knowledge_query"] = knowledge_query
        captured["session_id"] = req.session_id

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

    async def failing_chat_stream(req, payload, *, knowledge_query=None):
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

    async def disconnected_chat_stream(req, payload, *, knowledge_query=None):
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
