"""平台调度器 — 容器内 APScheduler, 驱动云端子 Agent 定时执行。

设计决策(为什么不用 Hermes cron):
- 服务器 Hermes cron 踩过坑: gateway 重启即停摆 / admin-root 双实例 / jobs.json 合并复杂
- 平台自建调度器: 与 API 同生共死(容器重启自动恢复), Agent 定义在 DB, 汇报走站内通知
- 每 60s 扫描一次 due agents(状态=active 且 next_run_at<=now), 执行后计算下次运行时间
- 执行经 hermes-bridge 调云端 Hermes; 结果写 notifications 表 + 更新 last_run_at/status
"""

from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from croniter import croniter

logger = logging.getLogger(__name__)

HERMES_BRIDGE_URL = os.environ.get(
    "HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat"
)
HERMES_TIMEOUT = 240  # Agent 定时执行更宽松(采集+入库+编译)

_scheduler: AsyncIOScheduler | None = None
_scan_interval = 60  # 秒

# 调度时区: 北京时间(CST=UTC+8) — cron 表达式按用户可读的 18:00 解释
CST = timezone(timedelta(hours=8))


def compute_next_run(cron_expr: str, base: datetime | None = None) -> datetime:
    """cron 表达式 → 下次运行时间(UTC 存储)。表达式按北京时间(CST)解释。"""
    base_cst = base or datetime.now(CST)
    if base_cst.tzinfo is None:
        base_cst = base_cst.replace(tzinfo=CST)
    else:
        base_cst = base_cst.astimezone(CST)
    try:
        it = croniter(cron_expr, base_cst)
        nxt = it.get_next(datetime)
        if nxt.tzinfo is None:
            nxt = nxt.replace(tzinfo=CST)
        else:
            nxt = nxt.astimezone(CST)
        return nxt.astimezone(timezone.utc)
    except Exception as e:
        logger.warning("cron 表达式非法 %r → 回退 24h: %s", cron_expr, e)
        return datetime.now(timezone.utc) + timedelta(days=1)


async def _call_hermes_bridge(goal: str) -> str:
    """透传 Hermes bridge。"""
    try:
        async with httpx.AsyncClient(timeout=HERMES_TIMEOUT) as client:
            r = await client.post(HERMES_BRIDGE_URL, json={"goal": goal})
            if r.status_code == 200:
                return r.json().get("reply", "").strip()
            return f"⚠️ Hermes 桥接失败（HTTP {r.status_code}）"
    except Exception as e:
        logger.error("Hermes 桥接调用异常: %s", e)
        return f"⚠️ Hermes 桥接调用异常: {e}"


async def _run_agent_once(agent_id: str) -> None:
    """执行一个 Agent(独立事务, 失败不影响其他 Agent)。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent
    from backend.models.notification import Notification

    try:
        async with SessionLocal() as db:
            agent = (
                await db.execute(select(Agent).where(Agent.id == agent_id))
            ).scalar_one_or_none()
            if agent is None or agent.status != "active":
                return

            mission = agent.mission or ""
            prompt = agent.prompt or mission

            agent.last_run_at = datetime.now(timezone.utc)
            agent.last_status = "running"
            await db.commit()

        # 执行(不持锁, 长任务)
        reply = await _call_hermes_bridge(
            f"【定时任务·{agent.name}】{prompt}"
        )
        success = not reply.startswith("⚠️")

        async with SessionLocal() as db:
            agent = (
                await db.execute(select(Agent).where(Agent.id == agent_id))
            ).scalar_one_or_none()
            if agent is None:
                return
            agent.last_status = "ok" if success else "error"
            agent.last_output = reply[:4000]
            agent.next_run_at = compute_next_run(agent.schedule)
            await db.commit()

            # 站内通知(无论成败都通知, 失败内容带 ⚠️)
            notif = Notification(
                tenant_key=agent.tenant_key,
                agent_id=agent.id,
                title=f"{agent.name} · 定时汇报",
                content=reply[:8000],
                channel="inapp",
            )
            db.add(notif)
            await db.commit()

            # 飞书推送(agent 配置了 feishu 通道时)
            if "feishu" in (agent.channel or "").split(","):
                from backend.services.feishu import send_feishu_async

                await send_feishu_async(
                    f"{agent.name} · 定时汇报", reply[:3500]
                )
            logger.info(
                "Agent %s 执行完成 | status=%s | next=%s",
                agent.name,
                agent.last_status,
                agent.next_run_at,
            )
    except Exception as e:
        logger.error("Agent %s 执行异常: %s", agent_id, e, exc_info=True)
        try:
            async with SessionLocal() as db:
                agent = (
                    await db.execute(select(Agent).where(Agent.id == agent_id))
                ).scalar_one_or_none()
                if agent is not None:
                    agent.last_status = "error"
                    agent.last_output = f"⚠️ 执行异常: {e}"[:4000]
                    agent.next_run_at = compute_next_run(agent.schedule)
                    await db.commit()
        except Exception:
            logger.exception("Agent 失败态回写失败 %s", agent_id)


async def _scan_due() -> None:
    """扫描到点 Agent 并执行(串行, 避免并发写 vault 冲突)。"""
    from sqlalchemy import select

    from backend.db import SessionLocal
    from backend.models.agent import Agent

    # now 用 UTC(DB 里 next_run_at 是 UTC 存储)
    now = datetime.now(timezone.utc)
    try:
        async with SessionLocal() as db:
            due = (
                await db.execute(
                    select(Agent).where(
                        Agent.status == "active",
                        Agent.next_run_at.is_(None)
                        | (Agent.next_run_at <= now),
                    )
                )
            ).scalars().all()
            ids = [a.id for a in due]
    except Exception as e:
        logger.error("扫描 due agents 失败: %s", e)
        return

    for aid in ids:
        # 新建 Agent 首次调度: 先算 next_run_at 再执行
        try:
            async with SessionLocal() as db:
                from sqlalchemy import select

                from backend.models.agent import Agent

                agent = (
                    await db.execute(select(Agent).where(Agent.id == aid))
                ).scalar_one_or_none()
                if agent is None:
                    continue
                if agent.next_run_at is None:
                    agent.next_run_at = compute_next_run(agent.schedule)
                    await db.commit()
        except Exception:
            logger.exception("初始化 next_run_at 失败 %s", aid)
        await _run_agent_once(aid)


async def _scan_loop() -> None:
    """后台循环: 每 60s 扫描一次。"""
    while True:
        try:
            await _scan_due()
        except Exception:
            logger.exception("调度扫描异常")
        await asyncio.sleep(_scan_interval)


def start_scheduler() -> None:
    """FastAPI lifespan 调用: 启动后台扫描循环。"""
    global _scheduler
    if _scheduler is not None:
        return
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _scan_loop,
        "interval",
        seconds=_scan_interval,
        id="agent-scan",
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    _scheduler = scheduler
    logger.info("平台 Agent 调度器已启动(每 %ds 扫描)", _scan_interval)


def stop_scheduler() -> None:
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=False)
        _scheduler = None
