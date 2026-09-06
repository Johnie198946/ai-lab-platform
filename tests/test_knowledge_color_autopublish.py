from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from backend.services.knowledge_catalog import bookshelf_catalog, compute_catalog, document_index
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


def test_projection_uses_raw_original_author_then_quantum_fallback(tmp_path):
    raw = tmp_path / "wiki/sources/original.md"
    _note(raw, security="green", classification="approved")
    raw.write_text(
        raw.read_text(encoding="utf-8").replace(
            "status: active\n", "status: active\nsource_author: Louis Claxton；Anthropic\n"
        ),
        encoding="utf-8",
    )
    sourced = tmp_path / "wiki/方法论/有原文.md"
    official = tmp_path / "wiki/方法论/官方来源.md"
    fallback = tmp_path / "wiki/方法论/自研.md"
    _note(sourced, security="green", classification="approved")
    _note(official, security="green", classification="approved")
    _note(fallback, security="green", classification="approved")
    sourced.write_text(
        sourced.read_text(encoding="utf-8").replace(
            "status: active\n", "status: active\nsource_files:\n  - wiki/sources/original.md\n"
        ),
        encoding="utf-8",
    )
    official.write_text(
        official.read_text(encoding="utf-8").replace(
            "status: active\n",
            "status: active\nsource_urls:\n  - https://gist.github.com/karpathy/example\n",
        ),
        encoding="utf-8",
    )

    documents = {item["path"]: item for item in approved_color_documents(tmp_path)}

    assert documents["wiki/方法论/有原文.md"]["book_author"] == "Louis Claxton / Anthropic"
    assert documents["wiki/方法论/有原文.md"]["author_source"] == "raw"
    assert documents["wiki/方法论/官方来源.md"]["book_author"] == "Andrej Karpathy"
    assert documents["wiki/方法论/官方来源.md"]["author_source"] == "official_source"
    assert documents["wiki/方法论/自研.md"]["book_author"] == "Quantum 研究团队"


def test_green_author_attribution_cannot_read_another_tenant_red_source(tmp_path):
    private = tmp_path / "wiki/tenant/tenant-b/private.md"
    _note(private, security="red", classification="approved", owner="tenant-b")
    private.write_text(
        private.read_text(encoding="utf-8").replace(
            "status: active\n", "status: active\nsource_author: SECRET-TENANT-B-CONTACT\n"
        ),
        encoding="utf-8",
    )
    public = tmp_path / "wiki/public/method.md"
    _note(public, security="green", classification="approved")
    public.write_text(
        public.read_text(encoding="utf-8").replace(
            "status: active\n",
            "status: active\nsource_files:\n  - wiki/tenant/tenant-b/private.md\n",
        ),
        encoding="utf-8",
    )

    documents = {item["path"]: item for item in approved_color_documents(tmp_path)}

    assert documents["wiki/public/method.md"]["book_author"] == "Quantum 研究团队"
    assert "SECRET-TENANT-B-CONTACT" not in str(documents["wiki/public/method.md"])


def test_cached_atomic_projection_rejects_removed_red_owner_and_yellow_entitlement(tmp_path):
    red = tmp_path / "wiki/private.md"
    yellow = tmp_path / "wiki/paid.md"
    _note(red, security="red", classification="approved", owner="tenant-a")
    _note(
        yellow,
        security="yellow",
        classification="approved",
        entitlement="pro.access",
    )

    assert "wiki/private.md" in document_index(tmp_path)
    assert "wiki/paid.md" in document_index(tmp_path)
    assert bookshelf_catalog("tenant-a", tmp_path)

    red.write_text(
        red.read_text(encoding="utf-8").replace("owner_tenant: tenant-a\n", ""),
        encoding="utf-8",
    )
    yellow.write_text(
        yellow.read_text(encoding="utf-8").replace("entitlement_key: pro.access\n", ""),
        encoding="utf-8",
    )

    assert "wiki/private.md" not in document_index(tmp_path)
    assert "wiki/paid.md" not in document_index(tmp_path)
    assert bookshelf_catalog(
        "tenant-a",
        tmp_path,
        frozenset({"knowledge/methodology/entitlement/pro.access"}),
    ) == []


def test_raw_author_reference_is_not_read_on_the_bookshelf_path(tmp_path):
    raw = tmp_path / "raw/original.md"
    raw.parent.mkdir()
    raw.write_text("---\nsource_author: PRIVATE RAW AUTHOR\n---\n", encoding="utf-8")
    public = tmp_path / "wiki/public.md"
    _note(public, security="green", classification="approved")
    public.write_text(
        public.read_text(encoding="utf-8").replace(
            "status: active\n", "status: active\nsource_files:\n  - raw/original.md\n"
        ),
        encoding="utf-8",
    )

    document = next(
        item for item in approved_color_documents(tmp_path)
        if item["path"] == "wiki/public.md"
    )

    assert document["book_author"] == "Quantum 研究团队"
    assert "PRIVATE RAW AUTHOR" not in str(document)


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
