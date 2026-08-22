from pathlib import Path

import yaml

from backend.services.knowledge_catalog import document_index
from scripts.repair_xfusion_tokenfactory_public_knowledge import (
    PUBLIC_TOKENFACTORY_PATHS,
    repair_tokenfactory_public_knowledge,
)


def _write_note(vault: Path, relative: str, *, security: str) -> str:
    path = vault / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    body = (
        "---\n"
        f"title: {path.stem}\n"
        f"security_level: {security}\n"
        "classification_status: approved\n"
        "owner_tenant: ''\n"
        "entitlement_key: ''\n"
        "knowledge_level: K5\n"
        "---\n\n"
        "公开产品事实。\n"
    )
    path.write_text(body, encoding="utf-8")
    return body


def _frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1])


def test_repair_is_dry_run_by_default(tmp_path: Path) -> None:
    originals = {
        relative: _write_note(tmp_path, relative, security="red")
        for relative in PUBLIC_TOKENFACTORY_PATHS
    }

    result = repair_tokenfactory_public_knowledge(
        tmp_path, apply_changes=False, approved_by="admin"
    )

    assert result["mode"] == "dry-run"
    for relative, original in originals.items():
        assert (tmp_path / relative).read_text(encoding="utf-8") == original


def test_repair_makes_only_allowlisted_documents_public_and_recoverable(
    tmp_path: Path,
) -> None:
    originals = {
        relative: _write_note(tmp_path, relative, security="yellow")
        for relative in PUBLIC_TOKENFACTORY_PATHS
    }
    unrelated = "wiki/产品/内部经营材料.md"
    unrelated_original = _write_note(tmp_path, unrelated, security="red")
    backup = tmp_path / "backups" / "run-1"

    result = repair_tokenfactory_public_knowledge(
        tmp_path,
        apply_changes=True,
        approved_by="admin-1",
        backup_root=backup,
    )

    assert result["changed"] == list(PUBLIC_TOKENFACTORY_PATHS)
    for relative, original in originals.items():
        metadata = _frontmatter(tmp_path / relative)
        assert metadata["security_level"] == "green"
        assert metadata["classification_status"] == "approved"
        assert metadata["owner_tenant"] == "public"
        assert metadata["entitlement_key"] is None
        assert (backup / relative).read_text(encoding="utf-8") == original
        assert document_index(tmp_path)[relative]["pack_id"] == "knowledge/product/public"
    assert (tmp_path / unrelated).read_text(encoding="utf-8") == unrelated_original
