"""Executable workflow V1 API, approval gate, and tenant isolation tests."""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import httpx
from jose import jwt as jose_jwt
from sqlalchemy import delete, func, select

os.environ.setdefault("AUTHEN_JWT_SECRET", "test-secret")


def token(sub: str) -> str:
    return jose_jwt.encode(
        {"sub": sub, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        "test-secret",
        algorithm="HS256",
    )


class TestWorkflowsAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        from backend.db import SessionLocal, init_db
        from backend.main import app
        from backend.models.workflow import (
            WorkflowApproval,
            WorkflowArtifact,
            WorkflowDefinition,
            WorkflowEvent,
            WorkflowExecution,
            WorkflowNodeRun,
            WorkflowPlanningJob,
            WorkflowPlanVersion,
            WorkflowClarificationSession,
            WorkflowLifecycleEvent,
            WorkflowSessionMessage,
        )
        from backend.models.tenant_agent import AgentInvocationRelation, TenantAgentModel

        self._old_resolver = auth.tenant_resolver
        self._old_super = auth._is_super_admin

        async def fake_resolver(user_id):
            return {
                "tenant_key": {
                    "alpha": "tenant-alpha",
                    "gamma": "tenant-alpha",
                    "beta": "tenant-beta",
                }[user_id],
                "is_super_admin": False,
                "categories": {"wiki"},
            }

        async def fake_super(user_id):
            return False

        auth.tenant_resolver = fake_resolver
        auth._is_super_admin = fake_super
        asyncio.run(init_db())

        async def wipe():
            async with SessionLocal() as db:
                for model in (
                    WorkflowEvent,
                    WorkflowArtifact,
                    WorkflowNodeRun,
                    WorkflowApproval,
                    WorkflowExecution,
                    WorkflowPlanningJob,
                    WorkflowPlanVersion,
                    WorkflowLifecycleEvent,
                    WorkflowSessionMessage,
                    WorkflowClarificationSession,
                    WorkflowDefinition,
                    AgentInvocationRelation,
                    TenantAgentModel,
                ):
                    await db.execute(delete(model))
                await db.commit()

        asyncio.run(wipe())
        self._transport = httpx.ASGITransport(app=app)

    def tearDown(self):
        import backend.api.auth as auth

        auth.tenant_resolver = self._old_resolver
        auth._is_super_admin = self._old_super

    def request(self, method: str, path: str, *, sub: str = "alpha", json=None):
        async def run():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {token(sub)}"},
            ) as client:
                return await client.request(method, path, json=json)

        return asyncio.run(run())

    def create(self):
        response = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "拜仁洞察",
                "description": "在知识库中搜索拜仁近期情况并生成带证据的洞察报告",
                "desired_output": "Markdown 研究报告",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()["workflow"]

    def create_ready(self):
        from backend.services.workflow_planning import process_next_once

        workflow = self.create()
        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        for answer in ("学生个人使用", "先完成核心闭环", "交付物可直接使用"):
            response = self.request("POST", path, json={"response": answer})
            self.assertEqual(response.status_code, 200, response.text)
        async def confirm_and_wait():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {token('alpha')}"},
            ) as client:
                confirmed = await client.post(
                    path, json={"response": "确认，进入方案设计"}
                )
                await process_next_once()
                return confirmed

        confirmed = asyncio.run(confirm_and_wait())
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        workflow = self.request("GET", f"/api/v1/workflows/{workflow['id']}").json()
        workflow["plan"] = self.request(
            "GET", f"/api/v1/workflows/{workflow['id']}/plan"
        ).json()
        self.assertEqual(workflow["plan"]["max_tokens"], 999999)
        return workflow

    def test_create_is_immediate_draft_and_does_not_plan_or_execute(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowExecution

        body = self.create()
        self.assertEqual(body["status"], "clarifying")
        self.assertIsNotNone(body["clarification_session_id"])
        self.assertIsNone(body["active_plan_id"])

        async def count():
            async with SessionLocal() as db:
                return int(
                    (
                        await db.execute(select(func.count(WorkflowExecution.id)))
                    ).scalar_one()
                )

        self.assertEqual(asyncio.run(count()), 0)

    def test_delete_archives_owned_workflow_and_hides_it(self):
        from backend.db import SessionLocal
        from backend.models.workflow import (
            WorkflowClarificationSession,
            WorkflowDefinition,
        )

        workflow = self.create()
        denied = self.request(
            "DELETE", f"/api/v1/workflows/{workflow['id']}", sub="gamma"
        )
        self.assertEqual(denied.status_code, 404, denied.text)

        deleted = self.request("DELETE", f"/api/v1/workflows/{workflow['id']}")
        self.assertEqual(deleted.status_code, 204, deleted.text)
        self.assertNotIn(
            workflow["id"],
            [item["id"] for item in self.request("GET", "/api/v1/workflows").json()],
        )
        self.assertEqual(
            self.request("GET", f"/api/v1/workflows/{workflow['id']}").status_code,
            404,
        )

        async def archived_state():
            async with SessionLocal() as db:
                row = await db.get(WorkflowDefinition, workflow["id"])
                session = (
                    await db.execute(
                        select(WorkflowClarificationSession).where(
                            WorkflowClarificationSession.workflow_id == workflow["id"]
                        )
                    )
                ).scalar_one()
                return row.status, row.archived_at, session.phase

        status, archived_at, phase = asyncio.run(archived_state())
        self.assertEqual(status, "archived")
        self.assertIsNotNone(archived_at)
        self.assertEqual(phase, "archived")

    def test_clarification_phase_column_fits_confirmation_state(self):
        from backend.models.workflow import WorkflowClarificationSession

        phase_type = WorkflowClarificationSession.__table__.c.phase.type
        self.assertGreaterEqual(
            phase_type.length,
            len("awaiting_requirement_confirmation"),
        )

    def test_plan_output_repairs_legacy_partial_dsl(self):
        from backend.api.workflows import plan_out
        from backend.models.workflow import WorkflowPlanVersion

        plan = WorkflowPlanVersion(
            id="wfp_legacy",
            workflow_id="wf_legacy",
            version=1,
            dsl={"nodes": [], "edges": []},
            goal="生成英语评估方案",
            deliverable="Markdown",
            allow_network=True,
            max_tokens=24000,
            estimated_tokens=12000,
            knowledge_scope=[],
            validation_errors=[],
        )

        output = plan_out(plan)
        self.assertEqual(output["dsl"]["plan_id"], "wfp_legacy")
        self.assertEqual(output["dsl"]["name"], "生成英语评估方案")
        self.assertEqual(output["dsl"]["version"], "1.0.0")

    def test_hermes_node_budgets_are_fitted_to_workflow_limit(self):
        from backend.services.workflow_planner import fit_node_budgets

        raw = {
            "nodes": [
                {"id": "a", "parameters": {"max_tokens": 10000}},
                {"id": "b", "parameters": {"max_tokens": 9000}},
                {"id": "c", "parameters": {"max_tokens": 7000}},
            ]
        }
        fitted = fit_node_budgets(raw, 24000)
        budgets = [node["parameters"]["max_tokens"] for node in fitted["nodes"]]
        self.assertEqual(sum(budgets), 24000)
        self.assertTrue(all(value > 0 and value % 100 == 0 for value in budgets))

    def test_hermes_node_budgets_are_clamped_to_dsl_node_limit(self):
        from backend.services.workflow_planner import fit_node_budgets

        raw = {
            "nodes": [
                {"id": "a", "parameters": {"max_tokens": 165100}},
                {"id": "b", "parameters": {"max_tokens": 165100}},
                {"id": "c", "parameters": {"max_tokens": 165100}},
                {"id": "d", "parameters": {"max_tokens": 165100}},
            ]
        }
        fitted = fit_node_budgets(raw, 999999)
        budgets = [node["parameters"]["max_tokens"] for node in fitted["nodes"]]
        self.assertEqual(budgets, [128000, 128000, 128000, 128000])
        self.assertLessEqual(sum(budgets), 999999)

    def test_create_does_not_wait_for_blocked_planner(self):
        import backend.services.workflow_planner as workflow_planner

        blocked_planner = AsyncMock()
        with patch.object(workflow_planner, "build_plan", blocked_planner):
            body = self.create()
        self.assertEqual(body["status"], "clarifying")
        blocked_planner.assert_not_awaited()

    def test_confirmation_enqueues_one_durable_planning_job_and_active_scope(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowPlanningJob

        workflow = self.create()
        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        for answer in ("学生个人使用", "先完成核心闭环", "交付物可直接使用"):
            self.assertEqual(
                self.request("POST", path, json={"response": answer}).status_code, 200
            )
        confirmed = self.request(
            "POST", path, json={"response": "确认，进入方案设计"}
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        duplicate = self.request(
            "POST", path, json={"response": "确认，进入方案设计"}
        )
        self.assertEqual(duplicate.status_code, 409)

        async def jobs():
            async with SessionLocal() as db:
                return list((await db.execute(select(WorkflowPlanningJob))).scalars().all())

        queued = asyncio.run(jobs())
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0].status, "queued")
        own = self.request("GET", "/api/v1/workflow-activities/active").json()
        same_tenant_other_user = self.request(
            "GET", "/api/v1/workflow-activities/active", sub="gamma"
        ).json()
        self.assertEqual([item["workflow"]["id"] for item in own], [workflow["id"]])
        self.assertEqual(same_tenant_other_user, [])

    def test_expired_planning_lease_is_reclaimed_without_duplicate_plan(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowPlanningJob, WorkflowPlanVersion
        from backend.services.workflow_planning import process_next_once

        workflow = self.create()
        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        for answer in ("个人", "核心闭环", "可直接使用"):
            self.request("POST", path, json={"response": answer})
        self.request("POST", path, json={"response": "确认，进入方案设计"})

        async def expire_and_process():
            async with SessionLocal() as db:
                job = (await db.execute(select(WorkflowPlanningJob))).scalar_one()
                job.status = "running"
                job.lease_owner = "dead-worker"
                job.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
                await db.commit()
            self.assertTrue(await process_next_once(owner="replacement-worker"))
            async with SessionLocal() as db:
                return int(
                    (
                        await db.execute(
                            select(func.count(WorkflowPlanVersion.id)).where(
                                WorkflowPlanVersion.workflow_id == workflow["id"]
                            )
                        )
                    ).scalar_one()
                )

        self.assertEqual(asyncio.run(expire_and_process()), 1)

    def test_worker_backfills_planning_workflow_missing_durable_job(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowPlanningJob
        from backend.services.workflow_planning import backfill_orphaned_planning_jobs

        workflow = self.create()
        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        for answer in ("个人", "核心闭环", "可直接使用"):
            self.request("POST", path, json={"response": answer})
        self.request("POST", path, json={"response": "确认，进入方案设计"})

        async def remove_and_repair():
            async with SessionLocal() as db:
                await db.execute(
                    delete(WorkflowPlanningJob).where(
                        WorkflowPlanningJob.workflow_id == workflow["id"]
                    )
                )
                await db.commit()
                first = await backfill_orphaned_planning_jobs(db)
                second = await backfill_orphaned_planning_jobs(db)
                count = int(
                    (
                        await db.execute(
                            select(func.count(WorkflowPlanningJob.id)).where(
                                WorkflowPlanningJob.workflow_id == workflow["id"]
                            )
                        )
                    ).scalar_one()
                )
                return first, second, count

        self.assertEqual(asyncio.run(remove_and_repair()), (1, 0, 1))

    def test_explicit_requirement_goes_directly_to_confirmation_card(self):
        description = (
            "用户场景：销售经理在 iOS 端创建周报任务；MVP 范围：只包含知识库检索、"
            "报告生成与人工确认，不包含自动发布；数据与集成：仅使用已授权知识库接口；"
            "约束：必须离线恢复、禁止越权访问且总预算不超过 20000 Token；"
            "验收标准：生成 Markdown 报告并通过人工复核，所有引用均可追溯。"
        )
        response = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "明确需求",
                "description": description,
                "desired_output": "Markdown 周报",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        workflow_id = response.json()["workflow"]["id"]
        snapshot = self.request(
            "GET", f"/api/v1/workflows/{workflow_id}/clarification"
        ).json()
        self.assertEqual(snapshot["session"]["phase"], "awaiting_requirement_confirmation")
        self.assertEqual(snapshot["messages"][-1]["message_type"], "requirement_confirmation")
        self.assertIn("验收标准", snapshot["messages"][-1]["payload"]["question"])

    def test_approve_builds_agent_and_start_creates_execution(self):
        body = self.create_ready()
        response = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"comment": "确认执行"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        build = response.json()
        self.assertEqual(build["workflow"]["status"], "agent_ready")
        self.assertEqual(build["agent"]["visibility"], "private")
        self.assertIn("main_agent", build["agent"]["composition_manifest"]["capability_agent_ids"])
        started = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/start",
            json={"request_id": "ios-start-0001"},
        )
        self.assertEqual(started.status_code, 201, started.text)
        execution = started.json()
        self.assertEqual(execution["status"], "queued")
        self.assertEqual(
            [node["status"] for node in execution["nodes"]], ["pending"] * 5
        )
        self.assertEqual(execution["nodes"][0]["node_type"], "KNOWLEDGE_RETRIEVAL")

    def test_approve_request_id_is_idempotent(self):
        body = self.create_ready()
        request_body = {"comment": "确认执行", "request_id": "ios-request-0001"}
        first = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/approve-plan", json=request_body
        )
        second = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/approve-plan", json=request_body
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["agent"]["id"], second.json()["agent"]["id"])

    def test_ready_workflow_can_start_same_frozen_plan_twice(self):
        body = self.create_ready()
        approved = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"request_id": "ios-approve-agent-0001"},
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        first = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/start",
            json={"request_id": "ios-rerun-first-0001"},
        )
        rerun = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/start",
            json={"request_id": "ios-rerun-second-0002"},
        )
        duplicate = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/start",
            json={"request_id": "ios-rerun-second-0002"},
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(rerun.status_code, 201, rerun.text)
        self.assertNotEqual(first.json()["id"], rerun.json()["id"])
        self.assertEqual(rerun.json()["id"], duplicate.json()["id"])
        self.assertEqual(first.json()["plan_id"], rerun.json()["plan_id"])

    def test_cross_tenant_workflow_is_invisible(self):
        body = self.create_ready()
        response = self.request("GET", f"/api/v1/workflows/{body['id']}", sub="beta")
        self.assertEqual(response.status_code, 404)
        response = self.request("GET", "/api/v1/workflows", sub="beta")
        self.assertEqual(response.json(), [])

    def test_same_tenant_other_user_cannot_read_task_session_or_private_agent(self):
        body = self.create_ready()
        approved = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"request_id": "ios-private-agent-0001"},
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        agent_id = approved.json()["agent"]["id"]

        self.assertEqual(
            self.request("GET", f"/api/v1/workflows/{body['id']}", sub="gamma").status_code,
            404,
        )
        self.assertEqual(
            self.request(
                "GET", f"/api/v1/workflows/{body['id']}/clarification", sub="gamma"
            ).status_code,
            404,
        )
        visible_agents = self.request("GET", "/api/v1/tenant-agents", sub="gamma").json()
        self.assertNotIn(agent_id, {item["id"] for item in visible_agents})
        self.assertEqual(
            self.request("DELETE", f"/api/v1/tenant-agents/{agent_id}", sub="gamma").status_code,
            404,
        )

    def test_lifecycle_sse_resumes_after_event_id(self):
        body = self.create_ready()
        response = self.request(
            "GET", f"/api/v1/workflows/{body['id']}/lifecycle-events?after=3"
        )
        self.assertEqual(response.status_code, 200, response.text)
        event_ids = [
            int(line.removeprefix("id: "))
            for line in response.text.splitlines()
            if line.startswith("id: ")
        ]
        self.assertTrue(event_ids)
        self.assertTrue(all(event_id > 3 for event_id in event_ids))

    def test_replan_returns_session_before_background_plan_finishes(self):
        from backend.services.workflow_planning import process_next_once

        body = self.create_ready()

        async def request_and_wait():
            async with httpx.AsyncClient(
                transport=self._transport,
                base_url="http://testserver",
                headers={"Authorization": f"Bearer {token('alpha')}"},
            ) as client:
                response = await client.post(
                    f"/api/v1/workflows/{body['id']}/replan",
                    json={"instruction": "增加人工复核"},
                )
                self.assertEqual(response.status_code, 200, response.text)
                self.assertEqual(response.json()["phase"], "planning")
                self.assertTrue(await process_next_once())

        asyncio.run(request_and_wait())
        plan = self.request("GET", f"/api/v1/workflows/{body['id']}/plan").json()
        self.assertEqual(plan["version"], 2)

    def test_agent_composition_uses_platform_delegation_limits(self):
        from backend.api.workflows import compose_task_agent
        from backend.models.workflow import WorkflowDefinition, WorkflowPlanVersion

        workflow = WorkflowDefinition(
            id="wf-compose",
            tenant_key="tenant-alpha",
            title="iOS 安全代码审核",
            description="开发 iOS 功能并完成安全审核和测试",
            desired_output="代码与测试报告",
        )
        plan = WorkflowPlanVersion(
            id="wfp-compose",
            workflow_id=workflow.id,
            version=1,
            dsl={
                "nodes": [
                    {"node_type": "KNOWLEDGE_RETRIEVAL", "parameters": {}},
                    {"node_type": "FILTER_PASS", "parameters": {}},
                ]
            },
            knowledge_scope=["wiki"],
        )
        with patch.dict(
            os.environ,
            {
                "WORKFLOW_DELEGATION_MAX_CONCURRENT": "2",
                "WORKFLOW_DELEGATION_MAX_DEPTH": "1",
            },
        ):
            manifest = compose_task_agent(workflow, plan)
        self.assertEqual(
            manifest["capability_agent_ids"],
            ["main_agent", "knowledge", "coder", "supervision"],
        )
        self.assertEqual(
            manifest["delegation"],
            {"max_concurrent_children": 2, "max_spawn_depth": 1},
        )

    def test_reused_agent_creates_only_explicit_described_topology_edge(self):
        body = self.create_ready()
        reused = self.request(
            "POST",
            "/api/v1/tenant-agents",
            json={"base_agent_id": "knowledge", "custom_name": "既有研究 Agent"},
        )
        self.assertEqual(reused.status_code, 201, reused.text)
        reused_id = reused.json()["id"]
        plan = body["plan"]
        plan["dsl"]["nodes"][0]["parameters"]["agent_id"] = reused_id
        plan["dsl"]["nodes"][0]["parameters"]["instruction"] = "检索既有研究资料"
        edited = self.request(
            "PATCH",
            f"/api/v1/workflows/{body['id']}/plan",
            json={
                "dsl": plan["dsl"],
                "deliverable": plan["deliverable"],
                "allow_network": plan["allow_network"],
                "max_tokens": plan["max_tokens"],
                "knowledge_scope": plan["knowledge_scope"],
            },
        )
        self.assertEqual(edited.status_code, 200, edited.text)
        approved = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"request_id": "ios-agent-reuse-0001"},
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        source_id = f"db_{approved.json()['agent']['id']}"
        topology = self.request("GET", "/api/v1/topology").json()
        matching = [
            edge for edge in topology["edges"]
            if edge["source"] == source_id and edge["target"] == f"db_{reused_id}"
        ]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0]["label"], "检索既有研究资料")

    def test_cyclic_edited_plan_is_rejected(self):
        body = self.create_ready()
        plan = body["plan"]
        plan["dsl"]["edges"].append(
            {"source": "format_delivery", "target": "retrieve_evidence"}
        )
        response = self.request(
            "PATCH",
            f"/api/v1/workflows/{body['id']}/plan",
            json={
                "dsl": plan["dsl"],
                "deliverable": plan["deliverable"],
                "allow_network": True,
                "max_tokens": 24000,
                "knowledge_scope": ["wiki"],
            },
        )
        self.assertEqual(response.status_code, 422, response.text)

    def test_worker_executes_nodes_and_persists_artifacts(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowArtifact, WorkflowExecution
        from backend.services.workflow_artifacts import run_root
        import backend.services.workflow_executor as executor

        body = self.create_ready()
        built = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"comment": "执行"},
        )
        self.assertEqual(built.status_code, 201, built.text)
        approved = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/start",
            json={"request_id": "worker-start-0001"},
        ).json()
        node_ids = [node["node_id"] for node in approved["nodes"]]
        events = [{
            "seq": 1,
            "event_id": f"{approved['id']}:1",
            "type": "run_started",
            "message": "Hermes 开始执行",
        }]
        seq = 2
        for index, node_id in enumerate(node_ids):
            events.append({
                "seq": seq,
                "event_id": f"{approved['id']}:{seq}",
                "type": "node_started",
                "node_id": node_id,
                "message": "节点开始",
            })
            seq += 1
            events.append({
                "seq": seq,
                "event_id": f"{approved['id']}:{seq}",
                "type": "node_succeeded",
                "node_id": node_id,
                "message": "节点完成",
                "progress": int(((index + 1) / len(node_ids)) * 100),
                "usage": {
                    "input_tokens": 100,
                    "output_tokens": 50,
                    "total_tokens": 150,
                    "cache_read_tokens": 25,
                    "api_calls": 1,
                },
                "route": {"model": "deepseek-v4-flash", "provider": "deepseek"},
                "artifact": {
                    "kind": "final" if index == len(node_ids) - 1 else "draft",
                    "title": "节点成果",
                    "content": "# 节点成果\n\n证据与结论已整理。",
                },
            })
            seq += 1
        events.append({
            "seq": seq,
            "event_id": f"{approved['id']}:{seq}",
            "type": "run_completed",
            "message": "执行完成",
            "usage": {
                "input_tokens": 500,
                "output_tokens": 250,
                "total_tokens": 750,
                "cache_read_tokens": 125,
                "api_calls": 5,
                "model": "deepseek-v4-flash",
                "provider": "deepseek",
            },
        })

        async def fake_dispatch(execution, plan):
            return {"status": "running", "hermes_session_id": "hermes-test"}

        async def fake_snapshot(execution):
            return {
                "status": "completed",
                "hermes_session_id": "hermes-test",
                "events": events,
            }

        async def run_worker():
            async with SessionLocal() as db:
                await executor.sync_execution(approved["id"], db)
            async with SessionLocal() as db:
                execution = (
                    await db.execute(
                        select(WorkflowExecution).where(
                            WorkflowExecution.id == approved["id"]
                        )
                    )
                ).scalar_one()
                artifacts = list(
                    (
                        await db.execute(
                            select(WorkflowArtifact).where(
                                WorkflowArtifact.execution_id == approved["id"]
                            )
                        )
                    )
                    .scalars()
                    .all()
                )
                return execution, artifacts

        old_dispatch, old_read = executor.dispatch, executor.read_bridge_run
        executor.dispatch, executor.read_bridge_run = fake_dispatch, fake_snapshot
        try:
            execution, artifacts = asyncio.run(run_worker())
        finally:
            executor.dispatch, executor.read_bridge_run = old_dispatch, old_read
        self.assertEqual(execution.status, "awaiting_review")
        self.assertEqual(execution.progress, 100)
        self.assertTrue(any(item.kind == "final" for item in artifacts))
        self.assertTrue(all(item.content_hash for item in artifacts))
        self.assertEqual(execution.token_used, 750)
        self.assertEqual(execution.cache_read_tokens, 125)

        artifact = artifacts[0]
        content_path = run_root(execution) / artifact.relative_path
        content_path.unlink()

        async def full_snapshot(execution, *, after_seq=None):
            self.assertEqual(after_seq, 0)
            return {"events": events}

        with patch("backend.api.workflows.read_bridge_run", full_snapshot):
            recovered = self.request(
                "GET",
                f"/api/v1/workflow-executions/{execution.id}/artifacts/{artifact.id}/content",
            )
        self.assertEqual(recovered.status_code, 200, recovered.text)
        self.assertEqual(recovered.json()["content"], "# 节点成果\n\n证据与结论已整理。")
        self.assertTrue(content_path.is_file())

        content_path.unlink()
        artifact.content_hash = "0" * 64

        async def corrupt_hash():
            from backend.db import SessionLocal

            async with SessionLocal() as db:
                row = await db.get(WorkflowArtifact, artifact.id)
                row.content_hash = artifact.content_hash
                await db.commit()

        asyncio.run(corrupt_hash())
        with patch("backend.api.workflows.read_bridge_run", full_snapshot):
            rejected = self.request(
                "GET",
                f"/api/v1/workflow-executions/{execution.id}/artifacts/{artifact.id}/content",
            )
        self.assertEqual(rejected.status_code, 404, rejected.text)
        self.assertFalse(content_path.exists())


if __name__ == "__main__":
    unittest.main()
