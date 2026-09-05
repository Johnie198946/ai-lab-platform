"""One-action Green/Yellow/Red publication approval for super administrators."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re

import httpx
import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.auth import require_auth
from backend.api import knowledge_policy
from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionBinding as Binding,
    KnowledgeContributionOutbox as Event,
    KnowledgeContributionPolicy as Policy,
    KnowledgeContributionProjection as Projection,
    KnowledgeContributionRun as Run,
)
from backend.services.knowledge_catalog import (
    CONTRIBUTION_PUBLICATION_POLICY, _live_frontmatter, clear_manifest_cache,
)
from backend.services.knowledge_color_projection import approve_color, color_approval_candidates, restore_note
from backend.services.knowledge_contribution import _epoch

router = APIRouter(prefix="/api/v1/admin/knowledge-publication", tags=["knowledge-publication"])
AUTHEN_URL = os.environ.get("AUTHEN_SUBSCRIPTION_URL", "http://host.docker.internal:8006").rstrip("/")
AUTHEN_TOKEN = os.environ.get("AUTHEN_AI_PLATFORM_SERVICE_TOKEN", "")
APPROVAL_SECRET = os.environ.get("AUTHEN_KNOWLEDGE_APPROVAL_SECRET", "")


class PublicationDecision(BaseModel):
    path: str = Field(..., min_length=6, max_length=1200)
    security_level: str = Field(..., pattern="^(green|yellow|red)$")
    entitlement_key: str = Field(default="", max_length=128)
    owner_tenant: str = Field(default="", max_length=64)
    contribution_projection_id: str = Field(default="", max_length=96)


def _super(payload: dict) -> None:
    if not payload.get("is_super_admin"):
        raise HTTPException(status_code=403, detail="super administrator required")


def _vault():
    from backend.services.knowledge_catalog import _vault as catalog_vault
    return catalog_vault()


def _invalidate_publication_caches() -> None:
    clear_manifest_cache()
    knowledge_policy._SEARCH_CACHE.clear()


def _receipt_value(receipt: dict, name: str) -> str:
    return str(receipt.get(name) or "")


async def _green_contribution_gate(*, relative_path: str, projection_id: str) -> Projection | None:
    """Verify every durable V4 gate before a contributed artifact becomes Green."""
    file_metadata = _live_frontmatter(_vault(), relative_path)
    file_policy = str(file_metadata.get("publication_policy") or "")
    file_projection_id = str(file_metadata.get("contribution_projection_id") or "")
    async with SessionLocal() as db:
        query = select(Projection).where(
            Projection.artifact_ref == relative_path,
        )
        projections = list((await db.scalars(query)).all())
        if projection_id:
            projections = [row for row in projections if row.projection_id == projection_id]
            if len(projections) != 1:
                raise ValueError("contribution projection binding not found")
        elif not projections and (file_policy == CONTRIBUTION_PUBLICATION_POLICY
                                  or file_projection_id):
            raise ValueError("tenant contribution cannot use manual approval")
        elif not projections:
            return None  # Legacy/manual document, retained for compatibility.
        elif len(projections) != 1:
            raise ValueError("ambiguous contribution projection binding")
        projection = projections[0]
        if file_projection_id and file_projection_id != projection.projection_id:
            raise ValueError("contribution file binding mismatch")
        snapshot = projection.metadata_snapshot or {}
        governance = snapshot.get("governance") or {}
        if (projection.status != "active" or projection.security_level != "green"
                or projection.read_only is not True
                or any(snapshot.get(flag) is not True for flag in (
                    "enforced_searchable", "enforced_summarizable", "enforced_agent_callable"
                ))):
            raise ValueError("contribution projection is not active")
        if (governance.get("publication_policy") != CONTRIBUTION_PUBLICATION_POLICY
                or governance.get("classification_status") != "approved"
                or governance.get("security_level") != "green"
                or not governance.get("approved_by")
                or (governance.get("governance_thresholds_met") is not True
                    and governance.get("thresholds_passed") is not True)
                or governance.get("privacy_decision") != "approve"):
            raise ValueError("tenant contribution governance gate failed")
        receipts = governance.get("stage_receipts")
        expected_stages = [
            "knowledge_tenant_compile", "knowledge_sanitize", "knowledge_privacy_review"
        ]
        if not isinstance(receipts, list) or len(receipts) != 3:
            raise ValueError("three persisted Hermes stage receipts required")
        by_stage = {str(item.get("stage") or ""): item for item in receipts if isinstance(item, dict)}
        if set(by_stage) != set(expected_stages):
            raise ValueError("complete Hermes stage receipt chain required")
        ordered = [by_stage[stage] for stage in expected_stages]
        run_ids = [_receipt_value(item, "run_id") for item in ordered]
        sessions = [_receipt_value(item, "session_id") for item in ordered]
        hashes = [_receipt_value(item, "candidate_hash") for item in ordered]
        epochs = [_receipt_value(item, "authorization_epoch") for item in ordered]
        if (len(set(run_ids)) != 3 or len(set(sessions)) != 3 or not all(run_ids)
                or not all(sessions) or len(set(hashes)) != 1 or not hashes[0]
                or len(set(epochs)) != 1 or not epochs[0]
                or not re.fullmatch(r"[a-f0-9]{64}", hashes[0])
                or not re.fullmatch(r"[a-f0-9]{64}", epochs[0])
                or _receipt_value(ordered[0], "predecessor_run_id")
                or _receipt_value(ordered[1], "predecessor_run_id") != run_ids[0]
                or _receipt_value(ordered[2], "predecessor_run_id") != run_ids[1]
                or any(item.get("validated") is not True or item.get("simulated") is not False
                       or item.get("type") != "knowledge_stage_receipt"
                       or item.get("version") != "knowledge-run-v4.1"
                       or item.get("tenant_id") != projection.tenant_key
                       or item.get("user_id") != projection.user_id for item in ordered)
                or ordered[-1].get("decision") != "approve"):
            raise ValueError("Hermes receipt independence or binding failed")
        if (governance.get("candidate_hash") != hashes[0]
                or governance.get("authorization_epoch") != epochs[0]):
            raise ValueError("candidate hash or authorization epoch mismatch")
        run = await db.scalar(select(Run).where(Run.projection_id == projection.projection_id))
        policy = await db.get(Policy, projection.tenant_key)
        if (not run or run.status != "accepted" or run.authorization_epoch != epochs[0]
                or not policy or not policy.enabled or _epoch(policy) != epochs[0]):
            raise ValueError("durable run or current authorization gate failed")
        bindings = list((await db.scalars(select(Binding).where(
            Binding.projection_id == projection.projection_id
        ))).all())
        if not bindings or any(binding.active is not True for binding in bindings):
            raise ValueError("active evidence bindings required")
        events = [await db.get(Event, binding.event_id) for binding in bindings]
        if (any(event is None or event.status in {
                "withdrawn", "excluded", "archived", "stale", "quarantined", "withdrawing"
            } or event.authorization_epoch != epochs[0] for event in events)
                or any(event.business_state.get("synthetic_hypothesis")
                       or event.business_state.get("simulated") for event in events if event)):
            raise ValueError("non-synthetic active real-world evidence required")
        return projection


def _bind_contribution_file(path, metadata: dict, original: str, projection: Projection) -> None:
    match = re.match(r"^---\s*\n(.*?)\n---\s*(?:\n|$)", original, re.DOTALL)
    body = original[match.end():] if match else original
    metadata.update({
        "publication_policy": CONTRIBUTION_PUBLICATION_POLICY,
        "contribution_projection_id": projection.projection_id,
    })
    rendered = "---\n" + yaml.safe_dump(metadata, allow_unicode=True, sort_keys=False).rstrip() + "\n---\n\n" + body.lstrip("\n")
    temporary = path.with_name(f".{path.name}.{os.getpid()}.contribution.tmp")
    temporary.write_text(rendered, encoding="utf-8")
    os.replace(temporary, path)


async def _notify_authen(*, path: str, entitlement_key: str, approved_by: str) -> None:
    if not AUTHEN_TOKEN or not APPROVAL_SECRET:
        raise HTTPException(status_code=503, detail={"code": "authen_approval_sync_unconfigured", "message": "Yellow 审批联动尚未配置，文档未发布"})
    event = {
        "event_id": "kpa_" + hashlib.sha256(f"{path}:{entitlement_key}".encode()).hexdigest()[:32],
        "application_id": "ai-lab-platform", "entitlement_key": entitlement_key,
        "approved_by": approved_by, "source_path": path,
    }
    raw = json.dumps(event, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    signature = hmac.new(APPROVAL_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                f"{AUTHEN_URL}/api/v1/internal/knowledge-pack-approvals",
                content=raw,
                headers={"Authorization": f"Bearer {AUTHEN_TOKEN}", "Content-Type": "application/json", "X-Approval-Signature": f"sha256={signature}"},
            )
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail={"code": "authen_approval_sync_failed", "message": "Authen 暂不可达，审批已回滚"}) from exc
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail={"code": "authen_approval_sync_rejected", "message": "Authen 未接受知识包审批，审批已回滚"})


async def machine_approve_green(*, relative_path: str, projection_id: str) -> dict:
    """Publish only a Green projection carrying all verified Hermes receipts."""
    projection = await _green_contribution_gate(
        relative_path=relative_path, projection_id=projection_id,
    )
    path = None
    original = None
    try:
        path, original, metadata = approve_color(
            _vault(), relative_path=relative_path, security_level="green",
            approved_by="hermes:tenant_contribution_policy_v1",
            entitlement_key="", owner_tenant="",
        )
        _bind_contribution_file(path, metadata, original, projection)
    except Exception:
        if path is not None and original is not None:
            restore_note(path, original)
        _invalidate_publication_caches()
        raise
    _invalidate_publication_caches()
    return {"path": relative_path, "security_level": "green",
            "classification_status": metadata["classification_status"],
            "gateway_status": "available"}


@router.get("")
async def candidates(payload=Depends(require_auth)):
    _super(payload)
    return {"items": color_approval_candidates(_vault())}


@router.post("/approve")
async def approve(body: PublicationDecision, payload=Depends(require_auth)):
    _super(payload)
    actor = str(payload.get("user_id") or payload.get("sub") or "")
    projection = None
    if body.security_level == "green":
        try:
            projection = await _green_contribution_gate(
                relative_path=body.path,
                projection_id=body.contribution_projection_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    try:
        path, original, metadata = approve_color(
            _vault(), relative_path=body.path, security_level=body.security_level,
            approved_by=actor, entitlement_key=body.entitlement_key,
            owner_tenant=body.owner_tenant,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        if projection is not None:
            _bind_contribution_file(path, metadata, original, projection)
        if body.security_level == "yellow":
            await _notify_authen(
                path=body.path, entitlement_key=body.entitlement_key,
                approved_by=actor,
            )
    except HTTPException:
        restore_note(path, original)
        _invalidate_publication_caches()
        raise
    except Exception as exc:
        restore_note(path, original)
        _invalidate_publication_caches()
        raise HTTPException(status_code=500, detail={"code": "approval_transaction_failed", "message": "审批联动失败，文档已回滚"}) from exc
    _invalidate_publication_caches()
    return {"path": body.path, "security_level": body.security_level, "classification_status": metadata["classification_status"], "gateway_status": "available"}
