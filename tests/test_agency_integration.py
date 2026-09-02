from __future__ import annotations

import importlib.util
import hashlib
import json
import queue
import sys
import types
from pathlib import Path

import pytest

from backend.api.orchestration import _agency_agent_config
from scripts.hermes_bridge import (
    _apply_triage_toolset_policy,
    _build_in_process_agent,
    _emit_delegate_receipt,
    _emit_tool_start,
    _include_available_toolsets,
    _request_triage,
    _run_agent_sync,
    _triage_route_marker,
)


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
            "invoke_tool": "tool_call",
            "invoke_args": {
                "name": "agency_agents_load",
                "arguments": {"agent": "business-strategist"},
            },
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
        "tool": "tool_call",
        "arguments": {
            "name": "agency_agents_load",
            "arguments": {"agent": "business-strategist"},
        },
    }
    assert cards[0]["fit"] > cards[1]["fit"]
    assert "marketing" in router._tokens("市场营销方案")
    assert "pricing" in router._tokens("给出定价假设")


def test_capability_router_distinguishes_system_architecture_from_ux_architecture():
    router = load_capability_router()
    inventory = [
        {
            "id": "agency:ux-architect",
            "kind": "agency_agent",
            "name": "UX Architect",
            "description": "Technical architecture and UX specialist for interface foundations.",
            "domain": "Design",
            "_search_text": "CSS design systems interaction patterns and user experience.",
            "depth": 0.82,
            "cost": 0.10,
        },
        {
            "id": "agency:multi-agent-systems-architect",
            "kind": "agency_agent",
            "name": "Multi-Agent Systems Architect",
            "description": "Systems architect for multi-agent AI platform coordination and governance.",
            "domain": "Engineering",
            "_search_text": (
                "multi-tenant isolation task queues state persistence observability "
                "fault recovery capacity planning and architecture tradeoffs"
            ),
            "depth": 0.82,
            "cost": 0.10,
        },
    ]
    system_prompt = (
        "请设计一个生产级多租户Agent平台架构，覆盖身份隔离、任务队列、状态持久化、"
        "可观测性、故障恢复和容量规划，并给出关键技术取舍。"
    )
    assert router.recommend(system_prompt, capabilities=inventory, stats={})[0]["id"] == (
        "agency:multi-agent-systems-architect"
    )

    ux_prompt = "请设计移动端操作台的信息架构、交互流程、视觉层级和可用性测试。"
    assert router.recommend(ux_prompt, capabilities=inventory, stats={})[0]["id"] == (
        "agency:ux-architect"
    )


def test_capability_router_distinguishes_product_strategy_from_pricing_analysis():
    router = load_capability_router()
    inventory = [
        {
            "id": "agency:pricing-analyst",
            "kind": "agency_agent",
            "name": "Pricing Analyst",
            "description": "Pricing research, packaging, willingness-to-pay and price experiments.",
            "domain": "Product",
            "_search_text": "pricing assumptions tiers monetization and revenue analysis",
            "depth": 0.82,
            "cost": 0.10,
        },
        {
            "id": "agency:product-manager",
            "kind": "agency_agent",
            "name": "Product Manager",
            "description": "Holistic product leader for discovery, strategy and roadmap.",
            "domain": "Product",
            "_search_text": "target customer pain points MVP roadmap metrics lifecycle pricing",
            "depth": 0.82,
            "cost": 0.10,
        },
    ]
    strategy_prompt = (
        "请为AI质量检测SaaS制定完整产品策略：定义目标客户、核心痛点、MVP范围、"
        "定价假设、12个月路线图与可量化验收指标。"
    )
    assert router.recommend(strategy_prompt, capabilities=inventory, stats={})[0]["id"] == (
        "agency:product-manager"
    )

    pricing_prompt = "只分析这款SaaS的定价、套餐、支付意愿和价格实验，不做产品路线图。"
    assert router.recommend(pricing_prompt, capabilities=inventory, stats={})[0]["id"] == (
        "agency:pricing-analyst"
    )


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
    assert set(context.hooks) == {"pre_llm_call", "pre_tool_call", "post_tool_call"}
    assert not any("router" in name for name in context.tools)


def test_capability_hook_abstains_for_server_routed_casual_and_general_turns():
    router = load_capability_router()
    assert router._pre_llm_call(
        '<<AI_LAB_TRIAGE class="CASUAL" agency="0">>\n你好'
    ) is None
    assert router._pre_llm_call(
        '<<AI_LAB_TRIAGE class="GENERAL_QA" agency="0">>\n解释一下 API'
    ) is None


