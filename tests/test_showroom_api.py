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
    InsightCompleteRequest,
    InsightMutationRequest,
    InsightProgressRequest,
    InsightReviewCompleteRequest,
    InsightRevisionExtractionRequest,
    InsightStaffingPlanRequest,
    LEGACY_DEMAND,
    LEGACY_INSIGHT,
    LEGACY_MESSAGES,
    LEGACY_PROTOTYPE,
    SessionCreate,
    ReviewSubmission,
    ShowroomCommand,
    _initial_session_data,
    _extract_demand_interview_state,
    _migrate_legacy_session_data,
    _persona_metadata,
    _validate_websocket_token,
    apply_showroom_command,
    apply_showroom_insight_revision,
    content_manifest,
    create_showroom_session,
    complete_showroom_insight_job,
    complete_showroom_insight_review_task,
    confirm_showroom_insight,
    create_showroom_insight_review_task,
    extract_showroom_demand,
    extract_showroom_insight_revision,
    generate_showroom_insight,
    generate_showroom_ipd_artifacts,
    hub,
    submit_showroom_review,
    save_showroom_staffing_plan,
    start_showroom_insight_job,
    update_showroom_insight_progress,
    update_showroom_demand_draft,
    _finish_showroom_insight_job,
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


def test_insight_progress_request_normalizes_model_authored_legacy_events() -> None:
    stage = InsightProgressRequest.model_validate(
        {"event_id": "stage-1", "stage": "analysis"}
    )
    section = InsightProgressRequest.model_validate(
        {"event_id": "section-1", "section": "summary", "payload": {"title": "洞察"}}
    )
    employee = InsightProgressRequest.model_validate(
        {
            "event_id": "employee-1",
            "kind": "employee_status",
            "employee_id": "researcher",
            "status": "working",
        }
    )

    assert stage.kind == "stage"
    assert section.kind == "section"
    assert employee.kind == "employee"
    assert employee.employee_status == "working"


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
    assert "最多追问三轮" in screen["station_context"]
    assert "禁止" in screen["station_context"] and "完整建设方案" in screen["station_context"]
    assert screen["data_bindings"][1]["source"] == "/api/ws"


def test_screen_0035_and_004_use_hermes_incremental_insight_contract() -> None:
    screens = load_screen_configs()
    insight = screens["screen-04"]

    assert any(binding["source"].endswith("/insight/jobs") for binding in insight["data_bindings"])
    assert all(binding["source"] != "/api/chat/stream" for binding in insight["data_bindings"])


def test_frontend_nginx_normalizes_hermes_websocket_origin() -> None:
    dockerfile = Path("frontend/Dockerfile").read_text(encoding="utf-8")

    websocket_blocks = []
    marker = "location = /api/ws {"
    end_marker = "    }\\n\\\n"
    cursor = 0
    while (start := dockerfile.find(marker, cursor)) >= 0:
        end = dockerfile.index(end_marker, start)
        websocket_blocks.append(dockerfile[start:end])
        cursor = end + len(end_marker)
    assert len(websocket_blocks) == 2
    assert all(
        block.count("proxy_set_header Origin http://127.0.0.1;") == 1
        for block in websocket_blocks
    )


def test_new_showroom_session_has_no_seed_business_data() -> None:
    data = _initial_session_data("3")

    assert data["messages"] == []
    assert data["demand"]["completeness"] == 0
    assert data["demand"]["core_problem"] == ""
    assert data["demand_document"] == {}
    assert data["insight"] == {}
    assert data["prototype"] == {}
    assert data["artifacts"] == {}


def test_new_main_session_separates_backstage_and_frontstage_hermes() -> None:
    data = _initial_session_data("main")

    assert data["hermes_sessions"]["backstage_stored_session_id"] == ""
    assert data["hermes_sessions"]["frontstage_stored_session_id"] == ""
    assert data["demand_interview"]["followup_count"] == 0
    assert len(data["demand_interview"]["missing"]) == 4


