from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from backend.api.showroom import (
    DemandConfirmation,
    DemandDraftPatch,
    DemandExtractionRequest,
    LEGACY_DEMAND,
    LEGACY_INSIGHT,
    LEGACY_MESSAGES,
    LEGACY_PROTOTYPE,
    SessionCreate,
    ReviewSubmission,
    ShowroomCommand,
    _initial_session_data,
    _migrate_legacy_session_data,
    _validate_websocket_token,
    apply_showroom_command,
    content_manifest,
    create_showroom_session,
    extract_showroom_demand,
    generate_showroom_insight,
    generate_showroom_ipd_artifacts,
    hub,
    submit_showroom_review,
    update_showroom_demand_draft,
)
from backend.api.screens import _load_all as load_screen_configs
from backend.models.showroom import ShowroomRuntime, ShowroomSession


def auth_token() -> str:
    return jwt.encode(
        {"sub": "showroom-user", "username": "guide"},
        "test-secret",
        algorithm="HS256",
    )


def payload() -> dict[str, str]:
    return {"sub": "showroom-user", "username": "guide", "tenant_key": "demo"}


def reset_state() -> None:
    hub.state.update(
        {
            "epoch": 0,
            "stage": "station-1",
            "payload": {},
            "reviews": {},
        }
    )
    hub.ready_sessions.clear()


def test_showroom_prepare_commit_and_stale_epoch() -> None:
    reset_state()
    prepared = asyncio.run(
        apply_showroom_command(
            ShowroomCommand(
                type="PREPARE",
                epoch=100,
                stage="station-4",
                payload={"demand": "换模"},
            ),
            payload(),
        )
    )
    assert prepared["stage"] == "station-1"

    committed = asyncio.run(
        apply_showroom_command(
            ShowroomCommand(
                type="COMMIT",
                epoch=100,
                stage="station-4",
                payload={"demand": "换模"},
            ),
            payload(),
        )
    )
    assert committed["stage"] == "station-4"
    assert committed["payload"]["demand"] == "换模"

    with pytest.raises(HTTPException) as stale:
        asyncio.run(
            apply_showroom_command(
                ShowroomCommand(type="COMMIT", epoch=99, stage="station-2"),
                payload(),
            )
        )
    assert stale.value.status_code == 409


def test_review_requires_comment_for_non_approval() -> None:
    reset_state()
    with pytest.raises(HTTPException) as rejected:
        asyncio.run(
            submit_showroom_review(
                "TR1",
                ReviewSubmission(decision="changes", comment="", phase="概念"),
                payload(),
            )
        )
    assert rejected.value.status_code == 422

    accepted = asyncio.run(
        submit_showroom_review(
            "TR1",
            ReviewSubmission(decision="approved", comment="", phase="概念"),
            payload(),
        )
    )
    assert accepted["reviews"]["TR1"]["decision"] == "approved"


def test_websocket_token_validation() -> None:
    assert _validate_websocket_token(auth_token())["username"] == "guide"
    with pytest.raises(JWTError):
        _validate_websocket_token("not-a-token")


def test_content_contract_covers_all_screens_and_ipd() -> None:
    screen_ids = {
        item["id"]
        for group in content_manifest["navigation"]
        for item in group["items"]
        if item["id"].startswith("screen-")
    }
    assert {f"screen-{index:02d}" for index in range(1, 10)} <= screen_ids
    assert len(content_manifest["ipd_phases"]) == 6
    assert all(phase["outputs"] for phase in content_manifest["ipd_phases"])
    assert "default_session" not in content_manifest
    assert "换模" not in str(content_manifest.get("artifacts", {}))


def test_screen_003_bootstrap_contract_uses_hermes_demand_clinic() -> None:
    screen = load_screen_configs()["screen-03"]

    assert screen["transport"] == "hermes-gateway"
    assert screen["skill_command"] == "solution-consultant-persona"
    assert screen["station"] == "demand-clinic"
    assert "禁止迎宾" in screen["station_context"]
    assert "AI_LAB_DEMAND_V1" in screen["station_context"]
    assert screen["data_bindings"][1]["source"] == "/api/ws"


