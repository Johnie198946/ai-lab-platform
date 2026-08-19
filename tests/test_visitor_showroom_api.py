from __future__ import annotations

import asyncio
import json

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import backend.api.showroom as showroom_api
from backend.api.showroom import VisitorInsightRequest, VisitorPatch
from backend.models.showroom import ShowroomRuntime, ShowroomSession


def payload() -> dict[str, str]:
    return {"sub": "showroom-user", "username": "showroom_demo", "tenant_key": "demo"}


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
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(ShowroomSession.__table__.create)
            await connection.run_sync(ShowroomRuntime.__table__.create)
        monkeypatch.setattr(showroom_api, "SessionLocal", maker)
        showroom_api._runtime_hydrated = True
        showroom_api.hub.state.update(
            {
                "active_main_session_id": "",
                "active_main_tenant_key": "",
                "epoch": 0,
            }
        )

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
