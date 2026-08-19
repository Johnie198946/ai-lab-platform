"""Executable workflow V1 API, approval gate, and tenant isolation tests."""

from __future__ import annotations

import asyncio
import os
import unittest
from datetime import datetime, timedelta, timezone

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
            WorkflowPlanVersion,
        )

        self._old_resolver = auth.tenant_resolver
        self._old_super = auth._is_super_admin

        async def fake_resolver(user_id):
            return {
                "tenant_key": {"alpha": "tenant-alpha", "beta": "tenant-beta"}[user_id],
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
                    WorkflowPlanVersion,
                    WorkflowDefinition,
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
        return response.json()

    def test_create_generates_plan_but_does_not_execute(self):
        from backend.db import SessionLocal
        from backend.models.workflow import WorkflowExecution

        body = self.create()
        self.assertEqual(body["status"], "awaiting_approval")
        self.assertEqual(len(body["plan"]["dsl"]["nodes"]), 5)

        async def count():
            async with SessionLocal() as db:
                return int(
                    (
                        await db.execute(select(func.count(WorkflowExecution.id)))
                    ).scalar_one()
                )

        self.assertEqual(asyncio.run(count()), 0)

    def test_approve_creates_queued_execution_and_real_nodes(self):
        body = self.create()
        response = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"comment": "确认执行"},
        )
        self.assertEqual(response.status_code, 201, response.text)
        execution = response.json()
        self.assertEqual(execution["status"], "queued")
        self.assertEqual(
            [node["status"] for node in execution["nodes"]], ["pending"] * 5
        )
        self.assertEqual(execution["nodes"][0]["node_type"], "KNOWLEDGE_RETRIEVAL")

    def test_approve_request_id_is_idempotent(self):
        body = self.create()
        request_body = {"comment": "确认执行", "request_id": "ios-request-0001"}
        first = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/approve-plan", json=request_body
        )
        second = self.request(
            "POST", f"/api/v1/workflows/{body['id']}/approve-plan", json=request_body
        )
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json()["id"], second.json()["id"])

    def test_cross_tenant_workflow_is_invisible(self):
        body = self.create()
        response = self.request("GET", f"/api/v1/workflows/{body['id']}", sub="beta")
        self.assertEqual(response.status_code, 404)
        response = self.request("GET", "/api/v1/workflows", sub="beta")
        self.assertEqual(response.json(), [])

    def test_cyclic_edited_plan_is_rejected(self):
        body = self.create()
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
        import backend.services.workflow_executor as executor

        body = self.create()
        approved = self.request(
            "POST",
            f"/api/v1/workflows/{body['id']}/approve-plan",
            json={"comment": "执行"},
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


if __name__ == "__main__":
    unittest.main()
