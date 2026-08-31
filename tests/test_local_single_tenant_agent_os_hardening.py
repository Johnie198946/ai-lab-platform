from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    ROOT
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "__init__.py"
)


def load_router():
    package_name = "local_single_tenant_agent_os_hardening_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        PLUGIN_PATH,
        submodule_search_locations=[str(PLUGIN_PATH.parent)],
    )
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.capability_router"]


def agency():
    return [{
        "id": "agency:trend-researcher",
        "kind": "agency_agent",
        "name": "Trend Researcher",
        "description": "Research market trends with evidence.",
        "domain": "research",
        "invoke_tool": "agency_agents_load",
        "invoke_args": {"agent": "trend-researcher"},
        "depth": 0.82,
        "cost": 0.10,
    }]


def skill(router):
    return router._govern_skill({
        "id": "skill:business-model-research",
        "kind": "skill",
        "name": "business-model-research",
        "description": "Use when researching a business model.",
        "domain": "research",
        "invoke_tool": "skill_view",
        "invoke_args": {"name": "business-model-research"},
        "depth": 0.82,
        "cost": 0.035,
    })


def _create_state_db(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE async_delegations (
            delegation_id TEXT, parent_session_id TEXT, state TEXT,
            dispatched_at REAL, completed_at REAL, task_json TEXT, result_json TEXT
        );
        CREATE TABLE sessions (
            id TEXT, parent_session_id TEXT, source TEXT, started_at REAL
        );
        CREATE TABLE messages (
            id INTEGER, session_id TEXT, tool_name TEXT, content TEXT
        );
        """
    )
    return connection


def _insert_receipt_fixture(
    connection: sqlite3.Connection,
    *,
    parent_id: str,
    delegation_id: str,
    summary: str,
    result_hash: str | None,
) -> None:
    requested = "trend-researcher"
    result = {"status": "completed", "summary": summary}
    if result_hash is not None:
        result["result_hash"] = result_hash
    connection.execute(
        "INSERT INTO async_delegations VALUES (?,?,?,?,?,?,?)",
        (
            delegation_id,
            parent_id,
            "completed",
            10.0,
            20.0,
            json.dumps({"context": f"AI_LAB_AGENCY_SPECIALIST={requested}"}),
            json.dumps({"results": [result]}),
        ),
    )
    connection.execute(
        "INSERT INTO sessions VALUES (?,?,?,?)",
        (f"child-{delegation_id}", parent_id, "subagent", 11.0),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?,?,?,?)",
        (
            1,
            f"child-{delegation_id}",
            "agency_agents_load",
            json.dumps({"success": True, "agent": {"slug": requested}}),
        ),
    )


def test_delegate_task_is_blocked_until_selected_skill_really_loads(monkeypatch):
    router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", agency)
    pre_result = router._pre_llm_call(
        "请必须委派子代理系统调研企业 AI 市场并给出有证据的专业报告",
        session_id="skill-gate-parent",
        turn_id="skill-gate-turn",
        platform="desktop",
        sender_id="local-owner",
    )
    assert pre_result is not None
    assert pre_result["defer_streaming"] is True
    expected_args = router._LOCAL_TURN_STATES["skill-gate-parent"][
        "expected_delegate_args"
    ]

    blocked = router._pre_tool_call(
        "delegate_task",
        expected_args,
        session_id="skill-gate-parent",
    )
    assert blocked and blocked["action"] == "block"
    assert "skill_view" in blocked["message"]

    router._post_tool_call(
        "skill_view",
        {"name": "business-model-research"},
        json.dumps({
            "success": True,
            "name": "business-model-research",
            "content": "verified skill instructions",
        }),
        session_id="skill-gate-parent",
    )
    assert router._pre_tool_call(
        "delegate_task",
        expected_args,
        session_id="skill-gate-parent",
    ) is None


def test_final_transform_never_falls_back_to_in_memory_receipt(monkeypatch):
    router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", agency)
    router._pre_llm_call(
        "请必须委派子代理系统调研市场趋势并核验多源证据",
        session_id="canonical-only-parent",
        turn_id="canonical-only-turn",
        platform="desktop",
        sender_id="owner",
    )
    summary = "内存中看似成功、但没有canonical receipt的结果。"
    router._subagent_stop(
        parent_session_id="canonical-only-parent",
        child_session_id="canonical-only-child",
        child_status="completed",
        child_summary=summary,
        tool_call_history=[{
            "tool_name": "agency_agents_load",
            "tool_input": {"targets": {"agent": "trend-researcher"}},
            "status": "ok",
        }],
    )
    monkeypatch.setattr(router, "_canonical_local_receipt", lambda *_args: None)

    transformed = router._transform_llm_output(
        response_text="未经canonical验证的回答。",
        session_id="canonical-only-parent",
    )
    assert "未通过本地 Agent OS 执行验证" in transformed


def test_canonical_receipt_requires_matching_producer_hash(tmp_path, monkeypatch):
    router = load_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    connection = _create_state_db(tmp_path / "state.db")
    valid_summary = "producer hash matches"
    _insert_receipt_fixture(
        connection,
        parent_id="parent-valid",
        delegation_id="deleg-valid",
        summary=valid_summary,
        result_hash=hashlib.sha256(valid_summary.encode()).hexdigest(),
    )
    _insert_receipt_fixture(
        connection,
        parent_id="parent-missing",
        delegation_id="deleg-missing",
        summary="missing hash",
        result_hash=None,
    )
    _insert_receipt_fixture(
        connection,
        parent_id="parent-mismatch",
        delegation_id="deleg-mismatch",
        summary="mismatched hash",
        result_hash="0" * 64,
    )
    connection.commit()
    connection.close()

    valid = router._canonical_local_receipt("parent-valid", "trend-researcher")
    assert valid is not None
    assert valid["result_hash"] == hashlib.sha256(valid_summary.encode()).hexdigest()
    assert router._canonical_local_receipt("parent-missing", "trend-researcher") is None
    assert router._canonical_local_receipt("parent-mismatch", "trend-researcher") is None


def test_compact_skill_manifest_never_reverse_imports_run_agent(monkeypatch):
    router = load_router()
    sentinel = object()
    fake_run_agent = type("FakeRunAgent", (), {})()
    monkeypatch.setitem(sys.modules, "run_agent", fake_run_agent)

    real_import = __import__

    def guarded_import(name, *args, **kwargs):
        if name == "run_agent":
            raise AssertionError("plugin discovery must not reverse-import run_agent")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", guarded_import)
    router._compact_skill_manifest()

    assert getattr(fake_run_agent, "build_skills_system_prompt", sentinel) is router._compact_skills_prompt


def test_async_completion_is_adoption_continuation_not_new_routing(monkeypatch):
    router = load_router()
    router._LOCAL_TURN_STATES.clear()
    state = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": "ipd-04-architecture",
        "agency_decision": "CALL",
        "requested_agent": "multi-agent-systems-architect",
        "receipt": None,
        "main_adopted": False,
    }
    router._LOCAL_TURN_STATES["adoption-parent"] = state
    result = router._pre_llm_call(
        "[ASYNC DELEGATION BATCH COMPLETE — deleg_exact123]\ncompleted",
        session_id="adoption-parent",
        turn_id="adoption-turn",
        platform="desktop",
        sender_id="local-owner",
    )
    assert result is not None and result["defer_streaming"] is True
    assert state["route_class"] == "PROFESSIONAL_TASK"
    assert state["requested_skill"] == "ipd-04-architecture"
    assert state["requested_agent"] == "multi-agent-systems-architect"
    assert state["completion_delegation_id"] == "deleg_exact123"
    blocked = router._pre_tool_call(
        "delegate_task",
        {"goal": "must not recurse"},
        session_id="adoption-parent",
    )
    assert blocked and blocked["action"] == "block"


def test_transform_binds_canonical_lookup_to_completion_delegation(monkeypatch):
    router = load_router()
    router._LOCAL_TURN_STATES.clear()
    router._LOCAL_TURN_STATES["bound-parent"] = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": "ipd-04-architecture",
        "agency_decision": "CALL",
        "requested_agent": "multi-agent-systems-architect",
        "completion_delegation_id": "deleg_bound123",
        "receipt": None,
        "main_adopted": False,
    }
    seen = []
    monkeypatch.setattr(
        router,
        "_canonical_local_receipt",
        lambda parent, agent, delegation_id="": seen.append(
            (parent, agent, delegation_id)
        ) or {
            "verifier": "pass",
            "delegation_id": delegation_id,
            "result": "verified child result",
        },
    )
    transformed = router._transform_llm_output(
        "main draft",
        session_id="bound-parent",
    )
    assert transformed == "verified child result"
    assert seen == [(
        "bound-parent",
        "multi-agent-systems-architect",
        "deleg_bound123",
    )]


def test_canonical_receipt_accepts_core_persisted_agency_trace(tmp_path, monkeypatch):
    router = load_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    connection = _create_state_db(tmp_path / "state.db")
    summary = "canonical producer summary"
    result_hash = hashlib.sha256(summary.encode()).hexdigest()
    connection.execute(
        "INSERT INTO async_delegations VALUES (?,?,?,?,?,?,?)",
        (
            "deleg-core-trace",
            "parent-core-trace",
            "completed",
            10.0,
            20.0,
            json.dumps({"goal": "bounded task"}),
            json.dumps({"results": [{
                "status": "completed",
                "summary": summary,
                "result_hash": result_hash,
                "child_session_id": "child-core-trace",
                "tool_trace": [{
                    "tool": "agency_agents_load",
                    "status": "ok",
                    "input_summary": {
                        "argument_keys": ["agent", "task"],
                        "targets": {"agent": "trend-researcher"},
                    },
                }],
            }]}),
        ),
    )
    connection.commit()
    connection.close()

    receipt = router._canonical_local_receipt(
        "parent-core-trace",
        "trend-researcher",
        "deleg-core-trace",
    )
    assert receipt is not None
    assert receipt["verifier"] == "pass"
    assert receipt["child_session_id"] == "child-core-trace"
    assert receipt["result_hash"] == result_hash
    assert router._canonical_local_receipt(
        "parent-core-trace",
        "other-agent",
        "deleg-core-trace",
    ) is None
