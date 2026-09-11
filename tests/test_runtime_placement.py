from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.db import Base
from backend.models.tenant import RuntimePlacement
from backend.services import runtime_placement


@pytest.mark.asyncio
async def test_placement_is_sticky_and_migration_requires_a_frozen_generation(
    tmp_path, monkeypatch,
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'placement.db'}")
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(lambda sync: Base.metadata.create_all(
            sync, tables=[RuntimePlacement.__table__]
        ))
    monkeypatch.setattr(runtime_placement, "SessionLocal", factory)
    monkeypatch.setenv("QUANTUM_RUNTIME_SHARDS", "shard-1,shard-2")
    monkeypatch.setenv("QUANTUM_RUNTIME_SHARD_ID", "shard-1")
    auth = {"sub": "user-a", "tenant_key": "tenant-a"}

    first = await runtime_placement.resolve_runtime_placement(auth)
    again = await runtime_placement.resolve_runtime_placement(auth)
    assert first == again
    assert await runtime_placement.claim_runtime_placement(auth) == first
    with pytest.raises(runtime_placement.RuntimePlacementConflict):
        await runtime_placement.migrate_runtime_placement(
            first.tenant_user_hash,
            source_shard="shard-1",
            target_shard="shard-2",
            expected_generation=1,
        )
    await runtime_placement.freeze_runtime_placement(
        first.tenant_user_hash, source_shard="shard-1", expected_generation=1,
    )
    migrated = await runtime_placement.migrate_runtime_placement(
        first.tenant_user_hash,
        source_shard="shard-1",
        target_shard="shard-2",
        expected_generation=1,
    )
    assert (migrated.shard_id, migrated.generation) == ("shard-2", 2)
    with pytest.raises(runtime_placement.RuntimePlacementConflict, match="shard_mismatch"):
        await runtime_placement.claim_runtime_placement(auth)
    await engine.dispose()
