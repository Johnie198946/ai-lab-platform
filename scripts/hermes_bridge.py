#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（方案 C2）

把 `hermes -p default -z "<goal>"` 包成 HTTP API，供 API 容器
通过 host.docker.internal 调用。解决"容器内无法执行宿主机 venv Hermes"
的依赖链问题（宿主机 Hermes 本身 100% 可用）。

用法: nohup python3 hermes_bridge.py &   （监听 0.0.0.0:9118）
"""
import asyncio
import subprocess
from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge")

HERMES_BIN = "/opt/hermes/venv/bin/hermes"
HERMES_CWD = "/opt/ai-lab-platform"
MAX_INPUT = 4000
TIMEOUT = 120


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)


def _run_hermes(goal: str) -> str:
    """同步执行 Hermes CLI（子进程隔离，宿主机 Python 3.11 环境完整）"""
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]
    try:
        r = subprocess.run(
            [HERMES_BIN, "-p", "default", "-z", goal],
            capture_output=True, text=True, timeout=TIMEOUT,
            cwd=HERMES_CWD,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return f"⚠️ Hermes 执行失败（exit {r.returncode}）: {r.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return "⚠️ Hermes 执行超时（>120s）"
    except Exception as e:
        return f"⚠️ Hermes 调用异常: {e}"


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """编排平台对话入口：goal → Hermes main 执行 → 返回文本"""
    reply = await asyncio.to_thread(_run_hermes, body.goal)
    return {"reply": reply}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-bridge"}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
