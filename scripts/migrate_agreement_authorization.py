"""Evidence-only authorization repair. Default: READ ONLY, never replay notes.

Run from repository root: python -m scripts.migrate_agreement_authorization
DATABASE_URL must be explicitly set. --apply additionally requires a NEW --audit
JSONL path. No schema creation, login calls, source edits, or Hermes execution.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path

from sqlalchemy import select, text

from backend.models.agreement import UserAgreementAcceptance as Acceptance
from backend.models.tenant import TenantMapping
from backend.services.agreement_authorization import CURRENT_VERSION, project_acceptance, utc
from backend.services.user_note_context import namespace


def inventory(root: Path, grants: dict) -> dict:
    """Inspect exact persisted source times. Unknown evidence is excluded.

    A post-acceptance source is only a *candidate*, never an authorization grant.
    This inventory deliberately does not enqueue it or modify private indexes.
    """
    counts = Counter()
    records = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        counts["total"] += 1
        state = "archive" if ".archive" in rel.parts else "trash" if ".trash" in rel.parts else "active"
        counts[state] += 1
        reason = "excluded_unknown_evidence"
        changed_at = None
        if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
            reason = "excluded_unsafe_path"
        else:
            try:
                metadata = json.loads(path.with_suffix(".sync.json").read_text())
                changed_at = utc(datetime.fromisoformat(metadata.get("source_changed_at") or
                    metadata.get("client_updated_at") or metadata["synced_at"]))
                grant = grants.get(tuple(rel.parts[:2]))
                if state != "active":
                    reason = "excluded_inactive"
                elif hashlib.sha256(path.read_bytes()).hexdigest() != metadata.get("content_hash"):
                    reason = "excluded_hash_mismatch"
                elif not grant or metadata.get("owner_user_id") != grant["user_id"]:
                    reason = "excluded_no_current_acceptance"
                elif changed_at < utc(datetime.fromisoformat(grant["accepted_at"])):
                    reason = "excluded_pre_acceptance"
                elif changed_at > datetime.now(timezone.utc):
                    reason = "excluded_future_timestamp"
                elif grant["status"] != "ready":
                    reason = "excluded_authorization_conflict"
                elif changed_at < utc(datetime.fromisoformat(grant["contribution_effective_at"])):
                    reason = "excluded_pre_participation"
                else:
                    reason = "post_acceptance_candidate_not_enqueued"
            except (OSError, ValueError, KeyError, TypeError):
                pass
        counts[reason] += 1
        records.append({"path": rel.as_posix(), "state": state, "reason": reason,
                        "source_changed_at": changed_at.isoformat() if changed_at else None})
    return {"counts": dict(sorted(counts.items())), "records": records,
            "private_index_action": "unchanged", "source_action": "unchanged"}


def audit_line(handle, value: dict) -> None:
    handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n")
    handle.flush()
    os.fsync(handle.fileno())


async def migrate(session_factory, *, root: Path, apply: bool = False, audit=None) -> dict:
    if apply and audit is None:
        raise ValueError("apply requires a durable audit journal")
    reports = []
    async with session_factory() as db:
        if not apply and db.bind.dialect.name == "postgresql":
            await db.execute(text("SET TRANSACTION READ ONLY"))
        mappings = list((await db.scalars(select(TenantMapping).order_by(TenantMapping.user_id))).all())
        acceptances = list((await db.scalars(select(Acceptance).where(
            Acceptance.agreement_version == CURRENT_VERSION,
        ).order_by(Acceptance.accepted_at, Acceptance.id))).all())
        by_user = {row.user_id: row for row in mappings}
        for acceptance in acceptances:
            mapping = by_user.get(acceptance.user_id)
            if mapping is None:
                reports.append({"acceptance_id": acceptance.id, "user_id": acceptance.user_id,
                                "status": "blocked_missing_mapping"})
                continue
            try:
                reports.append(await project_acceptance(db, acceptance=acceptance,
                    tenant_key=mapping.tenant_key, apply=apply))
            except ValueError as exc:
                reports.append({"acceptance_id": acceptance.id, "user_id": acceptance.user_id,
                                "status": "blocked_invalid_evidence", "reason": str(exc)})
        grants = {(namespace(r["tenant_key"]), namespace(r["user_id"])): r
                  for r in reports if "tenant_key" in r}
        result = {"tool": "agreement-authorization-v1", "mode": "apply" if apply else "dry-run",
                  "agreement_version": CURRENT_VERSION, "acceptance_count": len(acceptances),
                  "mapped_user_count": len(mappings),
                  "mapped_without_current_acceptance": sorted(set(by_user) - {a.user_id for a in acceptances}),
                  "authorizations": reports, "notes": inventory(root, grants),
                  "historical_backfill": False, "notes_enqueued": 0}
        result["plan_sha256"] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        if apply:
            audit_line(audit, {"phase": "prepared", "report": result})
            await db.commit()
            audit_line(audit, {"phase": "committed", "plan_sha256": result["plan_sha256"]})
        else:
            await db.rollback()
    if apply:
        # Read back exact targets; no "commit succeeded therefore verified" claim.
        verified = []
        async with session_factory() as db:
            for report in reports:
                if report["status"] != "ready":
                    continue
                acceptance = await db.get(Acceptance, report["acceptance_id"])
                check = await project_acceptance(db, acceptance=acceptance,
                                                tenant_key=report["tenant_key"], apply=False)
                if check["status"] != "ready" or check["policy_action"] != "unchanged" or check["consent_action"] != "unchanged":
                    raise RuntimeError("post-apply verification conflict; consult audit journal")
                verified.append(report["acceptance_id"])
        result["verified_acceptance_ids"] = verified
        audit_line(audit, {"phase": "verified", "acceptance_ids": verified,
                           "plan_sha256": result["plan_sha256"]})
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="explicitly apply authorization-only repairs")
    parser.add_argument("--audit", type=Path, help="new private JSONL journal; required for apply")
    parser.add_argument("--sync-root", type=Path, required=True, help="raw/dialogues/tenants root to inventory")
    args = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        parser.error("DATABASE_URL must be explicitly configured (never print credentials)")
    if not args.sync_root.is_dir():
        parser.error("--sync-root must be an existing directory")
    if args.apply and not args.audit:
        parser.error("--apply requires --audit pointing to a new journal")
    from backend.db import SessionLocal, engine

    async def run(audit=None):
        try:
            result = await migrate(SessionLocal, root=args.sync_root, apply=args.apply, audit=audit)
            print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2))
        finally:
            await engine.dispose()

    if args.audit:
        fd = os.open(args.audit, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            asyncio.run(run(handle))
    else:
        asyncio.run(run())


if __name__ == "__main__":
    main()
