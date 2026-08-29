from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PLUGIN_PATH = (
    ROOT
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "__init__.py"
)


def load_router():
    package_name = "local_agent_os_nested_wrapper_regression_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        PLUGIN_PATH,
        submodule_search_locations=[str(PLUGIN_PATH.parent)],
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return sys.modules[f"{package_name}.capability_router"]


def nested_delegate_calls():
    return [
        (
            "tool_call",
            {
                "name": "ai_lab_execute",
                "arguments": {
                    "capability": "agency_agent:multi-agent-systems-architect",
                },
            },
        ),
        (
            "tool_call",
            {
                "name": "tool_call",
                "arguments": {
                    "name": "delegate_task",
                    "arguments": {"goal": "must not bypass"},
                },
            },
        ),
        (
            "tool_call",
            {
                "name": "tool_call",
                "arguments": json.dumps({
                    "name": "delegate_task",
                    "arguments": {"goal": "JSON wrapper must not bypass"},
                }),
            },
        ),
    ]


@pytest.mark.parametrize("tool_name,args", nested_delegate_calls())
def test_nested_delegate_wrappers_cannot_bypass_skill_first(tool_name, args):
    router = load_router()
    session = "nested-skill-parent"
    router._LOCAL_TURN_STATES[session] = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "agency_decision": "CALL",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": None,
    }

    blocked = router._pre_tool_call(tool_name, args, session_id=session)

    assert blocked and blocked["action"] == "block"
    assert "skill_view" in blocked["message"]


@pytest.mark.parametrize("tool_name,args", nested_delegate_calls())
def test_nested_delegate_wrappers_cannot_bypass_adoption_recursion(tool_name, args):
    router = load_router()
    session = "nested-adoption-parent"
    router._LOCAL_TURN_STATES[session] = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "agency_decision": "CALL",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": "ipd-04-architecture",
        "adoption_continuation": True,
    }

    blocked = router._pre_tool_call(tool_name, args, session_id=session)

    assert blocked and blocked["action"] == "block"
    assert "recursive" in blocked["message"]


def test_malformed_or_overdeep_wrapper_fails_closed():
    router = load_router()
    session = "malformed-wrapper-parent"
    router._LOCAL_TURN_STATES[session] = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "agency_decision": "CALL",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": None,
    }
    malformed = {"name": "tool_call", "arguments": "not-json"}
    overdeep = {"name": "delegate_task", "arguments": {"goal": "deep"}}
    for _ in range(12):
        overdeep = {"name": "tool_call", "arguments": overdeep}

    for args in (malformed, overdeep):
        blocked = router._pre_tool_call("tool_call", args, session_id=session)
        assert blocked and blocked["action"] == "block"
        assert "wrapper" in blocked["message"].casefold()


def _wrap_tool(name, arguments, depth):
    wrapped = {"name": name, "arguments": arguments}
    for _ in range(depth):
        wrapped = {"name": "tool_call", "arguments": wrapped}
    return wrapped


def test_wrapper_depth_boundary_allows_eight_and_blocks_nine():
    router = load_router()
    session = "wrapper-depth-boundary-parent"
    router._LOCAL_TURN_STATES[session] = {
        "principal": "local_owner",
        "route_class": "PROFESSIONAL_TASK",
        "agency_decision": "CALL",
        "skill_decision": "SELECT",
        "requested_skill": "ipd-04-architecture",
        "loaded_skill": None,
    }

    safe_at_eight = router._pre_tool_call(
        "tool_call",
        _wrap_tool("web_search", {"query": "boundary"}, 7),
        session_id=session,
    )
    delegate_at_eight = router._pre_tool_call(
        "tool_call",
        _wrap_tool("delegate_task", {"goal": "boundary"}, 7),
        session_id=session,
    )
    safe_at_nine = router._pre_tool_call(
        "tool_call",
        _wrap_tool("web_search", {"query": "boundary"}, 8),
        session_id=session,
    )

    assert safe_at_eight is None
    assert delegate_at_eight and "skill_view" in delegate_at_eight["message"]
    assert safe_at_nine and "wrapper" in safe_at_nine["message"].casefold()
