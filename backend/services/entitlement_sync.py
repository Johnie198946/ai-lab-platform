"""Periodic Authen organization-entitlement reconciliation.

Webhook delivery gives low latency; this loop is the recovery path for missed events.
Yellow knowledge remains fail-closed because policy resolution rejects snapshots older
than the configured maximum age.
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

import httpx
from sqlalchemy import select

from backend.db import SessionLocal
from backend.models.tenant import TenantEntitlementSnapshot, TenantMapping

AUTHEN_SUBSCRIPTION_URL = os.environ.get(
    "AUTHEN_SUBSCRIPTION_URL", "http://host.docker.internal:8006"
).rstrip("/")
AUTHEN_SERVICE_TOKEN = os.environ.get("AUTHEN_AI_PLATFORM_SERVICE_TOKEN", "")
AUTHEN_APP_ID = os.environ.get("AUTHEN_APP_ID", "ai-lab-platform")
RECONCILE_SECONDS = int(os.environ.get("AUTHEN_ENTITLEMENT_RECONCILE_SECONDS", "300"))

_task: asyncio.Task | None = None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


async def reconcile_once() -> int:
    if not AUTHEN_SERVICE_TOKEN:
        return 0
    async with SessionLocal() as db:
        mappings = list((await db.execute(select(TenantMapping))).scalars().all())
    by_org: dict[str, set[str]] = {}
    for mapping in mappings:
        if mapping.org_id:
            by_org.setdefault(mapping.org_id, set()).add(mapping.tenant_key)
    updated = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for org_id, tenants in by_org.items():
            try:
                response = await client.get(
                    f"{AUTHEN_SUBSCRIPTION_URL}/api/v1/internal/organizations/{org_id}/entitlements",
                    params={"app_id": AUTHEN_APP_ID},
                    headers={"Authorization": f"Bearer {AUTHEN_SERVICE_TOKEN}"},
                )
                response.raise_for_status()
                item = response.json()
            except Exception:
                # Do not refresh synced_at on failure: yellow access naturally closes
                # once the existing projection reaches its 15 minute maximum age.
                continue
            async with SessionLocal() as db:
                for tenant_key in tenants:
                    snapshot = await db.get(TenantEntitlementSnapshot, tenant_key)
                    if snapshot is None:
                        snapshot = TenantEntitlementSnapshot(tenant_key=tenant_key, org_id=org_id)
                        db.add(snapshot)
                    incoming_version = int(item.get("entitlement_version") or 0)
                    if incoming_version < int(snapshot.entitlement_version or 0):
                        continue
                    snapshot.application_id = str(item.get("application_id") or AUTHEN_APP_ID)
                    snapshot.plan_id = str(item.get("plan_id") or "")
                    snapshot.status = str(item.get("status") or "inactive")
                    snapshot.knowledge_entitlements = sorted(
                        set(str(x) for x in item.get("knowledge_entitlements") or [])
                    )
                    snapshot.entitlement_version = incoming_version
                    snapshot.effective_until = _parse_datetime(item.get("effective_until"))
                    snapshot.synced_at = datetime.now(timezone.utc)
                    updated += 1
                await db.commit()
    return updated


async def _loop() -> None:
    while True:
        try:
            await reconcile_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(max(30, RECONCILE_SECONDS))


def start_entitlement_sync() -> None:
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop(), name="authen-entitlement-reconcile")


async def stop_entitlement_sync() -> None:
    global _task
    if _task is not None:
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