def test_frontend_nginx_normalizes_hermes_websocket_origin() -> None:
    dockerfile = Path("frontend/Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.count("location = /api/ws") == 2
    assert dockerfile.count("proxy_set_header Origin http://127.0.0.1;") == 2


def test_new_showroom_session_has_no_seed_business_data() -> None:
    data = _initial_session_data("3")

    assert data["messages"] == []
    assert data["demand"]["completeness"] == 0
    assert data["demand"]["core_problem"] == ""
    assert data["demand_document"] == {}
    assert data["insight"] == {}
    assert data["prototype"] == {}
    assert data["artifacts"] == {}


def test_exact_legacy_seed_is_removed_without_deleting_real_messages() -> None:
    real_message = {
        "role": "user",
        "content": "这是用户后来补充的真实问题",
        "created_at": "2026-08-19T10:00:00+08:00",
    }
    migrated, changed = _migrate_legacy_session_data(
        {
            "role": "业务负责人",
            "messages": [*LEGACY_MESSAGES, real_message],
            "demand": LEGACY_DEMAND,
            "insight": LEGACY_INSIGHT,
            "prototype": LEGACY_PROTOTYPE,
        }
    )

    assert changed is True
    assert migrated["messages"] == [real_message]
    assert migrated["demand"]["completeness"] == 0
    assert migrated["insight"] == {}
    assert migrated["prototype"] == {}


def test_modified_legacy_business_data_is_preserved() -> None:
    modified_demand = {**LEGACY_DEMAND, "core_problem": "用户已经修改的真实问题"}
    migrated, _ = _migrate_legacy_session_data(
        {
            "messages": [{**LEGACY_MESSAGES[0], "created_at": "2026-08-19T10:00:00Z"}],
            "demand": modified_demand,
            "insight": {**LEGACY_INSIGHT, "title": "用户确认后的洞察"},
            "prototype": {**LEGACY_PROTOTYPE, "title": "用户修改后的原型"},
        }
    )

    assert migrated["messages"][0]["created_at"]
    assert migrated["demand"] == modified_demand
    assert migrated["insight"]["title"] == "用户确认后的洞察"
    assert migrated["prototype"]["title"] == "用户修改后的原型"


def test_session_demand_insight_and_ipd_are_persisted(monkeypatch) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.api.knowledge as knowledge_api
    import backend.api.showroom as showroom_api

    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(ShowroomSession.__table__.create)
            await connection.run_sync(ShowroomRuntime.__table__.create)
        monkeypatch.setattr(showroom_api, "SessionLocal", maker)
        monkeypatch.setattr(
            knowledge_api,
            "search",
            lambda query, limit: {
                "docs": [
                    {
                        "title": "制造知识条目",
                        "path": "wiki/制造知识条目.md",
                        "snippet": "换模步骤标准化",
                        "score": 9,
                    }
                ]
            },
        )

        created = await create_showroom_session(
            SessionCreate(session_id="showroom-integration", slot="1"), payload()
        )
        assert created["slot"] == "1"

        confirmed = await showroom_api.confirm_showroom_demand(
            "showroom-integration",
            DemandConfirmation(
                demand={
                    "core_problem": "换模依赖经验",
                    "target_metric": "45 分钟 → 20 分钟",
                }
            ),
            payload(),
        )
        assert confirmed["data"]["demand"]["confirmed"] is True

        insight = await generate_showroom_insight("showroom-integration", payload())
        assert insight["data"]["insight"]["sources"][0]["score"] == 9

        ipd = await generate_showroom_ipd_artifacts(
            "showroom-integration", 0, payload()
        )
        assert "需求合理性·调研支撑" in ipd["data"]["artifacts"]
        await engine.dispose()

    asyncio.run(scenario())


def test_demand_extraction_is_draft_idempotent_and_preserves_manual_fields(
    monkeypatch,
) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.api.showroom as showroom_api

    first = """
## 集团算力治理需求确认单
### 四维确认单
| 维度 | 内容 |
|---|---|
| 目标 | 3 个月内利用率提升至 60% |
| 非目标 | 不对外运营 |
| 约束 | 数据不出园区 |
| 验收 | 连续四周达到 60% |
"""
    revised = first.replace("3 个月内利用率提升至 60%", "6 个月内利用率提升至 70%")

    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(ShowroomSession.__table__.create)
            await connection.run_sync(ShowroomRuntime.__table__.create)
        monkeypatch.setattr(showroom_api, "SessionLocal", maker)

        await create_showroom_session(
            SessionCreate(session_id="showroom-demand-extract", slot="main"), payload()
        )
        extracted = await extract_showroom_demand(
            "showroom-demand-extract",
            DemandExtractionRequest(content=first),
            payload(),
        )
        assert extracted["recognized"] is True
        assert extracted["session"]["data"]["demand"]["confirmed"] is False
        assert extracted["session"]["data"]["demand_document"]["status"] == "draft"

        duplicate = await extract_showroom_demand(
            "showroom-demand-extract",
            DemandExtractionRequest(content=first),
            payload(),
        )
        assert duplicate["unchanged"] is True

        edited = await update_showroom_demand_draft(
            "showroom-demand-extract",
            DemandDraftPatch(
                demand={"core_problem": "人工确认的真实核心问题"},
                manual_fields=["core_problem"],
            ),
            payload(),
        )
        assert edited["data"]["demand"]["core_problem"] == "人工确认的真实核心问题"

        updated = await extract_showroom_demand(
            "showroom-demand-extract",
            DemandExtractionRequest(content=revised),
            payload(),
        )
        assert (
            updated["session"]["data"]["demand"]["core_problem"]
            == "人工确认的真实核心问题"
        )
        assert "70%" in updated["session"]["data"]["demand"]["target_metric"]
        await engine.dispose()

    asyncio.run(scenario())