def test_demand_state_reaches_forced_draft_after_three_rounds() -> None:
    state = None
    for index in range(3):
        content = f'''<!-- AI_LAB_DEMAND_STATE_V1
{{"status":"collecting","dimensions":{{"business_scene":"政务服务","user_role":"居民","current_blocker":"{('入口分散' if index > 0 else '')}","target_outcome":""}}}}
AI_LAB_DEMAND_STATE_V1 -->'''
        state, recognized = _extract_demand_interview_state(content, state)
        assert recognized is True

    assert state["followup_count"] == 3
    assert state["status"] == "draft"
    assert state["missing"] == ["target_outcome"]


def test_persona_metadata_blocks_duplicate_skill_resolution(tmp_path, monkeypatch) -> None:
    skills = tmp_path / "skills"
    formal = skills / "productivity" / "solution-consultant-persona" / "SKILL.md"
    backup = skills / ".curator_backups" / "solution-consultant-persona" / "SKILL.md"
    formal.parent.mkdir(parents=True)
    backup.parent.mkdir(parents=True)
    formal.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.7.0\n---\n# V1.7",
        encoding="utf-8",
    )
    backup.write_text(
        "---\nname: solution-consultant-persona\nversion: 1.3.0\n---\n# old",
        encoding="utf-8",
    )
    monkeypatch.setenv("SHOWROOM_PERSONA_SKILL_PATH", str(formal))

    metadata = _persona_metadata()

    assert metadata["disk_version"] == "1.7.0"
    assert metadata["duplicate_count"] == 1
    assert metadata["compatible"] is False
    assert metadata["resolved_version"] == ""


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


@pytest.mark.skip(reason="V1浏览器编排已由服务端持久化洞察V2取代")
def test_staffing_job_is_idempotent_and_incrementally_persists_sections(monkeypatch) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.api.showroom as showroom_api

    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(ShowroomSession.__table__.create)
            await connection.run_sync(ShowroomRuntime.__table__.create)
        monkeypatch.setattr(showroom_api, "SessionLocal", maker)

        await create_showroom_session(
            SessionCreate(session_id="showroom-staffing", slot="main"), payload()
        )
        await showroom_api.confirm_showroom_demand(
            "showroom-staffing",
            DemandConfirmation(
                demand={
                    "core_problem": "权限管理阻碍HR场景落地",
                    "target_metric": "形成可审计的001实践输入",
                }
            ),
            payload(),
        )
        started = await start_showroom_insight_job("showroom-staffing", payload())
        resumed = await start_showroom_insight_job("showroom-staffing", payload())
        assert resumed["resumed"] is True
        assert resumed["job"]["job_id"] == started["job"]["job_id"]

        job_id = started["job"]["job_id"]
        planned = await save_showroom_staffing_plan(
            "showroom-staffing",
            job_id,
            InsightStaffingPlanRequest(
                plan={
                    "mission": "完成权限合规洞察",
                    "squads": [
                        {
                            "stage": "IPD0",
                            "employees": [
                                {"employee_id": "researcher", "task": "查找权限治理证据"}
                            ],
                        }
                    ],
                }
            ),
            payload(),
        )
        assert len(planned["plan"]["squads"][0]["employees"]) == 4

        progress = await update_showroom_insight_progress(
            "showroom-staffing",
            job_id,
            InsightProgressRequest(
                event_id="summary-event-1",
                kind="section",
                section="summary",
                payload={"title": "HR权限治理洞察", "judgment": "适合进入001实践"},
            ),
            payload(),
        )
        assert "summary" in progress["job"]["completed_sections"]
        assert progress["session"]["data"]["insight"]["title"] == "HR权限治理洞察"

        partial = await complete_showroom_insight_job(
            "showroom-staffing",
            job_id,
            InsightCompleteRequest(content=""),
            payload(),
        )
        assert partial["job"]["status"] == "partial"
        assert "concept.customer_user" in partial["backfill_required_fields"]
        assert partial["session"]["data"]["insight_review"]["coverage"]["blocking_items"]

        for section in ("concept", "root_causes", "impacts", "evidence", "recommendation"):
            await update_showroom_insight_progress(
                "showroom-staffing",
                job_id,
                InsightProgressRequest(
                    event_id=f"{section}-event",
                    kind="section",
                    section=section,
                    payload={section: ["已完成"]},
                ),
                payload(),
            )

        completed = await complete_showroom_insight_job(
            "showroom-staffing",
            job_id,
            InsightCompleteRequest(
                content=(
                    '<!-- AI_LAB_INSIGHT_V1 '
                    f'{{"job_id":"{job_id}","sections":["summary","root_causes"]}} '
                    'AI_LAB_INSIGHT_V1 -->'
                )
            ),
            payload(),
        )
        assert completed["job"]["status"] == "completed"
        assert isinstance(completed["backfill_required_fields"], list)

        recovered = await _finish_showroom_insight_job(
            "showroom-staffing",
            job_id,
            "final callback failed",
            "failed",
            "demo",
        )
        assert recovered["job"]["status"] == "completed"
        assert recovered["job"]["error"] == ""
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


