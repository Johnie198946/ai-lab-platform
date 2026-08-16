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
import queue
import re
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# 保证仓库根在 sys.path：桥接服务独立运行时（systemd / uvicorn 直跑 scripts/）
# 也能导入 backend 包（reasoning_extractor）。websockets 改为懒加载（WS PTY 默认禁用）。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from backend.services.reasoning_extractor import extract_steps  # noqa: E402

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
# 消费水位线持久化文件（user_id -> 已投递最大消息 id），供断点 0ms 回读判定
WATERMARK_FILE = Path(
    os.environ.get(
        "HERMES_WATERMARK_FILE",
        "/opt/ai-lab-platform/data/delivered_watermarks.json",
    )
)
MAX_INPUT = 4000
DEFAULT_TIMEOUT = 300
SERVE_TIMEOUT = 300
# 状态回读 stale 判定阈值（秒）：最新消息超过该阈值未更新即判 timeout
STATUS_STALE_SECONDS = 300

# ---------------------------------------------------------------------------
# v7 真实流式（进程内 agent runner）配置
# ---------------------------------------------------------------------------
# 进程内流式开关：true 时 /v1/chat/stream 走 AIAgent 进程内 runner（真实逐 token）
IN_PROCESS_STREAM_ENABLED = os.environ.get("HERMES_IN_PROCESS_STREAM", "false") == "true"
# SSE keepalive 注释帧间隔（对齐 Hermes CHAT_COMPLETIONS_SSE_KEEPALIVE_SECONDS=30.0）
STREAM_KEEPALIVE_SECONDS = float(os.environ.get("HERMES_STREAM_KEEPALIVE", "30"))
# 单次流式总时长上限（超时 → interrupt + error 帧）
STREAM_MAX_DURATION_SECONDS = int(os.environ.get("HERMES_STREAM_MAX_DURATION", "300"))
# clarify 等待用户响应超时（默认 180s，替代 Hermes 原生 3600s）
CLARIFY_TIMEOUT_SECONDS = int(os.environ.get("HERMES_CLARIFY_TIMEOUT", "180"))
# 事件队列容量（线程 → async 桥）
STREAM_QUEUE_CAPACITY = 512

# user_id -> 在途流式运行状态（agent holder / 线程 / 队列 / 停止事件），供 cancel/clarify 端点寻址
_stream_runs: dict[str, dict] = {}
_stream_runs_guard = threading.Lock()

# ANSI 转义序列清洗正则（匹配所有 ANSI escape codes）
ANSI_ESCAPE_RE = re.compile(r'\x1b\[[0-9;]*[a-zA-Z]')

# user_id -> hermes_session_id 显式绑定（内存缓存 + JSON 持久化）
_user_session_map: dict[str, str] = {}
# user_id -> 已投递最大消息 id（消费水位线，断点 0ms 回读判定）
_delivered_watermark: dict[str, int] = {}
# 全局并发信号量（两级锁序第一级）
_semaphore = asyncio.Semaphore(2)
# MAPPING_FILE 读写进程内全局锁（原子写防并发损坏）
_mapping_lock = threading.Lock()
# WATERMARK_FILE 读写进程内全局锁
_watermark_lock = threading.Lock()

# user_id -> asyncio.Lock 细粒度锁（两级锁序第二级），LRU 512 有界 + 30min 空闲 TTL
_user_locks: dict[str, asyncio.Lock] = {}
_user_lock_timestamps: dict[str, float] = {}
USER_LOCK_CAPACITY = 512
USER_LOCK_TTL_SECONDS = 30 * 60
ANONYMOUS_LOCK_KEY = "_anonymous"

# user_id -> 在途任务开始时间戳（首秒 running 状态兜底）。
# 请求进入 chat/chat_stream 协程第一瞬间登记，finally 块移除；即使 Hermes CLI
# 启动首秒内尚未向 state.db 落库，GET /v1/chat/status/{user_id} 也能立刻返回 running，
# 绝不误报 not_found。
_in_flight_users: dict[str, float] = {}
# 在途判定 stale 阈值（秒）：超过该阈值视为任务僵死，不再兜底 running。
IN_FLIGHT_STALE_SECONDS = 300


