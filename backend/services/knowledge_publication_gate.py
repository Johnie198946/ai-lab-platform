"""Fail-closed publication gate for V4 Green projections."""
from __future__ import annotations

import os
import re
from typing import Any

import yaml
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.knowledge_contribution import (
    KnowledgeContributionBinding as Binding,
    KnowledgeContributionOutbox as Event,
    KnowledgeContributionPolicy as Policy,
    KnowledgeContributionProjection as Projection,
    KnowledgeContributionRun as Run,
)
from backend.services.knowledge_catalog import (
    CONTRIBUTION_PUBLICATION_POLICY,
    _live_frontmatter,
    _vault,
    clear_knowledge_caches,
)
from backend.services.knowledge_color_projection import approve_color, restore_note
from backend.services.knowledge_contribution import _epoch


def _receipt_value(receipt: dict, name: str) -> str:
    return str(receipt.get(name) or "")


async def validate_green_contribution(*, relative_path: str, projection_id: str) -> Projection | None:
    metadata = _live_frontmatter(_vault(), relative_path)
    file_policy = str(metadata.get("publication_policy") or "")
    file_projection_id = str(metadata.get("contribution_projection_id") or "")
    async with SessionLocal() as db:
        rows = list((await db.scalars(select(Projection).where(
            Projection.artifact_ref == relative_path,
        ))).all())
        if projection_id:
            rows = [row for row in rows if row.projection_id == projection_id]
            if len(rows) != 1:
                raise ValueError("contribution projection binding not found")
        elif not rows and (file_policy == CONTRIBUTION_PUBLICATION_POLICY or file_projection_id):
            raise ValueError("tenant contribution cannot use manual approval")
        elif not rows:
            return None
        elif len(rows) != 1:
            raise ValueError("ambiguous contribution projection binding")
        projection = rows[0]
        if file_projection_id and file_projection_id != projection.projection_id:
            raise ValueError("contribution file binding mismatch")
        snapshot = projection.metadata_snapshot or {}
        governance = snapshot.get("governance") or {}
        flags = ("enforced_searchable", "enforced_summarizable", "enforced_agent_callable")
        if (projection.status != "active" or projection.security_level != "green"
                or projection.read_only is not True
                or any(snapshot.get(flag) is not True for flag in flags)):
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
        expected = ["knowledge_tenant_compile", "knowledge_sanitize", "knowledge_privacy_review"]
        if not isinstance(receipts, list) or len(receipts) != 3:
            raise ValueError("three persisted Hermes stage receipts required")
        by_stage = {str(item.get("stage") or ""): item for item in receipts if isinstance(item, dict)}
        if set(by_stage) != set(expected):
            raise ValueError("complete Hermes stage receipt chain required")
        ordered = [by_stage[stage] for stage in expected]
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
            Binding.projection_id == projection.projection_id,
        ))).all())
        if not bindings or any(binding.active is not True for binding in bindings):
            raise ValueError("active evidence bindings required")
        events = [await db.get(Event, binding.event_id) for binding in bindings]
        blocked = {"withdrawn", "excluded", "archived", "stale", "quarantined", "withdrawing"}
        if (any(event is None or event.status in blocked
                or event.authorization_epoch != epochs[0] for event in events)
                or any(event.business_state.get("synthetic_hypothesis")
                       or event.business_state.get("simulated") for event in events if event)):
            raise ValueError("non-synthetic active real-world evidence required")
        return projection


def _bind(path, metadata: dict, original: str, projection: Projection) -> None:
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


async def machine_approve_green(*, relative_path: str, projection_id: str) -> dict[str, Any]:
    projection = await validate_green_contribution(
        relative_path=relative_path, projection_id=projection_id,
    )
    path = original = None
    try:
        path, original, metadata = approve_color(
            _vault(), relative_path=relative_path, security_level="green",
            approved_by="hermes:tenant_contribution_policy_v1",
            entitlement_key="", owner_tenant="",
        )
        _bind(path, metadata, original, projection)
    except Exception:
        if path is not None and original is not None:
            restore_note(path, original)
        clear_knowledge_caches()
        raise
    clear_knowledge_caches()
    return {"path": relative_path, "security_level": "green",
            "classification_status": metadata["classification_status"],
            "gateway_status": "available"}