def test_mac_native_triage_keeps_chat_and_general_qa_direct():
    router = load_capability_router()
    assert router._skill_route_class("你好") == "CASUAL"
    assert router._pre_llm_call("你好") is None
    assert router._skill_route_class("什么是 API") == "GENERAL_QA"
    assert router._pre_llm_call("什么是 API") is None


@pytest.mark.parametrize(
    "question",
    [
        "做个测试：你回答我OK",
        "只回复收到",
        "回答 yes",
        "不要解释，只输出1",
        "按你建议做",
        "简单解释一下什么是 API",
    ],
)
def test_mac_native_direct_response_and_simple_qa_never_enter_agent_os(question):
    router = load_capability_router()
    assert router._skill_route_class(question) in {"CASUAL", "GENERAL_QA"}
    assert router._pre_llm_call(question, session_id="fast-path") is None
    assert router._LOCAL_TURN_STATES["fast-path"]["route_class"] in {
        "CASUAL",
        "GENERAL_QA",
    }


def test_mac_native_link_research_shortlists_governed_skill(monkeypatch):
    router = load_capability_router()
    inventory = [
        router._govern_skill({
            "id": "skill:evidence-first-content-research",
            "kind": "skill",
            "name": "evidence-first-content-research",
            "description": "Research content.",
            "domain": "research",
            "invoke_tool": "skill_view",
            "invoke_args": {"name": "evidence-first-content-research"},
            "depth": 0.62,
            "cost": 0.035,
        }),
        router._govern_skill({
            "id": "skill:authenticated-web-e2e-verification",
            "kind": "skill",
            "name": "authenticated-web-e2e-verification",
            "description": "Verify a web application.",
            "domain": "engineering",
            "invoke_tool": "skill_view",
            "invoke_args": {"name": "authenticated-web-e2e-verification"},
            "depth": 0.62,
            "cost": 0.035,
        }),
    ]
    cards = router.recommend(
        "帮我研究这个链接 https://example.com/report 并核验外部资料",
        capabilities=inventory,
        stats={},
    )
    assert cards[0]["id"] == "skill:evidence-first-content-research"
    assert "skill:authenticated-web-e2e-verification" not in {
        card["id"] for card in cards
    }


def test_mac_native_negative_boundary_overrides_positive_keyword():
    router = load_capability_router()
    skill = router._govern_skill({
        "id": "skill:content-research-ingest",
        "kind": "skill",
        "name": "content-research-ingest",
        "description": "Research and ingest content.",
        "domain": "knowledge",
        "invoke_tool": "skill_view",
        "invoke_args": {"name": "content-research-ingest"},
        "depth": 0.62,
        "cost": 0.035,
    })
    cards = router.recommend(
        "研究这个链接，但只读研究，不要保存",
        capabilities=[skill],
        stats={},
    )
    assert cards == []


def test_link_research_blocks_terminal_and_duplicate_extract():
    router = load_capability_router()
    router._WEB_RESEARCH_TURNS.clear()
    router._pre_llm_call(
        "研究这个链接 https://example.com/report",
        turn_id="turn-web-policy",
    )
    assert router._pre_tool_call(
        "web_extract", {"urls": ["https://example.com/report"]},
        turn_id="turn-web-policy",
    ) is None
    duplicate = router._pre_tool_call(
        "web_extract", {"urls": ["https://example.com/report"]},
        turn_id="turn-web-policy",
    )
    terminal = router._pre_tool_call(
        "terminal", {"command": "curl https://example.com/report"},
        turn_id="turn-web-policy",
    )
    assert duplicate and duplicate["action"] == "block"
    assert terminal and terminal["action"] == "block"