def _mark_in_flight(user_id: str) -> None:
    """登记 user 在途任务开始时间戳（进程内瞬时状态，finally 移除）。"""
    _in_flight_users[user_id] = time.time()


def _clear_in_flight(user_id: str) -> None:
    """移除 user 在途标记（任务结束/异常 finally 块调用）。"""
    _in_flight_users.pop(user_id, None)


def _is_in_flight(user_id: str | None) -> bool:
    """判定 user 是否有在途任务且未超时（首秒 running 兜底依据）。"""
    if not user_id:
        return False
    ts = _in_flight_users.get(user_id)
    if ts is None:
        return False
    return (time.time() - ts) <= IN_FLIGHT_STALE_SECONDS


def _get_user_lock(user_id: str) -> asyncio.Lock:
    """按 user_id 取细粒度锁；anonymous 统一固定 `_anonymous` key。

    LRU 512 上限 + 30 分钟空闲 TTL 惰性清理，杜绝锁对象无限堆积内存泄漏。
    """
    lock_key = user_id if user_id and user_id != "anonymous" else ANONYMOUS_LOCK_KEY
    now = time.monotonic()

    # 空闲 TTL 惰性清理
    stale = [
        k for k, ts in _user_lock_timestamps.items()
        if now - ts > USER_LOCK_TTL_SECONDS
    ]
    for k in stale:
        _user_locks.pop(k, None)
        _user_lock_timestamps.pop(k, None)

    lock = _user_locks.get(lock_key)
    if lock is None:
        # LRU 淘汰最久未使用
        if len(_user_locks) >= USER_LOCK_CAPACITY:
            oldest = min(_user_lock_timestamps.items(), key=lambda kv: kv[1])[0]
            _user_locks.pop(oldest, None)
            _user_lock_timestamps.pop(oldest, None)
        lock = asyncio.Lock()
        _user_locks[lock_key] = lock
    _user_lock_timestamps[lock_key] = now
    return lock


class GoalRequest(BaseModel):
    goal: str = Field(..., max_length=MAX_INPUT)
    session_id: str | None = None  # 前端传入的 user_id（用于映射 Hermes 原生 session）
    isolation: str = Field("standard", description="向后兼容·子Agent工厂使用")


# ---------- 映射持久化 ----------

def _load_mapping() -> None:
    global _user_session_map
    with _mapping_lock:
        if MAPPING_FILE.exists():
            try:
                _user_session_map = json.loads(MAPPING_FILE.read_text())
            except Exception:
                _user_session_map = {}


def _save_mapping() -> None:
    """原子写 MAPPING_FILE（临时文件 + os.replace），进程内锁保护，杜绝并发损坏。"""
    global _user_session_map
    with _mapping_lock:
        try:
            MAPPING_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(_user_session_map, ensure_ascii=False, indent=2)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(MAPPING_FILE.parent),
                prefix=".session_mappings.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp_path, MAPPING_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            print(f"[bridge] 保存映射失败: {e}")


def _load_watermarks() -> None:
    """加载消费水位线（user_id -> 已投递最大消息 id）。"""
    global _delivered_watermark
    with _watermark_lock:
        if WATERMARK_FILE.exists():
            try:
                data = json.loads(WATERMARK_FILE.read_text())
                _delivered_watermark = {
                    str(k): int(v) for k, v in data.items()
                }
            except Exception:
                _delivered_watermark = {}


def _save_watermarks() -> None:
    """原子写消费水位线（临时文件 + os.replace），进程内锁保护。"""
    global _delivered_watermark
    with _watermark_lock:
        try:
            WATERMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(_delivered_watermark, ensure_ascii=False, indent=2)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(WATERMARK_FILE.parent),
                prefix=".delivered_watermarks.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp_path, WATERMARK_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as e:
            print(f"[bridge] 保存水位线失败: {e}")


def _get_watermark(user_id: str) -> int:
    return _delivered_watermark.get(user_id, 0)


def _set_watermark(user_id: str, max_msg_id: int) -> None:
    """推进消费水位线（只增不减），并持久化。"""
    if max_msg_id <= _get_watermark(user_id):
        return
    _delivered_watermark[user_id] = max_msg_id
    _save_watermarks()


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


