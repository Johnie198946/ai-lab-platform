"""任务 API 测试。"""

from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta

from jose import jwt as jose_jwt

os.environ["AUTHEN_JWT_SECRET"] = "test-secret"


def auth_headers() -> dict[str, str]:
    token = jose_jwt.encode(
        {
            "sub": "1",
            "username": "tester",
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )
    return {"Authorization": f"Bearer {token}"}


class TestTasksAPI(unittest.TestCase):
    def setUp(self):
        import backend.api.auth as auth
        import backend.api.tasks as tasks

        self._old_resolver = auth.tenant_resolver
        self._old_tasks = tasks._tasks.copy()
        tasks._tasks.clear()

        async def fake_resolver(user_id):
            return {
                "tenant_key": "u-test",
                "is_super_admin": True,
                "categories": set(),
            }

        auth.tenant_resolver = fake_resolver

        from fastapi.testclient import TestClient
        from backend.main import app

        self.client = TestClient(app, headers=auth_headers())

    def tearDown(self):
        import backend.api.auth as auth
        import backend.api.tasks as tasks

        auth.tenant_resolver = self._old_resolver
        tasks._tasks.clear()
        tasks._tasks.update(self._old_tasks)

    def test_create_and_complete_task(self):
        r = self.client.post(
            "/api/tasks",
            json={
                "task_type": "knowledge_compile",
                "goal": "重建知识矩阵并复核输出",
                "assigned_to": "Wiki Writer",
                "expected_outputs": ["data/knowledge_matrix.json"],
                "read_targets": ["研究系统/", "wiki/"],
                "write_targets": ["data/knowledge_matrix.json"],
                "policy": {
                    "readable_paths": ["研究系统/", "wiki/"],
                    "writable_paths": ["data/"],
                    "knowledge_scope": ["研究系统", "wiki"],
                    "allow_network": False,
                    "requires_review": True,
                    "max_tokens": 30000,
                },
            },
        )
        self.assertEqual(r.status_code, 201)
        body = r.json()
        self.assertEqual(body["status"], "ready")
        task_id = body["task_id"]

        inbox = self.client.get("/api/tasks/inbox", params={"agent": "Wiki Writer"})
        self.assertEqual(inbox.status_code, 200)
        self.assertEqual(inbox.json()[0]["task_id"], task_id)

        done = self.client.patch(
            f"/api/tasks/{task_id}",
            json={
                "status": "done",
                "result_summary": "矩阵已重建并完成复核",
                "next_actions": ["触发下游问答索引刷新"],
            },
        )
        self.assertEqual(done.status_code, 200)
        self.assertEqual(done.json()["status"], "done")
        self.assertEqual(done.json()["result_summary"], "矩阵已重建并完成复核")
        self.assertIsNotNone(done.json()["completed_at"])
