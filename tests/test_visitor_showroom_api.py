from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.showroom as showroom_api
from backend.api.showroom import (
    FrontstageRequest,
    VisitCompleteRequest,
    VisitRolloverRequest,
    VisitorInsightRequest,
    VisitorPatch,
)
from backend.models.showroom import ShowroomRuntime, ShowroomSession


def payload() -> dict[str, str]:
    return {"sub": "showroom-user", "username": "showroom_demo", "tenant_key": "demo"}


async def memory_store(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(ShowroomSession.__table__.create)
        await connection.run_sync(ShowroomRuntime.__table__.create)
    monkeypatch.setattr(showroom_api, "SessionLocal", maker)
    showroom_api._runtime_hydrated = True
    showroom_api.hub.connections.clear()
    showroom_api.hub.switch_ready.clear()
    showroom_api.hub.state.update(
        {
            "active_main_session_id": "",
            "active_main_tenant_key": "",
            "epoch": 0,
        }
    )
    return engine, maker


def test_active_visit_insight_and_wiki_round_trip(tmp_path, monkeypatch) -> None:
    skill = tmp_path / "solution-consultant-persona" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.7.0\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHOWROOM_PERSONA_SKILL_PATH", str(skill))
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))

    async def scenario() -> None:
        engine, _ = await memory_store(monkeypatch)

        active = await showroom_api._active_main_session("demo")
        assert active.data["persona_skill_version"] == "1.7.0"
        session_id = active.session_id

        updated = await showroom_api.update_showroom_visitor(
            session_id,
            VisitorPatch(
                company_name="示例科技",
                visitors=[{"name": "张三", "title": "CTO"}],
                purpose="验证 Agent 编排",
                focus_topics=["Agent"],
            ),
            payload(),
        )
        assert updated["data"]["visitor"]["status"] == "researching"

        insight_payload = {
            "customer_positioning": ["公开定位"],
            "verified_facts": ["公开事实"],
            "hypotheses": ["待验证"],
            "sources": [
                {
                    "title": "企业官网",
                    "url": "https://example.com",
                    "date": "2026-08-01",
                    "confidence": "high",
                }
            ],
        }
        content = (
            "摘要\n<!-- AI_LAB_VISITOR_INSIGHT_V1 "
            f"{json.dumps(insight_payload, ensure_ascii=False)} "
            "AI_LAB_VISITOR_INSIGHT_V1 -->"
        )
        extracted = await showroom_api.extract_showroom_visitor_insight(
            session_id,
            VisitorInsightRequest(content=content),
            payload(),
        )
        insight = extracted["session"]["data"]["customer_insight"]
        assert insight["status"] == "completed"
        assert insight["public_wiki_slug"]
        assert insight["private_record_path"].startswith("tenants/demo/")

        repeated = await showroom_api.extract_showroom_visitor_insight(
            session_id,
            VisitorInsightRequest(content=content),
            payload(),
        )
        assert repeated["unchanged"] is True
        await engine.dispose()

    asyncio.run(scenario())


def test_v17_gate_blocks_incompatible_persona(tmp_path, monkeypatch) -> None:
    skill = tmp_path / "solution-consultant-persona" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.6.9\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHOWROOM_PERSONA_SKILL_PATH", str(skill))

    async def scenario() -> None:
        engine, _ = await memory_store(monkeypatch)
        with pytest.raises(HTTPException) as error:
            await showroom_api._active_main_session("demo")
        assert error.value.status_code == 503
        assert "1.7.0" in str(error.value.detail)
        await engine.dispose()

    asyncio.run(scenario())


def test_frontstage_completion_and_rollover_preserve_experience_slots(
    tmp_path, monkeypatch
) -> None:
    skill = tmp_path / "solution-consultant-persona" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.7.0\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHOWROOM_PERSONA_SKILL_PATH", str(skill))

    async def scenario() -> None:
        engine, maker = await memory_store(monkeypatch)
        main = await showroom_api._active_main_session("demo")
        main_id = main.session_id
        slot = await showroom_api._get_or_create_session(
            "experience-slot-1", "1", "demo", "体验访客"
        )

        await showroom_api.update_showroom_visitor(
            main_id,
            VisitorPatch(
                company_name="示例科技",
                purpose="验证接待闭环",
                focus_topics=["Agent 编排"],
            ),
            payload(),
        )
        frontstage = await showroom_api.activate_showroom_frontstage(
            main_id, FrontstageRequest(message_count=7), payload()
        )
        assert frontstage["session"]["data"]["frontstage_message_offset"] == 7
        assert frontstage["session"]["data"]["visitor"]["status"] == "in_tour"
        assert "示例科技" in frontstage["station_context"]
        assert "禁止复述后台洞察" in frontstage["station_context"]

        completed = await showroom_api.complete_showroom_visit(
            main_id, VisitCompleteRequest(source="screen-09"), payload()
        )
        assert completed["data"]["visitor"]["status"] == "awaiting_rollover"

        rolled = await showroom_api.rollover_showroom_visit(
            main_id, VisitRolloverRequest(epoch=1), payload()
        )
        new_id = rolled["session"]["session_id"]
        assert new_id != main_id
        assert rolled["runtime"]["active_main_session_id"] == new_id
        assert rolled["session"]["data"]["visitor"]["status"] == "preparing"

        async with maker() as database:
            archived = await database.get(ShowroomSession, main_id)
            preserved_slot = await database.get(ShowroomSession, slot.session_id)
        assert archived.status == "archived"
        assert archived.data["visitor"]["status"] == "archived"
        assert preserved_slot.status == "active"
        assert preserved_slot.data["role"] == "体验访客"
        await engine.dispose()

    asyncio.run(scenario())