# ---------- 思维链水位线快照与增量回读 ----------

def _get_baseline_id(session_id: str | None) -> int:
    """请求前快照：当前 session 已落库的最大消息 id（新会话/异常返回 0）。"""
    if not session_id or not os.path.exists(STATE_DB):
        return 0
    try:
        conn = sqlite3.connect(STATE_DB)
        try:
            cur = conn.execute(
                "SELECT COALESCE(MAX(id), 0) FROM messages WHERE session_id=?",
                (session_id,),
            )
            row = cur.fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception as e:
        print(f"[bridge] 水位线快照失败·按 0 处理: {e}")
        return 0


def _readback_delta(session_id: str | None, baseline_id: int) -> list[dict]:
    """执行后增量回读：仅 id > baseline_id 的当次新增行（只读 SELECT·禁止写操作）。"""
    if not session_id or not os.path.exists(STATE_DB):
        return []
    conn = sqlite3.connect(STATE_DB)
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.execute(
            "SELECT id, session_id, role, content, reasoning_content, tool_name, tool_calls "
            "FROM messages WHERE session_id=? AND id>? ORDER BY id ASC",
            (session_id, baseline_id),
        )
        return [dict(r) for r in cur.fetchall()]
    finally:
        conn.close()


# ---------- 状态回读（GET /v1/chat/status） ----------

def _latest_step_text(last_row) -> str:
    """从最新一行提炼 human-readable 最新步骤摘要。"""
    role = (last_row["role"] or "").strip()
    if role == "tool":
        name = (last_row["tool_name"] or "").strip()
        return f"工具执行完成: {name}" if name else "工具执行完成"
    if role == "assistant":
        content = (last_row["content"] or "").strip()
        if content:
            return "已生成回答"
        if last_row["tool_calls"]:
            return "正在调用工具"
        if (last_row["reasoning_content"] or "").strip():
            return "思考中"
        return "处理中"
    return "等待处理"


def _query_status(hermes_sid: str | None, user_id: str | None = None) -> dict:
    """只读查询 state.db 会话状态，返回 4 态状态机结果。

    - not_found：无映射 / 会话不存在 / 已归档
    - completed：最后一条为 role='assistant' 且内容非空（附完整 answer + reasoning）
    - running：最新为 tool/thought/user 且 300s 内有更新（附 latest_step + 已产生 steps）
    - timeout：超时（>300s 无更新）或进程已退出且无 assistant 回答

    首秒兜底：Hermes CLI 启动中尚未向 state.db 落库时，若该 user 有在途请求
    （_in_flight_users 命中且未超时），直接返回 running，绝不误报 not_found。
    """
    wm_key = user_id or hermes_sid or ""
    empty = {"status": "not_found", "answer": "", "reasoning": [], "latest_step": ""}

    def _running_fallback() -> dict:
        if _is_in_flight(user_id):
            return {"status": "running", "answer": "", "reasoning": [], "latest_step": "处理中"}
        return empty

    if not hermes_sid:
        return _running_fallback()
    if not os.path.exists(STATE_DB):
        return _running_fallback()
    try:
        conn = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    except Exception as e:
        print(f"[bridge] state.db 只读连接失败: {e}")
        return _running_fallback()
    try:
        conn.row_factory = sqlite3.Row
        srow = conn.execute(
            "SELECT ended_at, archived FROM sessions WHERE id=? LIMIT 1",
            (hermes_sid,),
        ).fetchone()
        if srow is None or srow["archived"]:
            return _running_fallback()

        rows = conn.execute(
            "SELECT id, role, content, reasoning_content, tool_name, tool_calls, timestamp "
            "FROM messages WHERE session_id=? AND active=1 ORDER BY id ASC",
            (hermes_sid,),
        ).fetchall()
        if not rows:
            return {"status": "running", "answer": "", "reasoning": [], "latest_step": ""}

        last = rows[-1]
        role = (last["role"] or "").strip()
        content = (last["content"] or "").strip()
        ts = last["timestamp"] or 0
        steps = [s.model_dump() for s in extract_steps([dict(r) for r in rows])]
        latest_step = _latest_step_text(last)

        # completed：最后一条 assistant 且内容非空
        if role == "assistant" and content:
            return {
                "status": "completed",
                "answer": content,
                "reasoning": steps,
                "latest_step": "",
                "consumed": last["id"] <= _get_watermark(wm_key),
            }

        # running vs timeout
        session_ended = srow["ended_at"] is not None
        stale = (time.time() - ts) > STATUS_STALE_SECONDS
        if not stale and not session_ended:
            return {
                "status": "running",
                "answer": "",
                "reasoning": steps,
                "latest_step": latest_step,
            }
        return {
            "status": "timeout",
            "answer": "",
            "reasoning": [],
            "latest_step": latest_step,
        }
    finally:
        conn.close()


