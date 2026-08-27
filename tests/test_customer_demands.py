from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.api.customer_demands import (
    DemandCreate,
    DemandConfirm,
    DemandPatch,
    confirm_demand,
    create_demand,
    get_demand,
    patch_demand,
)
from backend.db import Base
from backend.models.customer_demand import CustomerDemand


AUTH = {"sub": "user-1", "user_id": "user-1", "tenant_key": "tenant-a"}


def run(coro):
    return asyncio.run(coro)


@pytest.fixture
def demand_db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    run(setup())

    import backend.api.customer_demands as api

    monkeypatch.setattr(api, "SessionLocal", maker)
    yield maker
    run(engine.dispose())


@pytest.fixture
def concurrent_demand_db(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'demands.db'}")
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    run(setup())
    import backend.api.customer_demands as api
    monkeypatch.setattr(api, "SessionLocal", maker)
    yield maker
    run(engine.dispose())


def body(text="产线换型效率提升", **extra):
    return DemandCreate(source_text=text, **extra)


def test_demand_id_is_stable_and_duplicate_post_is_idempotent(demand_db):
    first = run(create_demand(body(), AUTH))
    duplicate = run(create_demand(body(tenant_key="spoofed", created_by="attacker"), AUTH))

    assert duplicate["demand_id"] == first["demand_id"]
    assert duplicate["source_hash"] == first["source_hash"]
    assert duplicate["tenant_key"] == "tenant-a"
    assert duplicate["created_by"] == "user-1"


def test_local_demo_identity_is_server_derived(demand_db):
    created = run(create_demand(body("本地验收需求"), {
        "tenant_key": "demo",
        "user_id": "",
        "sub": "",
        "username": "dev",
    }))

    assert created["tenant_key"] == "demo"
    assert created["created_by"] == "dev"


def test_cross_tenant_read_is_404(demand_db):
    created = run(create_demand(body(), AUTH))

    with pytest.raises(HTTPException) as error:
        run(get_demand(created["demand_id"], {"sub": "user-2", "user_id": "user-2", "tenant_key": "tenant-b"}))

    assert error.value.status_code == 404


def test_confirm_is_idempotent_and_confirmed_patch_is_rejected(demand_db):
    created = run(create_demand(body(), AUTH))
    confirmed = run(confirm_demand(created["demand_id"], DemandConfirm(expected_version=created["version"]), AUTH))
    with pytest.raises(HTTPException) as repeated:
        run(confirm_demand(created["demand_id"], DemandConfirm(expected_version=confirmed["version"]), AUTH))

    assert confirmed["status"] == "confirmed"
    assert repeated.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        run(patch_demand(created["demand_id"], DemandPatch(overall_goal="另一个目标", expected_version=confirmed["version"]), AUTH))
    assert error.value.status_code == 409


def test_demand_survives_a_new_session_and_validates_lengths(demand_db):
    created = run(create_demand(body(), AUTH))
    loaded = run(get_demand(created["demand_id"], AUTH))
    assert loaded["source_text"] == "产线换型效率提升"

    with pytest.raises(Exception):
        body("x" * 12001)

    with pytest.raises(Exception):
        body("ok", stakeholders=["x" * 501])


def test_patch_source_hash_conflict_is_controlled_409(demand_db):
    run(create_demand(body("first"), AUTH))
    second = run(create_demand(body("second"), AUTH))

    with pytest.raises(HTTPException) as error:
        run(patch_demand(second["demand_id"], DemandPatch(source_text="first", expected_version=second["version"]), AUTH))

    assert error.value.status_code == 409
    assert "source_hash" in error.value.detail


def test_concurrent_patch_and_confirm_have_one_compare_and_swap_winner(concurrent_demand_db):
    created = run(create_demand(body("race"), AUTH))

    async def race():
        return await asyncio.gather(
            patch_demand(
                created["demand_id"],
                DemandPatch(overall_goal="编辑者", expected_version=created["version"]),
            AUTH,
            ),
            confirm_demand(
                created["demand_id"],
                DemandConfirm(expected_version=created["version"]),
                AUTH,
            ),
            return_exceptions=True,
        )

    results = run(race())
    assert sum(not isinstance(result, HTTPException) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1


def test_concurrent_double_confirm_has_one_winner(concurrent_demand_db):
    created = run(create_demand(body("double-confirm"), AUTH))

    async def race():
        return await asyncio.gather(
            confirm_demand(created["demand_id"], DemandConfirm(expected_version=created["version"]), AUTH),
            confirm_demand(created["demand_id"], DemandConfirm(expected_version=created["version"]), AUTH),
            return_exceptions=True,
        )

    results = run(race())
    assert sum(not isinstance(result, HTTPException) for result in results) == 1
    assert sum(isinstance(result, HTTPException) and result.status_code == 409 for result in results) == 1
