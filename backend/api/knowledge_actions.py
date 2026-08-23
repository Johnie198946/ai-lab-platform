"""Proposal ledger and idempotent commit protocol for local-first knowledge actions."""

from __future__ import annotations

import hashlib
import uuid
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.knowledge_action import KnowledgeActionExecution
from backend.services.knowledge_action_capability import (
    KnowledgeActionDenied,
    canonical_digest,
    verify_knowledge_action_capability,
)


router = APIRouter(
    prefix="/api/v1/me/knowledge-actions", tags=["knowledge-actions"]
)


class KnowledgeActionCommitRequest(BaseModel):
    capability: str = Field(..., min_length=32, max_length=8192)
    action_digest: str = Field(..., min_length=64, max_length=64)
    result_digest: str = Field(..., min_length=64, max_length=64)
    result_note_ids: list[str] = Field(default_factory=list, max_length=64)
    status: Literal["local_applied", "synced", "sync_pending", "failed"]
    error_code: str | None = Field(None, max_length=80)


class KnowledgeActionDiscardRequest(BaseModel):
    capability: str = Field(..., min_length=32, max_length=8192)
    action_digest: str = Field(..., min_length=64, max_length=64)


class KnowledgeActionResumeRequest(BaseModel):
    action_digest: str = Field(..., min_length=64, max_length=64)
    result_digest: str = Field(..., min_length=64, max_length=64)
    result_note_ids: list[str] = Field(default_factory=list, max_length=64)
    status: Literal["sync_pending", "synced"]
    error_code: str | None = Field(None, max_length=80)


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or ""),
        str(payload.get("user_id") or payload.get("sub") or ""),
    )


def _capability_digest(capability: str) -> str:
    return hashlib.sha256(capability.encode()).hexdigest()


async def persist_knowledge_action_proposal(
    *,
    tenant_key: str,
    user_id: str,
    session_id: str,
    request_id: str,
    policy_version: str,
    event: dict[str, Any],
    capability: str,
    action_hash: str,
    vault_revision: str,
) -> None:
    """Persist without body text; races converge on the tenant/user/action unique key."""
    action_id = str(event.get("action_id") or "")
    if not action_id:
        raise ValueError("knowledge action event missing action_id")
    steps = event.get("steps") if isinstance(event.get("steps"), list) else []
    target_ids = {
        str(step.get("target_note_id"))
        for step in steps
        if isinstance(step, dict) and step.get("target_note_id")
    }
    row = KnowledgeActionExecution(
        id=uuid.uuid4().hex,
        tenant_key=tenant_key,
        owner_user_id=user_id,
        action_id=action_id,
        session_id=session_id,
        request_id=request_id,
        policy_version=policy_version,
        action_digest=action_hash,
        capability_digest=_capability_digest(capability),
        vault_revision=vault_revision,
        status="proposed",
        operation_count=len(steps),
        target_count=len(target_ids),
    )
    async with SessionLocal() as db:
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = await db.scalar(
                select(KnowledgeActionExecution).where(
                    KnowledgeActionExecution.tenant_key == tenant_key,
                    KnowledgeActionExecution.owner_user_id == user_id,
                    KnowledgeActionExecution.action_id == action_id,
                )
            )
            if existing is None or existing.action_digest != action_hash:
                raise ValueError("knowledge action id collision")


async def _owned_row(
    db: AsyncSession, tenant_key: str, user_id: str, action_id: str, *, lock: bool = False
) -> KnowledgeActionExecution:
    statement = select(KnowledgeActionExecution).where(
            KnowledgeActionExecution.tenant_key == tenant_key,
            KnowledgeActionExecution.owner_user_id == user_id,
            KnowledgeActionExecution.action_id == action_id,
        )
    if lock:
        statement = statement.with_for_update()
    row = await db.scalar(statement)
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "action_not_found"})
    return row


def _verified_claims(
    capability: str, action_id: str, tenant_key: str, user_id: str, digest: str
) -> dict[str, Any]:
    try:
        claims = verify_knowledge_action_capability(capability)
    except KnowledgeActionDenied as exc:
        raise HTTPException(status_code=403, detail={"code": exc.code}) from exc
    if (
        claims.get("tenant_key") != tenant_key
        or claims.get("user_id") != user_id
        or claims.get("action_id") != action_id
        or claims.get("action_hash") != digest
    ):
        raise HTTPException(status_code=403, detail={"code": "knowledge_action_scope_denied"})
    return claims


