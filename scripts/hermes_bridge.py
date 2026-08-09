#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v2·会话复用版）

把 `hermes -z` 包成 HTTP API，供 API 容器通过 host.docker.internal 调用。

v2 改进（4G 内存升级后·2026-08-09）：
1. **会话复用**：每个 session_id 保持独立 Hermes 会话（--continue），
   多轮对话上下文连贯，减少重复冷启动
2. **并发控制**：asyncio.Semaphore 限制并发（2 核 CPU 保护）
3. **超时优化**：按请求类型区分超时（对话 90s·复杂任务 600s）

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
# 2026-08-09: 复杂任务 180s → 600s — 子 Agent 定时执行(采集+wiki编译)需更长
DEFAULT_TIMEOUT = 600      # 复杂任务（Agent 定时执行/长研究）
CHAT_TIMEOUT = 90          # 普通对话

# 会话存储：session_id -> (session_name, last_active)
# Hermes --continue 用 session 名恢复上下文
_sessions: dict[str, str] = {}
_semaphore = asyncio.Semaphore(2)  # 2 核 CPU·最多 2 并发


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)
    session_id: str | None = None   # 传入则复用会话
    isolation: str = Field("standard", pattern="^(pure|standard|kb)$")
    # pure: 纯净沙箱(新 Agent 默认) — 无记忆/无技能/无规则/工具集收窄
    # standard: 标准模式(老 Agent 兼容) — 全量上下文
    # kb: 知识库模式 — 纯净 + 显式 RAG 检索工具


# 隔离模式 → CLI 参数映射 (Supervision 批复意见 1/2·main 修订一)
ISOLATION_ARGS: dict[str, list[str]] = {
    "pure": [
        "--ignore-user-config",
        "--ignore-rules",
        "--safe-mode",
        "-t", "core,web",
    ],
    "kb": [
        "--ignore-user-config",
        "--ignore-rules",
        "-t", "core,web,memory",
    ],
    "standard": [],
}


def _run_hermes(goal: str, session_name: str | None, isolation: str = "standard") -> tuple[str, str]:
    """执行 Hermes CLI。返回 (reply, session_name)

    v2.2 (2026-08-09): 会话隔离加固 —— 全部用纯 -z 新会话, 彻底禁用 --continue。

    根因: 服务器有 hermes serve(9119) + 云端子 Agent 并发会话。实测
    `--continue web_xxx` 在会话不存在时 fallback 到最近会话, 导致
    web 洞察请求返回其他会话的"验证"内容(上下文污染)。

    方案: 多轮上下文由 orchestration.py 的 _build_multi_turn_prompt
    拼进 prompt(已在做), bridge 不再 --continue。每请求 = 全新
    Hermes 进程 = 进程级隔离, 零串扰。代价: 每轮冷启动(~10s), 可接受。

    v2.3 (2026-08-09): 纯净沙箱 — 按 isolation 参数注入隔离 CLI 参数。
    pure: --ignore-user-config --ignore-rules --safe-mode -t core,web
    kb:   --ignore-user-config --ignore-rules -t core,web,memory
    standard: 无隔离参数(向后兼容)
    """
    cmd = [HERMES_BIN, "-p", "default"]
    cmd.extend(ISOLATION_ARGS.get(isolation, []))
    cmd.extend(["-z", goal])
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
    """对话入口：支持会话复用（多轮上下文连贯）+ 隔离模式"""
    session_name = None
    if body.session_id:
        session_name = _sessions.get(body.session_id)
        if not session_name:
            session_name = f"web_{uuid.uuid4().hex[:8]}"
            _sessions[body.session_id] = session_name

    async with _semaphore:
        reply, _ = await asyncio.to_thread(_run_hermes, body.goal, session_name, body.isolation)

    # 会话建立：首次请求后回传 session_id 供前端保存
    return {"reply": reply, "session_id": body.session_id, "isolation": body.isolation}


@app.get("/health")
async def health():
    return {"status": "ok", "service": "hermes-bridge", "version": "v2", "sessions": len(_sessions)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
