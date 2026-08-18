from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException
from jose import JWTError, jwt

from backend.api.showroom import (
    DemandConfirmation,
    SessionCreate,
    ReviewSubmission,
    ShowroomCommand,
    _validate_websocket_token,
    apply_showroom_command,
    content_manifest,
    create_showroom_session,
    generate_showroom_insight,
    generate_showroom_ipd_artifacts,
    hub,
    submit_showroom_review,
)
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
