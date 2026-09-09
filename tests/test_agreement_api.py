import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import jwt
from sqlalchemy import func, inspect, select
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.schema import CreateTable

from backend import db as db_module
from backend.api import agreement as agreement_api, auth
from backend.main import app
from backend.models.agreement import UserAgreementAcceptance
from backend.models.tenant import TenantMapping
from backend.models.knowledge_contribution import KnowledgeContributionPolicy, KnowledgeContributionUserConsent


def token(user_id: str) -> str:
    return jwt.encode(
        {"sub": user_id, "username": "agreement-test", "is_super_admin": False,
         "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        "test-secret", algorithm="HS256",
    )


@pytest.fixture(autouse=True)
def resolver(monkeypatch):
    async def resolve(user_id: str):
        from sqlalchemy.dialects.sqlite import insert
        async with agreement_api.SessionLocal() as db:
            await db.execute(insert(TenantMapping).values(user_id=user_id, tenant_key=f"tenant-{user_id}")
                             .on_conflict_do_nothing())
            await db.commit()
        return {"tenant_key": f"tenant-{user_id}", "org_id": "", "is_super_admin": False}

    monkeypatch.setattr(auth, "tenant_resolver", resolve)


@pytest_asyncio.fixture(autouse=True)
async def isolated_agreement_db(tmp_path: Path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'agreement.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        for model in (UserAgreementAcceptance, TenantMapping, KnowledgeContributionPolicy, KnowledgeContributionUserConsent):
            await connection.run_sync(model.__table__.create)
    monkeypatch.setattr(agreement_api, "SessionLocal", session_factory)
    yield session_factory
    await engine.dispose()


async def request(method: str, path: str, **kwargs):
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(method, path, **kwargs)


@pytest.mark.asyncio
async def test_public_agreement_has_versioned_three_section_contract_and_etag():
    response = await request("GET", "/api/v1/legal/agreement?locale=zh-CN")
    assert response.status_code == 200
    assert response.headers["etag"].startswith('"')
    body = response.json()
    assert [section["title"] for section in body["sections"]] == [
        "用户服务协议", "隐私保护条款", "知识共建协议",
    ]
    assert all(section["clauses"] for section in body["sections"])
    assert "markdown" not in body

    default_locale = await request("GET", "/api/v1/legal/agreement")
    assert default_locale.json() == body
    assert default_locale.headers["etag"] == response.headers["etag"]
    unavailable = await request("GET", "/api/v1/legal/agreement?locale=en-US")
    assert unavailable.status_code == 404
    assert unavailable.json() == {
        "detail": {"code": "agreement_locale_unavailable"}
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("header", ["{etag}", "W/{etag}", '"other", {etag}', "*"])
async def test_public_agreement_honors_if_none_match_without_a_body(header: str):
    current = await request("GET", "/api/v1/legal/agreement")
    etag = current.headers["etag"]
    cached = await request(
        "GET",
        "/api/v1/legal/agreement",
        headers={"If-None-Match": header.format(etag=etag)},
    )
    assert cached.status_code == 304
    assert cached.content == b""
    assert cached.headers["etag"] == etag


@pytest.mark.asyncio
async def test_public_agreement_ignores_a_non_matching_etag():
    response = await request(
        "GET", "/api/v1/legal/agreement", headers={"If-None-Match": '"old"'}
    )
    assert response.status_code == 200
    assert response.json()["version"] == agreement_api.CURRENT_AGREEMENT_VERSION


def test_public_clauses_cover_the_server_owned_user_boundaries():
    clauses = "\n".join(
        clause
        for section in agreement_api._document()["sections"]
        for clause in section["clauses"]
    )
    for boundary in (
        "真实、准确、完整",
        "访问控制、加密及审计",
        "删除或匿名化",
        "不会向无关第三方提供",
        "不回填或追溯",
        "不等于转让内容权利",
        "不会因本协议而未经授权自动公开",
        "旧确认失效",
    ):
        assert boundary in clauses


@pytest.mark.asyncio
async def test_acceptance_get_and_put_require_authentication():
    assert (await request("GET", "/api/v1/me/agreement-acceptance")).status_code == 401
    assert (await request("PUT", "/api/v1/me/agreement-acceptance", json={
        "agreement_version": "2026-09-06", "idempotency_key": str(uuid4()),
    })).status_code == 401


@pytest.mark.asyncio
async def test_acceptance_rejects_an_empty_jwt_subject():
    headers = {"Authorization": f"Bearer {token('')}"}
    assert (await request("GET", "/api/v1/me/agreement-acceptance", headers=headers)).status_code == 401
    response = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION,
        "idempotency_key": str(uuid4()),
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_current_acceptance_is_idempotent_and_readable(isolated_agreement_db):
    user_id = f"agreement-{uuid4()}"
    headers = {"Authorization": f"Bearer {token(user_id)}"}
    key = str(uuid4())
    before = await request("GET", "/api/v1/me/agreement-acceptance", headers=headers)
    assert before.json() == {"agreement_version": None, "accepted_at": None}
    payload = {"agreement_version": "2026-09-06", "idempotency_key": key, "source": "ios"}
    first = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json=payload)
    second = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json=payload)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    accepted = await request("GET", "/api/v1/me/agreement-acceptance", headers=headers)
    assert accepted.json()["agreement_version"] == "2026-09-06"
    async with isolated_agreement_db() as db:
        count = await db.scalar(select(func.count()).select_from(UserAgreementAcceptance).where(
            UserAgreementAcceptance.user_id == user_id
        ))
    assert count == 1


@pytest.mark.asyncio
async def test_same_user_and_version_with_a_different_key_returns_the_same_fact(
    isolated_agreement_db,
):
    user_id = f"agreement-{uuid4()}"
    headers = {"Authorization": f"Bearer {token(user_id)}"}
    body = {"agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION}
    first = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        **body, "idempotency_key": str(uuid4()),
    })
    second = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        **body, "idempotency_key": str(uuid4()),
    })
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    async with isolated_agreement_db() as db:
        assert await db.scalar(select(func.count()).select_from(UserAgreementAcceptance)) == 1


