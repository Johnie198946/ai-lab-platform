"""Durable private originals and extracted text for authenticated document uploads."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from backend.services.upload_text_extractor import extract_uploaded_text
from backend.services.user_note_context import (
    namespace,
    note_directory,
    update_private_note_index,
)

MAX_DOCUMENT_BYTES = 25 * 1024 * 1024
MAX_PRESENTATION_SOURCE_CHARACTERS = 8_000
SUPPORTED_DOCUMENTS = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


class DocumentSourceError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def _directory(tenant_key: str, user_id: str, source_id: str) -> Path:
    if not source_id.startswith("doc_") or not source_id[4:].isalnum():
        raise DocumentSourceError("invalid_source_id", "文档来源标识无效")
    return note_directory(tenant_key, user_id) / ".documents" / source_id


def _atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def _safe_filename(filename: str) -> str:
    value = Path(filename.replace("\\", "/")).name.strip()
    return value[:240] or "document"


def _materialize_private_note(
    tenant_key: str, user_id: str, receipt: dict[str, Any], text: str
) -> str:
    note_id = str(receipt["source_id"])
    directory = note_directory(tenant_key, user_id)
    directory.mkdir(parents=True, exist_ok=True)
    title = Path(str(receipt["filename"])).stem or "上传文档"
    now = str(receipt["created_at"])
    markdown = (
        "---\n"
        f"id: {note_id}\n"
        f"title: {json.dumps(title, ensure_ascii=False)}\n"
        f"created: {now}\nupdated: {now}\n"
        "pinned: false\narchived_at:\nmerged_into:\n"
        "tags:\n  - uploaded-document\n"
        f"  - {Path(str(receipt['filename'])).suffix.lower().lstrip('.')}\n"
        "aliases: []\n"
        f"source_document_id: {note_id}\n"
        f"source_content_hash: {receipt['content_hash']}\n"
        "---\n\n"
        f"> [!info] 上传文档\n> 原件：{receipt['filename']}\n\n{text}\n"
    ).encode("utf-8")
    note_path = directory / f"{note_id}.md"
    _atomic_write(note_path, markdown)
    _atomic_write(
        directory / f"{note_id}.sync.json",
        json.dumps(
            {
                "version": 1,
                "note_id": note_id,
                "owner_user_id": user_id,
                "content_hash": hashlib.sha256(markdown).hexdigest(),
                "synced_at": now,
                "source": "uploaded_document",
                "source_document_id": note_id,
                "ingest_target": "private_user_knowledge",
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8"),
    )
    update_private_note_index(tenant_key, user_id, note_path)
    return note_id


def save_document_source(
    *,
    tenant_key: str,
    user_id: str,
    filename: str,
    content_type: str,
    data: bytes,
    expected_hash: str = "",
    file_opt_out: bool = False,
) -> dict[str, Any]:
    filename = _safe_filename(filename)
    suffix = Path(filename).suffix.lower()
    if suffix == ".doc":
        raise DocumentSourceError(
            "legacy_doc_unsupported", "暂不支持旧版 .doc，请另存为 .docx"
        )
    if suffix not in SUPPORTED_DOCUMENTS:
        raise DocumentSourceError("unsupported_document_type", "仅支持 PDF 或 DOCX")
    if not data:
        raise DocumentSourceError("empty_document", "文档为空")
    if len(data) > MAX_DOCUMENT_BYTES:
        raise DocumentSourceError("document_too_large", "文档超过 25 MB 上限")
    digest = hashlib.sha256(data).hexdigest()
    if expected_hash and expected_hash.lower() != digest:
        raise DocumentSourceError("content_hash_mismatch", "文档校验失败，请重新选择")

    source_id = f"doc_{uuid.uuid4().hex}"
    directory = _directory(tenant_key, user_id, source_id)
    original_name = f"original{suffix}"
    _atomic_write(
        directory / original_name, data
    )  # Preserve the original before parsing.
    now = datetime.now(timezone.utc).isoformat()
    receipt: dict[str, Any] = {
        "source_id": source_id,
        "source_revision": 1,
        "filename": filename,
        "content_type": SUPPORTED_DOCUMENTS[suffix],
        "size_bytes": len(data),
        "content_hash": digest,
        "status": "parsing",
        "parse_error": None,
        "text_available": False,
        "file_opt_out": file_opt_out,
        "contribution_status": "excluded" if file_opt_out else "pending",
        "created_at": now,
        "updated_at": now,
        "owner_tenant": namespace(tenant_key),
        "owner_user": namespace(user_id),
        "original_name": original_name,
    }
    try:
        text = extract_uploaded_text(data, filename=filename, content_type=content_type)
        encoded_text = text.encode("utf-8")
        _atomic_write(directory / "extracted.txt", encoded_text)
        receipt.update(
            status="ready",
            text_available=True,
            extracted_characters=len(text),
            extracted_hash=hashlib.sha256(encoded_text).hexdigest(),
        )
        receipt.update(
            note_id=_materialize_private_note(
                tenant_key, user_id, receipt, text
            ),
            note_status="ready",
        )
    except Exception as exc:
        message = str(exc)
        code = "document_parse_failed"
        if "encrypt" in message.lower() or "decrypt" in message.lower():
            code, message = "encrypted_pdf", "PDF 已加密，无法提取文本"
        elif "no extractable text" in message.lower():
            code, message = (
                "no_extractable_text",
                "PDF 没有可提取文字；暂不支持扫描件 OCR",
            )
        receipt.update(
            status="parse_failed",
            parse_error={"code": code, "message": message[:300]},
            note_id=None,
            note_status="unavailable",
        )
    _atomic_write(
        directory / "receipt.json",
        json.dumps(receipt, ensure_ascii=False, indent=2).encode(),
    )
    return receipt


def read_document_receipt(
    tenant_key: str, user_id: str, source_id: str
) -> dict[str, Any]:
    path = _directory(tenant_key, user_id, source_id) / "receipt.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError) as exc:
        raise DocumentSourceError("document_not_found", "文档不存在") from exc
    return value


def update_document_receipt(
    tenant_key: str, user_id: str, source_id: str, **updates: Any
) -> dict[str, Any]:
    value = read_document_receipt(tenant_key, user_id, source_id)
    value.update(updates, updated_at=datetime.now(timezone.utc).isoformat())
    _atomic_write(
        _directory(tenant_key, user_id, source_id) / "receipt.json",
        json.dumps(value, ensure_ascii=False, indent=2).encode(),
    )
    return value


def document_original_path(
    tenant_key: str, user_id: str, source_id: str
) -> tuple[Path, dict[str, Any]]:
    receipt = read_document_receipt(tenant_key, user_id, source_id)
    path = _directory(tenant_key, user_id, source_id) / str(receipt["original_name"])
    if (
        not path.is_file()
        or hashlib.sha256(path.read_bytes()).hexdigest() != receipt["content_hash"]
    ):
        raise DocumentSourceError("document_integrity_error", "文档完整性校验失败")
    return path, receipt


def document_text(
    tenant_key: str, user_id: str, source_id: str
) -> tuple[str, dict[str, Any]]:
    receipt = read_document_receipt(tenant_key, user_id, source_id)
    if receipt.get("status") != "ready":
        error = receipt.get("parse_error") or {
            "code": "text_unavailable",
            "message": "提取文本不可用",
        }
        raise DocumentSourceError(str(error["code"]), str(error["message"]))
    path = _directory(tenant_key, user_id, source_id) / "extracted.txt"
    try:
        data = path.read_bytes()
    except FileNotFoundError as exc:
        raise DocumentSourceError("document_integrity_error", "提取文本完整性校验失败") from exc
    expected_hash = str(receipt.get("extracted_hash") or "")
    if not expected_hash or hashlib.sha256(data).hexdigest() != expected_hash:
        raise DocumentSourceError("document_integrity_error", "提取文本完整性校验失败")
    try:
        return data.decode("utf-8"), receipt
    except UnicodeDecodeError as exc:
        raise DocumentSourceError("document_integrity_error", "提取文本完整性校验失败") from exc
