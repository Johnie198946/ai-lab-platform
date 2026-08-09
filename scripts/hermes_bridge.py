#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v3·极简版）

把 `hermes -z` 包成 HTTP API，供 API 容器通过 host.docker.internal 调用。

v3 (2026-08-09·用户拍板)：编排平台只调 Hermes·不做内部管理。
- bridge 负责注入多轮上下文（session_id 有历史时自动拼接）
- 去掉 isolation 控制（编排对话用 Hermes 完整能力）
- 去掉 --continue（进程隔离·防串扰）
- 保持 isolation 参数向后兼容（子 Agent 工厂仍用）

用法: systemctl start hermes-bridge
"""
import asyncio
import subprocess
from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge v3")

HERMES_BIN = "/opt/hermes/venv/bin/hermes"
HERMES_CWD = "/opt/ai-lab-platform"
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 180
MAX_HISTORY_TURNS = 5  # 最多传最近 5 轮对话

# 会话历史存储
_session_history: dict[str, list[tuple[str, str]]] = {}
_semaphore = asyncio.Semaphore(2)


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)
    session_id: str | None = None
    isolation: str = Field("standard", description="向后兼容·子Agent工厂使用")


def _run_hermes(goal: str) -> str:
    """执行 Hermes CLI（每次新进程·进程级隔离）。"""
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]
    try:
        r = subprocess.run(
            [HERMES_BIN, "-p", "default", "-z", goal],
            capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
            cwd=HERMES_CWD,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return f"⚠️ Hermes 执行失败（exit {r.returncode}）: {r.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return "⚠️ Hermes 执行超时"
    except Exception as e:
        return f"⚠️ Hermes 调用异常: {e}"


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """对话入口：自动注入多轮上下文。"""
    goal = body.goal

    # 注入对话历史（session_id 存在且有历史）
    if body.session_id and body.session_id in _session_history:
        history = _session_history[body.session_id][-MAX_HISTORY_TURNS:]
        lines = ["【对话历史】"]
        for g, r in history:
            lines.append(f"用户: {g}")
            lines.append(f"助手: {r}")
        lines.append(f"\n【当前问题】\n{goal}")
        goal = "\n".join(lines)

    async with _semaphore:
        reply = await asyncio.to_thread(_run_hermes, goal)

    # 存储本轮对话
    if body.session_id:
        history = _session_history.setdefault(body.session_id, [])
        history.append((body.goal, reply))
        # 限制历史长度
        if len(history) > 20:
            history = history[-20:]
            _session_history[body.session_id] = history

    return {"reply": reply, "session_id": body.session_id}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-bridge", "version": "v3", "sessions": len(_session_history)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
