from __future__ import annotations

import asyncio
import json

import pytest
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.showroom as showroom_api
from backend.api.showroom import (
    FrontstageRequest,
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


def test_invalid_insight_payload_closes_running_state(tmp_path, monkeypatch) -> None:
    skill = tmp_path / "solution-consultant-persona" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.7.0\n---\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHOWROOM_PERSONA_SKILL_PATH", str(skill))

    async def scenario() -> None:
        engine, _ = await memory_store(monkeypatch)
        active = await showroom_api._active_main_session("demo")
        session_id = active.session_id
        await showroom_api.update_showroom_visitor(
            session_id,
            VisitorPatch(company_name="示例科技"),
            payload(),
        )

        result = await showroom_api.extract_showroom_visitor_insight(
            session_id,
            VisitorInsightRequest(
                content=(
                    "摘要\n<!-- AI_LAB_VISITOR_INSIGHT_V1 {invalid} "
                    "AI_LAB_VISITOR_INSIGHT_V1 -->"
                )
            ),
            payload(),
        )

        assert result["recognized"] is False
        assert result["session"]["data"]["customer_insight"]["status"] == "failed"
        assert result["session"]["data"]["visitor"]["status"] == "research_failed"
        assert "有效 JSON" in result["session"]["data"]["customer_insight"]["warnings"][-1]
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


def test_rollover_archives_main_and_replaces_all_experience_slots(
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
        slots = [
            await showroom_api._get_or_create_session(
                f"experience-slot-{index}", str(index), "demo", f"体验访客{index}"
            )
            for index in range(1, 6)
        ]

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

        rolled = await showroom_api.rollover_showroom_visit(
            main_id, VisitRolloverRequest(epoch=1, source="controller"), payload()
        )
        new_id = rolled["session"]["session_id"]
        assert new_id != main_id
        assert rolled["runtime"]["active_main_session_id"] == new_id
        assert rolled["session"]["data"]["visitor"]["status"] == "preparing"
        assert rolled["runtime"]["stage"] == "station-1"
        assert len(rolled["session_switches"]) == 6
        assert {item["slot"] for item in rolled["session_switches"]} == {
            "main", "1", "2", "3", "4", "5"
        }

        async with maker() as database:
            archived = await database.get(ShowroomSession, main_id)
            archived_slots = [
                await database.get(ShowroomSession, slot.session_id) for slot in slots
            ]
            new_slots = [
                await database.get(
                    ShowroomSession,
                    next(
                        item["new_session_id"]
                        for item in rolled["session_switches"]
                        if item["slot"] == str(index)
                    ),
                )
                for index in range(1, 6)
            ]
        assert archived.status == "archived"
        assert archived.data["visitor"]["status"] == "archived"
        assert archived.data["visit_completed_by"] == "controller"
        assert archived.data["rollover_to"] == new_id
        assert all(row.status == "archived" for row in archived_slots)
        assert all(row.data["rollover_to"] for row in archived_slots)
        assert all(row.status == "active" and row.step == 0 for row in new_slots)
        assert all(row.data["role"] == "" and row.data["messages"] == [] for row in new_slots)

        repeated = await showroom_api.rollover_showroom_visit(
            main_id, VisitRolloverRequest(epoch=2, source="controller"), payload()
        )
        assert repeated["session"]["session_id"] == new_id
        assert repeated["session_switches"] == rolled["session_switches"]

        reopened = await showroom_api._get_or_create_session(
            slots[0].session_id, "1", "demo"
        )
        assert reopened.session_id == next(
            item["new_session_id"]
            for item in rolled["session_switches"]
            if item["slot"] == "1"
        )
        await engine.dispose()

    asyncio.run(scenario())
