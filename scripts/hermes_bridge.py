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
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

import httpx
from fastapi import FastAPI, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn

# 仓库根追加到 sys.path（不插 0 位）：仓库 tools/ 无 Hermes 网关模块，
# 若插在最前会遮蔽 venv site-packages 的 Hermes tools（managed_tool_gateway/
# clarify_gateway）与 run_agent，导致进程内 agent 构建失败。
# append 后：tools/hermes_cli/run_agent 解析到已安装 hermes_agent 0.19.0，
# backend 包仍可从仓库根解析（仅仓库持有）。
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.append(str(_REPO_ROOT))

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
MAX_INPUT = 12000
ALLOWED_CHAT_SKILLS = {"solution-consultant-persona"}
DEFAULT_TIMEOUT = 300
SERVE_TIMEOUT = 300
# 注：v5 起显式移除「>300s 无更新」stale 判定（STATUS_STALE_SECONDS），
# timeout 判定统一单一时钟源：run.start_ts 超 STREAM_MAX_DURATION_SECONDS(720s)。

# ---------------------------------------------------------------------------
# v7 真实流式（进程内 agent runner）配置
# ---------------------------------------------------------------------------
# 进程内流式开关：true 时 /v1/chat/stream 走 AIAgent 进程内 runner（真实逐 token）
IN_PROCESS_STREAM_ENABLED = os.environ.get("HERMES_IN_PROCESS_STREAM", "false") == "true"
# SSE keepalive 注释帧间隔（对齐 Hermes CHAT_COMPLETIONS_SSE_KEEPALIVE_SECONDS=30.0）
STREAM_KEEPALIVE_SECONDS = float(os.environ.get("HERMES_STREAM_KEEPALIVE", "30"))
# 单次流式总时长上限（超时 → watchdog interrupt + error 帧）
STREAM_MAX_DURATION_SECONDS = int(os.environ.get("HERMES_STREAM_MAX_DURATION", "720"))
# watchdog 扫描间隔（秒）：detached run 超时判定精度；G-10 压缩测试可覆盖
WATCHDOG_INTERVAL_SECONDS = float(os.environ.get("HERMES_WATCHDOG_INTERVAL", "10"))
# clarify 等待用户响应超时（默认 180s，替代 Hermes 原生 3600s）
CLARIFY_TIMEOUT_SECONDS = int(os.environ.get("HERMES_CLARIFY_TIMEOUT", "180"))
# Drill-me 至少完成三轮需求收敛后才允许输出方案。上限由 prompt 约束，避免无休止追问。
DRILL_ME_MIN_ROUNDS = max(2, int(os.environ.get("HERMES_DRILL_ME_MIN_ROUNDS", "3")))
DRILL_ME_MAX_ROUNDS = max(
    DRILL_ME_MIN_ROUNDS,
    int(os.environ.get("HERMES_DRILL_ME_MAX_ROUNDS", "5")),
)
# 事件队列容量（线程 → async 桥）
STREAM_QUEUE_CAPACITY = 1024

# 持久工作流运行投影。Hermes 负责计划节点推进、工具与模型调用；平台 Worker
# 只通过内部 API 投递并同步这些事件，避免 FastAPI 与 Hermes 各维护一套编排器。
WORKFLOW_RUNS_FILE = Path(
    os.environ.get(
        "HERMES_WORKFLOW_RUNS_FILE",
        "/opt/ai-lab-platform/data/hermes_workflow_runs.json",
    )
)
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")
_workflow_runs: dict[str, dict[str, Any]] = {}
_workflow_runs_lock = threading.RLock()
_workflow_threads: dict[str, threading.Thread] = {}

# user_id -> 在途流式运行状态（agent holder / 线程 / 队列 / 停止事件），供 cancel/clarify 端点寻址
# 状态模型（保活机制 v6）：{agent_holder, queue, attached, start_ts, run_id[, clarify_issued]}
#   - attached=True  → SSE 客户端仍连接（generator 存活）
#   - attached=False → SSE 断连已 detach（不 interrupt），由 watchdog 守护，超时 interrupt+discard
#   - start_ts       → run 启动时间戳（monotonic），watchdog 超时判定依据
#   - run_id         → 每次启动 run 的唯一标识，discard 校验防误删新 run
_stream_runs: dict[str, dict] = {}
_stream_runs_guard = threading.Lock()

# clarify_gateway 懒加载缓存（模块级）：首次调用 import tools.clarify_gateway 并缓存，
# 行为与原函数内 `from tools import clarify_gateway` 等价（模块对象恒定），
# 且测试可直接 patch 此引用（测试环境 sys.path 无 tools 包）
_clarify_gateway = None


def _get_clarify_gateway():
    """返回 clarify_gateway 模块（懒加载 + 缓存）。"""
    global _clarify_gateway
    if _clarify_gateway is None:
        from tools import clarify_gateway
        _clarify_gateway = clarify_gateway
    return _clarify_gateway

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
    request_id: str | None = Field(None, min_length=8, max_length=100)
    session_id: str | None = None  # 前端传入的 user_id（用于映射 Hermes 原生 session）
    skill_id: str | None = Field(None, max_length=80)
    isolation: str = Field("standard", description="向后兼容·子Agent工厂使用")
    # 重新生成语义（2026-08-17 修复）：true 时作废旧 run（interrupt 旧 agent + discard 注册）
    # 再启动全新尝试——对齐 ChatGPT「重新生成」= 上次回答作废重跑，而非被并发防护拒绝
    regenerate: bool = Field(False, description="重新生成：作废旧 run 后全新执行")


class WorkflowPlanRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    workflow_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=160)
    description: str = Field(..., min_length=3, max_length=12000)
    deliverable: str = Field(..., min_length=1, max_length=300)
    knowledge_scope: list[str] = Field(default_factory=list)
    allowed_agents: list[str] = Field(default_factory=list)
    allow_network: bool = True
    max_tokens: int = Field(24000, ge=1000, le=128000)
    revision_note: str = Field("", max_length=2000)


class WorkflowRunRequest(BaseModel):
    tenant_id: str = Field(..., min_length=1, max_length=64)
    execution_id: str = Field(..., min_length=1, max_length=64)
    idempotency_key: str = Field(..., min_length=8, max_length=160)
    goal: str = Field(..., min_length=1, max_length=12000)
    deliverable: str = Field(..., min_length=1, max_length=300)
    plan: dict[str, Any]
    allow_network: bool = True
    knowledge_scope: list[str] = Field(default_factory=list)
    max_tokens: int = Field(24000, ge=1000, le=128000)


class WorkflowRetryRequest(BaseModel):
    from_node_id: str | None = Field(None, max_length=80)


def _expand_requested_skill(goal: str, skill_id: str | None) -> str:
    """在Hermes进程内按官方skill command协议加载白名单技能。"""
    if not skill_id:
        return goal
    if skill_id not in ALLOWED_CHAT_SKILLS:
        raise HTTPException(status_code=400, detail=f"unsupported skill: {skill_id}")
    from agent.skill_commands import (
        build_skill_invocation_message,
        resolve_skill_command_key,
    )

    command_key = resolve_skill_command_key(skill_id)
    if not command_key:
        raise HTTPException(status_code=503, detail=f"skill not installed: {skill_id}")
    expanded = build_skill_invocation_message(command_key, goal)
    if not expanded:
        raise HTTPException(status_code=503, detail=f"skill load failed: {skill_id}")
    return expanded


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


def _load_workflow_runs() -> None:
    """加载 Hermes 工作流投影；运行中的任务在 Worker 重连时显式恢复。"""
    global _workflow_runs
    with _workflow_runs_lock:
        if not WORKFLOW_RUNS_FILE.exists():
            _workflow_runs = {}
            return
        try:
            raw = json.loads(WORKFLOW_RUNS_FILE.read_text(encoding="utf-8"))
            _workflow_runs = raw if isinstance(raw, dict) else {}
            for run in _workflow_runs.values():
                if run.get("status") == "running":
                    run["status"] = "interrupted"
                    run["error"] = "Hermes Bridge 重启，等待持久派发器恢复"
        except Exception as exc:
            print(f"[bridge] 加载工作流投影失败: {exc}")
            _workflow_runs = {}


def _save_workflow_runs() -> None:
    """原子保存工作流投影，内容不包含密钥。"""
    with _workflow_runs_lock:
        try:
            WORKFLOW_RUNS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = json.dumps(_workflow_runs, ensure_ascii=False, indent=2)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(WORKFLOW_RUNS_FILE.parent),
                prefix=".hermes_workflow_runs.",
                suffix=".tmp",
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(data)
                os.replace(tmp_path, WORKFLOW_RUNS_FILE)
            except Exception:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
                raise
        except Exception as exc:
            print(f"[bridge] 保存工作流投影失败: {exc}")


def _workflow_event(run: dict[str, Any], event_type: str, **payload: Any) -> dict[str, Any]:
    seq = int(run.get("next_seq", 1))
    event = {
        "seq": seq,
        "event_id": f"{run['execution_id']}:{seq}",
        "type": event_type,
        "created_at": time.time(),
        **payload,
    }
    run.setdefault("events", []).append(event)
    run["next_seq"] = seq + 1
    # 事件是断点恢复的审计真相源；限制单次运行数量，防异常工具循环撑爆投影文件。
    if len(run["events"]) > 5000:
        run["events"] = run["events"][-5000:]
    _save_workflow_runs()
    return event


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

