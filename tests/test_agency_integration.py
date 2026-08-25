from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from backend.api.orchestration import _agency_agent_config


ROOT = Path(__file__).resolve().parents[1]


class FakePluginContext:
    def __init__(self):
        self.tools = {}
        self.dispatched = []

    def register_tool(self, *, name, schema, handler, **metadata):
        self.tools[name] = {"schema": schema, "handler": handler, **metadata}

    def dispatch_tool(self, name, args):
        self.dispatched.append((name, args))
        return {"tool": name, "args": args}


def load_capability_plugin():
    path = ROOT / "agency/hermes-plugins/ai-lab-capabilities/__init__.py"
    spec = importlib.util.spec_from_file_location("ai_lab_capabilities_plugin", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


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


def test_installer_preserves_pre_install_plugin_config_and_adds_both_routers():
    installer = (ROOT / "scripts/install_agency_hermes.sh").read_text()
    assert 'original_config="$tmp_dir/config.before-agency.yaml"' in installer
    assert 'source = original if original and original.exists() else path' in installer
    assert '("agency-agents-router", "ai-lab-capabilities")' in installer
    assert "yaml.safe_load" in installer
