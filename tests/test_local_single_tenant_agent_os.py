from __future__ import annotations

import hashlib
import importlib.util
import json
import sqlite3
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    ROOT
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "__init__.py"
)


class LocalPluginContext:
    profile_name = "default"

    def __init__(self):
        self.tools = {}
        self.hooks = {}

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}

    def register_hook(self, name, callback):
        self.hooks[name] = callback

    def dispatch_tool(self, name, args):
        return {"tool": name, "args": args}


def load_router():
    package_name = "local_single_tenant_agent_os_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        PLUGIN_PATH,
        submodule_search_locations=[str(PLUGIN_PATH.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module, sys.modules[f"{package_name}.capability_router"]


def agency(router):
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


def test_default_profile_registers_local_agent_os_lifecycle():
    plugin, router = load_router()
    router._INSTALLED = False
    context = LocalPluginContext()
    plugin.register(context)
    assert set(context.hooks) == {
        "pre_gateway_dispatch",
        "pre_llm_call",
        "pre_tool_call",
        "post_tool_call",
        "subagent_start",
        "subagent_stop",
        "transform_llm_output",
    }


def test_local_professional_turn_requires_native_skill_then_delegation(monkeypatch):
    _, router = load_router()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))

    result = router._pre_llm_call(
        "请系统调研企业 AI 市场并给出有证据的专业报告",
        session_id="local-parent",
        turn_id="local-turn",
        platform="desktop",
        sender_id="local-owner",
    )

    assert result is not None
    context = result["context"]
    assert "LOCAL_SINGLE_TENANT_AGENT_OS" in context
    assert context.index('"tool":"skill_view"') < context.index('"tool":"delegate_task"')
    state = router._LOCAL_TURN_STATES["local-parent"]
    assert state["skill_decision"] == "SELECT"
    assert state["requested_skill"] == "business-model-research"
    assert state["agency_decision"] == "CALL"
    assert state["requested_agent"] == "trend-researcher"


def test_local_principal_scope_is_inherited_by_native_child(monkeypatch):
    _, router = load_router()
    router._LOCAL_TURN_STATES.clear()
    router._GATEWAY_IDENTITIES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    source = types.SimpleNamespace(
        platform=types.SimpleNamespace(value="feishu"),
        user_id="member-1",
        chat_id="group-1",
        chat_type="group",
    )
    event = types.SimpleNamespace(source=source, text="请专业调研行业趋势")
    assert router._pre_gateway_dispatch(event=event) is None
    router._pre_llm_call(
        event.text,
        session_id="parent-group",
        turn_id="turn-group",
        platform="feishu",
        sender_id="member-1",
    )
    assert router._LOCAL_TURN_STATES["parent-group"]["principal"] == "group_member"
    assert router._pre_tool_call(
        "web_search", {"query": "AI market"}, session_id="parent-group"
    ) is None
    denied = router._pre_tool_call(
        "terminal", {"command": "whoami"}, session_id="parent-group"
    )
    assert denied and denied["action"] == "block"

    router._subagent_start(
        parent_session_id="parent-group",
        child_session_id="child-group",
    )
    assert router._pre_llm_call(
        "执行委派的专业研究任务",
        session_id="child-group",
        platform="subagent",
    ) is None
    assert router._LOCAL_TURN_STATES["child-group"]["route_class"] == "CHILD"
    child_denied = router._pre_tool_call(
        "write_file", {"path": "/tmp/nope"}, session_id="child-group"
    )
    assert child_denied and child_denied["action"] == "block"


def test_local_in_memory_receipt_is_diagnostic_only(monkeypatch):
    _, router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency(router))
    router._pre_llm_call(
        "请系统调研市场趋势并核验多源证据",
        session_id="receipt-parent",
        turn_id="receipt-turn",
        platform="desktop",
        sender_id="owner",
    )

    blocked = router._transform_llm_output(
        response_text="看起来已经完成。",
        session_id="receipt-parent",
    )
    assert "未通过本地 Agent OS 执行验证" in blocked

    summary = "独立研究结论：企业采用率增长的主要约束是数据治理与集成成本。"
    router._subagent_stop(
        parent_session_id="receipt-parent",
        child_session_id="receipt-child",
        child_status="completed",
        child_summary=summary,
        tool_call_history=[{
            "tool_name": "agency_agents_load",
            "tool_input": {"targets": {"agent": "trend-researcher"}},
            "status": "ok",
        }],
    )
    state = router._LOCAL_TURN_STATES["receipt-parent"]
    assert state["receipt"]["verifier"] == "pass"
    assert state["receipt"]["result_hash"] == hashlib.sha256(summary.encode()).hexdigest()

    adopted = router._transform_llm_output(
        response_text="一段没有消费 child 结论的空泛回答。",
        session_id="receipt-parent",
    )
    assert "未通过本地 Agent OS 执行验证" in adopted


def test_untrusted_sender_cannot_use_wrapped_or_direct_privileged_tools(monkeypatch):
    _, router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [])
    monkeypatch.setattr(router, "_agency_capabilities", lambda: [])
    router._pre_llm_call(
        "请检查系统",
        session_id="untrusted",
        turn_id="untrusted-turn",
        platform="feishu",
        sender_id="",
    )
    assert router._LOCAL_TURN_STATES["untrusted"]["principal"] == "untrusted_sender"
    direct = router._pre_tool_call(
        "terminal", {"command": "whoami"}, session_id="untrusted"
    )
    wrapped = router._pre_tool_call(
        "tool_call",
        {"name": "write_file", "arguments": {"path": "/tmp/nope"}},
        session_id="untrusted",
    )
    assert direct and direct["action"] == "block"
    assert wrapped and wrapped["action"] == "block"


def test_canonical_receipt_is_rebuilt_from_hermes_state_db(tmp_path, monkeypatch):
    _, router = load_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    connection = sqlite3.connect(tmp_path / "state.db")
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
    summary = "child verified result"
    requested = "trend-researcher"
    connection.execute(
        "INSERT INTO async_delegations VALUES (?,?,?,?,?,?,?)",
        (
            "deleg-real",
            "parent-real",
            "completed",
            10.0,
            20.0,
            json.dumps({"context": None}),
            json.dumps({
                "results": [{
                    "status": "completed",
                    "summary": summary,
                    "result_hash": hashlib.sha256(summary.encode()).hexdigest(),
                    "child_session_id": "child-real",
                    "tool_trace": [{
                        "tool": "tool_call",
                        "status": "ok",
                        "input_summary": {"targets": {}},
                    }],
                }]
            }),
        ),
    )
    connection.execute(
        "INSERT INTO sessions VALUES (?,?,?,?)",
        # Real Desktop delegations currently persist the child surface as
        # desktop; parent binding and delegation window are the stable facts.
        ("child-real", "parent-real", "desktop", 11.0),
    )
    connection.execute(
        "INSERT INTO messages VALUES (?,?,?,?)",
        (
            1,
            "child-real",
            "agency_agents_load",
            json.dumps({"success": True, "agent": {"slug": requested}}),
        ),
    )
    connection.commit()
    connection.close()

    receipt = router._canonical_local_receipt("parent-real", requested)
    assert receipt is not None
    assert receipt["verifier"] == "pass"
    assert receipt["delegation_id"] == "deleg-real"
    assert receipt["child_session_id"] == "child-real"
    assert receipt["loaded_agent"] == requested
    assert receipt["result_hash"] == hashlib.sha256(summary.encode()).hexdigest()
