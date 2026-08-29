from __future__ import annotations

import importlib.util
import json
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
    package_name = "local_agent_os_review_regression_plugin"
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


def _skill(router):
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


def _agency():
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


def test_delegate_wrappers_cannot_bypass_skill_first_gate(monkeypatch):
    router = load_router()
    router._LOCAL_TURN_STATES.clear()
    monkeypatch.setattr(router, "_skill_capabilities", lambda: [_skill(router)])
    monkeypatch.setattr(router, "_agency_capabilities", _agency)
    router._pre_llm_call(
        "请系统调研企业 AI 市场并给出有证据的专业报告",
        session_id="wrapper-skill-gate-parent",
        turn_id="wrapper-skill-gate-turn",
        platform="desktop",
        sender_id="local-owner",
    )

    calls = [
        ("tool_call", {"name": "delegate_task", "arguments": {"goal": "研究市场"}}),
        (
            "ai_lab_execute",
            {"capability": "agency_agent:trend-researcher", "goal": "研究市场"},
        ),
    ]
    for tool_name, args in calls:
        blocked = router._pre_tool_call(
            tool_name,
            args,
            session_id="wrapper-skill-gate-parent",
        )
        assert blocked and blocked["action"] == "block"
        assert "skill_view" in blocked["message"]

    router._post_tool_call(
        "skill_view",
        {"name": "business-model-research"},
        json.dumps({"success": True}),
        session_id="wrapper-skill-gate-parent",
    )
    for tool_name, args in calls:
        assert router._pre_tool_call(
            tool_name,
            args,
            session_id="wrapper-skill-gate-parent",
        ) is None