def _mark_consumed(user_id: str, hermes_sid: str | None) -> None:
    """将当前会话最新消息 id 推进到消费水位线（断点 0ms 回读后标记已消费）。"""
    if not hermes_sid:
        return
    try:
        _set_watermark(user_id, _get_baseline_id(hermes_sid))
    except Exception as e:
        print(f"[bridge] 标记消费失败·忽略: {e}")


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
    import websockets  # 懒加载：WS PTY 默认禁用，无 websockets 依赖也不阻塞启动

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
    _load_watermarks()
    print(f"[bridge] v5 启动·已加载 {len(_user_session_map)} 条 user→session 映射")
    if not HERMES_SERVE_TOKEN:
        print("[bridge] ⚠️ 警告: HERMES_SERVE_TOKEN 未设置·serve 认证可能失败")


@app.post("/v1/chat/stream")
async def chat_stream(body: GoalRequest):
    """SSE 流式对话入口（Bridge v7 核心端点）。

    优先级：进程内 agent runner（真实逐 token·v7 主路径）→ WS PTY（默认禁用）→ CLI -z 非流式降级。
    全部以 SSE data: {type:...} 格式推送给前端。
    在途标记 _in_flight_users 首秒登记、finally 移除，供 /v1/chat/status 瞬时 running 兜底。
    """
    user_id = body.session_id or "anonymous"
    _mark_in_flight(user_id)

    # v7 主路径：进程内 AIAgent 真实流式（IN_PROCESS_STREAM_ENABLED 默认 true）
    if IN_PROCESS_STREAM_ENABLED:
        try:
            print(f"[bridge] v7 进程内流式: user={user_id}")
            return StreamingResponse(
                _sse_from_in_process(user_id, body.goal),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                },
            )
        except Exception as stream_err:
            print(f"[bridge] v7 进程内流式失败·降级: {stream_err}")

    try:
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
    finally:
        _clear_in_flight(user_id)


# ---------------------------------------------------------------------------
# v7 进程内 agent runner（真实流式·SSE 事件流）
# ---------------------------------------------------------------------------

# 模糊需求澄清门禁（AI Lab 交互铁律 · 2026-08-16 用户拍板）：
# 通过 ephemeral_system_prompt 声明式注入，防 agent 在模糊需求下自嗨跑完整套 IPD 工具链。
CLARIFY_GATE_PROMPT = """【AI Lab 需求澄清门禁 · 必须遵守】
1. 零废话·秒拦截：用户输入是模糊开发/方案/架构/立项需求（如"做电商平台"、"开发手机操作系统"、"做大模型应用"——目标范围过大、缺场景/边界/验收标准）时，第一轮输出正文 ≤2 句极简引导（≤40 字），并【立即调用 clarify 工具】弹出选项卡片（2~4 个结构化选项，单选/多选），严禁输出长篇分析、架构设计、IPD 流程说教长文。
2. 严禁手写「1. 请回答… 2. 请回答…」文本问答题——必须用 clarify 工具的 choices 选项卡片（手机软键盘长文输入是反人机交互）。
3. IPD 关口步进（Gate-by-Gate）：流程拆解为 CDCP→PDCP→EDCP→ADCP，每阶段只交付当前关口产物 + 《需求收敛确认单》，用户确认后才推进下一步，严禁一轮对话一揽子跑完全程。
4. 需求已清晰（含明确场景/边界/验收依据）时不受此限，正常执行。"""


