"""Persistent shard placement and writer leases for user state capsules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import os

from sqlalchemy import func, select, text

from backend.db import SessionLocal
from backend.models.tenant import RuntimePlacement
from backend.services.llm_usage import usage_user_id


LEASE_SECONDS = max(int(os.environ.get("QUANTUM_RUNTIME_LEASE_SECONDS", "900")), 60)


class RuntimePlacementConflict(RuntimeError):
    pass


@dataclass(frozen=True)
class Placement:
    tenant_user_hash: str
    shard_id: str
    generation: int

    def bridge_config(self) -> dict[str, object]:
        return {
            "tenant_user_hash": self.tenant_user_hash,
            "shard_id": self.shard_id,
            "generation": self.generation,
        }


def _shards() -> tuple[str, ...]:
    values = tuple(dict.fromkeys(
        item.strip() for item in os.environ.get("QUANTUM_RUNTIME_SHARDS", "shard-1").split(",")
        if item.strip()
    ))
    if not values:
        raise RuntimeError("runtime_shards_not_configured")
    return values


def tenant_user_hash(auth_payload: dict) -> str:
    tenant = str(auth_payload.get("tenant_key") or "").strip()
    user = usage_user_id(auth_payload)
    if not tenant or not user:
        raise RuntimePlacementConflict("runtime_identity_required")
    return hashlib.sha256(f"{tenant}\0{user}".encode()).hexdigest()


def _utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


async def claim_runtime_placement(auth_payload: dict) -> Placement:
    """Renew a writer lease only from the capsule's assigned shard."""
    owner_hash = tenant_user_hash(auth_payload)
    local_shard = os.environ.get("QUANTUM_RUNTIME_SHARD_ID", "shard-1").strip()
    shards = _shards()
    if local_shard not in shards:
        raise RuntimeError("runtime_local_shard_not_configured")
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_id = int.from_bytes(bytes.fromhex(owner_hash[:16]), "big", signed=True)
                await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            row = await db.get(RuntimePlacement, owner_hash)
            if row is None:
                raise RuntimePlacementConflict("runtime_placement_not_resolved")
            if row.state != "active":
                raise RuntimePlacementConflict("runtime_capsule_migrating")
            if row.shard_id != local_shard:
                raise RuntimePlacementConflict("runtime_shard_mismatch")
            if row.lease_owner != local_shard and _utc(row.lease_expires_at) > now:
                raise RuntimePlacementConflict("runtime_writer_lease_conflict")
            row.lease_owner = local_shard
            row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            row.updated_at = now
            return Placement(owner_hash, row.shard_id, int(row.generation))


async def resolve_runtime_placement(
    auth_payload: dict, *, preferred_shard: str | None = None,
) -> Placement:
    """Persist a least-loaded shard choice without granting filesystem write access."""
    owner_hash = tenant_user_hash(auth_payload)
    shards = _shards()
    if preferred_shard is not None and preferred_shard not in shards:
        raise RuntimePlacementConflict("runtime_shard_not_configured")
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        async with db.begin():
            if db.bind is not None and db.bind.dialect.name == "postgresql":
                lock_id = int.from_bytes(bytes.fromhex(owner_hash[:16]), "big", signed=True)
                await db.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})
            row = await db.get(RuntimePlacement, owner_hash)
            if row is None:
                counts = dict((await db.execute(
                    select(RuntimePlacement.shard_id, func.count()).group_by(RuntimePlacement.shard_id)
                )).all())
                shard = preferred_shard or min(
                    shards, key=lambda item: (int(counts.get(item, 0)), item)
                )
                row = RuntimePlacement(
                    tenant_user_hash=owner_hash,
                    shard_id=shard,
                    generation=1,
                    lease_owner="",
                    lease_expires_at=now,
                    state="active",
                )
                db.add(row)
                await db.flush()
            if row.state != "active":
                raise RuntimePlacementConflict("runtime_capsule_migrating")
            if row.shard_id not in shards:
                raise RuntimePlacementConflict("runtime_shard_not_configured")
            return Placement(owner_hash, row.shard_id, int(row.generation))


async def migrate_runtime_placement(
    owner_hash: str, *, source_shard: str, target_shard: str, expected_generation: int,
) -> Placement:
    """Atomically transfer ownership after an operator has restored the capsule."""
    if target_shard not in _shards() or target_shard == source_shard:
        raise RuntimePlacementConflict("invalid_runtime_migration")
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        async with db.begin():
            row = await db.get(RuntimePlacement, owner_hash)
            if (
                row is None
                or row.shard_id != source_shard
                or int(row.generation) != expected_generation
                or row.lease_owner != source_shard
                or row.state != "migrating"
            ):
                raise RuntimePlacementConflict("runtime_migration_cas_failed")
            row.shard_id = target_shard
            row.generation += 1
            row.lease_owner = target_shard
            row.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            row.state = "active"
            row.updated_at = now
            return Placement(owner_hash, target_shard, int(row.generation))


async def freeze_runtime_placement(
    owner_hash: str, *, source_shard: str, expected_generation: int,
) -> None:
    """Stop new runs on a drained source shard before snapshotting its capsule."""
    now = datetime.now(timezone.utc)
    async with SessionLocal() as db:
        async with db.begin():
            row = await db.get(RuntimePlacement, owner_hash)
            if (
                row is None
                or row.shard_id != source_shard
                or int(row.generation) != expected_generation
                or row.lease_owner != source_shard
                or row.state != "active"
            ):
                raise RuntimePlacementConflict("runtime_freeze_cas_failed")
            row.state = "migrating"
            row.lease_expires_at = now
            row.updated_at = now
