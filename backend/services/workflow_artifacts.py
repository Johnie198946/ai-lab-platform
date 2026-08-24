"""Append-only workflow artifact storage with tenant-safe paths."""

from __future__ import annotations

import base64
import hashlib
import json
import mimetypes
import os
import re
import uuid
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
from typing import Any
from xml.etree import ElementTree
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile, ZipInfo

from backend.models.workflow import WorkflowArtifact, WorkflowExecution


def _safe(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", value or "")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid workflow path component")
    return cleaned[:100]


def vault_root() -> Path:
    return Path(os.environ.get("AI_LAB_HOME", "data/vault")).resolve()


def run_root(execution: WorkflowExecution) -> Path:
    root = (
        vault_root()
        / "workflows"
        / _safe(execution.tenant_key)
        / _safe(execution.workflow_id)
        / "runs"
        / _safe(execution.id)
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def initialize_run(execution: WorkflowExecution, plan: dict[str, Any]) -> Path:
    root = run_root(execution)
    for child in ("sources", "evidence", "outputs"):
        (root / child).mkdir(parents=True, exist_ok=True)
    _write_once(root / "plan.json", json.dumps(plan, ensure_ascii=False, indent=2))
    _write_once(root / "events.jsonl", "")
    return root


def _write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(content)
    except FileExistsError:
        return


def _write_bytes_once(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("xb") as handle:
            handle.write(content)
    except FileExistsError:
        return


def _xml_safe_text(value: str) -> str:
    return "".join(
        character
        for character in value
        if character in {"\t", "\n", "\r"}
        or 0x20 <= ord(character) <= 0xD7FF
        or 0xE000 <= ord(character) <= 0xFFFD
        or 0x10000 <= ord(character) <= 0x10FFFF
    )


def _docx_bytes(content: str) -> bytes:
    paragraphs = content.split("\n\n") or [""]
    body = "".join(
        f'<w:p><w:r><w:t xml:space="preserve">{escape(_xml_safe_text(paragraph))}</w:t></w:r></w:p>'
        for paragraph in paragraphs
    )
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}<w:sectPr/></w:body></w:document>"
    )
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        def add(name: str, value: str) -> None:
            info = ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            archive.writestr(info, value.encode("utf-8"))

        add(
            "[Content_Types].xml",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
            "</Types>",
        )
        add(
            "_rels/.rels",
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            "</Relationships>",
        )
        add("word/document.xml", document)
    return buffer.getvalue()


def encode_artifact_content(content: str, extension: str) -> bytes:
    return _docx_bytes(content) if str(extension).lower().lstrip(".") == "docx" else content.encode("utf-8")


_MAX_PREVIEW_BYTES = 8 * 1024 * 1024
_WORD_NAMESPACE = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


def artifact_extension(artifact: WorkflowArtifact) -> str:
    return Path(str(artifact.relative_path or "")).suffix.lower().lstrip(".")


def artifact_mime_type(artifact: WorkflowArtifact) -> str:
    extension = artifact_extension(artifact)
    if extension == "md":
        return "text/markdown"
    return mimetypes.guess_type(f"artifact.{extension}")[0] or "application/octet-stream"


def _image_dimensions(data: bytes, image_mime: str) -> tuple[int, int]:
    if image_mime == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        return int.from_bytes(data[16:20], "big"), int.from_bytes(data[20:24], "big")
    if image_mime == "image/gif" and data[:6] in {b"GIF87a", b"GIF89a"} and len(data) >= 10:
        return int.from_bytes(data[6:8], "little"), int.from_bytes(data[8:10], "little")
    if image_mime == "image/jpeg" and data.startswith(b"\xff\xd8"):
        offset = 2
        sof_markers = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}
        while offset + 9 < len(data):
            if data[offset] != 0xFF:
                offset += 1
                continue
            marker = data[offset + 1]
            if marker in sof_markers:
                return int.from_bytes(data[offset + 7:offset + 9], "big"), int.from_bytes(data[offset + 5:offset + 7], "big")
            if marker in {0xD8, 0xD9}:
                offset += 2
                continue
            if offset + 4 > len(data):
                break
            segment_length = int.from_bytes(data[offset + 2:offset + 4], "big")
            if segment_length < 2:
                break
            offset += 2 + segment_length
    raise ValueError("invalid or unsupported image artifact")


