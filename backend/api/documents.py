"""Authenticated private document upload, status, text, and original download."""

from __future__ import annotations

from datetime import datetime
from urllib.parse import unquote

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse

from backend.api.auth import require_auth
from backend.services.document_sources import (
    DocumentSourceError,
    MAX_DOCUMENT_BYTES,
    document_original_path,
    document_text,
    read_document_receipt,
    save_document_source,
    update_document_receipt,
)
from backend.services.knowledge_candidate_ingest import enqueue_and_schedule
from backend.services.knowledge_contribution import (
    ContributionCandidate,
    enqueue_contribution,
)

router = APIRouter(prefix="/api/v1/documents", tags=["documents"])


def _identity(payload: dict) -> tuple[str, str]:
    return str(payload.get("tenant_key") or ""), str(
        payload.get("user_id") or payload.get("sub") or ""
    )


def _error(exc: DocumentSourceError) -> HTTPException:
    status = (
        404
        if exc.code == "document_not_found"
        else 413
        if exc.code == "document_too_large"
        else 422
    )
    return HTTPException(
        status_code=status, detail={"code": exc.code, "message": str(exc)}
    )


@router.post("", status_code=201)
async def upload_document(
    request: Request,
    filename: str = Header(..., alias="X-File-Name"),
    content_hash: str = Header("", alias="X-Content-Hash"),
    file_opt_out: bool = Header(False, alias="X-File-Opt-Out"),
    payload: dict = Depends(require_auth),
):
    try:
        length = int(request.headers.get("content-length") or 0)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail={"code": "invalid_content_length", "message": "上传长度无效"},
        ) from exc
    if length > MAX_DOCUMENT_BYTES:
        raise HTTPException(
            status_code=413,
            detail={"code": "document_too_large", "message": "文档超过 25 MB 上限"},
        )
    data = bytearray()
    async for chunk in request.stream():
        if len(data) + len(chunk) > MAX_DOCUMENT_BYTES:
            raise HTTPException(
                status_code=413,
                detail={"code": "document_too_large", "message": "文档超过 25 MB 上限"},
            )
        data.extend(chunk)
    tenant_key, user_id = _identity(payload)
    try:
        receipt = save_document_source(
            tenant_key=tenant_key,
            user_id=user_id,
            filename=unquote(filename),
            content_type=request.headers.get("content-type", ""),
            data=bytes(data),
            expected_hash=content_hash,
            file_opt_out=file_opt_out,
        )
    except DocumentSourceError as exc:
        raise _error(exc) from exc
    if receipt["status"] == "ready":
        candidate = ContributionCandidate(
            tenant_key=tenant_key,
            user_id=user_id,
            source_surface="ios",
            source_kind="uploaded_file",
            source_id=receipt["source_id"],
            source_revision=receipt["source_revision"],
            content_hash=receipt["content_hash"],
            source_changed_at=datetime.fromisoformat(receipt["created_at"]),
            file_opt_out=file_opt_out,
        )
        try:
            if file_opt_out:
                await enqueue_contribution(candidate)
                updates = {"contribution_status": "excluded"}
            else:
                text, _ = document_text(tenant_key, user_id, receipt["source_id"])
                contribution = await enqueue_and_schedule(
                    candidate, source_content=text
                )
                if contribution is None:
                    updates = {"contribution_status": "denied"}
                elif (
                    contribution.get("schedule_status") == "scheduled"
                    and contribution.get("event_id")
                    and contribution.get("run_id")
                ):
                    updates = {
                        "contribution_status": "queued",
                        "contribution_event_id": contribution["event_id"],
                        "contribution_run_id": contribution["run_id"],
                    }
                elif contribution.get("event_id"):
                    updates = {
                        "contribution_status": "pending",
                        "contribution_event_id": contribution["event_id"],
                        "contribution_error": str(
                            contribution.get("schedule_error") or "调度回执待确认"
                        )[:240],
                    }
                else:
                    updates = {
                        "contribution_status": "failed",
                        "contribution_error": "贡献入队回执无效",
                    }
            receipt = update_document_receipt(
                tenant_key, user_id, receipt["source_id"], **updates
            )
        except (
            Exception
        ) as exc:  # Contribution is independent from the private PPT flow.
            receipt = update_document_receipt(
                tenant_key,
                user_id,
                receipt["source_id"],
                contribution_status="failed",
                contribution_error=str(exc)[:240],
            )
    return receipt


@router.get("/{source_id}")
async def get_document(source_id: str, payload: dict = Depends(require_auth)):
    try:
        return read_document_receipt(*_identity(payload), source_id)
    except DocumentSourceError as exc:
        raise _error(exc) from exc


@router.get("/{source_id}/text", response_class=PlainTextResponse)
async def get_document_text(source_id: str, payload: dict = Depends(require_auth)):
    try:
        text, _ = document_text(*_identity(payload), source_id)
        return PlainTextResponse(text, headers={"Cache-Control": "private, no-store"})
    except DocumentSourceError as exc:
        raise _error(exc) from exc


@router.get("/{source_id}/download")
async def download_document(source_id: str, payload: dict = Depends(require_auth)):
    try:
        path, receipt = document_original_path(*_identity(payload), source_id)
    except DocumentSourceError as exc:
        raise _error(exc) from exc
    return FileResponse(
        path,
        media_type=receipt["content_type"],
        filename=receipt["filename"],
        headers={
            "Cache-Control": "private, no-store",
            "X-Content-SHA256": receipt["content_hash"],
            "X-Source-Revision": str(receipt["source_revision"]),
        },
    )