@pytest.mark.asyncio
async def test_same_key_for_a_different_version_is_a_conflict(isolated_agreement_db):
    user_id = f"agreement-{uuid4()}"
    key = str(uuid4())
    async with isolated_agreement_db() as db:
        db.add(UserAgreementAcceptance(
            user_id=user_id,
            agreement_version="prior-version",
            locale="zh-CN",
            source="ios",
            idempotency_key=key,
        ))
        await db.commit()
    response = await request(
        "PUT",
        "/api/v1/me/agreement-acceptance",
        headers={"Authorization": f"Bearer {token(user_id)}"},
        json={
            "agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION,
            "idempotency_key": key,
        },
    )
    assert response.status_code == 409
    assert response.json() == {"detail": {"code": "idempotency_key_conflict"}}


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_requests_recover_both_unique_constraint_races(
    isolated_agreement_db, same_key: bool,
):
    user_id = f"agreement-{uuid4()}"
    headers = {"Authorization": f"Bearer {token(user_id)}"}
    keys = [str(uuid4())] * 2 if same_key else [str(uuid4()), str(uuid4())]
    responses = await asyncio.gather(*(
        request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
            "agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION,
            "idempotency_key": key,
        })
        for key in keys
    ))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json() == responses[1].json()
    async with isolated_agreement_db() as db:
        assert await db.scalar(select(func.count()).select_from(UserAgreementAcceptance)) == 1


@pytest.mark.asyncio
async def test_acceptance_get_ignores_a_newer_obsolete_version(isolated_agreement_db):
    user_id = f"agreement-{uuid4()}"
    async with isolated_agreement_db() as db:
        db.add(UserAgreementAcceptance(
            user_id=user_id,
            agreement_version="obsolete-version",
            locale="zh-CN",
            source="web",
            idempotency_key=str(uuid4()),
            accepted_at=datetime(2030, 1, 1, tzinfo=timezone.utc),
        ))
        await db.commit()
    response = await request(
        "GET", "/api/v1/me/agreement-acceptance",
        headers={"Authorization": f"Bearer {token(user_id)}"},
    )
    assert response.json() == {"agreement_version": None, "accepted_at": None}


@pytest.mark.asyncio
async def test_stale_unknown_and_old_consent_fields_fail_closed():
    headers = {"Authorization": f"Bearer {token('agreement-' + uuid4().hex)}"}
    stale = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "2026-01-01", "idempotency_key": str(uuid4()),
    })
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "agreement_version_outdated"
    malformed = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "2026-09-06", "idempotency_key": "not-a-uuid",
    })
    assert malformed.status_code == 422
    old_field = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "2026-09-06", "idempotency_key": str(uuid4()),
        "knowledge_contribution_enabled": False,
    })
    assert old_field.status_code == 422
    extra_field = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "2026-09-06", "idempotency_key": str(uuid4()),
        "effective_at": "2026-09-06T00:00:00Z",
    })
    assert extra_field.status_code == 422


