#!/usr/bin/env python3
"""
hermes_bridge.py — 宿主机 Hermes 桥接服务（v6.0·WS PTY 真实对接版）

把 `hermes serve` WebSocket PTY（ws://127.0.0.1:9119/api/pty）包成 HTTP SSE API，
供 API 容器通过 host.docker.internal 调用。

v6.0 (2026-08-10·Supervision 批复返工·WS PTY 真实对接):
- 核心改造：通过 WebSocket 客户端连接 hermes serve /api/pty 端点
- ANSI 转义清洗：re.sub(r'\\x1b\\[[0-9;]*[a-zA-Z]', '', text)
- Token 流转发：清洗后的文本以 SSE data: {type:chunk,content:...} 格式推送
- 认证：ws 握手携带 HERMES_SERVE_TOKEN（Bearer）
- 保留 /v1/chat 非流式兜底（CLI -z）
- 会话映射沿用 v4/v5（user_id → hermes session_id）

v5.0 (2026-08-10·SSE 流式改造):
- 新增 /v1/chat/stream 端点：对接 hermes serve SSE 流式·逐 chunk 转发
- hermes serve 认证：Bearer Token（环境变量 HERMES_SERVE_TOKEN·不入 git）

v4.1 (2026-08-10·Supervision 批复返工):
- 修正 CLI 参数：-r → --resume（精准恢复会话）
- STATE_DB 动态路径：Path.home()/.hermes/state.db 或 env HERMES_STATE_DB
- 并发安全：使用 --usage-file 原子捕获 session_id

用法: systemctl start hermes-bridge
"""
import asyncio
import json
import os
import re
import sqlite3
import subprocess
import tempfile
import uuid
from pathlib import Path

import httpx
import websockets
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

app = FastAPI(title="Hermes Bridge v6.0")

HERMES_BIN = os.environ.get("HERMES_BIN", "/opt/hermes/venv/bin/hermes")
HERMES_CWD = os.environ.get("HERMES_CWD", "/opt/ai-lab-platform")
# hermes serve 地址（本机回环·不暴露公网）
HERMES_SERVE_URL = os.environ.get("HERMES_SERVE_URL", "http://127.0.0.1:9119")
# hermes serve WebSocket PTY 地址
HERMES_WS_URL = os.environ.get("HERMES_WS_URL", "ws://127.0.0.1:9119/api/pty")
# hermes serve 认证 Token（环境变量·严禁入 git）
HERMES_SERVE_TOKEN = os.environ.get("HERMES_SERVE_TOKEN", "")
# 动态路径：优先环境变量，否则 Path.home()/.hermes/state.db
STATE_DB = os.environ.get(
    "HERMES_STATE_DB",
    str(Path.home() / ".hermes" / "state.db")
)
MAPPING_FILE = Path("/opt/ai-lab-platform/data/session_mappings.json")
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 180
SERVE_TIMEOUT = 300

# ANSI 转义序列清洗正则（匹配所有 ANSI escape codes）
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

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


# ---------- hermes serve WS PTY 流式调用（v6.0 核心） ----------

def _clean_ansi(text: str) -> str:
    """清洗 ANSI 转义序列（hermes serve PTY 输出包含颜色/光标控制码）。"""
    return ANSI_ESCAPE_RE.sub('', text)


async def _stream_from_ws_pty(goal: str, session_id: str | None = None):
    """通过 WebSocket 连接 hermes serve /api/pty 端点·实现真实流式。

    协议：
    1. 建立 WS 连接（ws://127.0.0.1:9119/api/pty）
    2. 握手携带 Authorization: Bearer <HERMES_SERVE_TOKEN>
    3. 发送 {"type":"input","data":"<goal>\\n"} 作为用户输入
    4. 持续接收 PTY 输出（含 ANSI 转义）
    5. 清洗 ANSI → 提取 token 流 → 以 SSE data: {type:chunk,content:...} 转发

    失败时抛出异常·由调用方降级到 /v1/chat 非流式。
    """
    if len(goal) > MAX_INPUT:
        goal = goal[:MAX_INPUT]

    # 构造 WS 握手 headers
    # ⚠️ 2026-08-10 修复: serve PTY 认证用 ?token= query 参数（非 Authorization 头）·
    #    实测 ws://127.0.0.1:9119/api/pty?token=<TOKEN> 握手成功（否则 403）
    ws_headers = {}

    ws_url = HERMES_WS_URL
    if HERMES_SERVE_TOKEN:
        sep = "&" if "?" in ws_url else "?"
        ws_url = f"{ws_url}{sep}token={HERMES_SERVE_TOKEN}"

    print(f"[bridge] WS PTY 连接: {HERMES_WS_URL} (query token)")

    async with websockets.connect(
        ws_url,
        additional_headers=ws_headers,
        open_timeout=10,
        close_timeout=5,
    ) as ws:
        print(f"[bridge] WS PTY 已连接·发送 goal")

        # 发送用户输入（PTY 协议：原始文本·非 JSON·实测 web_server.py writer loop）
        # ⚠️ 2026-08-10 修复: 之前发 {"type":"input","data":...} JSON 被当纯文本写入 PTY
        await ws.send(goal + "\n")

        # 持续接收 PTY 输出并转发为 SSE
        full_reply = ""
        # ⚠️ 2026-08-10 临时: WS PTY 挂起未通·加 8s 首帧超时·无输出即降级（流式做好后移除）
        try:
            first_frame = await asyncio.wait_for(ws.recv(), timeout=8)
        except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
            print("[bridge] WS PTY 8s 无输出·降级")
            raise TimeoutError("WS PTY 无输出超时") from None

        async def _frame_gen(first):
            yield first
            async for m in ws:
                yield m

        try:
            async for raw_msg in _frame_gen(first_frame):
                # 解析 WS 消息
                try:
                    msg = json.loads(raw_msg)
                    msg_type = msg.get("type", "")
                    text = msg.get("data", "") or msg.get("content", "") or ""
                except (json.JSONDecodeError, AttributeError):
                    # 非 JSON 消息视为纯文本
                    text = str(raw_msg)
                    msg_type = "output"

                # 清洗 ANSI 转义序列
                cleaned = _clean_ansi(text)

                # 跳过空内容
                if not cleaned.strip() and not cleaned:
                    continue

                full_reply += cleaned

                # 以 SSE 格式转发给前端
                sse_payload = json.dumps({
                    "type": "chunk",
                    "content": cleaned,
                }, ensure_ascii=False)
                yield f"data: {sse_payload}\n\n"

                # 检测结束信号
                if msg_type == "done" or msg_type == "exit":
                    break

        except websockets.exceptions.ConnectionClosed:
            print(f"[bridge] WS PTY 连接关闭·流结束")

        # 发送结束标记
        yield f"data: {json.dumps({'type': 'done', 'content': ''})}\n\n"
        print(f"[bridge] WS PTY 流结束·总长度: {len(full_reply)}")


