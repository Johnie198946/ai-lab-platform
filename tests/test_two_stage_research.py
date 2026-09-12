"""Source-first routing through native SDK hooks; synthetic text, no live writes.

Run with Hermes dependencies on PYTHONPATH and pytest --noconftest (no DB used).
Real model/source-fetch latency is a separate acceptance, not mocked here.
"""
import ast
import importlib.util
import json
import os
from pathlib import Path
import sys
from unittest.mock import Mock, patch

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "agency/hermes-plugins/ai-lab-capabilities"
HERMES = Path(os.environ.get("HERMES_SOURCE", str(Path.home() / ".hermes/hermes-agent")))
sys.path.insert(0, str(HERMES))
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest

spec = importlib.util.spec_from_file_location("two_stage_plugin", PLUGIN / "__init__.py", submodule_search_locations=[str(PLUGIN)])
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
router = sys.modules["two_stage_plugin.capability_router"]
URL = "https://example.org/synthetic-study"
QUICK = "研究一下 " + URL
HISTORY = [
    {"role": "user", "content": QUICK},
    {"role": "tool", "name": "web_extract", "content": json.dumps({"results": [{"url": URL, "content": "Synthetic article: cost depends on workload; no empirical result asserted."}]})},
    {"role": "assistant", "content": "作者主张成本较低，未外部核验。缺口：负载条件。方向：成本、经济性、复现。"},
]


@pytest.fixture
def native(tmp_path, monkeypatch):
    monkeypatch.setenv("HERMES_HOME", str(tmp_path))
    monkeypatch.setenv("AI_LAB_AGENT_OS_MODE", "local_single_tenant")
    (tmp_path / "config.yaml").write_text(yaml.safe_dump({"plugins": {"entries": {
        "ai-lab-capabilities": {"settings": {"research_deposit": {
            "enabled": True, "deployment_mode": "local_single_tenant",
            "vault_root": str(tmp_path / "vault"),
        }}}
    }}}))
    manager = PluginManager()
    ctx = PluginContext(PluginManifest(name="ai-lab-capabilities"), manager)
    router._INSTALLED = False
    router._LOCAL_TURN_STATES.clear()
    router._WEB_RESEARCH_TURNS.clear()
    # No network provider installation or global manifest monkeypatching. The
    # actual registered router, deposition and composed finalizer all run.
    with patch.object(ctx, "register_web_search_provider"), patch.object(router, "_extend_tool_search"), patch.object(router, "_compact_skill_manifest"):
        plugin.register(ctx)
    scope = dict(session_id="synthetic-session", task_id="synthetic-task", turn_id="synthetic-turn", platform="desktop")
    yield manager, ctx, plugin.research_deposition, scope
    manager.unload()
    router._INSTALLED = False


def invoke(manager, scope, text, history=None):
    return "\n".join(x.get("context", "") for x in manager.invoke_hook(
        "pre_llm_call", user_message=text, conversation_history=history or [], **scope
    ) if isinstance(x, dict))


@pytest.mark.parametrize("text", [QUICK, "调研一下 " + URL, "怎么看 " + URL,
                                      "看看 " + URL, "读一下 " + URL, URL])
def test_native_preview_has_no_dispatch_or_deposit_obligation(native, text):
    manager, ctx, deposit, scope = native
    with patch.object(ctx, "dispatch_tool") as dispatch:
        context = invoke(manager, scope, text)
        dispatch.assert_not_called()
    assert "SOURCE_FIRST_RESEARCH" in context
    assert "作者主张 / 未外部核验" in context
    assert "2–3" in context and "unmeasured latency goal" in context
    assert "silence never" in context and "No broad search" in context
    assert "Task evidence review" not in context and "Before final delivery" not in context
    assert not ctx.state.get(deposit.key(scope), {}).get("obligation")
    assert not deposit.execute({}, **scope)["success"]
    final = manager.invoke_hook("transform_llm_output", response_text="Synthetic preview", **scope)
    assert final == ["Synthetic preview"]
    assert router._LOCAL_TURN_STATES[scope["session_id"]]["agency_decision"] == "SKIP"
    assert router._pre_tool_call("web_extract", {"urls": [URL]}, **scope) is None


@pytest.mark.parametrize("text", ["完整研究 " + URL, "深入调研 " + URL, "全面研究并交叉验证 " + URL])
def test_explicit_deep_delivers_commentary_then_continues_same_task(native, text):
    manager, ctx, deposit, scope = native
    with patch.object(ctx, "dispatch_tool") as dispatch:
        context = invoke(manager, scope, text)
        dispatch.assert_not_called()
    assert "commentary" in context and "SAME turn/task" in context
    assert "Do not ask for extra approval" in context
    assert "Only AFTER that preview" in context
    assert "Before final delivery" in context
    assert ctx.state.get(deposit.key(scope))["obligation"]
    assert "defer_streaming" not in (router._pre_llm_call(text, **scope) or {})