def _qput(stream_q: queue.Queue, item: dict) -> None:
    """线程安全投递事件；队列满用 put_nowait 丢弃（绝不阻塞 agent 线程）。"""
    try:
        stream_q.put_nowait(item)
    except queue.Full:
        print(f"[bridge] ⚠️ 流式事件队列满·丢弃事件: {item.get('type')}")


def _stream_run_register(user_id: str, state: dict) -> None:
    with _stream_runs_guard:
        _stream_runs[user_id] = state


def _stream_run_get(user_id: str) -> dict | None:
    with _stream_runs_guard:
        return _stream_runs.get(user_id)


def _stream_run_discard(user_id: str) -> None:
    with _stream_runs_guard:
        _stream_runs.pop(user_id, None)


def _emit_tool_start(stream_q: queue.Queue, tool_call_id, function_name, function_args) -> None:
    """工具启动事件（模块级可测）：过滤内部工具 + 载荷治理（仅 preview/label）。"""
    if not tool_call_id or (function_name or "").startswith("_"):
        return
    label = function_name
    try:
        from agent.display import build_tool_preview
        preview = build_tool_preview(function_name, function_args)
        if preview:
            label = preview
    except Exception:
        pass
    _qput(stream_q, {
        "type": "tool_start",
        "id": tool_call_id,
        "tool": function_name,
        "label": label,
    })


def _emit_tool_complete(stream_q: queue.Queue, tool_call_id, function_name, function_args=None, result=None) -> None:
    """工具完成事件（模块级可测）：不发 raw result（对齐 api_server 契约·防内部信息泄露）。"""
    if not tool_call_id or (function_name or "").startswith("_"):
        return
    _qput(stream_q, {
        "type": "tool_complete",
        "id": tool_call_id,
        "tool": function_name,
    })


def _build_in_process_agent(
    goal: str,
    user_id: str,
    hermes_sid: str | None,
    stream_q: queue.Queue,
) -> object:
    """进程内构建 AIAgent（复用 oneshot 构建模式·保留全部流式回调）。

    - stream_delta_callback → delta 事件
    - reasoning_callback → thought 事件（实时思考流）
    - tool_start/tool_complete → tool 事件（载荷治理·不发 raw result）
    - clarify_callback → clarify_gateway 注册 + clarify 事件 + 阻塞等待解锁
    """
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_cli.tools_config import _get_platform_tools
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.oneshot import _create_session_db_for_oneshot
    from run_agent import AIAgent

    cfg = load_config()
    model_cfg = cfg.get("model") or {}
    if isinstance(model_cfg, str):
        cfg_model = model_cfg
    else:
        cfg_model = model_cfg.get("default") or model_cfg.get("model") or ""

    runtime = resolve_runtime_provider(requested=None, target_model=cfg_model or None)
    toolsets_list = sorted(_get_platform_tools(cfg, "cli"))
    _fb = get_fallback_chain(cfg)
    session_db = _create_session_db_for_oneshot()

    def _clarify_cb(question: str, choices=None, multi_select: bool = False) -> str:
        """clarify 回调：注册进 clarify_gateway → 推 clarify 事件 → 阻塞等用户响应。"""
        from tools import clarify_gateway as cg

        clarify_id = uuid.uuid4().hex[:10]
        cg.register(
            clarify_id=clarify_id,
            session_key=user_id,
            question=question,
            choices=list(choices) if choices else None,
            multi_select=bool(multi_select),
        )
        _qput(stream_q, {
            "type": "clarify",
            "question": question,
            "choices": list(choices) if choices else None,
            "multi_select": bool(multi_select) and bool(choices),
        })
        resp = cg.wait_for_response(clarify_id, timeout=float(CLARIFY_TIMEOUT_SECONDS))
        if resp is None or resp == "":
            return (
                f"[user did not respond within {CLARIFY_TIMEOUT_SECONDS}s. "
                "Make the most reasonable assumption and continue.]"
            )
        return resp

    def _delta_cb(text) -> None:
        if text:
            _qput(stream_q, {"type": "delta", "content": text})

    def _reasoning_cb(text) -> None:
        if text:
            _qput(stream_q, {"type": "thought", "content": text})

    def _tool_start_cb(tool_call_id, function_name, function_args) -> None:
        _emit_tool_start(stream_q, tool_call_id, function_name, function_args)

    def _tool_complete_cb(tool_call_id, function_name, function_args, result) -> None:
        # 载荷治理：不发 raw result（对齐 api_server 契约·防内部信息泄露）
        _emit_tool_complete(stream_q, tool_call_id, function_name, function_args, result)

    # 服务器 Hermes v0.19.0 AIAgent 无 requested_provider 参数（本地 v0.19.1 有）——
    # 一律不传，避免跨版本签名不兼容；runtime 解析已含该信息，非必需
    agent = AIAgent(
        api_key=runtime.get("api_key"),
        base_url=runtime.get("base_url"),
        provider=runtime.get("provider"),
        api_mode=runtime.get("api_mode"),
        model=cfg_model,
        enabled_toolsets=toolsets_list,
        quiet_mode=True,
        platform="cli",
        session_id=hermes_sid,
        session_db=session_db,
        credential_pool=runtime.get("credential_pool"),
        fallback_model=_fb or None,
        ephemeral_system_prompt=CLARIFY_GATE_PROMPT,
        clarify_callback=_clarify_cb,
        stream_delta_callback=_delta_cb,
        reasoning_callback=_reasoning_cb,
        tool_start_callback=_tool_start_cb,
        tool_complete_callback=_tool_complete_cb,
    )
    return agent, session_db


