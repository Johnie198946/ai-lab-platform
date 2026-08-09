#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v4·原生会话版）

把 `hermes -z` 包成 HTTP API，供 API 容器通过 host.docker.internal 调用。

v4 (2026-08-10·Route C 实施·监督批复):
- 彻底删除 _session_history 字典与【对话历史】手动文本拼接（零文本处理）
- 引入 user_id -> hermes_session_id 显式绑定 + 存在性断言
- 首次对话：hermes -z 创建原生 Session，从 state.db 捕获 Session ID 建立映射
- 后续对话：精准 hermes -r <session_id> 恢复（严禁裸 --continue 防 fallback 污染）
- 持久化：依托 Hermes 原生 state.db；user→session 映射用 JSON 文件（支持重启恢复）

用法: systemctl start hermes-bridge
"""
import asyncio
import json
import os
import sqlite3
import subprocess
from pathlib import Path

from fastapi import FastAPI
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge v4")

HERMES_BIN = "/opt/hermes/venv/bin/hermes"
HERMES_CWD = "/opt/ai-lab-platform"
STATE_DB = "/root/.hermes/state.db"
MAPPING_FILE = Path("/opt/ai-lab-platform/data/session_mapping.json")
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 180

# user_id -> hermes_session_id 显式绑定（内存缓存 + JSON 持久化）
_user_session_map: dict[str, str] = {}
_semaphore = asyncio.Semaphore(2)


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)
    session_id: str | None = None  # 前端传入的 user_id（用于映射 Hermes 原生 session）
    isolation: str = Field("standard", description="向后兼容·子Agent工厂使用")


# ---------- 映射持久化 ----------

def _load_mapping() -> None:
    global _user_session_map
    if MAPPING_FILE.exists():
        try:
            _user_session_map = json.loads(MAPPING_FILE.read_text())
        except Exception:
            _user_session_map = {}


def _save_mapping() -> None:
    try:
        MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
        MAPPING_FILE.write_text(json.dumps(_user_session_map, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"[bridge] 保存映射失败: {e}")


# ---------- Hermes 原生 Session 存在性断言 ----------

def _session_exists(session_id: str) -> bool:
    """查询 Hermes state.db 确认 session 真实存在（防 --resume fallback 污染）。"""
    if not os.path.exists(STATE_DB):
        return False
    try:
        conn = sqlite3.connect(STATE_DB)
        try:
            cur = conn.execute(
                "SELECT 1 FROM sessions WHERE id=? AND archived=0 LIMIT 1",
                (session_id,),
            )
            return cur.fetchone() is not None
        finally:
            conn.close()
    except Exception as e:
        print(f"[bridge] state.db 查询失败: {e}")
        return False


def _get_latest_session_id() -> str | None:
    """获取 state.db 中最新创建的 session ID（用于首次对话后捕获）。"""
    if not os.path.exists(STATE_DB):
        return None
    try:
        conn = sqlite3.connect(STATE_DB)
        try:
            cur = conn.execute(
                "SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1"
            )
            row = cur.fetchone()
            return row[0] if row else None
        finally:
            conn.close()
    except Exception as e:
        print(f"[bridge] 获取最新 session 失败: {e}")
        return None


# ---------- Hermes CLI 调用 ----------

def _run_hermes(goal: str, session_id: str | None = None) -> str:
    """执行 Hermes CLI。session_id 存在时用 -r 精准恢复；否则新建。"""
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]

    cmd = [HERMES_BIN, "-p", "default"]
    if session_id:
        cmd += ["-r", session_id]  # 精准恢复·严禁裸 --continue
    cmd += ["-z", goal]

    env = os.environ.copy()
    env["HERMES_ACCEPT_HOOKS"] = "1"

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
            cwd=HERMES_CWD, env=env,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return f"⚠️ Hermes 执行失败（exit {r.returncode}）: {r.stderr[:300]}"
    except subprocess.TimeoutExpired:
        return "⚠️ Hermes 执行超时"
    except Exception as e:
        return f"⚠️ Hermes 调用异常: {e}"


# ---------- 会话入口 ----------

@app.on_event("startup")
async def _startup():
    _load_mapping()
    print(f"[bridge] v4 启动·已加载 {len(_user_session_map)} 条 user→session 映射")


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """对话入口：基于 user_id 的 Hermes 原生会话。"""
    user_id = body.session_id or "anonymous"

    hermes_sid = _user_session_map.get(user_id)

    # 存在性断言：映射存在但 state.db 中无此 session → 丢弃映射·新建
    if hermes_sid and not _session_exists(hermes_sid):
        print(f"[bridge] user {user_id} 的 session {hermes_sid} 已失效·重建")
        hermes_sid = None
        _user_session_map.pop(user_id, None)

    # 首次对话：执行 -z → 从 state.db 捕获最新 session ID → 建立映射
    if not hermes_sid:
        reply = await asyncio.to_thread(_run_hermes, body.goal, None)
        new_sid = await asyncio.to_thread(_get_latest_session_id)
        if new_sid:
            _user_session_map[user_id] = new_sid
            _save_mapping()
            print(f"[bridge] 新建会话: user={user_id} -> session={new_sid}")
        return {"reply": reply, "session_id": user_id, "hermes_session_id": new_sid}

    # 后续对话：精准恢复原生 Session（已断言存在·杜绝 fallback 污染）
    reply = await asyncio.to_thread(_run_hermes, body.goal, hermes_sid)
    return {"reply": reply, "session_id": user_id, "hermes_session_id": hermes_sid}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "hermes-bridge",
        "version": "v4",
        "sessions": len(_user_session_map),
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
