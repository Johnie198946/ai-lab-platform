from __future__ import annotations

import pytest
from sqlalchemy import BigInteger, event, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.showroom_insight_execution import (
    CONCEPT_KEYS,
    NODE_IDS,
    SCHEMA,
    build_dsl,
    document_to_insight,
    validate_document,
    ensure_execution,
)
from backend.db import Base
from backend.models.showroom import ShowroomInsightExecution, ShowroomSession
from backend.models.workflow import WorkflowNodeRun
from backend.models.workflow import WorkflowExecution
from backend.services.workflow_artifacts import store_artifact
from backend.services.showroom_insight_execution import project_execution


def _document() -> dict:
    concept = {
        key: {
            "status": "tbd",
            "reason": f"{key}尚缺客户材料",
            "owner": "客户业务负责人",
            "action": f"访谈并核验{key}",
        }
        for key in CONCEPT_KEYS
    }
    return {
        "schema": SCHEMA,
        "run_id": "run-1",
        "demand_hash": "d" * 64,
        "sections": {
            "summary": {"title": "HR AI权限治理", "judgment": "条件接纳", "gap": "需补证"},
            "root_causes": {"causes": [{"title": "授权不清", "detail": "缺少责任矩阵"}]},
            "impacts": {"impacts": [{"label": "合规风险", "score": 80, "basis": "待访谈"}]},
            "evidence": {"evidence": [["E-01", "内部事实", "高", "已核验"]], "sources": []},
            "recommendation": {"recommendation": "进入受控001实践"},
            "ipd_handoff": {"slice": "权限约束下的HR查询"},
            "concept": concept,
        },
        "sources": [{"title": "客户Wiki", "path": "wiki/客户/C036.md", "date": "2026-08-20", "confidence": "high"}],
        "warnings": [],
    }


def test_controlled_dag_has_six_ordered_bridge_nodes() -> None:
    dsl = build_dsl("run-1", "d" * 64, {"core_problem": "HR权限治理"})
    compiled = DSLSafetyCompiler.compile_and_validate(dsl)
    assert DSLSafetyCompiler.check_dag_cycle_kahn(compiled) == list(NODE_IDS)
    assert compiled.nodes[-1].node_type.value == "OUTPUT_FORMAT"
    assert compiled.nodes[2].parameters["skill_id"] == "ipd-01-market-insight"
    assert compiled.nodes[3].parameters["skill_id"] == "ipd-02-requirement-analysis"


def test_showroom_epoch_column_accepts_unix_milliseconds() -> None:
    assert isinstance(ShowroomInsightExecution.__table__.c.epoch.type, BigInteger)


def test_v2_artifact_projects_all_report_sections() -> None:
    document = validate_document(_document(), execution_id="run-1", demand_hash="d" * 64)
    insight = document_to_insight(document)
    assert insight["status"] == "completed"
    assert insight["title"] == "HR AI权限治理"
    assert insight["causes"][0]["title"] == "授权不清"
    assert insight["concept"]["market"]["status"] == "tbd"
    assert insight["sources"][0]["path"] == "wiki/客户/C036.md"


def test_v2_artifact_rejects_missing_concept_and_unsafe_source() -> None:
    missing = _document()
    del missing["sections"]["concept"]["market"]
    with pytest.raises(ValueError, match="概念阶段字段"):
        validate_document(missing, execution_id="run-1", demand_hash="d" * 64)

    unsafe = _document()
    unsafe["sources"] = [{"title": "bad", "url": "javascript:alert(1)"}]
    with pytest.raises(ValueError, match="来源路径无效"):
        validate_document(unsafe, execution_id="run-1", demand_hash="d" * 64)


def test_v2_artifact_rejects_unowned_tbd() -> None:
    document = _document()
    document["sections"]["concept"]["market"].pop("owner")
    with pytest.raises(ValueError, match="TBD缺少"):
        validate_document(document, execution_id="run-1", demand_hash="d" * 64)