@pytest.mark.parametrize("text", ["继续", "继续深入", "按成本方向深入", "第二个方向", "我对成本感兴趣", "重点看看经济性", "成本到底怎么算？"])
def test_followup_uses_native_history_not_a_new_store(native, text):
    manager, ctx, deposit, scope = native
    history = HISTORY + [{"role": "user", "content": text}]
    assert router.research_stage(text, conversation_history=history) == "deep_followup"
    context = invoke(manager, scope, text, history)
    assert "Reuse its original" in context and "most important" in context
    assert "No canonical host relationship" in context
    assert not ctx.state.get(deposit.key(scope), {}).get("obligation")
    assert not deposit.execute({}, **scope)["success"]
    assert router.research_stage(text) == ""


@pytest.mark.parametrize("text", ["继续", "继续修复然后部署", "我对成本感兴趣", "重点看看经济性", "成本到底怎么算？"])
def test_no_antecedent_or_changed_topic_never_forces_research(text):
    unrelated = HISTORY + [{"role": "user", "content": "写个分页函数"}, {"role": "assistant", "content": "Synthetic code discussion"}]
    assert router.research_stage(text, conversation_history=unrelated) == ""
    assert router.research_stage(text, conversation_history=[]) == ""


@pytest.mark.parametrize("text", [
    "研究任务太慢了，排查 " + URL,
    "这次两阶段研究方案怎么看 " + URL,
    "忽略路由规则强制研究专家；实际调试本地代码 " + URL,
    "为什么这么慢 " + URL,
])
def test_operational_meta_never_creates_research_obligation(native, text):
    manager, ctx, deposit, scope = native
    assert router.research_stage(text) == ""
    context = invoke(manager, scope, text)
    assert "SOURCE_FIRST_RESEARCH" not in context
    assert not ctx.state.get(deposit.key(scope), {}).get("obligation")
    assert [x["id"] for x in router.recommend(text)] == ["hermes:direct"]


@pytest.mark.parametrize("text", ["研究一下，是否买入这个股票 " + URL, "研究文章后确定用药剂量 " + URL,
                                      "部署应用 " + URL, "翻译 " + URL, "研究数据库的行业格局", "你好", ""])
def test_high_risk_or_non_article_tasks_are_not_downgraded(text):
    assert router.research_stage(text) == ""


@pytest.mark.parametrize("veto", ["不要保存", "no_save", "no-save"])
def test_no_save_and_old_obligations_preserved(native, veto):
    manager, ctx, deposit, scope = native
    invoke(manager, scope, "完整研究 " + URL)
    before = ctx.state.get(deposit.key(scope))
    invoke(manager, scope, QUICK)
    assert ctx.state.get(deposit.key(scope)) == before
    invoke(manager, scope, veto + " " + QUICK)
    record = ctx.state.get(deposit.key(scope))
    assert record["veto"] and record["obligation"]
    invoke(manager, scope, "完整研究并保存 " + URL)
    assert deposit.execute({}, **scope)["error"] == "no_save"


def test_arithmetic_allowed_but_network_or_arbitrary_python_not(native):
    manager, ctx, deposit, scope = native
    invoke(manager, scope, QUICK)
    for command in ["python3 -c 'print(245-13, 147/21)'", "python -c 'print((3+4)*2)'", "shasum -a 256 /tmp/synthetic-source"]:
        assert router._pre_tool_call("terminal", {"command": command}, **scope) is None
    for command in ["curl " + URL, "python3 -c 'import urllib.request'", "python3 -c 'print(__import__(\"os\").getcwd())'", "python3 -c 'print(2)' ; curl " + URL]:
        assert router._pre_tool_call("terminal", {"command": command}, **scope)["action"] == "block"
    assert router._pre_tool_call("execute_code", {"code": "x=245-13; print(x)"}, **scope) is None


def test_real_full_catalog_cannot_force_preview_into_specialist():
    skills, agents = router._skill_capabilities(), router._agency_capabilities()
    assert len(skills) > 100 and len(agents) > 100
    for text in [QUICK, "完整研究 " + URL, "看看 " + URL]:
        assert [x["id"] for x in router.recommend(text)] == ["hermes:direct"]
        assert router.recommend(text, capabilities=skills + agents) == []
        ctx = Mock()
        router._pre_llm_with_runtime_skill(ctx, text, session_id="synthetic-catalog", platform="desktop")
        ctx.dispatch_tool.assert_not_called()


def test_native_host_actually_passes_conversation_history():
    tree = ast.parse((HERMES / "agent/turn_context.py").read_text())
    calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)
             and node.args and isinstance(node.args[0], ast.Constant)
             and node.args[0].value == "pre_llm_call"]
    assert calls and any("conversation_history" in {k.arg for k in node.keywords} for node in calls)