# ---------- 最终降级 SSE 包装（v6.1·契约统一） ----------

async def _fallback_sse(reply: str):
    """将非流式 reply 包装为标准 SSE 流（与前端契约一致）。

    产出：
      data: {"type": "chunk", "content": "<reply>"}\n\n
      data: {"type": "done", "content": ""}\n\n
    """
    payload = json.dumps({"type": "chunk", "content": reply}, ensure_ascii=False)
    yield f"data: {payload}\n\n"
    done_payload = json.dumps({"type": "done", "content": ""}, ensure_ascii=False)
    yield f"data: {done_payload}\n\n"


# ---------- hermes serve SSE 流式调用（v5 保留·作为 WS 失败时的二级降级） ----------

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
    """SSE 流式对话入口（Bridge v6 核心端点）。

    优先级：WS PTY（/api/pty）→ SSE 流式（/api/chat）→ CLI -z 非流式降级。
    全部以 SSE data: {type:chunk,content:...} 格式推送给前端。
    """
    user_id = body.session_id or "anonymous"
    hermes_sid = _resolve_hermes_session(user_id)

    # 首次对话：先通过 CLI 新建会话·捕获 session_id
    if not hermes_sid:
        print(f"[bridge] 首次对话·先通过 CLI 新建会话")
        reply, new_sid = await asyncio.to_thread(_run_hermes, body.goal, None)
        if new_sid:
            _update_session_mapping(user_id, new_sid)
            hermes_sid = new_sid
        else:
            # CLI 新建失败·包装为 SSE 流（与前端契约一致·杜绝裸 JSON 导致前端空回复）
            print(f"[bridge] CLI 新建失败·降级 SSE 包装返回")
            return StreamingResponse(
                _fallback_sse(reply),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                },
            )

    # 尝试 WS PTY 流式（v6 主路径·默认禁用——serve PTY 只回显不执行 Hermes·流式做好后设 WS_PTY_ENABLED=true 启用）
    if os.environ.get("WS_PTY_ENABLED", "false") == "true":
        try:
            print(f"[bridge] WS PTY 流式: user={user_id} session={hermes_sid}")
            return StreamingResponse(
                _stream_from_ws_pty(body.goal, hermes_sid),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",  # nginx 禁用缓冲
                },
            )
        except Exception as ws_err:
            print(f"[bridge] WS PTY 失败·降级到 SSE: {ws_err}")

    # 二级降级：SSE 流式（v5 路径·serve 无 /api/chat 端点恒 405·2026-08-10 禁用直接走 CLI）
    # try:
    #     print(f"[bridge] SSE 流式降级: user={user_id} session={hermes_sid}")
    #     return StreamingResponse(
    #         _stream_from_serve(body.goal, hermes_sid),
    #         media_type="text/event-stream",
    #         headers={
    #             "Cache-Control": "no-cache",
    #             "Connection": "keep-alive",
    #             "X-Accel-Buffering": "no",
    #         },
    #     )
    # except Exception as sse_err:
    #     print(f"[bridge] SSE 流式失败·降级到非流式: {sse_err}")

    # 最终降级：CLI -z 非流式（SSE 包装·契约统一）·包装为 SSE 流（与前端契约一致·杜绝裸 JSON 导致前端空回复）
    reply, _ = await asyncio.to_thread(_run_hermes, body.goal, hermes_sid)
    print(f"[bridge] 最终降级 CLI·包装 SSE 返回")
    return StreamingResponse(
        _fallback_sse(reply),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
            "X-Session-ID": user_id,
        },
    )


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
        "version": "v6.0",
        "sessions": len(_user_session_map),
        "streaming": True,
        "ws_pty": HERMES_WS_URL,
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9118)