def _run_agent_sync(
    goal: str,
    user_id: str,
    hermes_sid: str | None,
    stream_q: queue.Queue,
    agent_holder: list,
) -> None:
    """agent 同步执行（worker 线程内）：执行 → done/error → finally 强制 close。"""
    agent = None
    session_db = None
    try:
        agent, session_db = _build_in_process_agent(goal, user_id, hermes_sid, stream_q)
        agent_holder[0] = agent
        result = agent.run_conversation(goal)
        final = (result.get("final_response") or "") if isinstance(result, dict) else str(result or "")
        _qput(stream_q, {"type": "done", "session_id": user_id, "answer": final})
    except Exception as e:
        print(f"[bridge] ⚠️ 进程内 agent 执行失败: {e}")
        _qput(stream_q, {"type": "error", "code": "internal", "message": str(e)[:200]})
    finally:
        # 显式回收：agent.close + session_db.close（防内存泄漏）
        try:
            if agent is not None:
                agent.close()
        except Exception:
            pass
        try:
            if session_db is not None:
                session_db.close()
        except Exception:
            pass


def _sse_from_in_process(user_id: str, goal: str):
    """SSE 事件生成器：agent 线程事件 → queue → asyncio 逐帧输出（thread-safe）。"""
    stream_q: queue.Queue = queue.Queue(maxsize=STREAM_QUEUE_CAPACITY)
    agent_holder: list = [None]
    start_ts = time.monotonic()
    last_keepalive_ts = time.monotonic()

    hermes_sid = _resolve_hermes_session(user_id)

    worker = threading.Thread(
        target=_run_agent_sync,
        args=(goal, user_id, hermes_sid, stream_q, agent_holder),
        daemon=True,
        name=f"agent-stream-{user_id[:12]}",
    )
    worker.start()
    _stream_run_register(user_id, {"agent_holder": agent_holder, "queue": stream_q})

    try:
        while True:
            now = time.monotonic()

            # 总时长上限（对齐方案 v4：300s 可配置）
            if now - start_ts > STREAM_MAX_DURATION_SECONDS:
                _qput(stream_q, {"type": "error", "code": "timeout"})
                break

            # keepalive 注释帧（对齐 Hermes 30s 常量）
            if now - last_keepalive_ts >= STREAM_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_keepalive_ts = now

            try:
                item = stream_q.get(timeout=0.5)
            except queue.Empty:
                if not worker.is_alive() and stream_q.empty():
                    break
                continue

            if item is None:
                break
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
    finally:
        # 断连/取消回收：interrupt + 清理 streaming 标记
        agent = agent_holder[0]
        if agent is not None:
            try:
                agent.interrupt()
            except Exception:
                pass
        _stream_run_discard(user_id)


class ClarifyResolveRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)


class CancelRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