@pytest.mark.asyncio
async def test_reusing_a_current_key_with_a_stale_payload_is_an_idempotency_conflict():
    user_id = f"agreement-{uuid4()}"
    headers = {"Authorization": f"Bearer {token(user_id)}"}
    key = str(uuid4())
    accepted = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION,
        "idempotency_key": key,
    })
    assert accepted.status_code == 200
    reused = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "stale-version",
        "idempotency_key": key,
    })
    assert reused.status_code == 409
    assert reused.json() == {"detail": {"code": "idempotency_key_conflict"}}


@pytest.mark.asyncio
async def test_legacy_clients_and_compatible_environment_cannot_waive_agreement(monkeypatch):
    monkeypatch.delenv("AGREEMENT_ENFORCEMENT_MODE", raising=False)
    user_id = f"agreement-{uuid4()}"
    legacy_headers = {"Authorization": f"Bearer {token(user_id)}"}
    assert (await request("GET", "/api/screens", headers=legacy_headers)).status_code == 428
    # The old arbitrary opt-in header is ignored; it is not an authorization boundary.
    old_header = {**legacy_headers, "X-Agreement-Contract": "current"}
    assert (await request("GET", "/api/screens", headers=old_header)).status_code == 428
    headers = {**legacy_headers, "X-Client-Contract": "ios-unified-agreement-v1"}
    blocked = await request("GET", "/api/screens", headers=headers)
    assert blocked.status_code == 428
    assert blocked.json()["detail"] == {
        "code": "agreement_required", "current_version": "2026-09-06",
    }
    accepted = await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": "2026-09-06", "idempotency_key": str(uuid4()),
    })
    assert accepted.status_code == 200
    assert (await request("GET", "/api/screens", headers=headers)).status_code == 200


@pytest.mark.asyncio
async def test_required_mode_is_global_and_does_not_trust_client_marker(monkeypatch):
    monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", "required")
    headers = {"Authorization": f"Bearer {token('agreement-' + uuid4().hex)}"}
    assert (await request("GET", "/api/screens", headers=headers)).status_code == 428
    spoofed = {**headers, "X-Client-Contract": "legacy"}
    assert (await request("GET", "/api/screens", headers=spoofed)).status_code == 428


@pytest.mark.asyncio
async def test_unknown_enforcement_mode_fails_closed(monkeypatch):
    monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", "typo")
    headers = {"Authorization": f"Bearer {token('agreement-' + uuid4().hex)}"}
    assert (await request("GET", "/api/screens", headers=headers)).status_code == 428


@pytest.mark.asyncio
async def test_required_mode_gates_showroom_http_and_admin_mutation(monkeypatch):
    monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", "required")
    headers = {"Authorization": f"Bearer {token('agreement-' + uuid4().hex)}"}
    for method, path, body in (
        ("GET", "/api/showroom/state", None),
        ("POST", "/api/v1/admin/users", {}),
    ):
        response = await request(method, path, headers=headers, json=body)
        assert response.status_code == 428
        assert response.json() == {"detail": {
            "code": "agreement_required",
            "current_version": agreement_api.CURRENT_AGREEMENT_VERSION,
        }}


@pytest.mark.asyncio
async def test_legacy_contribution_consent_is_not_current_agreement_state(monkeypatch):
    monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", "compatible")
    user_id = f"agreement-{uuid4()}"
    headers = {"Authorization": f"Bearer {token(user_id)}"}
    legacy = await request(
        "PUT",
        "/api/v1/knowledge-contribution/me",
        headers=headers,
        json={
            "service_agreement_accepted": True,
            "service_agreement_version": "service-2026-09-06",
            "participation_enabled": False,
        },
    )
    assert legacy.status_code == 428
    monkeypatch.setenv("AGREEMENT_ENFORCEMENT_MODE", "required")
    assert (await request("GET", "/api/screens", headers=headers)).status_code == 428