def _response(row: KnowledgeActionExecution) -> dict[str, Any]:
    return {
        "action_id": row.action_id,
        "status": row.status,
        "action_digest": row.action_digest,
        "result_digest": row.result_digest,
        "result_note_ids": row.result_note_ids or [],
        "error_code": row.error_code,
        "updated_at": row.updated_at,
    }


@router.get("/{action_id}")
async def get_knowledge_action(
    action_id: str,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    async with SessionLocal() as db:
        return _response(await _owned_row(db, tenant_key, user_id, action_id))


@router.post("/{action_id}/commit")
async def commit_knowledge_action(
    action_id: str,
    body: KnowledgeActionCommitRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    claims = _verified_claims(
        body.capability, action_id, tenant_key, user_id, body.action_digest
    )
    # The result identity excludes transport status so sync_pending may later
    # advance to synced without becoming a conflicting payload.
    result_payload = {"result_note_ids": body.result_note_ids}
    if canonical_digest(result_payload) != body.result_digest:
        raise HTTPException(status_code=422, detail={"code": "result_digest_mismatch"})
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.capability_digest != _capability_digest(body.capability):
            raise HTTPException(status_code=409, detail={"code": "capability_replay_conflict"})
        if row.vault_revision and claims.get("vault_revision") != row.vault_revision:
            raise HTTPException(status_code=409, detail={"code": "vault_revision_conflict"})
        if row.result_digest:
            if row.result_digest != body.result_digest:
                raise HTTPException(status_code=409, detail={"code": "action_result_conflict"})
            if row.status in {"local_applied", "sync_pending", "failed"} and body.status == "synced":
                row.status = "synced"
                row.error_code = None
                await db.commit()
                await db.refresh(row)
            return _response(row)
        row.status = body.status
        row.result_digest = body.result_digest
        row.result_note_ids = body.result_note_ids
        row.error_code = body.error_code
        await db.commit()
        await db.refresh(row)
        return _response(row)


@router.post("/{action_id}/discard")
async def discard_knowledge_action(
    action_id: str,
    body: KnowledgeActionDiscardRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    tenant_key, user_id = _identity(payload)
    _verified_claims(body.capability, action_id, tenant_key, user_id, body.action_digest)
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.status in {"local_applied", "synced", "sync_pending"}:
            raise HTTPException(status_code=409, detail={"code": "action_already_applied"})
        row.status = "discarded"
        await db.commit()
        await db.refresh(row)
        return _response(row)


@router.post("/{action_id}/resume-sync")
async def resume_knowledge_action_sync(
    action_id: str,
    body: KnowledgeActionResumeRequest,
    payload: dict[str, Any] = Depends(require_auth),
) -> dict[str, Any]:
    """Resume only the sync ledger after a local transaction survived app restart.

    This endpoint cannot alter the proposal or note content. JWT ownership, the
    immutable action digest and the stable local result IDs must all match.
    """
    tenant_key, user_id = _identity(payload)
    if canonical_digest({"result_note_ids": body.result_note_ids}) != body.result_digest:
        raise HTTPException(status_code=422, detail={"code": "result_digest_mismatch"})
    async with SessionLocal() as db:
        row = await _owned_row(db, tenant_key, user_id, action_id, lock=True)
        if row.action_digest != body.action_digest:
            raise HTTPException(status_code=409, detail={"code": "action_payload_conflict"})
        if row.status == "discarded":
            raise HTTPException(status_code=409, detail={"code": "action_discarded"})
        if row.result_digest and row.result_digest != body.result_digest:
            raise HTTPException(status_code=409, detail={"code": "action_result_conflict"})
        if row.status == "synced":
            return _response(row)
        row.result_digest = body.result_digest
        row.result_note_ids = body.result_note_ids
        row.status = body.status
        row.error_code = body.error_code
        await db.commit()
        await db.refresh(row)
        return _response(row)
