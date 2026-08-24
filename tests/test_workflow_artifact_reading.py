from __future__ import annotations

from pathlib import Path
from hashlib import sha256
from types import SimpleNamespace
from zipfile import ZipFile

import pytest

from backend.services.workflow_artifacts import (
    artifact_extension,
    artifact_mime_type,
    read_artifact_text,
    read_verified_artifact,
    store_artifact,
)
from backend.services.workflow_executor import artifact_storage_contract


class ArtifactStub:
    relative_path = "outputs/final-review.docx"


def test_artifact_media_fields_are_explicit() -> None:
    artifact = ArtifactStub()
    assert artifact_extension(artifact) == "docx"
    assert artifact_mime_type(artifact) == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def test_docx_preview_extracts_real_paragraph_text(tmp_path: Path) -> None:
    path = tmp_path / "review.docx"
    document_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:r><w:t>第一段</w:t></w:r></w:p>
        <w:p><w:r><w:t>第二段</w:t></w:r><w:r><w:t>续文</w:t></w:r></w:p>
      </w:body>
    </w:document>"""
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    assert read_artifact_text(path) == "第一段\n\n第二段续文"


def test_docx_preview_rejects_unsafe_xml(tmp_path: Path) -> None:
    path = tmp_path / "unsafe.docx"
    with ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", '<!DOCTYPE x [<!ENTITY y "boom">]><x>&y;</x>')

    with pytest.raises(ValueError, match="unsafe DOCX XML"):
        read_artifact_text(path)


def test_image_preview_returns_a_browser_safe_data_uri(tmp_path: Path) -> None:
    path = tmp_path / "chart.png"
    path.write_bytes(bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d4944415408d763f8cfc0f01f00050001ff89993d1d0000000049454e44ae426082"))

    assert read_artifact_text(path).startswith("data:image/png;base64,")


def test_verified_preview_rejects_content_hash_drift(tmp_path: Path) -> None:
    path = tmp_path / "artifact.md"
    path.write_text("changed", encoding="utf-8")

    with pytest.raises(ValueError, match="hash mismatch"):
        read_verified_artifact(path, sha256(b"original").hexdigest())


def test_animated_gif_preview_is_not_embedded(tmp_path: Path) -> None:
    path = tmp_path / "animation.gif"
    path.write_bytes(b"GIF89a\x01\x00\x01\x00")

    with pytest.raises(ValueError, match="unsupported image"):
        read_artifact_text(path)


def test_word_contract_is_persisted_as_a_real_docx(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.services.workflow_artifacts.run_root", lambda execution: tmp_path)
    execution = SimpleNamespace(id="exec-1", tenant_id="tenant-1")
    row = store_artifact(
        execution,
        node_run_id="node-run-1",
        kind="final",
        title="评审报告",
        content="第一\x00段\n\n第二段",
        source_kind="hermes_output",
        extension="docx",
        metadata={"render_type": "word"},
    )
    path = tmp_path / row.relative_path

    assert path.read_bytes().startswith(b"PK")
    assert read_verified_artifact(path, row.content_hash) == "第一段\n\n第二段"


def test_artifact_kind_cannot_escape_run_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.services.workflow_artifacts.run_root", lambda execution: tmp_path)
    execution = SimpleNamespace(id="exec-1")
    row = store_artifact(
        execution,
        node_run_id=None,
        kind="../../escape",
        title="evidence",
        content="safe",
    )

    assert (tmp_path / row.relative_path).resolve().is_relative_to(tmp_path.resolve())
    assert ".." not in Path(row.relative_path).parts


def test_executor_forwards_only_explicit_artifact_contract_fields() -> None:
    extension, metadata = artifact_storage_contract(
        {"extension": "json", "mime_type": "application/json", "render_type": "topology", "ignored": "x"},
        event_id="evt-1",
        node=SimpleNamespace(node_id="node-1", agent_id="agent-1", model_used="m", provider_used="p"),
    )

    assert extension == "json"
    assert metadata["render_type"] == "topology"
    assert metadata["mime_type"] == "application/json"
    assert "ignored" not in metadata
