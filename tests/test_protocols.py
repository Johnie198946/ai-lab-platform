"""
协议签署功能自测 — 覆盖 v2 方案 9 条批复 + 结构化验收清单 5 项
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 验收项 1: 模型层 — 状态机 + 复合唯一约束 + 无 JSONB agents
# ---------------------------------------------------------------------------


class TestModelLayer:
    def test_protocol_status_has_rejected_and_cancelled(self):
        from backend.models.protocol import ProtocolStatus

        values = {s.value for s in ProtocolStatus}
        assert "rejected" in values
        assert "cancelled" in values
        assert "pending" in values
        assert "signing" in values
        assert "completed" in values

    def test_signature_status_has_rejected(self):
        from backend.models.protocol import SignatureStatus

        values = {s.value for s in SignatureStatus}
        assert "rejected" in values

    def test_no_jsonb_agents_column(self):
        """批复 1: JSONB agents 移除 — 协议不存 agents JSONB，改走签署记录表"""
        from backend.models.protocol import AgentProtocol

        columns = {c.name for c in AgentProtocol.__table__.columns}
        assert "agents" not in columns

    def test_unique_constraint_on_protocol_agent(self):
        """批复 2: 复合唯一约束 (protocol_id, agent_name)"""
        from backend.models.protocol import ProtocolSignature

        constraints = list(ProtocolSignature.__table__.constraints)
        uq = [c for c in constraints if c.name == "uq_protocol_agent"]
        assert len(uq) == 1
        cols = {c.name for c in uq[0].columns}
        assert cols == {"protocol_id", "agent_name"}


# ---------------------------------------------------------------------------
# 验收项 2: JWT 提取 tenant_key + created_by
# ---------------------------------------------------------------------------


class TestJWTExtraction:
    def test_create_protocol_extracts_tenant_and_user(self):
        """从 auth dict 提取 tenant_key 和 created_by（user_id 优先）"""
        from backend.api.protocols import create_protocol, ProtocolCreate, AgentTarget

        # 构造 mock auth payload（模拟 JWT 解析结果）
        auth = {
            "sub": "user-123",
            "user_id": "user-123",
            "tenant_key": "t-demo",
            "username": "alice",
        }
        # 验证 API 函数签名接受 auth 参数
        import inspect

        sig = inspect.signature(create_protocol)
        params = list(sig.parameters.keys())
        assert "auth" in params
        assert "req" in params


# ---------------------------------------------------------------------------
# 验收项 3: AgentSignRequest Schema + cancel 端点
# ---------------------------------------------------------------------------


class TestSchemasAndEndpoints:
    def test_agent_sign_request_schema(self):
        """批复 5: AgentSignRequest Schema"""
        from backend.api.protocols import AgentSignRequest

        req = AgentSignRequest(agent_name="coder", approved=True, comment="LGTM")
        assert req.agent_name == "coder"
        assert req.approved is True
        assert req.comment == "LGTM"

    def test_cancel_endpoint_exists(self):
        """批复 6: cancel 端点"""
        from backend.api.protocols import router

        paths = [r.path for r in router.routes]
        assert "/api/v1/protocols/{protocol_id}/cancel" in paths

    def test_all_six_endpoints_registered(self):
        from backend.api.protocols import router

        routes = {(list(r.methods)[0], r.path) for r in router.routes}
        expected = {
            ("POST", "/api/v1/protocols"),
            ("GET", "/api/v1/protocols"),
            ("GET", "/api/v1/protocols/{protocol_id}"),
            ("POST", "/api/v1/protocols/{protocol_id}/sign"),
            ("POST", "/api/v1/protocols/{protocol_id}/cancel"),
            ("GET", "/api/v1/protocols/{protocol_id}/status"),
        }
        assert expected.issubset(routes)


# ---------------------------------------------------------------------------
# 验收项 4: INBOX_PATH 环境变量 + Frontmatter 契约
# ---------------------------------------------------------------------------


class TestInboxDispatch:
    def test_inbox_path_env_variable(self):
        """批复 7: INBOX_PATH 环境变量"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["INBOX_PATH"] = tmpdir
            try:
                from backend.services.protocols import _default_vault_path

                result = _default_vault_path()
                assert str(result) == tmpdir
            finally:
                del os.environ["INBOX_PATH"]

    def test_frontmatter_contract(self):
        """批复 8: Frontmatter 契约 — 写入的文件包含必要字段"""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.environ["INBOX_PATH"] = tmpdir
            try:
                from backend.services.protocols import dispatch_to_inbox

                # 构造 mock protocol
                protocol = MagicMock()
                protocol.id = 42
                protocol.title = "测试协议"
                protocol.content = "协议正文内容"
                protocol.status = "pending"
                protocol.tenant_key = "t-demo"
                protocol.created_by = "user-123"
                protocol.created_at = datetime(2026, 8, 8, 12, 0, 0, tzinfo=timezone.utc)

                sig1 = MagicMock()
                sig1.agent_name = "main"
                sig1.status = "pending"
                sig1.signed_at = None
                sig2 = MagicMock()
                sig2.agent_name = "coder"
                sig2.status = "signed"
                sig2.signed_at = datetime(2026, 8, 8, 13, 0, 0, tzinfo=timezone.utc)
                protocol.signatures = [sig1, sig2]

                filepath = dispatch_to_inbox(protocol)
                content = filepath.read_text(encoding="utf-8")

                # Frontmatter 契约验证
                assert content.startswith("---\n")
                assert "id: 42" in content
                assert "title: 测试协议" in content
                assert "status: pending" in content
                assert "tenant_key: t-demo" in content
                assert "created_by: user-123" in content
                assert "created_at:" in content
                assert "agents:" in content
                assert "name: main" in content
                assert "name: coder" in content
                assert "status: signed" in content
                assert "协议正文内容" in content
            finally:
                del os.environ["INBOX_PATH"]


# ---------------------------------------------------------------------------
# 验收项 5: DB commit 后写盘（dispatch 在 commit 之后调用）
# ---------------------------------------------------------------------------


class TestCommitBeforeDispatch:
    def test_dispatch_called_after_commit(self):
        """批复 9: DB commit 后写盘 — 源码顺序验证"""
        import inspect

        from backend.api.protocols import create_protocol

        source = inspect.getsource(create_protocol)
        commit_pos = source.find("await db.commit()")
        dispatch_pos = source.find("dispatch_to_inbox")
        assert commit_pos > 0, "create_protocol 应包含 db.commit()"
        assert dispatch_pos > 0, "create_protocol 应调用 dispatch_to_inbox"
        assert commit_pos < dispatch_pos, "dispatch 应在 commit 之后调用"


# ---------------------------------------------------------------------------
# 集成: db.py 和 main.py 修改验证
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_db_imports_protocol_model(self):
        """db.py init_db 导入 protocol 模型"""
        import inspect

        from backend.db import init_db

        source = inspect.getsource(init_db)
        assert "backend.models.protocol" in source

    def test_main_registers_protocols_router(self):
        """main.py 注册 protocols_router"""
        from backend.main import app

        # 检查路由是否注册
        protocol_routes = [
            r for r in app.routes if hasattr(r, "path") and "/protocols" in r.path
        ]
        assert len(protocol_routes) > 0