def _run_hermes_with_usage(
    goal: str, session_id: str | None = None
) -> tuple[str, str | None, dict[str, Any]]:
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

    # 从 --usage-file 提取真实 usage（原子捕获·并发安全）
    usage = _extract_usage(usage_file)
    return reply, usage.get("session_id"), usage


def _run_hermes(goal: str, session_id: str | None = None) -> tuple[str, str | None]:
    """向后兼容的二元返回包装；工作流使用 `_run_hermes_with_usage`。"""
    reply, hermes_sid, _ = _run_hermes_with_usage(goal, session_id)
    return reply, hermes_sid


def _extract_usage(usage_file: Path) -> dict[str, Any]:
    """读取完整 Hermes usage，并始终删除临时文件。"""
    try:
        if usage_file.exists():
            data = json.loads(usage_file.read_text())
            return data if isinstance(data, dict) else {}
    except Exception as e:
        print(f"[bridge] 读取 usage-file 失败: {e}")
    finally:
        try:
            usage_file.unlink(missing_ok=True)
        except Exception:
            pass
    return {}


def _extract_session_from_usage(usage_file: Path) -> str | None:
    """保留给既有测试/调用方的兼容入口。"""
    return _extract_usage(usage_file).get("session_id")


def _require_internal(token: str | None) -> None:
    if HERMES_BRIDGE_INTERNAL_TOKEN and token != HERMES_BRIDGE_INTERNAL_TOKEN:
        raise HTTPException(status_code=401, detail="invalid bridge token")


