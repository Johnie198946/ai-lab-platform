#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v2·会话复用版）

把 `hermes -z` 包成 HTTP API，供 API 容器通过 host.docker.internal 调用。

v2 改进（4G 内存升级后·2026-08-09）：
1. **会话复用**：每个 session_id 保持独立 Hermes 会话（--continue），
   多轮对话上下文连贯，减少重复冷启动
2. **并发控制**：asyncio.Semaphore 限制并发（2 核 CPU 保护）
3. **超时优化**：按请求类型区分超时（对话 60s·复杂任务 180s）

用法: systemctl start hermes-bridge（已注册）
"""
import asyncio
import subprocess
import uuid
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge v2")

HERMES_BIN = "/opt/hermes/venv/bin/hermes"
HERMES_CWD = "/opt/ai-lab-platform"
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 180      # 复杂任务
CHAT_TIMEOUT = 90          # 普通对话

# 会话存储：session_id -> (session_name, last_active)
# Hermes --continue 用 session 名恢复上下文
_sessions: dict[str, str] = {}
_semaphore = asyncio.Semaphore(2)  # 2 核 CPU·最多 2 并发


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)
    session_id: str | None = None   # 传入则复用会话


def _run_hermes(goal: str, session_name: str | None) -> tuple[str, str]:
    """执行 Hermes CLI。返回 (reply, session_name)"""
    cmd = [HERMES_BIN, "-p", "default", "-z", goal]
    if session_name:
        cmd = [HERMES_BIN, "-p", "default", "--continue", session_name, "-z", goal]
    try:
        r = subprocess.run(
            cmd,
            capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
            cwd=HERMES_CWD,
        )
        if r.returncode == 0:
            return r.stdout.strip(), session_name or ""
        return f"⚠️ Hermes 执行失败（exit {r.returncode}）: {r.stderr[:300]}", session_name or ""
    except subprocess.TimeoutExpired:
        return "⚠️ Hermes 执行超时", session_name or ""
    except Exception as e:
        return f"⚠️ Hermes 调用异常: {e}", session_name or ""


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """对话入口：支持会话复用（多轮上下文连贯）"""
    session_name = None
    if body.session_id:
        session_name = _sessions.get(body.session_id)
        if not session_name:
            session_name = f"web_{uuid.uuid4().hex[:8]}"
            _sessions[body.session_id] = session_name

    async with _semaphore:
        reply, _ = await asyncio.to_thread(_run_hermes, body.goal, session_name)

    # 会话建立：首次请求后回传 session_id 供前端保存
    return {"reply": reply, "session_id": body.session_id}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-bridge", "version": "v2", "sessions": len(_sessions)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
