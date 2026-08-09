"""tests/test_isolation.py — 子 Agent 纯净沙箱隔离模式测试。

覆盖:
1. pure 参数映射断言（ISOLATION_ARGS 内容）
2. standard 无隔离参数（空列表）
3. kb 参数映射断言
4. isolation=invalid 返回 422（Pydantic pattern 校验）
5. Agent 模型 isolation 字段默认值
6. agent_engine.call_hermes 透传 isolation 参数

注: 本文件在 conftest 注入 SQLite 前打补丁 backend.db, 绕过 pool_size
与 SQLite NullPool 不兼容的预存问题(与本次 isolation 任务无关)。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 预存问题规避: SQLite 不支持 pool_size, 在 backend.db 模块级执行前替换
# create_async_engine 调用参数。
# ---------------------------------------------------------------------------
_SQLITE_URL = os.environ.get("DATABASE_URL", "")
if _SQLITE_URL.startswith("sqlite"):
    # 拦截 create_async_engine, 剥离 pool_size/pool_pre_ping
    from sqlalchemy.ext import asyncio as _sa_asyncio
    _orig_create = _sa_asyncio.create_async_engine

    def _patched_create(url, **kw):
        kw.pop("pool_size", None)
        kw.pop("pool_pre_ping", None)
        return _orig_create(url, **kw)

    _sa_asyncio.create_async_engine = _patched_create  # type: ignore

# 让 scripts/hermes_bridge.py 可被 import
REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import pytest
from pydantic import ValidationError

import hermes_bridge  # noqa: E402


# ---------------------------------------------------------------------------
# 1. pure 模式：参数映射断言
# ---------------------------------------------------------------------------
def test_isolation_args_pure_contains_all_flags():
    """pure 模式必须包含 ignore-user-config / ignore-rules / safe-mode + 收窄工具集。"""
    args = hermes_bridge.ISOLATION_ARGS["pure"]
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert "--safe-mode" in args
    assert "-t" in args
    idx = args.index("-t")
    assert args[idx + 1] == "core,web"


# ---------------------------------------------------------------------------
# 2. standard 模式：无隔离参数
# ---------------------------------------------------------------------------
def test_isolation_args_standard_is_empty():
    """standard 模式必须保持空列表（向后兼容·无隔离）。"""
    assert hermes_bridge.ISOLATION_ARGS["standard"] == []


# ---------------------------------------------------------------------------
# 3. kb 模式：参数映射断言
# ---------------------------------------------------------------------------
def test_isolation_args_kb_contains_memory_toolset():
    """kb 模式 = 纯净 + 显式 RAG（memory 工具集）。"""
    args = hermes_bridge.ISOLATION_ARGS["kb"]
    assert "--ignore-user-config" in args
    assert "--ignore-rules" in args
    assert "--safe-mode" not in args  # kb 需保留 memory 工具
    assert "-t" in args
    idx = args.index("-t")
    assert args[idx + 1] == "core,web,memory"


# ---------------------------------------------------------------------------
# 4. isolation=invalid → 422 (Pydantic pattern 校验)
# ---------------------------------------------------------------------------
def test_invalid_isolation_raises_validation_error():
    """非法 isolation 值必须被 Pydantic pattern 校验拦截（FastAPI 会转 422）。"""
    with pytest.raises(ValidationError) as exc:
        hermes_bridge.GoalRequest(goal="hello", isolation="invalid-mode")
    # 错误位置指向 isolation 字段
    errs = exc.value.errors()
    assert any(e["loc"] == ("isolation",) for e in errs)


@pytest.mark.asyncio
async def test_valid_isolation_modes_accepted(monkeypatch):
    """三种合法模式都通过 GoalRequest 校验 + chat 路由返回对应 isolation。"""
    monkeypatch.setattr(
        hermes_bridge, "_run_hermes",
        lambda goal, session, isolation: (f"echo:{isolation}", session or ""),
    )
    for mode in ("pure", "standard", "kb"):
        req = hermes_bridge.GoalRequest(goal="hi", isolation=mode)
        assert req.isolation == mode
        resp = await hermes_bridge.chat(req)
        assert resp["isolation"] == mode


# ---------------------------------------------------------------------------
# 5. Agent 模型 isolation 字段默认值 = pure
# ---------------------------------------------------------------------------
def test_agent_model_isolation_default_is_pure():
    """Agent DB 模型 isolation 字段默认 'pure'（新建 Agent 默认纯净沙箱）。"""
    from backend.models.agent import Agent

    col = Agent.__table__.columns["isolation"]
    assert col.default is not None
    assert col.default.arg == "pure"


# ---------------------------------------------------------------------------
# 6. agent_engine.call_hermes 透传 isolation 参数
# ---------------------------------------------------------------------------
def test_agent_engine_call_hermes_passes_isolation(monkeypatch):
    """agent_engine.call_hermes 必须把 isolation 透传到 bridge HTTP 请求体。"""
    from backend.services import agent_engine

    captured = {}

    class FakeResp:
        status_code = 200
        def json(self): return {"reply": "ok"}
        @property
        def text(self): return "ok"

    def fake_post(url, json=None, timeout=None):
        captured["url"] = url
        captured["json"] = json
        return FakeResp()

    import httpx
    monkeypatch.setattr(httpx, "post", fake_post)

    agent_engine.call_hermes("do-task", timeout=30, isolation="pure")
    assert captured["json"]["isolation"] == "pure"

    agent_engine.call_hermes("do-task", timeout=30, isolation="kb")
    assert captured["json"]["isolation"] == "kb"

    agent_engine.call_hermes("do-task", timeout=30)  # 默认 standard
    assert captured["json"]["isolation"] == "standard"