def _extract_json_object(text: str) -> dict[str, Any]:
    raw = (text or "").strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE)
        raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Hermes 未返回 JSON 计划")
    value = json.loads(raw[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("Hermes 计划必须是 JSON 对象")
    return value


def _workflow_order(plan: dict[str, Any]) -> list[str]:
    nodes = plan.get("nodes") or []
    ids = [str(node.get("id") or "") for node in nodes]
    if not ids or any(not node_id for node_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("工作流节点 ID 非法或重复")
    incoming = {node_id: 0 for node_id in ids}
    outgoing = {node_id: [] for node_id in ids}
    for edge in plan.get("edges") or []:
        source, target = str(edge.get("source") or ""), str(edge.get("target") or "")
        if source not in incoming or target not in incoming:
            raise ValueError("工作流依赖引用不存在的节点")
        outgoing[source].append(target)
        incoming[target] += 1
    queue_ids = [node_id for node_id in ids if incoming[node_id] == 0]
    ordered: list[str] = []
    while queue_ids:
        node_id = queue_ids.pop(0)
        ordered.append(node_id)
        for target in outgoing[node_id]:
            incoming[target] -= 1
            if incoming[target] == 0:
                queue_ids.append(target)
    if len(ordered) != len(ids):
        raise ValueError("工作流 DAG 存在循环依赖")
    return ordered


def _usage_delta(usage: dict[str, Any]) -> dict[str, Any]:
    integer_fields = (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "api_calls",
    )
    result = {field: int(usage.get(field) or 0) for field in integer_fields}
    result.update(
        {
            "estimated_cost_usd": float(usage.get("estimated_cost_usd") or 0),
            "model": str(usage.get("model") or ""),
            "provider": str(usage.get("provider") or ""),
            "cost_status": str(usage.get("cost_status") or "unknown"),
            "cost_source": str(usage.get("cost_source") or "none"),
        }
    )
    return result


def _accumulate_usage(run: dict[str, Any], usage: dict[str, Any]) -> dict[str, Any]:
    delta = _usage_delta(usage)
    total = run.setdefault("usage", {})
    for field in (
        "input_tokens",
        "output_tokens",
        "reasoning_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "total_tokens",
        "api_calls",
    ):
        total[field] = int(total.get(field) or 0) + int(delta[field])
    total["estimated_cost_usd"] = round(
        float(total.get("estimated_cost_usd") or 0) + delta["estimated_cost_usd"], 8
    )
    for field in ("model", "provider", "cost_status", "cost_source"):
        if delta.get(field):
            total[field] = delta[field]
    return delta


def _workflow_node_prompt(run: dict[str, Any], node: dict[str, Any]) -> str:
    params = node.get("parameters") or {}
    completed = []
    for candidate in run.get("plan", {}).get("nodes") or []:
        node_id = str(candidate.get("id") or "")
        state = (run.get("nodes") or {}).get(node_id) or {}
        if state.get("status") == "succeeded" and state.get("output"):
            completed.append(f"- {candidate.get('name') or node_id}: {str(state['output'])[:1200]}")
    return (
        "你是 Hermes 工作流编排引擎，正在同一个持久 Session 中推进已获用户批准的 DAG。\n"
        f"工作流目标：{run.get('goal', '')}\n"
        f"最终交付：{run.get('deliverable', '')}\n"
        f"当前节点：{node.get('name') or node.get('id')} ({node.get('node_type')})\n"
        f"指定 Agent：{params.get('agent_id') or 'main_agent'}\n"
        f"节点要求：{params.get('instruction') or params.get('query') or ''}\n"
        f"输出格式：{params.get('output_format') or '结构化 Markdown'}\n"
        f"知识范围：{json.dumps(params.get('knowledge_scope') or run.get('knowledge_scope') or [], ensure_ascii=False)}\n"
        f"联网权限：{'允许，但仅在证据缺口明确时使用' if run.get('allow_network') else '禁止'}\n"
        "必须自行调用所需 Agent、技能、知识库和工具；引用真实来源，不得虚构。"
        "只输出当前节点可落盘的完整成果，不要输出运行状态说明。\n"
        f"已完成上游摘要：\n{chr(10).join(completed) if completed else '无'}"
    )[:MAX_INPUT]


def _workflow_run_sync(execution_id: str) -> None:
    """Hermes 层推进整份 DAG；平台只消费事件，不参与节点调度。"""
    with _workflow_runs_lock:
        run = _workflow_runs.get(execution_id)
        if not run:
            return
        run["status"] = "running"
        run["error"] = None
        _workflow_event(run, "run_started", message="Hermes 工作流开始执行")
    try:
        plan = run["plan"]
        node_map = {str(node["id"]): node for node in plan.get("nodes") or []}
        order = _workflow_order(plan)
        hermes_sid = run.get("hermes_session_id")
        if hermes_sid and not _session_exists(str(hermes_sid)):
            hermes_sid = None
        for position, node_id in enumerate(order):
            with _workflow_runs_lock:
                if run.get("cancel_requested"):
                    run["status"] = "cancelled"
                    _workflow_event(run, "run_cancelled", message="执行已取消")
                    return
                state = run.setdefault("nodes", {}).setdefault(node_id, {})
                if state.get("status") == "succeeded":
                    continue
                node = node_map[node_id]
                state.update({"status": "running", "attempt": int(state.get("attempt") or 0) + 1})
                _workflow_event(
                    run,
                    "node_started",
                    node_id=node_id,
                    node_type=node.get("node_type"),
                    agent_id=(node.get("parameters") or {}).get("agent_id") or "main_agent",
                    message=f"开始：{node.get('name') or node_id}",
                )
            reply, new_sid, raw_usage = _run_hermes_with_usage(
                _workflow_node_prompt(run, node), str(hermes_sid) if hermes_sid else None
            )
            if new_sid:
                hermes_sid = new_sid
            if not reply or reply.startswith("⚠️"):
                raise RuntimeError(reply or "Hermes 返回空结果")
            with _workflow_runs_lock:
                run["hermes_session_id"] = hermes_sid
                delta = _accumulate_usage(run, raw_usage)
                if int(run["usage"].get("total_tokens") or 0) > int(run.get("max_tokens") or 0):
                    raise RuntimeError("Hermes 工作流 Token 预算已耗尽")
                state.update({"status": "succeeded", "output": reply, "usage": delta})
                artifact_kind = (
                    "final" if node.get("node_type") == "OUTPUT_FORMAT"
                    else "review" if node.get("node_type") == "FILTER_PASS"
                    else "source" if node.get("node_type") == "KNOWLEDGE_RETRIEVAL"
                    else "draft"
                )
                _workflow_event(
                    run,
                    "node_succeeded",
                    node_id=node_id,
                    progress=int(((position + 1) / max(1, len(order))) * 100),
                    usage=delta,
                    route={
                        "model": delta.get("model"),
                        "provider": delta.get("provider"),
                        "reason": "Hermes 多模型路由按当前 Profile、任务能力与回退策略选择",
                    },
                    artifact={
                        "kind": artifact_kind,
                        "title": str(node.get("name") or node_id),
                        "content": reply,
                        "source_kind": "hermes_output",
                    },
                    message=f"完成：{node.get('name') or node_id}",
                )
        with _workflow_runs_lock:
            run["status"] = "awaiting_review"
            _workflow_event(
                run,
                "run_completed",
                progress=100,
                usage=run.get("usage") or {},
                message="Hermes 执行完成，等待成果复核",
            )
    except Exception as exc:
        with _workflow_runs_lock:
            run["status"] = "failed"
            run["error"] = str(exc)[:2000]
            running_node = next(
                (node_id for node_id, state in (run.get("nodes") or {}).items() if state.get("status") == "running"),
                None,
            )
            if running_node:
                run["nodes"][running_node]["status"] = "failed"
            _workflow_event(
                run,
                "run_failed",
                node_id=running_node,
                error=run["error"],
                message="Hermes 工作流执行失败",
            )
    finally:
        with _workflow_runs_lock:
            _workflow_threads.pop(execution_id, None)
            _save_workflow_runs()


def _start_workflow_thread(execution_id: str) -> None:
    with _workflow_runs_lock:
        existing = _workflow_threads.get(execution_id)
        if existing and existing.is_alive():
            return
        thread = threading.Thread(
            target=_workflow_run_sync,
            args=(execution_id,),
            daemon=True,
            name=f"workflow-{execution_id[:16]}",
        )
        _workflow_threads[execution_id] = thread
        thread.start()


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

def _build_status_phrase(last_row) -> str:
    """latest_step 双驱动之一：tool_start 短语。

    最新一条为 tool 消息 → 「正在执行: <tool_name>」微信式进度短语。
    """
    role = (last_row["role"] or "").strip()
    if role == "tool":
        name = (last_row["tool_name"] or "").strip()
        return f"正在执行: {name}" if name else "正在执行工具"
    return ""


def _thought_summary(rows) -> str:
    """latest_step 双驱动之二：从最近 thought（assistant.reasoning_content）取摘要。

    截断 60 字符 + 省略号，避免长思考文本撑爆进度行。
    """
    for row in reversed(rows):
        if (row["role"] or "").strip() != "assistant":
            continue
        rc = (row["reasoning_content"] or "").strip()
        if rc:
            return rc[:60] + ("…" if len(rc) > 60 else "")
    return ""


def _latest_step_text(rows) -> str:
    """latest_step 双驱动合成：tool_start 短语优先，无则 thought 摘要，再兜底文案。"""
    last = rows[-1]
    role = (last["role"] or "").strip()
    phrase = _build_status_phrase(last)
    if phrase:
        return phrase
    if role == "assistant":
        summary = _thought_summary(rows)
        if summary:
            return f"思考中: {summary}"
        if (last["content"] or "").strip():
            return "已生成回答"
        return "思考中"
    if role == "user":
        return "正在初始化…"
    return "处理中"


def _pending_clarify(user_id: str) -> dict | None:
    """从 clarify_gateway._entries 取未 resolve 的 pending entry（response is None）。

    只返回当前 user 的 entry（session_key 匹配）；已 resolve/已消费（wait_for_response
    超时清理）的 entry 自然被过滤。载荷对齐前端 ClarifyBlock：question/choices/
    multi_select/clarify_id。
    """
    cg = None
    try:
        cg = _get_clarify_gateway()
        entries = getattr(cg, "_entries", None)
        lock = getattr(cg, "_lock", None)
        if entries is None:
            return None
        if lock is not None:
            with lock:
                items = list(entries.values())
        else:
            items = list(entries.values())
        # 诊断日志：多步 Clarify 卡丢失定位（微信模式 status 轮询读 pending entry）
        if items:
            debug_entries = [
                f"{getattr(e, 'session_key', '?')[:20]}/resp={getattr(e, 'response', '§') is not None}"
                for e in items
            ]
            print(f"[bridge] _pending_clarify entries={len(items)} user={user_id[:20]} list={debug_entries}")
        for entry in items:
            if getattr(entry, "session_key", None) == user_id and getattr(entry, "response", "§") is None:
                return {
                    "clarify_id": entry.clarify_id,
                    "question": entry.question,
                    "choices": list(entry.choices) if entry.choices else [],
                    # 兼容服务器 Hermes v0.19.0（_ClarifyEntry 无 multi_select 字段，仅 awaiting_text）
                    "multi_select": bool(getattr(entry, "multi_select", False)),
                }
    except Exception as e:
        print(f"[bridge] pending clarify 查询失败·忽略: {e}")
    return None


def _interrupt_and_discard(user_id: str, run_id: str | None) -> None:
    """超时回收：interrupt agent + discard run（watchdog 与 status 命中 timeout 共用路径）。"""
    state = _stream_run_get(user_id)
    if state:
        agent = state.get("agent_holder", [None])[0]
        if agent is not None:
            try:
                agent.interrupt()
            except Exception:
                pass
    _stream_run_discard(user_id, run_id)


def _query_status(
    hermes_sid: str | None, user_id: str | None = None, offset: int = 0
) -> dict:
    """只读查询 state.db 会话状态，返回四元组快照（方案 v5）。

    返回字段：
    - status     : completed / running / timeout / not_found（兼容旧客户端）
    - phase      : boot / reasoning / tool / clarify / completed / timeout / not_found
    - latest_step: tool_start 短语（build_status_phrase）+ thought 摘要双驱动
    - reasoning  : 思维链步骤；offset>0 时仅返回消息 id>offset 的新条（增量轮询）
    - clarify    : 未 resolve 的 pending clarify entry（无则 null）
    - last_message_id: 当前最大消息 id（前端据此推进 offset）
    - answer     : completed 时完整回答
    - consumed   : 消费水位线标记（consume=1 推进）

    timeout 判定（单一时钟源，对齐 watchdog）：
    - run 存在   → run.start_ts 超 STREAM_MAX_DURATION_SECONDS(720s) → timeout，
                   命中同时 interrupt+discard（复用 watchdog 路径）
    - run 不存在 → 会话 ended 无答案 / 最后消息超 720s 无更新 → timeout
                  （bridge 重启后旧 run 进程消亡，无双 run，按 state.db 判定）
    显式移除历史「>300s 无更新」stale 判定。
    """
    wm_key = user_id or hermes_sid or ""
    empty = {
        "status": "not_found",
        "phase": "not_found",
        "answer": "",
        "reasoning": [],
        "latest_step": "",
        "clarify": None,
        "last_message_id": 0,
    }

    def _running_fallback() -> dict:
        # 微信模式提交后立即轮询（2s）vs agent 构建 10s+：映射未写期间
        # 必须认 _stream_runs（进程内流式 run 已注册）→ running 兜底，绝不误报 not_found
        if _is_in_flight(user_id) or _stream_run_get(user_id) is not None:
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
            return {
                "status": "running",
                "phase": "boot",
                "answer": "",
                "reasoning": [],
                "latest_step": "正在初始化…",
                "clarify": None,
                "last_message_id": 0,
            }

        last = rows[-1]
        role = (last["role"] or "").strip()
        content = (last["content"] or "").strip()
        ts = last["timestamp"] or 0
        max_msg_id = max(int(r["id"]) for r in rows)
        latest_step = _latest_step_text(rows)

        # pending clarify 优先（agent 阻塞等用户点选时最后一条可能是引导语，
        # 必须先于 completed 判定，避免误判完成）
        clarify = _pending_clarify(user_id or "")

        # run 存在性判定（单一时钟源）：start_ts 超 720s → timeout + interrupt+discard
        run = _stream_run_get(user_id or "")
        if run is not None:
            start_ts = run.get("start_ts") or 0
            if time.monotonic() - start_ts > STREAM_MAX_DURATION_SECONDS:
                print(
                    f"[bridge] status 命中 timeout: user={user_id} run 超 "
                    f"{STREAM_MAX_DURATION_SECONDS}s·interrupt+discard"
                )
                _interrupt_and_discard(user_id or "", run.get("run_id"))
                return {
                    "status": "timeout",
                    "phase": "timeout",
                    "answer": "",
                    "reasoning": [],
                    "latest_step": latest_step,
                    "clarify": None,
                    "last_message_id": max_msg_id,
                }

        # completed：最后一条 assistant 且内容非空（且无 pending clarify 阻塞）
        if role == "assistant" and content and clarify is None:
            steps = [s.model_dump() for s in extract_steps([dict(r) for r in rows])]
            return {
                "status": "completed",
                "phase": "completed",
                "answer": content,
                "reasoning": steps,
                "latest_step": "",
                "clarify": None,
                "last_message_id": max_msg_id,
                "consumed": last["id"] <= _get_watermark(wm_key),
            }

        # 有 pending clarify → 卡在澄清等待（优先级高于 running 细分）
        if clarify is not None:
            return {
                "status": "running",
                "phase": "clarify",
                "answer": "",
                "reasoning": [],
                "latest_step": latest_step,
                "clarify": clarify,
                "last_message_id": max_msg_id,
            }

        # run 不存在（重启/被杀/异常结束）且非 completed：
        # 会话已 ended 无答案，或最后消息超 720s 无新消息 → timeout
        # （run 存在且未超预算时由 agent 线程保障，不适用此判定）
        if run is None:
            session_ended = srow["ended_at"] is not None
            no_progress = (time.time() - ts) > STREAM_MAX_DURATION_SECONDS
            if session_ended or no_progress:
                return {
                    "status": "timeout",
                    "phase": "timeout",
                    "answer": "",
                    "reasoning": [],
                    "latest_step": latest_step,
                    "clarify": None,
                    "last_message_id": max_msg_id,
                }

        # running 细分（boot/reasoning/tool）：reasoning 支持 offset 增量
        delta_rows = [dict(r) for r in rows if int(r["id"]) > offset]
        steps = [s.model_dump() for s in extract_steps(delta_rows)] if delta_rows else []
        if role == "tool":
            phase = "tool"
        elif role == "assistant":
            phase = "reasoning"
        else:
            phase = "boot"
        return {
            "status": "running",
            "phase": phase,
            "answer": "",
            "reasoning": steps,
            "latest_step": latest_step,
            "clarify": None,
            "last_message_id": max_msg_id,
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
    _load_workflow_runs()
    print(f"[bridge] v5 启动·已加载 {len(_user_session_map)} 条 user→session 映射")
    if not HERMES_SERVE_TOKEN:
        print("[bridge] ⚠️ 警告: HERMES_SERVE_TOKEN 未设置·serve 认证可能失败")
    # 保活机制 v6（M-3）：独立守护线程，扫描 detached runs 超时 interrupt+discard
    watchdog = threading.Thread(
        target=_watchdog_loop,
        daemon=True,
        name="bridge-watchdog",
    )
    watchdog.start()
    print(
        f"[bridge] watchdog 已启动: 间隔 {WATCHDOG_INTERVAL_SECONDS}s"
        f"·detached 超时 {STREAM_MAX_DURATION_SECONDS}s"
    )


@app.post("/v1/chat/stream")
async def chat_stream(body: GoalRequest):
    """SSE 流式对话入口（Bridge v7 核心端点）。

    优先级：进程内 agent runner（真实逐 token·v7 主路径）→ WS PTY（默认禁用）→ CLI -z 非流式降级。
    全部以 SSE data: {type:...} 格式推送给前端。
    在途标记 _in_flight_users 首秒登记、finally 移除，供 /v1/chat/status 瞬时 running 兜底。
    """
    user_id = body.session_id or "anonymous"
    goal = _expand_requested_skill(body.goal, body.skill_id)
    _mark_in_flight(user_id)

    # v7 主路径：进程内 AIAgent 真实流式（IN_PROCESS_STREAM_ENABLED 默认 true）
    if IN_PROCESS_STREAM_ENABLED:
        # 并发防护（G-6）：同 session 已有活跃 run（attached 或 detached 后台保活中）
        # → 返回 running 状态事件流，绝不启动第二个 agent
        # 例外：regenerate=true（重新生成）→ 作废旧 run 后全新执行，不被防护拦截
        existing = _stream_run_get(user_id)
        if existing is not None and not body.regenerate:
            print(f"[bridge] 并发防护: user={user_id} 已有活跃 run·拒绝新 agent")
            return StreamingResponse(
                _busy_sse(user_id),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "Connection": "keep-alive",
                    "X-Accel-Buffering": "no",
                    "X-Session-ID": user_id,
                },
            )
        if existing is not None and body.regenerate:
            # 重新生成：interrupt 旧 agent 线程（若可寻址）+ 作废注册，启动全新尝试
            print(f"[bridge] 重新生成: user={user_id} 作废旧 run 后全新执行")
            try:
                old_agent = (existing.get("agent_holder") or [None])[0]
                if old_agent is not None:
                    old_agent.interrupt(message="superseded-by-regenerate")
            except Exception:
                pass
            _stream_run_discard(user_id, existing.get("run_id"))
        try:
            print(f"[bridge] v7 进程内流式: user={user_id}")
            return StreamingResponse(
                _sse_from_in_process(user_id, goal),
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
            reply, new_sid = await asyncio.to_thread(_run_hermes, goal, None)
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
                    _stream_from_ws_pty(goal, hermes_sid),
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
        reply, _ = await asyncio.to_thread(_run_hermes, goal, hermes_sid)
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

# 常驻预热单例缓存（支柱一：消灭单次请求冷启动）
# - Config/Tools/Runtime/Fallback 为纯只读数据 → 全局单例共享（线程安全，0ms 读盘）
# - SessionDB 为可写资源 → 线程局部轻量创建（check_same_thread=False，<0.2ms）
_CACHED_CFG = None
_CACHED_CFG_LOCK = threading.Lock()
_CACHED_TOOLS = None
_CACHED_RUNTIME = None
_CACHED_FALLBACK = None


def _get_cached_config() -> dict:
    """常驻 Config 单例：首次加载后内存复用（0ms 读盘）。"""
    global _CACHED_CFG
    if _CACHED_CFG is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_CFG is None:
                from hermes_cli.config import load_config
                _CACHED_CFG = load_config()
    return _CACHED_CFG


def _get_cached_runtime(cfg: dict) -> dict:
    """常驻 Runtime Provider 单例（0ms 解析）。"""
    global _CACHED_RUNTIME
    if _CACHED_RUNTIME is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_RUNTIME is None:
                from hermes_cli.runtime_provider import resolve_runtime_provider
                model_cfg = cfg.get("model") or {}
                m = model_cfg if isinstance(model_cfg, str) else (model_cfg.get("default") or model_cfg.get("model") or "")
                _CACHED_RUNTIME = resolve_runtime_provider(requested=None, target_model=m or None)
    return _CACHED_RUNTIME


def _get_cached_tools(cfg: dict) -> list:
    """常驻 Tools 元数据单例（0ms 反射扫描）。"""
    global _CACHED_TOOLS
    if _CACHED_TOOLS is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_TOOLS is None:
                from hermes_cli.tools_config import _get_platform_tools
                _CACHED_TOOLS = sorted(_get_platform_tools(cfg, "cli"))
    return _CACHED_TOOLS


def _get_cached_fallback(cfg: dict):
    """常驻 Fallback 链单例。"""
    global _CACHED_FALLBACK
    if _CACHED_FALLBACK is None:
        with _CACHED_CFG_LOCK:
            if _CACHED_FALLBACK is None:
                from hermes_cli.fallback_config import get_fallback_chain
                _CACHED_FALLBACK = get_fallback_chain(cfg)
    return _CACHED_FALLBACK


def _resolve_dynamic_toolsets(goal: str, cfg: dict) -> list:
    """工具按需动态装配（消灭 18 个全量工具 Schema 导致的 2~3s TTFT 延迟与无关干扰）：
    - 意图分析：若目标涉及终端执行、写代码、构建部署等重度任务，挂载全量执行工具；
    - 方案/需求/澄清/知识检索阶段：仅挂载极简轻量核心工具集（Prompt 缩减 70%，TTFT 提速 60%）。
    """
    platform_tools = set(_get_cached_tools(cfg))
    execution_keywords = (
        "运行", "执行", "终端", "命令", "部署", "编译", "写代码", "脚本",
        "测试", "install", "run", "build", "npm", "git", "docker", "pip",
        "pytest", "terminal", "subagent", "delegate", "重写", "修复代码"
    )
    is_execution = any(k in goal.lower() for k in execution_keywords)
    if is_execution:
        return sorted(list(platform_tools))
    
    # 核心轻量对话与技能管理工具集（仅 6 个核心工具）
    core_tools = {"clarify", "skills", "web", "file", "memory", "session_search"}
    return sorted(list(core_tools & platform_tools))


def _prewarm_bridge_agent() -> None:
    """Bridge 启动预热（实例池化准备）：预先导入核心库与构建单例，消除首次请求 3~4s 冷启动。"""
    def _warmup_worker():
        try:
            t0 = time.monotonic()
            cfg = _get_cached_config()
            _get_cached_runtime(cfg)
            _get_cached_tools(cfg)
            _get_cached_fallback(cfg)
            _get_clarify_gateway()
            _get_shared_session_db()  # 预热 160MB state.db 的 SessionDB 冷建（6.6s 挪到启动期）
            from run_agent import AIAgent
            # 预热极简 AIAgent 实例以触发底层 httpx/openai/pydantic 模块编译与单例常驻
            _ = AIAgent(
                model="deepseek/deepseek-chat",
                quiet_mode=True,
                platform="cli",
                ephemeral_system_prompt="warmup",
            )
            print(f"[bridge] 实例池预热完成 · 耗时 {(time.monotonic() - t0)*1000:.1f}ms")
        except Exception as e:
            print(f"[bridge] 实例预热失败·忽略: {e}")

    threading.Thread(target=_warmup_worker, daemon=True, name="bridge-prewarm").start()


def _create_thread_local_session_db():
    """线程局部 SessionDB（避免 SQLite 跨线程冲突）：轻量创建 <0.2ms。"""
    from hermes_cli.oneshot import _create_session_db_for_oneshot
    return _create_session_db_for_oneshot()


# 全局共享 SessionDB 单例（实例池化核心）：160MB state.db 每次新建需 6.6s，
# SessionDB 内部自带 _lock 线程锁 + check_same_thread=False，可跨线程安全复用
_SHARED_SESSION_DB = None
_SHARED_SESSION_DB_LOCK = threading.Lock()


def _get_shared_session_db():
    """常驻 SessionDB 单例：首次懒加载（预热线程提前完成），后续 0ms 复用。"""
    global _SHARED_SESSION_DB
    if _SHARED_SESSION_DB is None:
        with _SHARED_SESSION_DB_LOCK:
            if _SHARED_SESSION_DB is None:
                _SHARED_SESSION_DB = _create_thread_local_session_db()
    return _SHARED_SESSION_DB


def _supports_reasoning_effort(model: str) -> bool:
    """自适应检测：目标模型/Provider 是否支持 reasoning_effort 参数（支柱二兼容层）。

    复用 Hermes 原生 capability 检查；检测失败时保守返回 False（不传该参数），
    由 CLARIFY_GATE_PROMPT 的 prompt 级限词约束兜底，绝不触发 400。
    """
    if not model:
        return False
    try:
        from hermes_cli.models import github_model_reasoning_efforts
        return bool(github_model_reasoning_efforts(model))
    except Exception:
        return False


def _cache_request_overrides(
    model: str,
    provider: str,
    overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """按实际路由过滤缓存字段，避免兼容接口收到不支持的 OpenAI 参数。

    DeepSeek 使用自身的隐式前缀缓存统计，不接受 OpenAI Responses 的
    ``prompt_cache_retention``。Bridge 不主动启用扩展保留；支持该能力的专用
    路由应由 Hermes provider adapter 自行协商。
    """
    cleaned = dict(overrides or {})
    normalized = f"{provider}/{model}".lower()
    if "deepseek" in normalized:
        cleaned.pop("prompt_cache_retention", None)
        cleaned.pop("prompt_cache_options", None)
        extra = cleaned.get("extra_body")
        if isinstance(extra, dict):
            extra = dict(extra)
            extra.pop("prompt_cache_retention", None)
            extra.pop("prompt_cache_options", None)
            cleaned["extra_body"] = extra
    return cleaned


# AI Lab 全局交互与澄清铁律：
# 1. 完整与详实输出：根据用户问题输出结构完整、详实准确的内容，严禁敷衍或人为截断。
# 2. 模糊需求极速澄清：判定为模糊开发/方案/决策需求，思考并调用 clarify 工具弹选项卡片辅助收敛。
# 3. 严禁手写文本问答：必须用 clarify 工具 choices 选项卡片点选。
# 4. IPD Gate-by-Gate 步进：单轮交付当前阶段所需产物，清晰递进。
# 5. 方案设计关卡（v3.1）：涉代码实现/系统开发的需求，收敛后必须先输出《方案设计》并 clarify 确认，确认后才可开工。

# 知识库检索纪律（2026-08-17 固化·对齐微信通道体验）：
# 事实/竞品/业务类问题必须先检索本地知识库（wiki/），严禁凭模型常识直接作答。
# 实测教训：search_files 的 pattern 中「|」是字面量不是正则 OR，会静默返回 0（vault-knowledge-retrieval
# 技能已警告但模型仍常踩坑）→ 必须在目标注入层强制约束。
KB_RETRIEVAL_DISCIPLINE = (
    "【知识库检索纪律·必须严格遵守】\n"
    "1. 回答事实/竞品/业务/技术类问题前，必须先检索本地知识库 wiki/ 目录（唯一真理源），"
    "知识库命中时以知识库内容为准作答；0 命中时才可凭模型常识或联网。\n"
    "2. 定位条目：用 ls 或 search_files(target='files') 按目录定位，如 wiki/竞品/华为.md、wiki/产品/*.md。\n"
    "3. search_files 搜索正文时 pattern 必须用【单个关键词】（如 \"华为\"），严禁用 | 连接多词"
    "（管道符是字面量，会静默返回 0 结果，即使文件存在）。\n"
    "4. 0 命中时二次核验：先 ls 目标目录 + read_file 直接读候选文件，确认确实无条目后再判定，"
    "严禁仅凭一次搜索就断言\"知识库无此条目\"。\n"
    "5. 命中知识库后，输出完整 Markdown（标题/列表/加粗/表格/引用），确保与微信端体验一致。"
)

CLARIFY_GATE_PROMPT = f"""【AI Lab 全局交互与对话规范】
1. 【输出完整详实】：根据用户指令提供结构清晰、逻辑完整、信息详实的解答与方案。
2. 【Drill-me 多轮收敛】：用户输入范围过大、缺关键边界的开发/方案需求（如仅有一句"做电商平台"、"开发操作系统"）时，必须进入 Drill-me；每轮只调用一次 clarify，提出一个聚焦问题并给出 2~4 个结构化选项。
3. 【选项是澄清答案，不是新指令】：clarify 返回的选项文本只是在回答当前问题。收到选择后，必须把答案并入需求状态并继续确认下一个尚未明确的维度；严禁脱离原始需求，单独解释或执行该选项文本。
4. 【收敛门槛】：Drill-me 至少完成 {DRILL_ME_MIN_ROUNDS} 轮、最多 {DRILL_ME_MAX_ROUNDS} 轮。依次覆盖目标用户/核心场景、产品范围/优先级、数据与技术约束、验收标准等关键维度；不得一问即答，也不得重复询问已确认内容。
5. 【需求确认单】：达到最少轮次且关键维度足够明确后，先输出且只输出一份 Markdown 需求确认单，再调用 clarify 做最终确认。确认单格式必须为：二级标题“## 需求确认单”；紧接两列表格，表头固定为“确认维度 | 已确认需求”，用 5~7 行完整覆盖产品形态、目标用户与场景、MVP 范围、技术路线、数据/集成约束、验收标准。单元格文字简明，禁止在表格前后重复复述。最终 clarify 问题固定为“以上需求确认单是否准确？”，选项至少包含“确认，进入方案设计”和“需要修改”。用户确认后才可输出方案；选择修改则继续 clarify 具体修改项。
6. 【交互形式】：收敛期间禁止用普通正文手写问题，下一问必须继续调用 clarify，以便前端展示下一张选项卡。
7. 【创建智能体标准流程】：（用户提出"创建/做一个…的agent/智能体"时强制执行）
   - 用 skill_manage(action=create) 创建租户专属技能作为该 Agent 的载体（技能即 Agent，插件化落地）；
   - 正文 = 该 Agent 的角色提示词：职责、工作流、调用哪些底层技能、输出格式；
   - 回复用户：Agent 已创建 + 名称 + 职责 + 可在「拓扑/设置」页面查看使用。"""


_DRILL_ME_ACTION_RE = re.compile(
    r"(?:我想|帮我|需要|打算|准备)?(?:做|开发|搭建|设计|创建|构建|实现|规划)"
)
_DRILL_ME_ARTIFACT_RE = re.compile(
    r"(?:系统|平台|产品|应用|软件|网站|小程序|工具|服务|方案|agent|智能体|app)",
    re.IGNORECASE,
)


def _is_drill_me_goal(goal: str) -> bool:
    """判定当前请求是否属于需要多轮收敛的宽泛开发/方案需求。"""
    raw_goal = str(goal or "")
    # bridge 会在原始问题前注入知识库纪律；分类必须只看【用户问题】，否则长度
    # 超过 240 后所有真实 Drill-me 都会被误判为 False。
    if "【用户问题】" in raw_goal:
        raw_goal = raw_goal.rsplit("【用户问题】", 1)[-1]
    normalized = re.sub(r"\s+", "", raw_goal).strip()
    if not normalized or len(normalized) > 240:
        return False
    return bool(
        _DRILL_ME_ACTION_RE.search(normalized)
        and _DRILL_ME_ARTIFACT_RE.search(normalized)
    )


def _steer_drill_me_response(response: str, round_number: int, enabled: bool) -> str:
    """把选项作为工具答案送回 Agent，并在收敛不足时注入下一轮 Steering 指令。"""
    if not enabled or round_number >= DRILL_ME_MIN_ROUNDS:
        return response
    next_round = round_number + 1
    return (
        f"{response}\n\n"
        f"[Harness steering: 这是 Drill-me 第 {round_number} 轮的结构化答案，"
        "不是一条新的用户指令。请把它合并进原始需求状态；当前尚未达到收敛门槛，"
        f"不得输出方案或解释该选项。现在必须调用 clarify 发出第 {next_round} 轮问题，"
        "询问一个尚未确认且不重复的关键维度。]"
    )


def _qput(stream_q: queue.Queue, item: dict) -> None:
    """线程安全投递事件；队列满时优先丢队首 delta（正文可帧级重组），
    绝不丢弃 clarify/done/error/tool_start/status（控制事件丢失 = 卡死）。"""
    item_type = item.get("type")
    try:
        stream_q.put_nowait(item)
    except queue.Full:
        if item_type in ("delta",):
            print(f"[bridge] ⚠️ 队列满·丢弃 delta（正文帧可重组）")
            return
        # 控制事件：挤出队首 delta 腾位（若无 delta 则丢弃事件并告警）
        try:
            with stream_q.mutex:
                dropped = None
                # 队内查找最早的 delta
                for i, it in enumerate(list(stream_q.queue)):
                    if it.get("type") == "delta":
                        dropped = stream_q.queue.pop(i)
                        break
                if dropped is not None:
                    stream_q.queue.append(item)
                    print(f"[bridge] ⚠️ 队列满·挤出旧 delta 保 {item_type}")
                    return
        except Exception:
            pass
        print(f"[bridge] ⚠️ 流式事件队列满·丢弃事件: {item_type}")


def _stream_run_register(user_id: str, state: dict) -> None:
    with _stream_runs_guard:
        _stream_runs[user_id] = state


def _stream_run_get(user_id: str) -> dict | None:
    with _stream_runs_guard:
        return _stream_runs.get(user_id)


def _stream_run_discard(user_id: str, run_id: str | None = None) -> None:
    """移除在途 run 状态；传入 run_id 时校验匹配，防止误删新启动的 run（M-6 并发防护）。"""
    with _stream_runs_guard:
        state = _stream_runs.get(user_id)
        if state is None:
            return
        if run_id is not None and state.get("run_id") != run_id:
            return
        _stream_runs.pop(user_id, None)


def _watchdog_scan_once(now: float | None = None) -> list[tuple[str, str | None]]:
    """watchdog 单次扫描：返回应中断的 (user_id, run_id) 列表（detached 且超时）。

    独立纯函数便于单测（G-10 压缩测试直接驱动）；attached run 由 SSE generator
    自身守护（客户端连接存在），不在 watchdog 管辖范围。
    """
    now = now if now is not None else time.monotonic()
    victims: list[tuple[str, str | None]] = []
    with _stream_runs_guard:
        for uid, state in list(_stream_runs.items()):
            if state.get("attached", True):
                continue
            start_ts = state.get("start_ts") or 0
            if now - start_ts > STREAM_MAX_DURATION_SECONDS:
                victims.append((uid, state.get("run_id")))
    return victims


def _watchdog_loop_step() -> None:
    """watchdog 单轮执行：扫描 → 逐个 interrupt + discard（可单测驱动，G-10）。

    interrupt+discard 复用 _interrupt_and_discard（status 命中 timeout 同路径）。
    """
    for uid, run_id in _watchdog_scan_once():
        print(
            f"[bridge] watchdog: detached run 超 {STREAM_MAX_DURATION_SECONDS}s"
            f"·interrupt+discard user={uid}"
        )
        _interrupt_and_discard(uid, run_id)


def _watchdog_loop() -> None:
    """独立守护线程：周期扫描 detached runs，超时 interrupt + discard（第 1 处中断入口）。"""
    while True:
        time.sleep(WATCHDOG_INTERVAL_SECONDS)
        _watchdog_loop_step()


def _emit_tool_start(stream_q: queue.Queue, tool_call_id, function_name, function_args) -> None:
    """工具启动事件（模块级可测）：过滤内部工具 + 载荷治理（仅 preview/label）。

    代码块唤起（对齐官方 gateway fenced code block 语义）：代码型工具
    （terminal/write_file/patch/execute_code）附 code 字段（截断预览），
    前端渲染为代码块卡片；非代码工具 code=None。
    """
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

    code: str | None = None
    try:
        args = function_args or {}
        if function_name == "terminal":
            code = str(args.get("command") or "").rstrip()
        elif function_name in ("write_file", "patch"):
            content = args.get("content") or args.get("new_string") or ""
            content_s = str(content)
            code = content_s[:400] + ("\n…（预览截断）" if len(content_s) > 400 else "")
        elif function_name == "execute_code":
            content_s = str(args.get("code") or "")
            code = content_s[:400] + ("\n…（预览截断）" if len(content_s) > 400 else "")
    except Exception:
        code = None
    if code is not None and not code.strip():
        code = None

    _qput(stream_q, {
        "type": "tool_start",
        "id": tool_call_id,
        "tool": function_name,
        "label": label,
        "code": code,
    })


def _tenantize_created_skill(function_args) -> None:
    """技能创建租户化：skill_manage(action=create) 后把新技能从全局分类目录
    迁移到 skills/tenants/<TENANT_ID>/<name>/（租户设置页只显示租户专属技能）。

    TENANT_ID 为空/public 时跳过（public 环境技能留在全局库）。
    """
    try:
        args = function_args or {}
        if args.get("action") != "create" or not args.get("name"):
            return
        tenant = os.environ.get("TENANT_ID", "").strip()
        if not tenant or tenant == "public":
            return
        name = str(args["name"]).strip()
        if not name:
            return
        home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
        skills_root = home / "skills" if home.name == ".hermes" else home / ".hermes" / "skills"
        # 新技能目录可能在分类子目录（<category>/<name>）或顶层（<name>）
        candidates = list(skills_root.glob(f"*/{name}")) + list(skills_root.glob(name))
        for src in candidates:
            if src.is_dir() and (src / "SKILL.md").exists() and "tenants" not in src.parts:
                dst = skills_root / "tenants" / tenant / name
                dst.parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    shutil.rmtree(str(dst))
                shutil.move(str(src), str(dst))
                print(f"[bridge] 技能租户化: {name} → tenants/{tenant}/")
                return
    except Exception as e:
        print(f"[bridge] 技能租户化失败: {e}")


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
    _build_t0 = time.monotonic()  # 延迟打点：构建入口
    from hermes_cli.config import load_config
    from hermes_cli.runtime_provider import resolve_runtime_provider
    from hermes_cli.tools_config import _get_platform_tools
    from hermes_cli.fallback_config import get_fallback_chain
    from hermes_cli.oneshot import _create_session_db_for_oneshot
    from run_agent import AIAgent

    cfg = _get_cached_config()  # 常驻单例：0ms 读盘
    model_cfg = cfg.get("model") or {}
    if isinstance(model_cfg, str):
        cfg_model = model_cfg
    else:
        cfg_model = model_cfg.get("default") or model_cfg.get("model") or ""

    runtime = _get_cached_runtime(cfg)  # 常驻单例：0ms 解析
    toolsets_list = _resolve_dynamic_toolsets(goal, cfg)  # 工具按需动态装配（极简 6 工具 vs 全量 18 工具）
    _fb = _get_cached_fallback(cfg)  # 常驻单例
    session_db = _get_shared_session_db()  # 常驻单例（预热完成）：消灭 6.6s SessionDB 冷建
    drill_me_enabled = _is_drill_me_goal(goal)
    clarify_round = 0

    def _clarify_cb(question: str, choices=None, multi_select: bool = False) -> str:
        """clarify 回调：注册进 clarify_gateway → 推 clarify 事件 → 阻塞等用户响应。"""
        nonlocal clarify_round
        cg = _get_clarify_gateway()

        clarify_id = uuid.uuid4().hex[:10]
        # 跨版本兼容：服务器 v0.19.0 register() 无 multi_select 参数（本地 v0.19.1 有）
        try:
            cg.register(
                clarify_id=clarify_id,
                session_key=user_id,
                question=question,
                choices=list(choices) if choices else None,
                multi_select=bool(multi_select),
            )
        except TypeError:
            cg.register(
                clarify_id=clarify_id,
                session_key=user_id,
                question=question,
                choices=list(choices) if choices else None,
            )
        _qput(stream_q, {
            "type": "clarify",
            "clarify_id": clarify_id,
            "question": question,
            "choices": list(choices) if choices else None,
            "multi_select": bool(multi_select) and bool(choices),
        })
        print(f"[bridge] clarify-REGISTER cid={clarify_id} user={user_id} q={str(question)[:30]}")
        # 记录 clarify 发出时间戳：resolve 失败分类依据（expired vs no_pending）
        run_state = _stream_run_get(user_id)
        if run_state:
            with _stream_runs_guard:
                run_state["clarify_issued"] = time.monotonic()
        resp = cg.wait_for_response(clarify_id, timeout=float(CLARIFY_TIMEOUT_SECONDS))
        print(f"[bridge] clarify-WAIT-RETURN cid={clarify_id} resp={str(resp)[:40]!r}")
        if resp is None or resp == "":
            return (
                f"[user did not respond within {CLARIFY_TIMEOUT_SECONDS}s. "
                "Make the most reasonable assumption and continue.]"
            )
        clarify_round += 1
        # Feedback：把收敛轮次写入在途状态，便于状态检查与线上诊断。
        with _stream_runs_guard:
            run_state = _stream_runs.get(user_id)
            if run_state:
                run_state["clarify_round"] = clarify_round
                run_state["drill_me"] = drill_me_enabled
        print(
            f"[bridge] clarify-FEEDBACK user={user_id} round={clarify_round} "
            f"drill_me={drill_me_enabled}"
        )
        # Steering Loop：前两轮明确禁止提前作答，并驱动 Agent 再次调用 clarify。
        return _steer_drill_me_response(str(resp), clarify_round, drill_me_enabled)

    def _delta_cb(text) -> None:
        if text:
            _qput(stream_q, {"type": "delta", "content": text})

    def _reasoning_cb(text) -> None:
        # 思考流治理（2026-08-17 固化）：禁止向前端逐 token 倾泻原始思考长文（防长条铺屏与无谓等待）
        # 思考期仅由 status(reasoning) 与 tool_start 驱动极简胶囊单行，正文生成完成后一口气出结果
        pass

    def _tool_start_cb(tool_call_id, function_name, function_args) -> None:
        _emit_tool_start(stream_q, tool_call_id, function_name, function_args)

    def _tool_complete_cb(tool_call_id, function_name, function_args, result) -> None:
        # 载荷治理：不发 raw result（对齐 api_server 契约·防内部信息泄露）
        _emit_tool_complete(stream_q, tool_call_id, function_name, function_args, result)
        # 技能创建租户化：skill_manage(action=create) 完成后把新技能迁移到 tenants/<tenant>/
        # （租户设置页只显示租户专属技能——用户创建的技能自动归租户，不留在 public）
        if function_name == "skill_manage":
            _tenantize_created_skill(function_args)

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
        request_overrides=_cache_request_overrides(cfg_model, str(runtime.get("provider") or "")),
        ephemeral_system_prompt=CLARIFY_GATE_PROMPT,
        clarify_callback=_clarify_cb,
        stream_delta_callback=_delta_cb,
        reasoning_callback=_reasoning_cb,
        tool_start_callback=_tool_start_cb,
        tool_complete_callback=_tool_complete_cb,
        # 支柱二：iOS 通道请求级思考预算覆盖（不影响微信 gateway 的 config medium）
        # - Hermes 原生 resolve_reasoning_config 处理 DeepSeek 映射；不支持的 Provider 自动忽略
        reasoning_config={"effort": "minimal"},
    )

    # 支柱二兜底：若模型能力检测不支持 reasoning_effort 字段注入，保留 prompt 级限词约束
    try:
        if not _supports_reasoning_effort(cfg_model):
            pass  # DeepSeek 系不走 reasoning_effort 字段，reasoning_config 已覆盖
    except Exception:
        pass

    build_ms = (time.monotonic() - _build_t0) * 1000.0
    print(f"[bridge] agent_build_ms={build_ms:.1f} user={user_id}")

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
        # 进程内 agent 会话映射（P0 断点恢复关键）：agent 可能自动创建新 session
        # （hermes_sid=None 首请求），创建后立即写回映射 → status 端点可查 completed/running，
        # 前端 probeAndResume 断点恢复不依赖 SSE 连接。
        agent_sid = getattr(agent, "session_id", None) or hermes_sid
        if agent_sid:
            _update_session_mapping(user_id, agent_sid)
        # 第二帧状态：agent 构建完成（build 返回后、run_conversation 前）→ 进入推理
        _qput(stream_q, {"type": "status", "phase": "reasoning", "detail": "正在理解需求…"})
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


def _busy_sse(user_id: str):
    """并发防护事件流：任务已在执行中（running 状态帧 + done 终帧）。

    前端收到后不启动新 agent，转为轮询 status 端点跟踪原任务（G-6/G-4）。
    """
    yield f"data: {json.dumps({'type': 'status', 'phase': 'running', 'detail': '任务已在执行中…'}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'type': 'done', 'session_id': user_id, 'answer': ''}, ensure_ascii=False)}\n\n"


def _sse_from_in_process(user_id: str, goal: str):
    """SSE 事件生成器：agent 线程事件 → queue → asyncio 逐帧输出（thread-safe）。

    保活机制 v6：
    - run 状态带 run_id / attached=True / start_ts（watchdog 寻址与超时判定）
    - 正常结束（done/error 帧）→ discard（run_id 校验防误删）
    - SSE 断连（客户端断开触发 finally）→ 仅 detach（attached=False，不 interrupt），
      agent 线程继续后台完成，结果落 state.db，由 status 端点回读 + watchdog 兜底超时
    """
    # 知识库检索纪律注入（仅 bridge/iOS 通道）：对齐微信通道的知识库体验，
    # 强制模型先查 wiki 再作答、单关键词搜索、0 命中二次核验
    goal = KB_RETRIEVAL_DISCIPLINE + "\n\n【用户问题】" + goal
    stream_q: queue.Queue = queue.Queue(maxsize=STREAM_QUEUE_CAPACITY)
    agent_holder: list = [None]
    start_ts = time.monotonic()
    last_keepalive_ts = time.monotonic()
    run_id = uuid.uuid4().hex[:12]

    # 首帧状态（worker 启动前入队 → SSE 首帧即 boot，<10ms 真实构建状态）
    _qput(stream_q, {"type": "status", "phase": "boot", "detail": "正在初始化推理引擎…"})

    hermes_sid = _resolve_hermes_session(user_id)

    worker = threading.Thread(
        target=_run_agent_sync,
        args=(goal, user_id, hermes_sid, stream_q, agent_holder),
        daemon=True,
        name=f"agent-stream-{user_id[:12]}",
    )
    worker.start()
    _stream_run_register(user_id, {
        "agent_holder": agent_holder,
        "queue": stream_q,
        "attached": True,
        "start_ts": start_ts,
        "run_id": run_id,
    })

    finished = False
    try:
        first_thought_recorded = False
        while True:
            now = time.monotonic()

            # keepalive 注释帧（对齐 Hermes 30s 常量）
            if now - last_keepalive_ts >= STREAM_KEEPALIVE_SECONDS:
                yield ": keepalive\n\n"
                last_keepalive_ts = now

            try:
                item = stream_q.get(timeout=0.5)
            except queue.Empty:
                if not worker.is_alive() and stream_q.empty():
                    print(f"[bridge] SSE-BREAK worker_dead queue_empty user={user_id}")
                    break
                continue

            if item is None:
                print(f"[bridge] SSE-BREAK item_none user={user_id}")
                break
            # 延迟打点：start_ts 至首个 thought 出队差（真实思维链首帧延迟）
            if not first_thought_recorded and item.get("type") == "thought":
                first_thought_recorded = True
                print(
                    f"[bridge] first_thought_ms={(time.monotonic() - start_ts) * 1000.0:.1f} user={user_id}"
                )
            if item.get("type") in ("done", "error", "clarify", "status"):
                print(f"[bridge] SSE-YIELD type={item.get('type')} user={user_id} worker_alive={worker.is_alive()} qsize={stream_q.qsize()}")
            yield f"data: {json.dumps(item, ensure_ascii=False)}\n\n"
            # 终帧（done/error）后流自然结束：标记 finished 供 finally 分流 discard
            if item.get("type") in ("done", "error"):
                finished = True
                break
    finally:
        # 断连/结束分流（保活机制 v6）：
        # - 任务已结束（done/error/worker 退出）→ discard 清理状态
        # - 任务仍在跑（客户端断连 detach）→ 仅 attached=False，不 interrupt，
        #   交给 watchdog 守护（超时 interrupt+discard）与 status 端点回读
        if finished or not worker.is_alive():
            _stream_run_discard(user_id, run_id)
        else:
            with _stream_runs_guard:
                state = _stream_runs.get(user_id)
                if state is not None and state.get("run_id") == run_id:
                    state["attached"] = False
                    print(
                        f"[bridge] SSE 断连 detach: user={user_id} run={run_id}"
                        "·agent 后台继续·watchdog 兜底"
                    )


class ClarifyResolveRequest(BaseModel):
    session_id: str = Field(..., min_length=1)
    response: str = Field(..., min_length=1)
    clarify_id: Optional[str] = Field(None, max_length=32)


class CancelRequest(BaseModel):
    session_id: str = Field(..., min_length=1)


@app.post("/v1/chat/clarify")
async def clarify_resolve(body: ClarifyResolveRequest):
    """澄清响应提交：解锁阻塞的 agent 线程（不占 session 锁·thread-safe）。

    失败分类（reason 三态，G-7）：
    - rejected   → 存在 pending clarify 但响应被拒（多选卡片收到自由文本）
    - expired    → 曾发出 clarify 但已超时被 wait_for_response 清理（卡片过期）
    - no_pending → 当前无任何 pending clarify（从未发出或已消费）
    """
    cg = _get_clarify_gateway()

    # 多步 Clarify 精确寻址（P0 根治）：优先按 clarify_id 直连 resolve——
    # 官方 get_pending_for_session 返回 oldest entry（含已消费），多卡场景必错配；
    # 带 clarify_id 则精确解锁本次卡对应的 agent 等待线程。
    if body.clarify_id:
        ok = cg.resolve_gateway_clarify(body.clarify_id, body.response)
        print(f"[bridge] clarify-RESOLVE cid={body.clarify_id} session={body.session_id} ok={ok}")
        if ok:
            return {"ok": True}
        # clarify_id 未命中（已超时/不存在）→ 回退 session 级 resolve（兼容旧前端）
    ok = cg.resolve_text_response_for_session(body.session_id, body.response)
    print(f"[bridge] clarify-RESOLVE-SESSION session={body.session_id} ok={ok}")
    if ok:
        return {"ok": True}

    run = _stream_run_get(body.session_id)
    if cg.has_pending(body.session_id):
        reason = "rejected"
    else:
        clarify_issued = run.get("clarify_issued") if run else None
        if clarify_issued is not None and (time.monotonic() - clarify_issued) <= CLARIFY_TIMEOUT_SECONDS + 60:
            reason = "expired"
        else:
            reason = "no_pending"
    if run:
        _qput(run["queue"], {"type": "clarify_rejected"})
    return {"ok": False, "reason": reason}


@app.post("/v1/chat/stream/cancel")
async def stream_cancel(body: CancelRequest):
    """取消在途流式：interrupt agent + 强制解锁 clarify + 清理状态。"""
    cg = _get_clarify_gateway()

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
        _stream_run_discard(body.session_id, run.get("run_id"))
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
    goal = _expand_requested_skill(body.goal, body.skill_id)
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
                    reply, new_sid = await asyncio.to_thread(_run_hermes, goal, None)
                    effective_sid = new_sid
                    if new_sid:
                        _update_session_mapping(user_id, new_sid)
                else:
                    reply, new_sid = await asyncio.to_thread(_run_hermes, goal, hermes_sid)
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
async def chat_status(user_id: str, consume: int = 0, offset: int = 0):
    """状态回读端点（只读·不写 state.db）。

    通过 user_id 锁定 hermes_session_id，返回四元组快照（方案 v5）：
    phase / latest_step / reasoning / clarify（附 last_message_id 供 offset 推进）。
    - consume=1 时，completed 结果顺带推进消费水位线（0ms 断点回读后标记已消费）。
    - offset=N 时，reasoning 仅返回消息 id>N 的新条（增量轮询）。
    """
    hermes_sid = _user_session_map.get(user_id)
    result = await asyncio.to_thread(_query_status, hermes_sid, user_id, offset)
    if consume == 1 and result.get("status") == "completed":
        _mark_consumed(user_id, hermes_sid)
    return result


@app.post("/v1/workflows/plan")
async def workflow_plan(
    body: WorkflowPlanRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """让 Hermes 将自然语言需求编译为结构化 DAG；平台仍负责安全校验。"""
    _require_internal(x_hermes_internal_token)
    prompt = (
        "你是 Hermes 工作流规划器。将需求编译为通用、可编辑、无环的 WorkflowDSLPlan。\n"
        "只输出一个 JSON 对象，不要 Markdown 代码围栏或解释。\n"
        "根字段必须为 plan_id/name/version/nodes/edges。每个节点必须包含 "
        "id/node_type/name/parameters；node_type 只能是 KNOWLEDGE_RETRIEVAL、"
        "LLM_INFERENCE、PROMPT_TRANSFORM、FILTER_PASS、AGGREGATION、OUTPUT_FORMAT。\n"
        "parameters 必须包含 agent_id、max_tokens、knowledge_scope、allow_network，并按需包含 "
        "query/instruction/output_format/requires_review。最后必须有 FILTER_PASS 与 OUTPUT_FORMAT。\n"
        f"workflow_id={body.workflow_id}\n标题={body.title}\n目标={body.description}\n"
        f"交付物={body.deliverable}\n知识范围={json.dumps(body.knowledge_scope, ensure_ascii=False)}\n"
        f"可用 Agent={json.dumps(body.allowed_agents, ensure_ascii=False)}\n"
        f"联网权限={body.allow_network}\n总 Token 上限={body.max_tokens}\n"
        f"修改意见={body.revision_note or '无'}"
    )
    reply, _, usage = await asyncio.to_thread(
        _run_hermes_with_usage,
        prompt[:MAX_INPUT],
        None,
    )
    try:
        plan = _extract_json_object(reply)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return {
        "plan": plan,
        "usage": _usage_delta(usage),
        "route": {
            "model": usage.get("model"),
            "provider": usage.get("provider"),
            "reason": "Hermes 多模型路由根据规划任务与当前 Profile 自动选择",
        },
    }


@app.post("/v1/workflow-runs")
async def start_workflow_run(
    body: WorkflowRunRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    """幂等启动或恢复 Hermes 工作流 Run。"""
    _require_internal(x_hermes_internal_token)
    _workflow_order(body.plan)
    with _workflow_runs_lock:
        current = _workflow_runs.get(body.execution_id)
        if current:
            if current.get("idempotency_key") != body.idempotency_key:
                raise HTTPException(status_code=409, detail="execution idempotency conflict")
            if current.get("status") in {"interrupted", "queued", "running"}:
                current["cancel_requested"] = False
                _start_workflow_thread(body.execution_id)
            return {
                "execution_id": body.execution_id,
                "status": current.get("status"),
                "hermes_session_id": current.get("hermes_session_id"),
            }
        run = body.model_dump(mode="json")
        run.update(
            {
                "status": "queued",
                "error": None,
                "events": [],
                "next_seq": 1,
                "nodes": {
                    str(node["id"]): {"status": "pending", "attempt": 0}
                    for node in body.plan.get("nodes") or []
                },
                "usage": {},
                "cancel_requested": False,
                "hermes_session_id": None,
            }
        )
        _workflow_runs[body.execution_id] = run
        _workflow_event(run, "run_queued", message="Hermes 工作流已入队")
        _start_workflow_thread(body.execution_id)
    return {"execution_id": body.execution_id, "status": "queued"}


@app.get("/v1/workflow-runs/{execution_id}")
async def get_workflow_run(
    execution_id: str,
    after_seq: int = Query(0, ge=0),
    x_hermes_internal_token: str | None = Header(None),
):
    _require_internal(x_hermes_internal_token)
    with _workflow_runs_lock:
        run = _workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        return {
            "execution_id": execution_id,
            "status": run.get("status"),
            "error": run.get("error"),
            "hermes_session_id": run.get("hermes_session_id"),
            "usage": run.get("usage") or {},
            "nodes": run.get("nodes") or {},
            "events": [
                event for event in run.get("events") or []
                if int(event.get("seq") or 0) > after_seq
            ],
        }


@app.post("/v1/workflow-runs/{execution_id}/cancel")
async def cancel_workflow_run(
    execution_id: str,
    x_hermes_internal_token: str | None = Header(None),
):
    _require_internal(x_hermes_internal_token)
    with _workflow_runs_lock:
        run = _workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        run["cancel_requested"] = True
        _workflow_event(run, "cancel_requested", message="已请求 Hermes 取消执行")
        return {"ok": True, "status": run.get("status")}


@app.post("/v1/workflow-runs/{execution_id}/retry")
async def retry_workflow_run(
    execution_id: str,
    body: WorkflowRetryRequest,
    x_hermes_internal_token: str | None = Header(None),
):
    _require_internal(x_hermes_internal_token)
    with _workflow_runs_lock:
        run = _workflow_runs.get(execution_id)
        if not run:
            raise HTTPException(status_code=404, detail="workflow run not found")
        order = _workflow_order(run["plan"])
        target = body.from_node_id
        if target is None:
            target = next(
                (node_id for node_id in order if (run.get("nodes") or {}).get(node_id, {}).get("status") == "failed"),
                None,
            )
        if target not in order:
            raise HTTPException(status_code=409, detail="no retryable node")
        start = order.index(target)
        for node_id in order[start:]:
            run["nodes"][node_id] = {"status": "pending", "attempt": run["nodes"].get(node_id, {}).get("attempt", 0)}
        run["status"] = "queued"
        run["error"] = None
        run["cancel_requested"] = False
        _workflow_event(run, "retry_queued", node_id=target, message="失败节点已重新入队")
        _start_workflow_thread(execution_id)
        return {"ok": True, "status": "queued", "from_node_id": target}


@app.get("/v1/skills")
async def list_skills(tenant: str = "public"):
    """技能库列表（租户隔离·软隔离）：读 HERMES_HOME/skills。

    目录约定：
    - skills/<category>/<name>/SKILL.md          → public 技能（全局分类）
    - skills/tenants/<tenant>/<name>/SKILL.md   → 租户专属技能（切片隔离）
    tenant 过滤：public 返回全局分类技能；指定 tenant 返回其专属技能 + public 技能。
    """
    home = Path(os.environ.get("HERMES_HOME", str(Path.home())))
    # HERMES_HOME 已是 ~/.hermes（含 .hermes）；未设置时补 .hermes
    skills_root = home / "skills" if home.name == ".hermes" else home / ".hermes" / "skills"
    items = []
    if not skills_root.exists():
        return {"skills": [], "tenant": tenant}
    for skill_md in sorted(skills_root.rglob("SKILL.md")):
        rel = skill_md.relative_to(skills_root)
        parts = rel.parts
        # parts: (名称, SKILL.md) | (分类, 名称, SKILL.md) | (tenants, <tenant>, 名称, SKILL.md)
        is_tenant = len(parts) >= 4 and parts[0] == "tenants"
        skill_tenant = parts[1] if is_tenant else "public"
        # 租户隔离：public 查询只返回全局技能；租户查询只返回该租户专属（互不含）
        if tenant == "public":
            if is_tenant:
                continue
        elif skill_tenant != tenant:
            continue
        if len(parts) == 2:
            name, category = parts[0], ""
        elif is_tenant:
            name, category = parts[2], parts[1]
        else:
            name, category = parts[1], parts[0]
        desc = ""
        created = None
        try:
            lines = skill_md.read_text(encoding="utf-8", errors="replace").splitlines()
            for line in lines:
                low = line.lower()
                if low.startswith("description:") and not desc:
                    desc = line.split(":", 1)[1].strip()
                if low.startswith("date:") and created is None:
                    created = line.split(":", 1)[1].strip()
        except Exception:
            pass
        items.append({
            "name": name,
            "description": desc[:120],
            "category": category,
            "tenant": skill_tenant,
            "created_at": created,
        })
    return {"skills": items, "tenant": tenant}


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "hermes-bridge",
        "version": "v6.0",
        "sessions": len(_user_session_map),
        "workflow_runs": len(_workflow_runs),
        "workflow_orchestration": True,
        "streaming": True,
        "ws_pty": HERMES_WS_URL,
    }


if __name__ == "__main__":
    # 实例池预热：后台线程预加载核心库与 AIAgent 单例，消除首次请求 3~4s 冷启动
    _prewarm_bridge_agent()
    uvicorn.run(app, host="0.0.0.0", port=9118)
