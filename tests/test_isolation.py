"""Knowledge Capability / Gateway 强隔离契约测试。

旧 pure/standard/kb 命令行隔离协议已废弃。知识权限的唯一来源是平台签发、
绑定 subject 与 policy_version 的短期 Capability；Hermes 只能携带该凭证调用
Knowledge Gateway。
"""
from __future__ import annotations

import os

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

os.environ.setdefault("HERMES_STATE_DB", "/tmp/test_state_isolation.db")

from backend.models.agent import Agent  # noqa: E402
from scripts import hermes_bridge  # noqa: E402


def test_legacy_isolation_field_is_rejected() -> None:
    """旧客户端不能再用 pure/standard/kb 伪造知识权限。"""
    with pytest.raises(ValidationError) as exc:
        hermes_bridge.GoalRequest(goal="hello", isolation="pure")
    assert any(error["loc"] == ("isolation",) for error in exc.value.errors())


def test_legacy_agent_isolation_column_is_not_mapped() -> None:
    """Agent 运行模型不再承载第二套隔离真值。"""
    assert "isolation" not in Agent.__table__.columns


def test_missing_capability_means_no_knowledge_access() -> None:
    claims = hermes_bridge._validated_knowledge_claims(
        None,
        subject_id="tenant-a:session-1",
        policy_version=None,
    )
    assert claims is None


def test_capability_is_bound_to_subject_and_policy(monkeypatch) -> None:
    monkeypatch.setattr(
        hermes_bridge,
        "verify_capability",
        lambda _token: {
            "tenant_key": "tenant-a",
            "subject_id": "tenant-a:session-1",
            "policy_version": "policy-v2:7",
            "scopes": ["public", "premium"],
        },
    )
    claims = hermes_bridge._validated_knowledge_claims(
        "signed-capability",
        subject_id="tenant-a:session-1",
        policy_version="policy-v2:7",
    )
    assert claims["tenant_key"] == "tenant-a"
    assert claims["scopes"] == ["public", "premium"]

    with pytest.raises(HTTPException) as subject_error:
        hermes_bridge._validated_knowledge_claims(
            "signed-capability",
            subject_id="tenant-b:session-1",
            policy_version="policy-v2:7",
        )
    assert subject_error.value.status_code == 403
    assert subject_error.value.detail == "knowledge_scope_denied"

    with pytest.raises(HTTPException) as policy_error:
        hermes_bridge._validated_knowledge_claims(
            "signed-capability",
            subject_id="tenant-a:session-1",
            policy_version="policy-v2:8",
        )
    assert policy_error.value.status_code == 403
    assert policy_error.value.detail == "knowledge_scope_denied"


def test_gateway_receives_capability_and_bounded_scope(monkeypatch) -> None:
    captured: dict = {}

    class Response:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"docs": [{"path": "public/a.md"}]}

    def fake_post(url, *, headers, json, timeout):
        captured.update(url=url, headers=headers, json=json, timeout=timeout)
        return Response()

    monkeypatch.setattr(hermes_bridge.httpx, "post", fake_post)
    docs = hermes_bridge._knowledge_gateway_search(
        "signed-capability",
        query="research",
        category_scope=["public"],
        limit=3,
    )

    assert docs == [{"path": "public/a.md"}]
    assert captured["headers"] == {"X-Knowledge-Capability": "signed-capability"}
    assert captured["json"]["category_scope"] == ["public"]
    assert captured["json"]["limit"] == 3


def test_gateway_denial_fails_closed(monkeypatch) -> None:
    class Response:
        status_code = 403

    monkeypatch.setattr(hermes_bridge.httpx, "post", lambda *args, **kwargs: Response())
    with pytest.raises(PermissionError, match="knowledge_scope_denied"):
        hermes_bridge._knowledge_gateway_search(
            "expired-capability",
            query="private data",
            category_scope=["private-b"],
        )