@pytest.mark.asyncio
async def test_server_execution_is_idempotent_and_persists_six_nodes() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as database:
        session = ShowroomSession(
            session_id="showroom-v2", tenant_key="demo", slot="main", step=2,
            data={"demand": {"confirmed": True, "core_problem": "HR权限治理"}},
        )
        database.add(session)
        await database.flush()
        first, resumed = await ensure_execution(
            database, session=session, demand_hash="d" * 64, epoch=7
        )
        await database.commit()
        assert resumed is False
        await database.refresh(session)
        assert session.data["insight_job"]["execution_id"] == first.execution_id

        second, resumed = await ensure_execution(
            database, session=session, demand_hash="d" * 64, epoch=7
        )
        assert resumed is True
        assert second.execution_id == first.execution_id
        nodes = list((await database.execute(
            select(WorkflowNodeRun)
            .where(WorkflowNodeRun.execution_id == first.execution_id)
            .order_by(WorkflowNodeRun.position)
        )).scalars())
        assert [node.node_id for node in nodes] == list(NODE_IDS)
        bindings = list((await database.execute(select(ShowroomInsightExecution))).scalars())
        assert len(bindings) == 1
    await engine.dispose()


@pytest.mark.asyncio
async def test_server_execution_accepts_millisecond_epoch() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as database:
        session = ShowroomSession(
            session_id="showroom-bigint-epoch", tenant_key="demo", slot="main", step=2,
            data={"demand": {"confirmed": True, "core_problem": "异构算力运营"}},
        )
        database.add(session)
        await database.flush()
        epoch = 1_787_229_084_053
        first, resumed = await ensure_execution(
            database, session=session, demand_hash="f" * 64, epoch=epoch
        )
        await database.commit()
        assert resumed is False
        assert first.epoch == epoch
        second, resumed = await ensure_execution(
            database, session=session, demand_hash="f" * 64, epoch=epoch
        )
        assert resumed is True
        assert second.job_id == first.job_id
    await engine.dispose()


@pytest.mark.asyncio
async def test_legacy_incomplete_report_is_archived_once_when_rebuilt() -> None:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as database:
        session = ShowroomSession(
            session_id="showroom-legacy", tenant_key="demo", slot="main", step=3,
            data={
                "demand": {"confirmed": True, "core_problem": "旧需求"},
                "insight_job": {"job_id": "browser-job", "status": "running"},
                "insight": {"status": "running", "title": "旧空报告"},
            },
        )
        database.add(session)
        await database.flush()
        first, _ = await ensure_execution(database, session=session, demand_hash="e" * 64, epoch=2)
        await database.commit()
        await database.refresh(session)
        assert session.data["insight_execution_history"][0]["status"] == "superseded"
        assert session.data["insight_history"][0]["insight"]["title"] == "旧空报告"
        _, resumed = await ensure_execution(database, session=session, demand_hash="e" * 64, epoch=2)
        assert resumed is True
        assert len(session.data["insight_history"]) == 1
        assert first.execution_id == session.data["insight_job"]["execution_id"]
    await engine.dispose()


@pytest.mark.asyncio
async def test_valid_output_artifact_is_the_only_report_authority(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AI_LAB_HOME", str(tmp_path / "vault"))
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with maker() as database:
        session = ShowroomSession(
            session_id="showroom-project", tenant_key="demo", slot="main", step=2,
            data={"demand": {"confirmed": True, "core_problem": "HR权限治理"}},
        )
        database.add(session)
        await database.flush()
        binding, _ = await ensure_execution(
            database, session=session, demand_hash="d" * 64, epoch=8
        )
        execution = await database.get(WorkflowExecution, binding.execution_id)
        nodes = list((await database.execute(
            select(WorkflowNodeRun).where(WorkflowNodeRun.execution_id == binding.execution_id)
        )).scalars())
        for node in nodes:
            node.status = "succeeded"
        output_node = next(node for node in nodes if node.node_id == "output-format")
        execution.status = "awaiting_review"
        document = _document()
        document["run_id"] = execution.id
        database.add(store_artifact(
            execution, node_run_id=output_node.id, kind="final", title="IPD0洞察V2",
            content=__import__("json").dumps(document, ensure_ascii=False),
            source_kind="hermes_output", extension="json",
        ))
        await database.flush()
        await project_execution(database, execution.id)
        await database.commit()
        await database.refresh(session)
        assert session.data["insight_job"]["status"] == "completed"
        assert session.data["insight_job"]["completed_sections"] == [
            "summary", "root_causes", "impacts", "evidence", "recommendation", "ipd_handoff", "concept"
        ]
        assert session.data["insight"]["title"] == "HR AI权限治理"
        assert session.data["insight_review"]["source_job_id"] == binding.job_id
    await engine.dispose()
