from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.services.knowledge_catalog import compute_catalog, document_index
from backend.services.knowledge_color_projection import (
    approve_color,
    approved_color_documents,
    color_approval_candidates,
)


def _note(path: Path, *, security: str, classification: str = "pending", entitlement: str = "", owner: str = "public") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "---\n"
        f"title: {path.stem}\n"
        "knowledge_level: K2\n"
        f"classification_status: {classification}\n"
        f"security_level: {security}\n"
        f"entitlement_key: {entitlement}\n"
        f"owner_tenant: {owner}\n"
        "status: active\n"
        "---\n\n# body\n",
        encoding="utf-8",
    )


def test_color_alone_is_not_approval_but_one_action_releases_green(tmp_path):
    path = tmp_path / "wiki/方法论/公共方法.md"
    _note(path, security="green")
    assert approved_color_documents(tmp_path) == []
    assert color_approval_candidates(tmp_path)[0]["path"] == "wiki/方法论/公共方法.md"

    approve_color(
        tmp_path, relative_path="wiki/方法论/公共方法.md",
        security_level="green", approved_by="admin-1",
    )
    documents = approved_color_documents(tmp_path)
    assert documents[0]["knowledge_level"] == "K2"
    assert documents[0]["security_level"] == "green"
    assert document_index(tmp_path)["wiki/方法论/公共方法.md"]["classification_status"] == "approved"
    assert compute_catalog(tmp_path)[0]["doc_count"] == 1


def test_projection_scan_is_reused_inside_document_filter_loops(tmp_path, monkeypatch):
    import backend.services.knowledge_color_projection as projection

    path = tmp_path / "wiki/方法论/公共方法.md"
    _note(path, security="green", classification="approved")
    projection.clear_color_projection_cache()
    calls = 0
    original = projection._scan_approved_color_documents

    def counted(vault):
        nonlocal calls
        calls += 1
        return original(vault)

    monkeypatch.setattr(projection, "_scan_approved_color_documents", counted)
    for _ in range(200):
        assert approved_color_documents(tmp_path)[0]["security_level"] == "green"
    assert calls == 1


def test_yellow_approval_requires_exact_entitlement_and_no_k5_minimum(tmp_path):
    path = tmp_path / "wiki/方法论/专业方法.md"
    _note(path, security="yellow")
    with pytest.raises(ValueError, match="exact entitlement"):
        approve_color(
            tmp_path, relative_path="wiki/方法论/专业方法.md",
            security_level="yellow", approved_by="admin-1", entitlement_key="",
        )
    approve_color(
        tmp_path, relative_path="wiki/方法论/专业方法.md",
        security_level="yellow", approved_by="admin-1",
        entitlement_key="kb.enterprise-ai-delivery",
    )
    pack = compute_catalog(tmp_path)[0]
    assert pack["security_level"] == "yellow"
    assert pack["entitlement_key"] == "kb.enterprise-ai-delivery"
    assert pack["doc_count"] == 1


def test_red_approval_requires_private_owner_and_path_cannot_escape(tmp_path):
    path = tmp_path / "wiki/方法论/内部.md"
    _note(path, security="red", owner="")
    with pytest.raises(ValueError, match="private owner"):
        approve_color(
            tmp_path, relative_path="wiki/方法论/内部.md",
            security_level="red", approved_by="admin-1",
        )


@pytest.mark.asyncio
async def test_yellow_authen_failure_rolls_back_document_approval(tmp_path, monkeypatch):
    import backend.api.knowledge_publication as api

    path = tmp_path / "wiki/方法论/受限.md"
    _note(path, security="yellow", entitlement="kb.restricted")
    original = path.read_text(encoding="utf-8")
    monkeypatch.setattr(api, "_vault", lambda: tmp_path)

    async def reject(**kwargs):
        raise HTTPException(status_code=503, detail="authen unavailable")

    monkeypatch.setattr(api, "_notify_authen", reject)
    with pytest.raises(HTTPException):
        await api.approve(
            api.PublicationDecision(
                path="wiki/方法论/受限.md", security_level="yellow",
                entitlement_key="kb.restricted", owner_tenant="",
            ),
            payload={"is_super_admin": True, "user_id": "admin-1"},
        )
    assert path.read_text(encoding="utf-8") == original
    assert approved_color_documents(tmp_path) == []
    with pytest.raises(ValueError, match="knowledge path"):
        approve_color(
            tmp_path, relative_path="../outside.md",
            security_level="green", approved_by="admin-1",
        )
