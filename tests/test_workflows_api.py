"""Executable workflow V1 API, approval gate, and tenant isolation tests."""

from __future__ import annotations

import asyncio
import copy
import json
import os
import tempfile
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
        from backend.models.showroom import ShowroomSession
        from backend.models.customer_demand import CustomerDemand

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
                    ShowroomSession,
                    CustomerDemand,
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

    def advance_to_confirmation(self):
        workflow = self.create()
        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        for answer in ("学生个人使用", "先完成核心闭环", "交付物可直接使用"):
            response = self.request("POST", path, json={"response": answer})
            self.assertEqual(response.status_code, 200, response.text)
        return workflow, path

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

    def test_create_can_continue_authorized_showroom_context(self):
        from backend.db import SessionLocal
        from backend.models.showroom import ShowroomSession

        async def seed_showroom():
            async with SessionLocal() as db:
                db.add(
                    ShowroomSession(
                        session_id="visit-bridge-alpha",
                        tenant_key="tenant-alpha",
                        slot="main",
                        data={
                            "visitor": {"company": "制造企业", "role": "研发负责人"},
                            "customer_insight": {"summary": "关注需求到验证协同"},
                            "hermes_sessions": {"backstage_stored_session_id": "private"},
                        },
                    )
                )
                await db.commit()

        asyncio.run(seed_showroom())
        response = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "产品开发共创",
                "description": "请拆解当前产品开发需求",
                "showroom_session_id": "visit-bridge-alpha",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        workflow = response.json()["workflow"]
        context = workflow["requirements_snapshot"]["showroom_context"]
        self.assertEqual(context["source"]["session_id"], "visit-bridge-alpha")
        self.assertEqual(context["visitor"]["company"], "制造企业")
        self.assertNotIn("hermes_sessions", context)
        self.assertIn("关注需求到验证协同", workflow["description"])

        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        if response.json()["clarification_session"]["phase"] != "awaiting_requirement_confirmation":
            for answer in ("研发负责人使用", "先完成需求到验证闭环", "交付可审阅方案"):
                advanced = self.request("POST", path, json={"response": answer})
                self.assertEqual(advanced.status_code, 200, advanced.text)
        confirmation = self.request(
            "POST", path, json={"response": "确认并规划", "intent": "confirm"}
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.text)
        refreshed = self.request("GET", f"/api/v1/workflows/{workflow['id']}").json()
        self.assertEqual(
            refreshed["requirements_snapshot"]["showroom_context"]["source"]["session_id"],
            "visit-bridge-alpha",
        )

        denied = self.request(
            "POST",
            "/api/v1/workflows",
            sub="beta",
            json={
                "title": "越权任务",
                "description": "不得读取其他租户来访上下文",
                "showroom_session_id": "visit-bridge-alpha",
            },
        )
        self.assertEqual(denied.status_code, 404, denied.text)

    def test_create_can_continue_confirmed_customer_demand(self):
        from backend.db import SessionLocal
        from backend.models.customer_demand import CustomerDemand

        async def seed():
            async with SessionLocal() as db:
                db.add(CustomerDemand(
                    demand_id="dmd_workflow_001",
                    tenant_key="tenant-alpha",
                    created_by="alpha",
                    source_text="新品需求评审周期太长",
                    source_hash="b" * 64,
                    business_scene="产品开发",
                    overall_goal="缩短评审周期",
                    stakeholders=["产品", "研发"],
                    requirement_items=["保留评审证据"],
                    conflict_notes=[],
                    constraints=["人工批准"],
                    acceptance_criteria=["周期可度量"],
                    status="confirmed",
                    version=2,
                ))
                await db.commit()

        asyncio.run(seed())
        response = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "需求续接",
                "description": "继续生成AI员工",
                "customer_demand_id": "dmd_workflow_001",
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        workflow = response.json()["workflow"]
        snapshot = workflow["requirements_snapshot"]["customer_demand"]
        self.assertEqual(snapshot["source"]["type"], "customer_demand")
        self.assertEqual(snapshot["source"]["version"], 2)
        self.assertIn("新品需求评审周期太长", workflow["description"])

        path = f"/api/v1/workflows/{workflow['id']}/clarification/respond"
        if response.json()["clarification_session"]["phase"] != "awaiting_requirement_confirmation":
            for answer in ("研发团队使用", "先做需求评审闭环", "交付带证据的方案"):
                advanced = self.request("POST", path, json={"response": answer})
                self.assertEqual(advanced.status_code, 200, advanced.text)
        confirmation = self.request(
            "POST",
            path,
            json={"response": "确认并进入方案", "intent": "confirm"},
        )
        self.assertEqual(confirmation.status_code, 200, confirmation.text)
        self.assertEqual(confirmation.json()["phase"], "planning")
        refreshed = self.request("GET", f"/api/v1/workflows/{workflow['id']}").json()
        preserved = refreshed["requirements_snapshot"]["customer_demand"]
        self.assertEqual(preserved["source"]["demand_id"], "dmd_workflow_001")
        self.assertEqual(preserved["source"]["version"], 2)

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

        workflow, path = self.advance_to_confirmation()
        confirmed = self.request(
            "POST", path, json={"response": "确认，进入方案设计"}
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.text)
        duplicate = self.request(
            "POST", path, json={"response": "确认，进入方案设计"}
        )
        self.assertEqual(duplicate.status_code, 200)

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

    def test_natural_confirmation_enters_planning_for_supported_phrases(self):
        for phrase in ("是的", "可以", "开始", "没有了，开始后面流程"):
            workflow, path = self.advance_to_confirmation()
            response = self.request("POST", path, json={"response": phrase})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["phase"], "planning")

    def test_explicit_confirm_intent_enters_planning_without_keyword_text(self):
        workflow, path = self.advance_to_confirmation()
        response = self.request(
            "POST", path, json={"response": "按按钮提交", "intent": "confirm"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["phase"], "planning")

    def test_explicit_revise_intent_never_queues_planning(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowPlanningJob

        workflow, path = self.advance_to_confirmation()
        response = self.request(
            "POST", path, json={"response": "", "intent": "revise"}
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["phase"], "clarifying")

        async def count_jobs():
            async with SessionLocal() as db:
                return int((await db.execute(select(func.count(WorkflowPlanningJob.id)))).scalar_one())

        self.assertEqual(asyncio.run(count_jobs()), 0)

    def test_negative_or_modification_confirmation_text_never_queues_planning(self):
        for phrase in (
            "确认，但需要修改配送范围",
            "不进入方案",
            "确认但不进入方案",
            "不要开始后面流程",
        ):
            workflow, path = self.advance_to_confirmation()
            response = self.request("POST", path, json={"response": phrase})
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()["phase"], "clarifying", phrase)

    def test_confirmation_is_atomic_and_enqueues_exactly_one_job(self):
        from backend.db import SessionLocal
        from backend.models.workflow import (
            WorkflowClarificationSession,
            WorkflowDefinition,
            WorkflowLifecycleEvent,
            WorkflowPlanningJob,
        )

        workflow, path = self.advance_to_confirmation()
        first = self.request("POST", path, json={"response": "go", "intent": "confirm"})
        second = self.request("POST", path, json={"response": "again", "intent": "confirm"})
        self.assertEqual(first.status_code, 200, first.text)
        self.assertEqual(second.status_code, 200, second.text)

        async def state():
            async with SessionLocal() as db:
                workflow_row = await db.get(WorkflowDefinition, workflow["id"])
                session = (
                    await db.execute(
                        select(WorkflowClarificationSession).where(
                            WorkflowClarificationSession.workflow_id == workflow["id"]
                        )
                    )
                ).scalar_one()
                jobs = int((await db.execute(select(func.count(WorkflowPlanningJob.id)))).scalar_one())
                queued_events = int(
                    (
                        await db.execute(
                            select(func.count(WorkflowLifecycleEvent.id)).where(
                                WorkflowLifecycleEvent.workflow_id == workflow["id"],
                                WorkflowLifecycleEvent.event_type == "planning_queued",
                            )
                        )
                    ).scalar_one()
                )
                return workflow_row.status, session.phase, session.confirmed_spec, jobs, queued_events

        status, phase, confirmed_spec, jobs, queued_events = asyncio.run(state())
        self.assertEqual((status, phase), ("planning", "planning"))
        self.assertTrue(confirmed_spec.get("goal"))
        self.assertEqual((jobs, queued_events), (1, 1))

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

    def test_confirmed_food_delivery_ipd_request_persists_registered_server_plan(self):
        from backend.services.workflow_planning import process_next_once

        created = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "外卖平台IPD",
                "description": "从零开发一个外卖平台，借鉴超聚变IPD。",
                "desired_output": "IPD计划",
            },
        )
        self.assertEqual(created.status_code, 201, created.text)
        workflow_id = created.json()["workflow"]["id"]
        path = f"/api/v1/workflows/{workflow_id}/clarification/respond"
        for answer in ("消费者与商家", "核心交易闭环", "通过人工决策门"):
            self.assertEqual(self.request("POST", path, json={"response": answer}).status_code, 200)
        self.assertEqual(
            self.request("POST", path, json={"intent": "confirm"}).status_code,
            200,
        )
        self.assertTrue(asyncio.run(process_next_once()))

        plan = self.request("GET", f"/api/v1/workflows/{workflow_id}/plan").json()["dsl"]
        self.assertEqual(len(plan["nodes"]), 7)
        self.assertEqual(
            [node["parameters"]["execution_enabled"] for node in plan["nodes"]].count(True),
            2,
        )
        self.assertTrue(all("decision_gate" in node["parameters"] for node in plan["nodes"]))

        approved = self.request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/approve-plan",
            json={"request_id": "ipd-approve-0001"},
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        started = self.request(
            "POST",
            f"/api/v1/workflows/{workflow_id}/start",
            json={"request_id": "ipd-start-0001"},
        )
        self.assertEqual(started.status_code, 201, started.text)
        self.assertEqual(
            [node["node_id"] for node in started.json()["nodes"]],
            ["market_requirement_evidence", "product_concept_ipd_mapping"],
        )

    def test_generic_product_request_persists_process_contract_plan(self):
        from backend.services.workflow_planning import process_next_once

        created = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "新品评审提效",
                "description": "我们要缩短新品需求评审周期，按IPD推进产品开发",
                "desired_output": "IPD评审计划",
            },
        )
        workflow_id = created.json()["workflow"]["id"]
        path = f"/api/v1/workflows/{workflow_id}/clarification/respond"
        for answer in ("产品与研发团队", "概念和需求评审", "评审周期可量化"):
            self.assertEqual(self.request("POST", path, json={"response": answer}).status_code, 200)
        self.assertEqual(self.request("POST", path, json={"intent": "confirm"}).status_code, 200)
        self.assertTrue(asyncio.run(process_next_once()))

        plan = self.request("GET", f"/api/v1/workflows/{workflow_id}/plan").json()["dsl"]
        self.assertEqual(plan["process_contract_id"], "xfusion.ipd")
        self.assertEqual(len(plan["process_contract_digest"]), 64)
        self.assertEqual(
            plan["nodes"][0]["parameters"]["skill_binding"]["skill_id"],
            "ipd-01-market-insight",
        )
        self.assertEqual(
            plan["nodes"][1]["parameters"]["skill_binding"]["skill_id"],
            "ipd-02-requirement-analysis",
        )

    def test_registered_ipd_plan_rejects_runtime_contract_patch_and_reuses_projection(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowExecution, WorkflowPlanVersion
        from backend.services.workflow_artifacts import run_root
        from backend.services.workflow_planning import process_next_once
        import backend.services.workflow_executor as executor

        created = self.request(
            "POST",
            "/api/v1/workflows",
            json={
                "title": "外卖平台IPD硬门",
                "description": "从零开发外卖平台，借鉴超聚变IPD",
                "desired_output": "IPD计划",
            },
        )
        workflow_id = created.json()["workflow"]["id"]
        path = f"/api/v1/workflows/{workflow_id}/clarification/respond"
        for answer in ("消费者与商家", "核心交易闭环", "通过人工决策门"):
            self.assertEqual(self.request("POST", path, json={"response": answer}).status_code, 200)
        self.assertEqual(self.request("POST", path, json={"intent": "confirm"}).status_code, 200)
        self.assertTrue(asyncio.run(process_next_once()))
        plan_response = self.request("GET", f"/api/v1/workflows/{workflow_id}/plan").json()

        variants = []
        enabled_third = copy.deepcopy(plan_response["dsl"])
        enabled_third["nodes"][2]["parameters"]["execution_enabled"] = True
        variants.append(enabled_third)
        replaced_first = copy.deepcopy(plan_response["dsl"])
        replaced_first["nodes"][0]["parameters"]["execution_enabled"] = False
        replaced_first["nodes"][2]["parameters"]["execution_enabled"] = True
        variants.append(replaced_first)
        reordered = copy.deepcopy(plan_response["dsl"])
        reordered["nodes"][0], reordered["nodes"][1] = reordered["nodes"][1], reordered["nodes"][0]
        variants.append(reordered)
        for dsl in variants:
            rejected = self.request(
                "PATCH",
                f"/api/v1/workflows/{workflow_id}/plan",
                json={
                    "dsl": dsl,
                    "deliverable": plan_response["deliverable"],
                    "allow_network": plan_response["allow_network"],
                    "max_tokens": plan_response["max_tokens"],
                    "knowledge_scope": plan_response["knowledge_scope"],
                },
            )
            self.assertIn(rejected.status_code, (409, 422), rejected.text)

        approved = self.request(
            "POST", f"/api/v1/workflows/{workflow_id}/approve-plan", json={"request_id": "hard-approve"}
        )
        self.assertEqual(approved.status_code, 201, approved.text)
        started = self.request(
            "POST", f"/api/v1/workflows/{workflow_id}/start", json={"request_id": "hard-start"}
        )
        self.assertEqual(started.status_code, 201, started.text)
        execution_id = started.json()["id"]
        expected_ids = ["market_requirement_evidence", "product_concept_ipd_mapping"]
        self.assertEqual([node["node_id"] for node in started.json()["nodes"]], expected_ids)

        async def rows():
            async with SessionLocal() as db:
                return await db.get(WorkflowExecution, execution_id), await db.get(
                    WorkflowPlanVersion, plan_response["id"]
                )

        execution, plan = asyncio.run(rows())
        captured = {}

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {"status": "running", "hermes_session_id": "hard-session"}

        class Client:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def post(self, url, **kwargs):
                captured.update(kwargs["json"])
                return Response()

        with patch.object(executor.httpx, "AsyncClient", lambda **kwargs: Client()):
            asyncio.run(executor.dispatch(execution, plan))
        self.assertEqual([node["id"] for node in captured["plan"]["nodes"]], expected_ids)
        self.assertEqual(captured["plan"]["edges"], [
            {"source": expected_ids[0], "target": expected_ids[1]}
        ])

        async def fake_dispatch(execution, plan):
            return {"status": "running", "hermes_session_id": "hard-session"}

        async def fake_snapshot(execution):
            return {"status": "running", "events": []}

        async def sync():
            async with SessionLocal() as db:
                await executor.sync_execution(execution_id, db)

        with tempfile.TemporaryDirectory() as home, patch.dict(os.environ, {"AI_LAB_HOME": home}):
            with patch.object(executor, "dispatch", fake_dispatch), patch.object(
                executor, "read_bridge_run", fake_snapshot
            ):
                asyncio.run(sync())
            runtime_plan = json.loads((run_root(execution) / "plan.json").read_text())
        self.assertEqual([node["id"] for node in runtime_plan["nodes"]], expected_ids)
        self.assertEqual(runtime_plan["edges"], [
            {"source": expected_ids[0], "target": expected_ids[1]}
        ])

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

    def test_approve_ignores_skill_references_when_persisting_agent_relations(self):
        from backend.db import SessionLocal
        from backend.models.tenant_agent import AgentInvocationRelation
        from backend.models.workflow import WorkflowPlanVersion

        body = self.create_ready()

        async def add_skill_reference():
            async with SessionLocal() as db:
                plan = await db.get(WorkflowPlanVersion, body["active_plan_id"])
                dsl = dict(plan.dsl)
                dsl["nodes"] = [
                    *dsl.get("nodes", []),
                    {
                        "id": "skill-backed-review",
                        "node_type": "LLM_INFERENCE",
                        "parameters": {"agent_id": "skill_ai-lab-competitive-intelligence"},
                    },
                ]
                plan.dsl = dsl
                await db.commit()

        asyncio.run(add_skill_reference())
        with patch("backend.api.workflows.validate_plan_policy", new=AsyncMock()):
            response = self.request(
                "POST",
                f"/api/v1/workflows/{body['id']}/approve-plan",
                json={"comment": "确认执行"},
            )
        self.assertEqual(response.status_code, 201, response.text)
        self.assertIn(
            "skill_ai-lab-competitive-intelligence",
            response.json()["agent"]["composition_manifest"]["invoked_agent_ids"],
        )

        async def relation_targets():
            async with SessionLocal() as db:
                return list((await db.execute(select(AgentInvocationRelation.target_agent_id))).scalars())

        self.assertNotIn("skill_ai-lab-competitive-intelligence", asyncio.run(relation_targets()))

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

    def test_active_workflow_rejects_second_start(self):
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
        self.assertEqual(rerun.status_code, 409, rerun.text)
        self.assertEqual(duplicate.status_code, 409, duplicate.text)
        self.assertIn("已有活动执行", rerun.json()["detail"])

    def test_dynamic_create_ready_enters_requirement_confirmation(self):
        with patch(
            "backend.api.workflows.request_bridge_clarification",
            new=AsyncMock(return_value={
                "status": "READY",
                "source": "hermes",
                "truth": "LIVE",
                "simulation": False,
                "usage": {},
            }),
        ):
            created = self.request(
                "POST",
                "/api/v1/workflows",
                json={
                    "title": "Dynamic ready",
                    "description": "Build an IPD workspace for our team.",
                    "desired_output": "Decision record",
                    "clarification_mode": "dynamic",
                },
            )
        self.assertEqual(created.status_code, 201, created.text)
        workflow_id = created.json()["workflow"]["id"]
        clarification = self.request("GET", f"/api/v1/workflows/{workflow_id}/clarification")
        self.assertEqual(clarification.status_code, 200, clarification.text)
        self.assertEqual(clarification.json()["session"]["phase"], "awaiting_requirement_confirmation")
        self.assertTrue(clarification.json()["messages"][-1]["content"])

    def test_dynamic_create_question_clears_pending_status(self):
        with patch(
            "backend.api.workflows.request_bridge_clarification",
            new=AsyncMock(return_value={
                "status": "question",
                "question": "Who is the primary user?",
                "dimension": "target user",
                "source": "hermes",
                "truth": "LIVE",
                "simulation": False,
                "usage": {},
            }),
        ):
            created = self.request(
                "POST",
                "/api/v1/workflows",
                json={
                    "title": "Dynamic question",
                    "description": "Build an IPD workspace for our team.",
                    "desired_output": "Decision record",
                    "clarification_mode": "dynamic",
                },
            )
        self.assertEqual(created.status_code, 201, created.text)
        self.assertEqual(created.json()["workflow"]["status"], "clarifying")
        self.assertEqual(created.json()["clarification_session"]["phase"], "clarifying")

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

        explain = self.request(
            "GET", f"/api/v1/workflow-executions/{execution.id}/explain-context"
        )
        self.assertEqual(explain.status_code, 200, explain.text)
        repeated = self.request(
            "GET", f"/api/v1/workflow-executions/{execution.id}/explain-context"
        )
        self.assertEqual(explain.json()["snapshot_id"], repeated.json()["snapshot_id"])
        report = self.request(
            "GET", f"/api/v1/workflow-executions/{execution.id}/evidence-report"
        )
        self.assertEqual(report.status_code, 200, report.text)
        self.assertTrue(report.json()["claims"])
        self.assertTrue(all(item["status"] == "SUPPORTED" for item in report.json()["claims"]))
        self.assertEqual(
            report.json()["token_factory_recommendation"]["status"],
            "NEEDS_BENCHMARK",
        )

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

    def test_lifecycle_event_bounds_display_message_but_preserves_detail(self):
        from backend.api.workflows import append_lifecycle_event
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowClarificationSession, WorkflowDefinition, WorkflowLifecycleEvent

        async def write_and_read():
            async with SessionLocal() as db:
                workflow = WorkflowDefinition(
                    id="wf_long_event",
                    tenant_key="tenant-alpha",
                    created_by="alpha",
                    title="长事件",
                    description="验证长生命周期事件",
                )
                session = WorkflowClarificationSession(
                    id="wfs_long_event",
                    workflow_id=workflow.id,
                    tenant_key="tenant-alpha",
                    owner_user_id="alpha",
                )
                db.add_all([workflow, session])
                await db.flush()
                detail = "需求摘要" * 300
                await append_lifecycle_event(
                    db,
                    workflow,
                    session,
                    "requirement_summary_ready",
                    detail,
                    {"detail": detail},
                )
                await db.commit()
                row = (
                    await db.execute(
                        select(WorkflowLifecycleEvent).where(
                            WorkflowLifecycleEvent.workflow_id == workflow.id
                        )
                    )
                ).scalar_one()
                return row.message, row.payload["detail"]

        message, detail = asyncio.run(write_and_read())
        self.assertEqual(len(message), 500)
        self.assertEqual(detail, "需求摘要" * 300)


if __name__ == "__main__":
    unittest.main()