def test_only_bootstrap_and_non_user_routes_are_intentionally_exempt():
    from fastapi.routing import APIRoute

    expected = {
        ("POST", "/api/v1/register"),
        ("POST", "/api/v1/dev-login"),
        ("GET", "/api/v1/auth/capabilities"),
        ("GET", "/api/v1/auth/agreement"),
        ("POST", "/api/v1/auth/phone/send-code"),
        ("POST", "/api/v1/auth/phone/login"),
        ("GET", "/api/v1/auth/oauth/{provider}/start"),
        ("GET", "/api/v1/auth/oauth/{provider}/callback"),
        ("POST", "/api/v1/auth/oauth/complete"),
        ("GET", "/api/v1/legal/agreement"),
        ("GET", "/api/v1/me/agreement-acceptance"),
        ("PUT", "/api/v1/me/agreement-acceptance"),
        ("POST", "/api/internal/authen/entitlements"),
        ("POST", "/api/internal/knowledge/search"),
        ("GET", "/health"),
        ("GET", "/ready"),
    }
    def effective_api_routes(routes, inherited_dependencies=frozenset()):
        for route in routes:
            if isinstance(route, APIRoute):
                route_dependencies = {
                    dependency.call for dependency in route.dependant.dependencies
                }
                yield route, inherited_dependencies | route_dependencies
            elif hasattr(route, "original_router") and hasattr(route, "include_context"):
                include_dependencies = {
                    dependency.dependency
                    for dependency in route.include_context.dependencies
                }
                yield from effective_api_routes(
                    route.original_router.routes,
                    inherited_dependencies | include_dependencies,
                )

    routes = list(effective_api_routes(app.routes))
    actual = set()
    for route, dependencies in routes:
        if agreement_api.require_current_agreement not in dependencies:
            actual.update((method, route.path) for method in route.methods)
    assert actual == expected

    agreement_methods = {
        method
        for route, _ in routes
        if route.path == "/api/v1/me/agreement-acceptance"
        for method in route.methods
    }
    assert agreement_methods == {"GET", "PUT"}


@pytest.mark.asyncio
async def test_acceptance_schema_has_constraints_indexes_and_timezone(isolated_agreement_db):
    async with isolated_agreement_db() as db:
        connection = await db.connection()
        schema = await connection.run_sync(
            lambda sync: {
                "checks": {item["name"] for item in inspect(sync).get_check_constraints(
                    UserAgreementAcceptance.__tablename__
                )},
                "uniques": {tuple(item["column_names"]) for item in inspect(sync).get_unique_constraints(
                    UserAgreementAcceptance.__tablename__
                )},
            }
        )
    assert schema["checks"] == {
        "ck_user_agreement_user_id",
        "ck_user_agreement_version",
        "ck_user_agreement_locale",
        "ck_user_agreement_source",
        "ck_user_agreement_uuid_length",
    }
    assert schema["uniques"] == {
        ("user_id", "agreement_version"),
        ("user_id", "idempotency_key"),
    }
    postgres_ddl = str(CreateTable(UserAgreementAcceptance.__table__).compile(
        dialect=postgresql.dialect()
    ))
    assert "TIMESTAMP WITH TIME ZONE" in postgres_ddl
    assert "BIGSERIAL" in postgres_ddl


@pytest.mark.asyncio
async def test_init_db_creates_the_acceptance_table_on_an_existing_database(
    tmp_path: Path, monkeypatch,
):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'deployment.db'}")
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", session_factory)
    await db_module.init_db()
    async with engine.connect() as connection:
        tables = await connection.run_sync(lambda sync: set(inspect(sync).get_table_names()))
    assert UserAgreementAcceptance.__tablename__ in tables
    await engine.dispose()


@pytest.mark.asyncio
async def test_websocket_legacy_token_requires_current_acceptance():
    from backend.api.showroom import showroom_websocket
    from fastapi import WebSocketDisconnect
    class Socket:
        accepted = False
        closed = None
        async def accept(self):
            self.accepted = True
        async def close(self, code, reason):
            self.closed = code
        async def send_json(self, value):
            pass
        async def receive_json(self):
            raise WebSocketDisconnect()
    user = "ws-" + uuid4().hex
    denied = Socket()
    await showroom_websocket(denied, token=token(user), session_id="test")
    assert denied.closed == 4428 and not denied.accepted
    headers = {"Authorization": f"Bearer {token(user)}"}
    assert (await request("PUT", "/api/v1/me/agreement-acceptance", headers=headers, json={
        "agreement_version": agreement_api.CURRENT_AGREEMENT_VERSION, "idempotency_key": str(uuid4()),
    })).status_code == 200
    allowed = Socket()
    await showroom_websocket(allowed, token=token(user), session_id="test")
    assert allowed.accepted and allowed.closed is None