def _preview_from_bytes(path: Path, data: bytes) -> str:
    image_mime = mimetypes.guess_type(path.name)[0]
    if image_mime in {"image/png", "image/jpeg"}:
        width, height = _image_dimensions(data, image_mime)
        if width <= 0 or height <= 0 or width * height > 24_000_000:
            raise ValueError("image preview dimensions exceed limit")
        encoded = base64.b64encode(data).decode("ascii")
        return f"data:{image_mime};base64,{encoded}"
    if image_mime and image_mime.startswith("image/"):
        raise ValueError("unsupported image artifact")
    if path.suffix.lower() != ".docx":
        return data.decode("utf-8", errors="replace")
    try:
        with ZipFile(BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            if info.file_size > _MAX_PREVIEW_BYTES:
                raise ValueError("DOCX preview exceeds size limit")
            document = archive.read(info)
    except (BadZipFile, KeyError) as exc:
        raise ValueError("invalid DOCX artifact") from exc
    if b"<!DOCTYPE" in document.upper() or b"<!ENTITY" in document.upper():
        raise ValueError("unsafe DOCX XML")
    try:
        root = ElementTree.fromstring(document)
    except ElementTree.ParseError as exc:
        raise ValueError("invalid DOCX XML") from exc
    paragraphs = []
    for paragraph in root.iter(f"{_WORD_NAMESPACE}p"):
        content = "".join(node.text or "" for node in paragraph.iter(f"{_WORD_NAMESPACE}t"))
        if content.strip():
            paragraphs.append(content)
    return "\n\n".join(paragraphs)


def read_artifact_text(path: Path) -> str:
    if path.stat().st_size > _MAX_PREVIEW_BYTES:
        raise ValueError("artifact preview exceeds size limit")
    data = path.read_bytes()
    if len(data) > _MAX_PREVIEW_BYTES:
        raise ValueError("artifact preview exceeds size limit")
    return _preview_from_bytes(path, data)


def read_verified_artifact(path: Path, expected_hash: str) -> str:
    if path.stat().st_size > _MAX_PREVIEW_BYTES:
        raise ValueError("artifact preview exceeds size limit")
    data = path.read_bytes()
    if len(data) > _MAX_PREVIEW_BYTES:
        raise ValueError("artifact preview exceeds size limit")
    if hashlib.sha256(data).hexdigest() != str(expected_hash or "").lower():
        raise ValueError("artifact content hash mismatch")
    return _preview_from_bytes(path, data)


def append_event(execution: WorkflowExecution, record: dict[str, Any]) -> None:
    path = run_root(execution) / "events.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def store_artifact(
    execution: WorkflowExecution,
    *,
    node_run_id: str | None,
    kind: str,
    title: str,
    content: str,
    source_url: str | None = None,
    source_kind: str | None = None,
    metadata: dict[str, Any] | None = None,
    extension: str = "md",
) -> WorkflowArtifact:
    normalized_kind = _safe(kind).lower()[:32]
    normalized_extension = _safe(extension).lower().lstrip(".") or "md"
    encoded = encode_artifact_content(content, normalized_extension)
    digest = hashlib.sha256(encoded).hexdigest()
    artifact_id = f"wfa_{uuid.uuid4().hex}"
    root = run_root(execution)
    if normalized_kind == "source":
        folder = root / "sources" / artifact_id
        rel = Path("sources") / artifact_id / f"content.{normalized_extension}"
    elif normalized_kind in {"draft", "final", "review"}:
        folder = root / "outputs"
        rel = Path("outputs") / f"{normalized_kind}-{artifact_id}.{normalized_extension}"
    else:
        folder = root / "evidence"
        rel = Path("evidence") / f"{normalized_kind}-{artifact_id}.{normalized_extension}"
    folder.mkdir(parents=True, exist_ok=True)
    _write_bytes_once(root / rel, encoded)
    meta = {
        **(metadata or {}),
        "artifact_id": artifact_id,
        "title": title,
        "source_url": source_url,
        "source_kind": source_kind,
        "content_hash": digest,
        "captured_at": datetime.now(timezone.utc).isoformat(),
    }
    if normalized_kind == "source":
        _write_once(
            folder / "metadata.json", json.dumps(meta, ensure_ascii=False, indent=2)
        )
    return WorkflowArtifact(
        id=artifact_id,
        execution_id=execution.id,
        node_run_id=node_run_id,
        kind=normalized_kind,
        title=title[:300],
        relative_path=str(rel),
        content_hash=digest,
        source_url=source_url,
        source_kind=source_kind,
        selected_for_publish=True,
        metadata_json=meta,
    )
