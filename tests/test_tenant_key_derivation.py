from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api.auth import (
    _default_resolve_tenant,
    _derived_tenant_key,
    _derived_tenant_key_v2,
    _legacy_key_locks,
)
from backend.db import Base
from backend.models.tenant import TenantMapping


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def tenant_db(monkeypatch):
    _legacy_key_locks.clear()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    run(setup())
    import backend.db as db
    monkeypatch.setattr(db, "SessionLocal", maker)
    yield maker
    _legacy_key_locks.clear()
    run(engine.dispose())


def test_legacy_derivation_is_exact_for_long_ids_and_special_characters():
    assert _derived_tenant_key("e2e-user-a") == "u-e2e-user"
    assert _derived_tenant_key("E2E-user-a") == "u-E2E-user"
    assert _derived_tenant_key(" User/中文 ") == "u-User/中文"
    assert _derived_tenant_key("abcdefghXYZ") == "u-abcdefgh"


def test_v2_is_collision_safe_for_shared_legacy_prefix():
    assert _derived_tenant_key("e2e-user-a") == _derived_tenant_key("e2e-user-b")
    assert _derived_tenant_key_v2("e2e-user-a") != _derived_tenant_key_v2("e2e-user-b")


def test_first_user_keeps_legacy_and_second_collision_gets_v2(tenant_db):
    first = run(_default_resolve_tenant("e2e-user-a"))
    second = run(_default_resolve_tenant("e2e-user-b"))
    assert first["tenant_key"] == "u-e2e-user"
    assert second["tenant_key"] == _derived_tenant_key_v2("e2e-user-b")


def test_concurrent_first_resolution_splits_legacy_collision(tenant_db):
    async def resolve_both():
        return await asyncio.gather(
            _default_resolve_tenant("abcdefgh-first"),
            _default_resolve_tenant("abcdefgh-second"),
        )

    resolved = run(resolve_both())
    keys = {item["tenant_key"] for item in resolved}
    assert keys == {"u-abcdefgh", _derived_tenant_key_v2("abcdefgh-second")}

    async def read_rows():
        async with tenant_db() as db:
            return (
                await db.execute(
                    select(TenantMapping).order_by(TenantMapping.user_id)
                )
            ).scalars().all()

    rows = run(read_rows())
    assert len(rows) == 2
    assert {row.tenant_key for row in rows} == keys
    assert rows[0].tenant_key != rows[1].tenant_key


def test_existing_explicit_mapping_is_unchanged(tenant_db):
    async def seed():
        async with tenant_db() as db:
            db.add(
                TenantMapping(
                    user_id="org-user", org_id="org-1", tenant_key="shared-org"
                )
            )
            await db.commit()
    run(seed())
    assert run(_default_resolve_tenant("org-user"))["tenant_key"] == "shared-org"


def test_resolution_failure_fails_closed(monkeypatch):
    import backend.db as db

    class BrokenSession:
        async def __aenter__(self):
            raise RuntimeError("database down")
        async def __aexit__(self, *args):
            return False

    monkeypatch.setattr(db, "SessionLocal", BrokenSession)
    with pytest.raises(HTTPException) as error:
        run(_default_resolve_tenant("user-1"))
    assert error.value.status_code == 503