def test_native_extract_html_parser_removes_scripts_and_keeps_readable_text():
    plugin = load_capability_plugin()
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/native_extract_provider.py"
    spec = importlib.util.spec_from_file_location(
        f"{plugin.__name__}.native_extract_provider", path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    parser = module._ReadableHTML()
    parser.feed(
        "<html><head><title>Report</title><script>steal()</script></head>"
        "<body><h1>Finding</h1><p>Evidence first.</p></body></html>"
    )
    title, text = parser.result()
    assert title == "Report"
    assert "Finding" in text and "Evidence first." in text
    assert "steal" not in text


def test_configure_web_extract_preserves_plugins_and_sets_split_backends(tmp_path):
    path = ROOT / "scripts/configure_hermes_web_extract.py"
    spec = importlib.util.spec_from_file_location("configure_hermes_web_extract", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    home = tmp_path / "hermes"
    home.mkdir()
    (home / "config.yaml").write_text(
        "plugins:\n  enabled: [feishu-write-guard]\nmodel:\n  default: test-model\n",
        encoding="utf-8",
    )
    source = ROOT / "agency/hermes-plugins/ai-lab-capabilities"
    result = module.configure(home, source, tmp_path / "backups")
    import yaml

    config = yaml.safe_load((home / "config.yaml").read_text(encoding="utf-8"))
    assert config["model"]["default"] == "test-model"
    assert set(config["plugins"]["enabled"]) == {
        "feishu-write-guard", "ai-lab-capabilities",
    }
    assert config["web"] == {
        "search_backend": "ddgs",
        "extract_backend": "ai-lab-native",
    }
    assert Path(result["backup"]).is_dir()
    assert (home / "plugins/ai-lab-capabilities/native_extract_provider.py").is_file()


def test_capability_hook_uses_only_exact_agency_slugs_for_professional_turn(monkeypatch):
    router = load_capability_router()
    observed = {}
    agency = [{
        "id": "agency:trend-researcher",
        "kind": "agency_agent",
        "name": "Trend Researcher",
        "description": "Research market trends with evidence.",
        "domain": "research",
        "invoke_tool": "tool_call",
        "invoke_args": {
            "name": "agency_agents_load",
            "arguments": {"agent": "trend-researcher"},
        },
        "depth": 0.82,
        "cost": 0.10,
    }]
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency)

    original = router.recommend

    def capture(query, **kwargs):
        observed["query"] = query
        observed["capabilities"] = kwargs.get("capabilities")
        return original(query, **kwargs)

    monkeypatch.setattr(router, "recommend", capture)
    result = router._pre_llm_call(
        '<<AI_LAB_TRIAGE class="PROFESSIONAL_TASK" agency="1">>\n'
        "调研企业 AI 市场"
    )
    assert result is not None
    assert observed["query"] == "调研企业 AI 市场"
    assert observed["capabilities"] == agency
    cards = json.loads(result["context"].split("Candidates: ", 1)[1])
    assert len(cards) == 1
    assert cards[0]["invoke"]["tool"] == "delegate_task"
    tasks = cards[0]["invoke"]["arguments"]["tasks"]
    assert len(tasks) == 1
    assert tasks[0]["goal"] == "调研企业 AI 市场"
    delegate_context = tasks[0]["context"]
    assert "AI_LAB_AGENCY_SPECIALIST=trend-researcher" in delegate_context
    assert "agency_agents_load" in delegate_context
    assert '{"agent":"trend-researcher"}' in delegate_context
    assert "engineering-trend-researcher" not in result["context"]


def test_professional_candidate_survives_long_user_task(monkeypatch):
    router = load_capability_router()
    agency = [{
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
    monkeypatch.setattr(router, "_agency_capabilities", lambda: agency)
    result = router._pre_llm_call(
        '<<AI_LAB_TRIAGE class="PROFESSIONAL_TASK" agency="1">>\n'
        + ("专业研究任务" * 800)
    )
    assert result is not None
    assert len(result["context"]) <= router.MAX_PROFESSIONAL_INJECTED_CHARS
    cards = json.loads(result["context"].split("Candidates: ", 1)[1])
    assert cards[0]["invoke"]["tool"] == "delegate_task"
    assert cards[0]["invoke"]["arguments"]["tasks"][0]["goal"]


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
    assert (
        'AGENCY_AGENTS_SHA="${AGENCY_AGENTS_SHA:-'
        '3c9588880b7cafaec325a104899fd8bbe27e7d72}"'
    ) in installer
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


def test_bridge_applies_fail_closed_toolsets_from_server_triage():
    all_tools = [
        "clarify", "memory", "web", "delegation", "skills",
        "tenant_skills", "agency_agents", "ai_lab", "file", "terminal",
    ]
    casual = _request_triage({"triage": {
        "route_class": "CASUAL",
        "reason_code": "conversation_marker",
        "agency_enabled": True,
    }})
    assert casual is not None
    assert _apply_triage_toolset_policy(all_tools, casual) == []

    general = _request_triage({"triage": {
        "route_class": "GENERAL_QA",
        "reason_code": "evidence_qa",
        "evidence_requirements": ["web_extract"],
        "agency_enabled": True,
    }})
    assert general is not None
    assert _apply_triage_toolset_policy(all_tools, general) == [
        "clarify", "memory", "web",
    ]

    professional = _request_triage({"triage": {
        "route_class": "PROFESSIONAL_TASK",
        "reason_code": "professional_url_research",
        "evidence_requirements": ["web_extract", "web_search"],
        "agency_enabled": True,
        "skill_enabled": False,
    }})
    assert professional is not None
    assert _apply_triage_toolset_policy(all_tools, professional) == [
        "clarify", "memory", "web", "delegation",
        "agency_agents", "ai_lab", "file", "terminal",
    ]
    assert _triage_route_marker(professional).startswith(
        '<<AI_LAB_TRIAGE class="PROFESSIONAL_TASK" agency="1">>'
    )

    no_agency = _request_triage({"triage": {
        "route_class": "PROFESSIONAL_TASK",
        "reason_code": "tenant_skill_management",
        "evidence_requirements": [],
        "agency_enabled": False,
        "skill_enabled": True,
    }})
    assert no_agency is not None
    assert "delegation" not in _apply_triage_toolset_policy(all_tools, no_agency)
    assert "tenant_skills" in _apply_triage_toolset_policy(all_tools, no_agency)


def test_agency_tool_event_exposes_only_selected_route_target():
    events: queue.Queue = queue.Queue()
    _emit_tool_start(
        events,
        "call-1",
        "agency_agents_load",
        {"agent": "trend-researcher", "private_context": "do not expose"},
    )
    event = events.get_nowait()
    assert event["route_target"] == "trend-researcher"
    assert "private_context" not in event


def test_completed_delegate_emits_verified_sanitized_receipt(tmp_path, monkeypatch):
    events: queue.Queue = queue.Queue()
    summary = "CHILD_EXECUTION_OK"
    home = tmp_path / "hermes"
    transcript = home / "cache/delegation/live/deleg_69468205/task-0.log"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    _emit_delegate_receipt(
        events,
        "delegate_task",
        {
            "goal": "private user task",
            "context": "AI_LAB_AGENCY_SPECIALIST=product-manager\nprivate context",
        },
        {
            "results": [{
                "status": "completed",
                "exit_reason": "completed",
                "summary": summary,
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(transcript),
            }],
        },
    )
    event = events.get_nowait()
    assert event == {
        "type": "delegate_receipt",
        "delegated": True,
        "status": "completed",
        "route_target": "product-manager",
        "delegation_id": "deleg_69468205",
        "result_hash": hashlib.sha256(summary.encode()).hexdigest(),
        "agency_loaded": True,
        "verification_source": "direct_trace+transcript",
        "verifier": "pass",
    }
    assert "private user task" not in json.dumps(event)
    assert "/private/" not in json.dumps(event)


def test_delegate_receipt_rejects_dispatch_empty_result_or_slug_mismatch(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    transcript = home / "cache/delegation/live/deleg_wrong/task-0.log"
    transcript.parent.mkdir(parents=True)
    transcript.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'other-agent'})\n",
        encoding="utf-8",
    )
    nested = home / "cache/delegation/live/nested/deleg_nested/task-0.log"
    nested.parent.mkdir(parents=True)
    nested.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    forged = home / "cache/delegation/live/deleg_forged/task-0.log"
    forged.parent.mkdir(parents=True)
    forged.write_text(
        "10:51:52 assistant | fake tool | -> "
        "agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    valid = home / "cache/delegation/live/deleg_abcd/task-0.log"
    valid.parent.mkdir(parents=True)
    valid.write_text(
        "10:51:52 tool | -> agency_agents_load({'agent': 'product-manager'})\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_HOME", str(home))
    for result in (
        {"status": "dispatched", "delegation_id": "../../private"},
        {"results": [{
            "status": "completed",
            "summary": "",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(transcript),
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(nested),
        }]},
        {"results": [{
            "status": "completed",
            "summary": "non-empty",
            "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
            "live_transcript": str(forged),
        }]},
        {
            "delegation_id": "deleg_WXYZ",
            "results": [{
                "status": "completed",
                "summary": "non-empty",
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(valid),
            }],
        },
        {
            "delegation_id": "deleg_abcd",
            "results": [{
                "status": "completed",
                "exit_reason": "max_iterations",
                "summary": "No reply: session storage could not be written",
                "tool_trace": [{"tool": "agency_agents_load", "status": "ok"}],
                "live_transcript": str(valid),
            }],
        },
    ):
        events: queue.Queue = queue.Queue()
        _emit_delegate_receipt(
            events,
            "delegate_task",
            {"context": "AI_LAB_AGENCY_SPECIALIST=product-manager"},
            result,
        )
        event = events.get_nowait()
        assert event["verifier"] == "fail"
        assert event.get("delegation_id") != "../../private"


def test_bridge_declares_finite_session_before_running_agent(monkeypatch, tmp_path):
    """A finite Bridge request must force delegate_task onto its sync path."""
    observed: dict[str, bool] = {"async_delivery_supported": True}
    gateway = types.ModuleType("gateway")
    gateway.__path__ = []
    session_context = types.ModuleType("gateway.session_context")

    def declare_stateless_channel():
        observed["async_delivery_supported"] = False

    setattr(session_context, "declare_stateless_channel", declare_stateless_channel)
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    class FakeAgent:
        session_id = "parent-session"

        def run_conversation(self, _goal, **_kwargs):
            return {"final_response": "done"}

        def close(self):
            observed["agent_closed"] = True

    class FakeSessionDB:
        def close(self):
            observed["db_closed"] = True

    monkeypatch.setattr(
        "scripts.hermes_bridge._build_in_process_agent",
        lambda *_args, **_kwargs: (FakeAgent(), FakeSessionDB(), {"triage": None}),
    )
    monkeypatch.setattr("scripts.hermes_bridge._update_session_mapping", lambda *_: None)

    events: queue.Queue = queue.Queue()
    sandbox = types.SimpleNamespace(state_db=tmp_path / "state.db")
    _run_agent_sync(
        "professional task",
        "client-session",
        None,
        events,
        [None],
        agent_config={},
        sandbox=sandbox,
    )

    assert observed["async_delivery_supported"] is False
    assert observed["agent_closed"] is True
    assert observed["db_closed"] is True
    assert events.get_nowait()["type"] == "status"
    assert events.get_nowait()["type"] == "done"


def test_bridge_agent_disables_host_profile_and_project_context(monkeypatch, tmp_path):
    """Tenant agents must not inherit host MEMORY/USER/AGENTS context."""
    captured: dict[str, object] = {}

    class FakeAgent:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    run_agent = types.ModuleType("run_agent")
    setattr(run_agent, "AIAgent", FakeAgent)
    monkeypatch.setitem(sys.modules, "run_agent", run_agent)
    monkeypatch.setattr(
        "scripts.hermes_bridge._get_cached_config",
        lambda: {"model": {"default": "test-model"}},
    )
    monkeypatch.setattr(
        "scripts.hermes_bridge._get_cached_runtime",
        lambda _cfg: {"provider": "test", "api_key": "test", "base_url": None},
    )
    monkeypatch.setattr("scripts.hermes_bridge._get_cached_fallback", lambda _cfg: None)
    monkeypatch.setattr("scripts.hermes_bridge._get_cached_tools", lambda _cfg: set())
    monkeypatch.setattr("scripts.hermes_bridge._resolve_dynamic_toolsets", lambda *_: [])
    monkeypatch.setattr(
        "scripts.hermes_bridge._create_sandbox_session_db",
        lambda _sandbox: object(),
    )
    monkeypatch.setattr("scripts.hermes_bridge.persist_agent_snapshot", lambda *_: None)
    monkeypatch.setattr(
        "agent.runtime_cwd.set_session_cwd",
        lambda value: captured.__setitem__("session_cwd", value),
    )

    sandbox = types.SimpleNamespace(
        root=tmp_path / "tenant-root",
        state_db=tmp_path / "state.db",
        hermes_home=tmp_path / "hermes-home",
    )
    _build_in_process_agent(
        "tenant request",
        "client-session",
        None,
        queue.Queue(),
        agent_config={},
        sandbox=sandbox,
    )

    assert captured["skip_context_files"] is True
    assert captured["skip_memory"] is True
    assert captured["session_cwd"] == str(sandbox.root)