@app.post("/v1/chat/clarify")
async def clarify_resolve(body: ClarifyResolveRequest):
    """澄清响应提交：解锁阻塞的 agent 线程（不占 session 锁·thread-safe）。"""
    from tools import clarify_gateway as cg

    ok = cg.resolve_text_response_for_session(body.session_id, body.response)
    if not ok:
        # 自由文本被 _coerce_text_response 拒绝 → 通知前端重试（防静默丢失）
        run = _stream_run_get(body.session_id)
        if run:
            _qput(run["queue"], {"type": "clarify_rejected"})
        return {"ok": False, "reason": "rejected"}
    return {"ok": True}


@app.post("/v1/chat/stream/cancel")
async def stream_cancel(body: CancelRequest):
    """取消在途流式：interrupt agent + 强制解锁 clarify + 清理状态。"""
    from tools import clarify_gateway as cg

    run = _stream_run_get(body.session_id)
    if run:
        agent = run["agent_holder"][0]
        if agent is not None:
            try:
                agent.interrupt()
            except Exception:
                pass
        # 强制解锁阻塞在 clarify Event.wait() 的线程（不等超时）
        try:
            cg.clear_session(body.session_id)
        except Exception:
            pass
        _stream_run_discard(body.session_id)
    return {"ok": True}


@app.post("/v1/chat")
async def chat(body: GoalRequest):
    """非流式对话入口（向后兼容·Agent 工厂/子代理使用）。

    两级锁序固定：全局 Semaphore(2) → user 细粒度锁，先取 Semaphore 再取 user 锁。
    临界区全程覆盖：解析映射 → 快照水位线 → CLI 执行(to_thread) → 增量回读 → 映射更新。
    思维链回读失败降级 reasoning=[] 并打 Warning 日志，严禁向客户端抛 500。
    在途标记 _in_flight_users 首秒登记、finally 移除，供 /v1/chat/status 瞬时 running 兜底。
    """
    user_id = body.session_id or "anonymous"
    _mark_in_flight(user_id)
    try:
        async with _semaphore:
            user_lock = _get_user_lock(user_id)
            async with user_lock:
                # 1) 解析 session 映射（失效则清除）
                hermes_sid = _resolve_hermes_session(user_id)

                # 2) 请求前快照：水位线 baseline_id
                baseline_id = await asyncio.to_thread(_get_baseline_id, hermes_sid)

                # 3) CLI 执行（唯一真实执行路径·to_thread 不阻塞事件循环）
                if not hermes_sid:
                    reply, new_sid = await asyncio.to_thread(_run_hermes, body.goal, None)
                    effective_sid = new_sid
                    if new_sid:
                        _update_session_mapping(user_id, new_sid)
                else:
                    reply, new_sid = await asyncio.to_thread(_run_hermes, body.goal, hermes_sid)
                    effective_sid = new_sid or hermes_sid

                # 4) 执行后增量回读 + 真实思维链映射（失败降级·不 500）
                reasoning: list[dict] = []
                try:
                    rows = await asyncio.to_thread(
                        _readback_delta, effective_sid, baseline_id
                    )
                    reasoning = [s.model_dump() for s in extract_steps(rows)]
                except Exception as e:
                    print(f"[bridge] ⚠️ 思维链回读失败·降级空 reasoning: {e}")

                # 投递成功后推进消费水位线（断点 0ms 回读判定依据）
                _mark_consumed(user_id, effective_sid)

                return {
                    "reply": reply,
                    "session_id": user_id,
                    "hermes_session_id": effective_sid,
                    "reasoning": reasoning,
                }
    finally:
        _clear_in_flight(user_id)


@app.get("/v1/chat/status/{user_id}")
async def chat_status(user_id: str, consume: int = 0):
    """状态回读端点（只读·不写 state.db）。

    通过 user_id 锁定 hermes_session_id，返回 4 态状态机：
    completed / running / timeout / not_found。
    consume=1 时，completed 结果顺带推进消费水位线（0ms 断点回读后标记已消费）。
    """
    hermes_sid = _user_session_map.get(user_id)
    result = await asyncio.to_thread(_query_status, hermes_sid, user_id)
    if consume == 1 and result.get("status") == "completed":
        _mark_consumed(user_id, hermes_sid)
    return result


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
