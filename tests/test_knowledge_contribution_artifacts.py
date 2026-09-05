from pathlib import Path

import yaml

from backend.services.knowledge_contribution_artifacts import (
    stage_green_projection, tenant_namespace, write_red_projection,
)


def frontmatter(path: Path):
    text = path.read_text(encoding="utf-8")
    return yaml.safe_load(text.split("---", 2)[1]), text


def test_red_is_tenant_scoped_read_only_and_source_ref_is_hashed(tmp_path):
    relative = write_red_projection(
        tmp_path, projection_id="tenant-kn-1", tenant_key="tenant-secret",
        title="验收方法", knowledge_type="方法论", knowledge_level="K2",
        confidence=0.84, content="# 方法\n按证据验收。",
        source_ref_hash="a" * 64, source_content_hash="b" * 64, source_revision=4,
    )
    assert tenant_namespace("tenant-secret") in relative
    metadata, text = frontmatter(tmp_path / relative)
    assert metadata["security_level"] == "red" and metadata["editable"] is False
    assert metadata["source_ref_hash"] == "a" * 64
    assert "source-id" not in text


def test_green_pending_file_has_no_private_identity_and_is_not_approved(tmp_path):
    relative = stage_green_projection(
        tmp_path, projection_id="kn-public-1", title="企业项目验收方法",
        knowledge_type="方法论", knowledge_level="K2", confidence=0.84,
        content="# 方法\n采用通用验收门禁。", source_count=2,
    )
    metadata, text = frontmatter(tmp_path / relative)
    assert metadata["classification_status"] == "pending"
    assert metadata["approval_source"] == "tenant_contribution_policy_v1"
    assert metadata["owner_tenant"] == "public"
    assert "tenant-secret" not in text and "source-id" not in text