@pytest.mark.skip(reason="V1浏览器回填夹具已由Artifact V2投影测试取代")
def test_insight_revision_preview_apply_and_human_confirmation(monkeypatch) -> None:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    import backend.api.showroom as showroom_api

    async def scenario() -> None:
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        maker = async_sessionmaker(engine, expire_on_commit=False)
        async with engine.begin() as connection:
            await connection.run_sync(ShowroomSession.__table__.create)
            await connection.run_sync(ShowroomRuntime.__table__.create)
        monkeypatch.setattr(showroom_api, "SessionLocal", maker)
        await create_showroom_session(SessionCreate(session_id="review-flow", slot="main"), payload())
        await showroom_api.confirm_showroom_demand(
            "review-flow",
            DemandConfirmation(demand={"core_problem": "HR权限治理", "target_metric": "可审计"}),
            payload(),
        )
        started = await start_showroom_insight_job("review-flow", payload())
        job = started["job"]
        await save_showroom_staffing_plan(
            "review-flow", job["job_id"], InsightStaffingPlanRequest(plan={}), payload()
        )
        concept = {
            "demand_trace": {"summary": "权限治理"},
            "customer_user": {"user": "HR专员", "value": "可审计"},
            "market": {"summary": "合规需求明确"},
            "competition": [{"name": "现有IAM"}],
            "technology": {"feasibility": "可行", "effort": "M"},
            "strategic_fit": {"boundary": "platform", "verdict": "fit"},
            "capability_mapping": [{"capability": "鉴权", "match": "support"}],
            "assessment": {"benefit": "high", "risk": "medium", "priority": "P1"},
            "special_checks": {key: {"status": "pass"} for key in ("cyber", "reliability", "energy", "function_performance")},
            "knowledge_status": {"facts": ["权限是首要阻碍"], "tbds": []},
            "verdict": {"decision": "conditional", "rationale": "先做001"},
            "initial_product_package": {"scope": "鉴权闭环", "components": ["策略引擎"]},
            "demo_slice": {"user": "HR专员", "action": "合规查询", "input": "授权范围", "output": "审计结果", "acceptance": ["越权被阻断"], "dependencies": ["权限规则"]},
        }
        sections = {
            "concept": concept,
            "summary": {"title": "HR权限洞察", "judgment": "条件接纳"},
            "root_causes": {"causes": [{"title": "权限边界", "detail": "规则不清"}]},
            "impacts": {"impacts": [{"label": "合规", "score": 90}]},
            "evidence": {"evidence": [["E1", "事实", "高", "已核验"]], "sources": [{"url": "https://example.com", "title": "来源", "date": "2026-08-19", "confidence": "high"}]},
            "recommendation": {"recommendation": "进入001"},
        }
        for index, (section, section_payload) in enumerate(sections.items()):
            await update_showroom_insight_progress(
                "review-flow", job["job_id"],
                    InsightProgressRequest(event_id=f"review-{index}", kind="section", section=section, payload=section_payload),
                payload(),
            )
        completed = await complete_showroom_insight_job(
            "review-flow", job["job_id"], InsightCompleteRequest(content=""), payload()
        )
        assert completed["session"]["data"]["insight_review"]["version"] == "V0.1"
        explanation = await extract_showroom_insight_revision(
            "review-flow",
            InsightRevisionExtractionRequest(
                content="这是一段普通解释",
                job_id=job["job_id"],
                demand_hash=job["source_hash"],
                base_version="V0.1",
                user_instruction="这个判断的依据是什么？",
                request_id="request-explain",
            ),
            payload(),
        )
        assert explanation["result_type"] == "explanation"
        repair = await extract_showroom_insight_revision(
            "review-flow",
            InsightRevisionExtractionRequest(
                content="我会把结论回填到报告",
                job_id=job["job_id"],
                demand_hash=job["source_hash"],
                base_version="V0.1",
                user_instruction="把这个回填进去",
                target_section="insight-summary",
                expected_revision=True,
                request_id="request-repair",
            ),
            payload(),
        )
        assert repair["result_type"] == "repair_required"
        revision_content = (
            '<!-- AI_LAB_INSIGHT_REVISION_V1 '
            f'{{"request_id":"request-backfill","job_id":"{job["job_id"]}","demand_hash":"{job["source_hash"]}","base_version":"V0.1","target_section":"insight-summary","changes":[{{"field":"judgment","after":"有条件接纳","reason":"措辞更准确"}}]}} '
            'AI_LAB_INSIGHT_REVISION_V1 -->'
        )
        extracted = await extract_showroom_insight_revision(
            "review-flow",
            InsightRevisionExtractionRequest(
                content=revision_content,
                job_id=job["job_id"],
                demand_hash=job["source_hash"],
                base_version="V0.1",
                user_instruction="把结论回填到报告",
                target_section="insight-summary",
                expected_revision=True,
                request_id="request-backfill",
            ),
            payload(),
        )
        assert extracted["result_type"] == "revision_ready"
        assert extracted["revision"]["target_section"] == "insight-summary"
        applied = await apply_showroom_insight_revision(
            "review-flow", extracted["revision"]["revision_id"],
            InsightMutationRequest(job_id=job["job_id"], demand_hash=job["source_hash"], base_version="V0.1"),
            payload(),
        )
        assert applied["session"]["data"]["insight"]["judgment"] == "有条件接纳"
        assert applied["version"] == "V0.2"
        assert applied["changed_fields"] == ["judgment"]
        assert "insight-summary" in applied["affected_sections"]
        duplicate_apply = await apply_showroom_insight_revision(
            "review-flow",
            extracted["revision"]["revision_id"],
            InsightMutationRequest(
                job_id=job["job_id"],
                demand_hash=job["source_hash"],
                base_version="V0.1",
            ),
            payload(),
        )
        assert duplicate_apply["unchanged"] is True
        assert duplicate_apply["version"] == "V0.2"
        assert duplicate_apply["changed_fields"] == ["judgment"]
        assigned = await create_showroom_insight_review_task(
            "review-flow",
            InsightMutationRequest(job_id=job["job_id"], demand_hash=job["source_hash"], base_version="V0.2"),
            payload(),
        )
        assert assigned["task"]["status"] == "assigned"
        assert len(assigned["task"]["ai_reviewers"]) == 3
        review_content = (
            '<!-- AI_LAB_CONCEPT_REVIEW_V1 '
            '{"decision":"conditional","summary":"已有TBD处置动作，可进入001实践","conditions":["补齐能耗基线"],'
            '"reviewer_results":[{"reviewer_id":"concept-chair","conclusion":"条件通过","comment":"切片完整"},'
            '{"reviewer_id":"evidence-auditor","conclusion":"通过","comment":"来源可追溯"},'
            '{"reviewer_id":"boundary-reviewer","conclusion":"条件通过","comment":"保留专项检查"}]} '
            'AI_LAB_CONCEPT_REVIEW_V1 -->'
        )
        frozen = await complete_showroom_insight_review_task(
            "review-flow",
            assigned["task"]["task_id"],
            InsightReviewCompleteRequest(
                content=review_content,
                job_id=job["job_id"],
                demand_hash=job["source_hash"],
                base_version="V0.2",
            ),
            payload(),
        )
        assert frozen["released"] is True
        assert frozen["session"]["data"]["insight_review"]["version"] == "V1.0"
        assert frozen["session"]["data"]["insight_review_gate"]["status"] == "conditional"
        assert {"需求合理性·调研支撑", "需求评审结论", "初始产品包"} <= set(frozen["session"]["data"]["artifacts"])
        await engine.dispose()

    asyncio.run(scenario())
