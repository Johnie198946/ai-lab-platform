"""通知中心 + 调度器测试。

租户 Agent 的现行 CRUD 契约由 test_tenant_agents_api.py 覆盖；这里不再测试已移除的
旧模板/通用 Agent 接口，避免测试反向要求恢复废弃兼容层。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import httpx

from backend.main import app
from backend.services.agent_scheduler import compute_next_run


async def _request(method: str, path: str, **kwargs):
    """使用当前 httpx ASGITransport，替代已废弃的 Starlette TestClient 适配层。"""
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path, **kwargs)


def request(method: str, path: str, **kwargs):
    return asyncio.run(_request(method, path, **kwargs))

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
            "exp": datetime.now(timezone.utc) + timedelta(hours=1),
        },
        "test-secret",
        algorithm="HS256",
    )


AUTH = {"Authorization": f"Bearer {_token()}"}


def test_compute_next_run():
    from datetime import datetime, timedelta, timezone

    # cron 表达式按北京时间解释: 0 18 * * * = 每天北京 18:00 = UTC 10:00
    base = datetime(2026, 8, 9, 10, 0, tzinfo=timezone.utc)
    nxt = compute_next_run("0 18 * * *", base)
    assert nxt.hour == 10 and nxt.day == 10  # UTC 10:00 = 北京 18:00
    assert nxt.tzinfo == timezone.utc
    # 北京时间换算校验
    bj = nxt.astimezone(timezone(timedelta(hours=8)))
    assert bj.hour == 18
    # 非法表达式回退 24h
    fallback = compute_next_run("not-a-cron", base)
    assert fallback > base


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
    r = request("GET", "/api/notifications", headers=AUTH)
    assert r.status_code == 200
    data = r.json()
    assert data["total"] >= 1
    assert data["unread"] >= 1

    # 标记已读
    r = request("POST", f"/api/notifications/{nid}/read", headers=AUTH)
    assert r.status_code == 200
    assert r.json()["ok"] is True

    # 全部已读
    r = request("POST", "/api/notifications/read-all", headers=AUTH)
    assert r.status_code == 200
    r = request("GET", "/api/notifications", headers=AUTH)
    assert r.json()["unread"] == 0


def test_notifications_require_auth():
    r = request("GET", "/api/notifications")
    assert r.status_code == 401
