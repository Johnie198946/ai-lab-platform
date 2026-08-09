"""Agent API + 通知中心 + 调度器测试。"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.services.agent_scheduler import compute_next_run

client = TestClient(app)

# 关闭调度器后台循环(测试环境不跑真实调度)
try:
    from backend.services.agent_scheduler import _scheduler

    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
except Exception:
    pass


def _token(username="tester"):
    from jose import jwt as jose_jwt

    return jose_jwt.encode(
        {
            "sub": "1",
            "username": username,
            "exp": datetime.utcnow() + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


AUTH = {"Authorization": f"Bearer {_token()}"}


def test_compute_next_run():
    from datetime import datetime, timezone

    base = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    nxt = compute_next_run("0 18 * * *", base)
    assert nxt.hour == 18 and nxt.day == 9
    # 非法表达式回退 24h
    fallback = compute_next_run("not-a-cron", base)
    assert fallback > base


def test_templates_list():
    r = client.get("/api/agents/templates/meta", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 3
    keys = {t["key"] for t in data["templates"]}
    assert "policy-research" in keys


def test_template_instantiate():
    r = client.post(
        "/api/agents/templates/policy-research/instantiate",
        headers=AUTH,
        json={
            "name": "政策研究雷达",
            "mission": "跟踪中国政府政策并每日汇报",
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()
    assert agent["status"] == "active"
    assert len(agent["sources"]) == 6
    assert agent["schedule"] == "0 18 * * *"
    assert agent["next_run_at"] is not None
    # 清理
    client.delete(f"/api/agents/{agent['id']}", headers=AUTH)


def test_agent_crud_flow():
    # 创建
    r = client.post(
        "/api/agents",
        headers=AUTH,
        json={
            "name": "测试雷达",
            "mission": "跟踪测试领域资讯",
            "sources": [{"name": "示例", "url": "https://example.com/", "kind": "news"}],
            "schedule": "0 9 * * 1",
        },
    )
    assert r.status_code == 201, r.text
    agent = r.json()
    aid = agent["id"]
    assert agent["status"] == "active"
    assert agent["schedule"] == "0 9 * * 1"

    # 列表
    r = client.get("/api/agents", headers=AUTH)
    assert r.status_code == 200
    assert any(a["id"] == aid for a in r.json()["agents"])

    # 详情
    r = client.get(f"/api/agents/{aid}", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["id"] == aid

    # 暂停
    r = client.patch(f"/api/agents/{aid}", headers=AUTH, json={"status": "paused"})
    assert r.status_code == 200
    assert r.json()["status"] == "paused"

    # 改频率
    r = client.patch(f"/api/agents/{aid}", headers=AUTH, json={"schedule": "0 18 * * *"})
    assert r.status_code == 200
    assert r.json()["schedule"] == "0 18 * * *"

    # 恢复
    r = client.patch(f"/api/agents/{aid}", headers=AUTH, json={"status": "active"})
    assert r.status_code == 200
    assert r.json()["status"] == "active"

    # 删除
    r = client.delete(f"/api/agents/{aid}", headers=AUTH)
    assert r.status_code == 204
    r = client.get(f"/api/agents/{aid}", headers=AUTH)
    assert r.status_code == 404


def test_notifications_flow():
    # 造一条通知
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent
    from backend.models.notification import Notification

    async def _seed():
        async with SessionLocal() as db:
            agent = (
                await db.execute(select(Agent).limit(1))
            ).scalar_one_or_none()
            tenant = agent.tenant_key if agent else "u-1"
            n = Notification(
                tenant_key=tenant,
                agent_id="test-agent",
                title="测试通知",
                content="测试内容",
                channel="inapp",
            )
            db.add(n)
            await db.commit()
            return n.id

    nid = asyncio.run(_seed())

    # 列表(至少 1 条, unread ≥ 1)
    r = client.get("/api/notifications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["unread"] >= 1

    # 标记已读
    r = client.post(f"/api/notifications/{nid}/read", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 全部已读
    r = client.post("/api/notifications/read-all", headers=AUTH)
    assert r.status_code == 200
    r = client.get("/api/notifications", headers=AUTH)
    assert r.json()["unread"] == 0


def test_agents_require_auth():
    r = client.get("/api/agents")
    assert r.status_code == 401
    r = client.get("/api/notifications")
    assert r.status_code == 401
