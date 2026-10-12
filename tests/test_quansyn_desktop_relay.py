from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


MODULE_PATH = (
    Path(__file__).parents[1]
    / "agency"
    / "hermes-plugins"
    / "ai-lab-capabilities"
    / "dashboard"
    / "plugin_api.py"
)


def load_module():
    name = "quansyn_desktop_api_test"
    spec = importlib.util.spec_from_file_location(name, MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_pull_to_composer_selects_one_pending_request(monkeypatch):
    module = load_module()
    transfer_id = "qs_" + "a" * 32
    monkeypatch.setattr(module, "_owner_sender", lambda: "owner")
    monkeypatch.setattr(module, "_pending", lambda sender: [{"id": transfer_id}])
    monkeypatch.setattr(
        module,
        "_pull_one",
        lambda sender, item: {"text": "question", "blocks": [], "files": [{"path": "/tmp/input.pdf"}]},
    )

    result = module.pull_to_composer(module.PullBody())

    assert result == {
        "success": True,
        "empty": False,
        "id": transfer_id,
        "text": "question",
        "blocks": [],
        "files": [{"path": "/tmp/input.pdf"}],
    }


def test_publish_keeps_full_text_and_markdown_block_with_stable_id(monkeypatch):
    module = load_module()
    transfer_id = "qs_" + "b" * 32
    calls = []

    def request(_sender, method, path, *, payload=None, sink=None):
        del sink
        calls.append((method, path, payload))
        if method == "GET":
            return {"direction": "request", "target": "mac"}
        return {"id": "qs_" + "c" * 32}

    monkeypatch.setattr(module, "_request", request)
    first = module._publish("owner", transfer_id, "# Answer\n\n|A|B|\n|-|-|\n|1|2|", "copy")
    second = module._publish("owner", transfer_id, "# Answer\n\n|A|B|\n|-|-|\n|1|2|", "copy")

    assert first["request_id"] == second["request_id"]
    payload = calls[1][2]
    assert payload["text"].startswith("# Answer")
    assert payload["blocks"] == [{
        "kind": "markdown",
        "content": payload["text"],
        "labels": [],
        "values": [],
    }]
    assert payload["reply_to"] == transfer_id


def test_push_last_reads_latest_visible_assistant_message(monkeypatch):
    module = load_module()

    class FakeDB:
        def __init__(self, read_only=False):
            assert read_only is True

        def resolve_resume_session_id(self, session_id):
            return session_id

        def get_messages(self, *_args, **_kwargs):
            return [
                {"role": "assistant", "content": "older"},
                {"role": "assistant", "content": "hidden", "display_kind": "hidden"},
                {"role": "user", "content": "question"},
                {"role": "assistant", "display_content": "**latest**", "content": "carrier"},
            ]

        def close(self):
            pass

    monkeypatch.setitem(sys.modules, "hermes_state", types.SimpleNamespace(SessionDB=FakeDB))

    assert module._last_assistant_text("session-1") == "**latest**"


def test_owner_resolution_fails_closed_when_ambiguous(monkeypatch):
    module = load_module()
    monkeypatch.setenv("AI_LAB_LOCAL_OWNER_IDS", "owner-a,owner-b")
    monkeypatch.delenv("FEISHU_CODE_WRITE_OWNER_IDS", raising=False)

    try:
        module._owner_sender()
    except ValueError as exc:
        assert "exactly one" in str(exc)
    else:
        raise AssertionError("ambiguous owner configuration must fail closed")
