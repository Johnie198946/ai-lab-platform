from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

from backend.api.orchestration import _agency_agent_config
from scripts.hermes_bridge import _include_available_toolsets


ROOT = Path(__file__).resolve().parents[1]


class FakePluginContext:
    def __init__(self):
        self.tools = {}
        self.dispatched = []
        self.hooks = {}

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}

    def dispatch_tool(self, name, args):
        self.dispatched.append((name, args))
        return {"tool": name, "args": args}

    def register_hook(self, name, callback):
        self.hooks[name] = callback


def load_capability_plugin():
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/__init__.py"
    package_name = "ai_lab_capabilities_plugin"
    sys.modules.pop(package_name, None)
    sys.modules.pop(f"{package_name}.capability_router", None)
    spec = importlib.util.spec_from_file_location(
        package_name,
        path,
        submodule_search_locations=[str(path.parent)],
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[package_name] = module
    spec.loader.exec_module(module)
    return module


def load_capability_router():
    plugin = load_capability_plugin()
    return sys.modules[f"{plugin.__name__}.capability_router"]


def test_agency_agent_config_is_server_owned_and_bounded():
    config = _agency_agent_config()
    assert config["composition"] == {"business_surface": "agency"}
    assert set(config["allowed_tools"]) == {
        "web_search",
        "web_extract",
        "knowledge_search",
        "skill_load",
        "delegate_task",
    }
    assert "terminal" not in config["allowed_tools"]
    assert "write_file" not in config["allowed_tools"]


def test_ai_lab_capability_plugin_routes_only_supported_tools():
    module = load_capability_plugin()
    context = FakePluginContext()
    module.register(context)
    assert set(context.tools) == {"ai_lab_capabilities", "ai_lab_execute"}

    payload = json.loads(context.tools["ai_lab_execute"]["handler"]({
        "capability": "web_research",
        "inputs": {"query": "AI server market"},
    }))
    assert payload["success"] is True
    assert context.dispatched == [("web_search", {"query": "AI server market"})]

    rejected = json.loads(context.tools["ai_lab_execute"]["handler"]({
        "capability": "terminal",
        "inputs": {"command": "whoami"},
    }))
    assert rejected == {
        "success": False,
        "error": "unsupported_capability",
        "capability": "terminal",
    }


def test_capability_router_understands_chinese_and_prefers_professional_depth():
    router = load_capability_router()
    inventory = [
        router._direct_capability(),
        {
            "id": "skill:quick-marketing-note",
            "kind": "skill",
            "name": "quick-marketing-note",
            "description": "Write a short general marketing note.",
            "domain": "marketing",
            "invoke_tool": "skill_view",
            "invoke_args": {"name": "quick-marketing-note"},
            "depth": 0.38,
            "cost": 0.02,
        },
        {
            "id": "agency:business-strategist",
            "kind": "agency_agent",
            "name": "Business Strategist",
            "description": (
                "Senior management consulting specialist for market entry, "
                "go-to-market strategy, business models and strategic decisions."
            ),
            "domain": "marketing strategy",
            "invoke_tool": "agency_agents_load",
            "invoke_args": {"agent": "business-strategist"},
            "depth": 0.86,
            "cost": 0.10,
        },
    ]
    prompt = (
        "我们准备面向企业客户发布一款AI知识管理SaaS。请输出可供管理层评审的专业GTM方案，"
        "包含ICP、定价假设、渠道、90天节奏、指标和风险，不要泛泛而谈。"
    )
    cards = router.recommend(prompt, capabilities=inventory, stats={})
    assert cards[0]["id"] == "agency:business-strategist"
    assert cards[0]["invoke"] == {
        "tool": "agency_agents_load",
        "arguments": {"agent": "business-strategist"},
    }
    assert cards[0]["fit"] > cards[1]["fit"]
    assert "marketing" in router._tokens("市场营销方案")
    assert "pricing" in router._tokens("给出定价假设")


def test_capability_router_keeps_context_bounded_and_can_choose_direct_answer():
    router = load_capability_router()
    inventory = [router._direct_capability()]
    inventory.extend({
        "id": f"agency:specialist-{index}",
        "kind": "agency_agent",
        "name": f"Specialist {index}",
        "description": "Expert go-to-market GTM specialist " + ("long description " * 80),
        "domain": "specialized",
        "invoke_tool": "agency_agents_load",
        "invoke_args": {"agent": f"specialist-{index}"},
        "depth": 0.85,
        "cost": 0.10,
    } for index in range(500))
    cards = router.recommend(
        "快速简单解释一下什么是GTM",
        capabilities=inventory,
        stats={},
        limit=50,
    )
    assert len(cards) == router.MAX_CANDIDATES
    assert cards[0]["id"] == "hermes:direct"

    original = router.recommend
    try:
        router.recommend = lambda query, limit=5: cards
        context = router._candidate_context("快速解释")
    finally:
        router.recommend = original
    assert context is not None
    assert len(context) <= router.MAX_INJECTED_CHARS
    json.loads(context.split("Candidates: ", 1)[1])


def test_capability_router_learns_success_without_storing_conversation(tmp_path, monkeypatch):
    router = load_capability_router()
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    router._post_tool_call(
        "agency_agents_load",
        {"agent": "business-strategist", "task": "private task text"},
        json.dumps({"success": True}),
        duration_ms=120,
    )
    stats = json.loads(
        (tmp_path / "state/capability-router-stats.json").read_text(encoding="utf-8")
    )
    assert stats == {
        "agency:business-strategist": {
            "avg_latency_ms": 120.0,
            "calls": 1,
            "successes": 1,
        }
    }
    assert "private task text" not in json.dumps(stats)


def test_capability_plugin_reuses_hermes_hooks_instead_of_registering_router_tool():
    module = load_capability_plugin()
    context = FakePluginContext()
    router = sys.modules[f"{module.__name__}.capability_router"]
    router._INSTALLED = False
    module.register(context)
    assert set(context.tools) == {"ai_lab_capabilities", "ai_lab_execute"}
    assert set(context.hooks) == {"pre_llm_call", "post_tool_call"}
    assert not any("router" in name for name in context.tools)


def test_capability_router_extends_existing_tool_search_contract(monkeypatch):
    router = load_capability_router()
    fake_search = types.ModuleType("tools.tool_search")
    fake_search.dispatch_tool_search = lambda args, **kwargs: json.dumps({
        "query": args["query"],
        "matches": [{"name": "existing_deferred_tool"}],
    })
    fake_search.bridge_tool_schemas = lambda *args, **kwargs: [{
        "type": "function",
        "function": {
            "name": "tool_search",
            "description": "Original Hermes search description.",
            "parameters": {"type": "object", "properties": {}},
        },
    }]
    fake_tools = types.ModuleType("tools")
    fake_tools.tool_search = fake_search
    monkeypatch.setitem(sys.modules, "tools", fake_tools)
    monkeypatch.setitem(sys.modules, "tools.tool_search", fake_search)
    monkeypatch.setattr(router, "recommend", lambda query, limit=5: [{
        "id": "agency:business-strategist",
        "fit": 88.0,
    }])

    router._extend_tool_search()
    payload = json.loads(fake_search.dispatch_tool_search({"query": "战略", "limit": 3}))
    assert payload["matches"] == [{"name": "existing_deferred_tool"}]
    assert payload["capability_matches"] == [{
        "id": "agency:business-strategist",
        "fit": 88.0,
    }]
    schemas = fake_search.bridge_tool_schemas(1)
    assert "Original Hermes search description" in schemas[0]["function"]["description"]
    assert "Hermes skills and Agency specialists" in schemas[0]["function"]["description"]


def test_installer_preserves_pre_install_plugin_config_and_adds_both_routers():
    installer = (ROOT / "scripts/install_agency_hermes.sh").read_text()
    assert 'original_config="$tmp_dir/config.before-agency.yaml"' in installer
    assert 'source = original if original and original.exists() else path' in installer
    assert '("agency-agents-router", "ai-lab-capabilities")' in installer
    assert "yaml.safe_load" in installer


def test_agency_plugins_are_added_after_lightweight_tool_selection():
    selected = _include_available_toolsets(
        ["clarify", "delegation"],
        {"clarify", "delegation", "agency_agents", "ai_lab", "terminal"},
        {"agency_agents", "ai_lab"},
    )
    assert selected == ["clarify", "delegation", "agency_agents", "ai_lab"]
    assert "terminal" not in selected
