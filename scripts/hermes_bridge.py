#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v5.0·SSE 流式版）

把 `hermes serve` (SSE 流式) 和 `hermes -z` (非流式降级) 包成 HTTP API，
供 API 容器通过 host.docker.internal 调用。

v5.0 (2026-08-10·SSE 流式改造):
- 新增 /v1/chat/stream 端点：对接 hermes serve SSE 流式·逐 chunk 转发
- hermes serve 认证：Bearer Token（环境变量 HERMES_SERVE_TOKEN·不入 git）
- 会话映射沿用 v4（user_id → hermes session_id）
- 保留 /v1/chat 非流式向后兼容
- 失败自动降级：serve 不可用时 fallback 到 CLI -z 非流式

v4.1 (2026-08-10·Supervision 批复返工):
- 修正 CLI 参数：-r → --resume（精准恢复会话）
- STATE_DB 动态路径：Path.home()/.hermes/state.db 或 env HERMES_STATE_DB
- 并发安全：使用 --usage-file 原子捕获 session_id
- 严格断言：_session_exists 为 False 时清除映射·按新建处理

用法: systemctl start hermes-bridge
"""
import asyncio
import json
import os
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge v5.0")

HERMES_BIN = os.environ.get("HERMES_BIN", "/opt/hermes/venv/bin/hermes")
HERMES_CWD = os.environ.get("HERMES_CWD", "/opt/ai-lab-platform")
# hermes serve 地址（本机回环·不暴露公网）
HERMES_SERVE_URL = os.environ.get("HERMES_SERVE_URL", "http://127.0.0.1:9119")
# hermes serve 认证 Token（环境变量·严禁入 git）
HERMES_SERVE_TOKEN = os.environ.get("HERMES_SERVE_TOKEN", "")
# 动态路径：优先环境变量，否则 Path.home()/.hermes/state.db
STATE_DB = os.environ.get(
    "HERMES_STATE_DB",
    str(Path.home() / ".hermes" / "state.db")
)
MAPPING_FILE = Path("/opt/ai-lab-platform/data/session_mapping.json")
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 180
SERVE_TIMEOUT = 300

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
        data = json.dumps(_user_session_map, ensure_ascii=False, indent=2)
        MAPPING_FILE.write_text(data)
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


# ---------- Hermes CLI 调用 ----------

def _run_hermes(goal: str, session_id: str | None = None) -> tuple[str, str | None]:
    """执行 Hermes CLI。

    返回 (reply, hermes_session_id)。
    - session_id 存在且通过断言时用 --resume 精准恢复
    - session_id=None 时新建会话
    - 使用 --usage-file 原子捕获新建会话的 session_id（并发安全）
    """
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]

    cmd = [HERMES_BIN, "-p", "default"]
    if session_id:
        # 精准恢复·已断言存在·杜绝 fallback 污染
        cmd += ["--resume", session_id]

    # --usage-file: 原子捕获 session_id（并发安全）
    usage_file = Path(tempfile.gettempdir()) / f"hermes_usage_{uuid.uuid4().hex}.json"
    cmd += ["--usage-file", str(usage_file), "-z", goal]

    env = os.environ.copy()
    env["HERMES_ACCEPT_HOOKS"] = "1"

    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=DEFAULT_TIMEOUT,
            cwd=HERMES_CWD, env=env,
        )
        reply = r.stdout.strip() if r.returncode == 0 else (
            f"⚠️ Hermes 执行失败（exit {r.returncode}）: {r.stderr[:300]}"
        )
    except subprocess.TimeoutExpired:
        reply = "⚠️ Hermes 执行超时"
    except Exception as e:
        reply = f"⚠️ Hermes 调用异常: {e}"

    # 从 --usage-file 提取 session_id（原子捕获·并发安全）
    hermes_sid = _extract_session_from_usage(usage_file)
    return reply, hermes_sid


def _extract_session_from_usage(usage_file: Path) -> str | None:
    """从 --usage-file JSON 中提取 session_id，读取后删除临时文件。"""
    try:
        if usage_file.exists():
            data = json.loads(usage_file.read_text())
            return data.get("session_id")
    except Exception as e:
        print(f"[bridge] 读取 usage-file 失败: {e}")
    finally:
        try:
            usage_file.unlink(missing_ok=True)
        except Exception:
            pass
    return None


# ---------- 会话管理辅助 ----------

def _resolve_hermes_session(user_id: str) -> str | None:
    """解析 user_id 对应的 hermes session_id（存在性断言·失效则清除）。"""
    hermes_sid = _user_session_map.get(user_id)
    if hermes_sid and not _session_exists(hermes_sid):
        print(f"[bridge] user {user_id} session {hermes_sid} 已失效·清除映射·新建")
        _user_session_map.pop(user_id, None)
        _save_mapping()
        hermes_sid = None
    return hermes_sid


def _update_session_mapping(user_id: str, hermes_sid: str) -> None:
    """更新 user_id → hermes session_id 映射并持久化。"""
    _user_session_map[user_id] = hermes_sid
    _save_mapping()
    print(f"[bridge] 会话映射: user={user_id} -> session={hermes_sid}")


# ---------- hermes serve SSE 流式调用 ----------

async def _stream_from_serve(goal: str, session_id: str | None = None):
    """对接 hermes serve SSE 流式端点·逐 chunk 转发。
    
    返回异步生成器·产出 SSE 格式字符串（data: {...}\n\n）。
    失败时抛出异常·由调用方降级处理。
    """
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]

    # 构造 hermes serve 请求
    headers = {"Content-Type": "application/json"}
    if HERMES_SERVE_TOKEN:
        headers["Authorization"] = f"Bearer {HERMES_SERVE_TOKEN}"

    payload = {
        "message": goal,
        "stream": True,
    }
    if session_id:
        payload["session_id"] = session_id

    # 连接 hermes serve（SSE 流式）
    async with httpx.AsyncClient(timeout=SERVE_TIMEOUT) as client:
        async with client.stream(
            "POST",
            f"{HERMES_SERVE_URL}/api/chat",
            json=payload,
            headers=headers,
        ) as response:
            if response.status_code != 200:
                raise RuntimeError(f"hermes serve 返回 {response.status_code}")

            # 逐行读取 SSE 流
            async for line in response.aiter_lines():
                if not line:
                    continue
                # SSE 格式：data: {...}
                if line.startswith("data: "):
                    data_str = line[6:]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        # 转发给前端（保持 SSE 格式）
                        yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                    except json.JSONDecodeError:
                        # 非 JSON 行·原样转发
                        yield f"data: {data_str}\n\n"


# ---------- 会话入口 ----------

@app.on_event("startup")
async def _startup():
    _load_mapping()
    print(f"[bridge] v5 启动·已加载 {len(_user_session_map)} 条 user→session 映射")
    if not HERMES_SERVE_TOKEN:
        print("[bridge] ⚠️ 警告: HERMES_SERVE_TOKEN 未设置·serve 认证可能失败")


@app.post("/v1/chat/stream")
async def chat_stream(body: GoalRequest):
    """SSE 流式对话入口（Bridge v5 核心端点）。
    
    对接 hermes serve SSE 流式·逐 chunk 转发。
    失败时自动降级到 /v1/chat 非流式。
    """
    user_id = body.session_id or "anonymous"
    hermes_sid = _resolve_hermes_session(user_id)

    # 尝试 SSE 流式
    try:
        # 首次对话：先通过 CLI 新建会话·捕获 session_id
        if not hermes_sid:
            print(f"[bridge] 首次对话·先通过 CLI 新建会话")
            reply, new_sid = await asyncio.to_thread(_run_hermes, body.goal, None)
            if new_sid:
                _update_session_mapping(user_id, new_sid)
                hermes_sid = new_sid
            else:
                # CLI 新建失败·直接返回非流式结果
                return {"reply": reply, "session_id": user_id, "hermes_session_id": None, "streamed": False}

        # 后续对话：SSE 流式
        print(f"[bridge] SSE 流式: user={user_id} session={hermes_sid}")
        return StreamingResponse(
            _stream_from_serve(body.goal, hermes_sid),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # nginx 禁用缓冲
            },
        )

    except Exception as e:
        # 流式失败·降级到非流式
        print(f"[bridge] SSE 流式失败·降级到非流式: {e}")
        reply, _ = await asyncio.to_thread(_run_hermes, body.goal, hermes_sid)
        return {"reply": reply, "session_id": user_id, "hermes_session_id": hermes_sid, "streamed": False}


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """非流式对话入口（向后兼容·Agent 工厂/子代理使用）。"""
    user_id = body.session_id or "anonymous"
    hermes_sid = _resolve_hermes_session(user_id)

    # 首次对话或映射失效：执行 -z 新建会话
    if not hermes_sid:
        reply, new_sid = await asyncio.to_thread(_run_hermes, body.goal, None)
        if new_sid:
            _update_session_mapping(user_id, new_sid)
        return {"reply": reply, "session_id": user_id, "hermes_session_id": new_sid}

    # 后续对话：精准恢复原生 Session
    reply, _ = await asyncio.to_thread(_run_hermes, body.goal, hermes_sid)
    return {"reply": reply, "session_id": user_id, "hermes_session_id": hermes_sid}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "hermes-bridge",
        "version": "v5.0",
        "sessions": len(_user_session_map),
        "streaming": True,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
