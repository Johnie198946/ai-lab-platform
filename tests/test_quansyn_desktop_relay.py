from __future__ import annotations

import importlib.util
import json
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


def test_dashboard_manifest_declares_hidden_api_plugin():
    dashboard = MODULE_PATH.parent
    manifest = json.loads((dashboard / "manifest.json").read_text())

    assert manifest["name"] == "ai-lab-capabilities"
    assert manifest["api"] == "plugin_api.py"
    assert manifest["tab"] == {"hidden": True}
    assert (dashboard / manifest["entry"]).is_file()


def test_pull_all_pending_and_include_paths(monkeypatch):
    module = load_module()
    monkeypatch.setattr(module, "_owner_sender", lambda: "owner")
    monkeypatch.setattr(module, "_pending", lambda sender: [{"id": "one"}, {"id": "two"}])
    monkeypatch.setattr(module, "_pull_one", lambda sender, ident: {
        "id": ident, "text": ident, "files": [{"name": "input.pdf", "path": "/tmp/input.pdf"}]})
    result = module.pull_to_composer(module.PullBody())
    assert [row["id"] for row in result["items"]] == ["one", "two"]
    assert result["text"].count("/tmp/input.pdf") == 2


def test_desktop_has_no_binding_and_intercepts_commands():
    source = (MODULE_PATH.parent.parent / "desktop" / "plugin.js").read_text()
    assert "ACTIVE_KEY" not in source
    assert "transfer_id:" not in source
    assert "activeForSession" not in source
    assert "/desktop/push-recent" in source
    assert "/desktop/pull-presented" in source
    assert source.index("insertIntoComposer(row.text)") < source.index("'/desktop/pull-presented'")
    assert "ai_lab_execute" not in source


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


def test_pending_pagination_limits_and_all_pages(monkeypatch):
    import pytest
    module = load_module()
    pages = iter([{'items': [{'id': 'one'}], 'next': 'next'}, {'items': [{'id': 'two'}]}])
    monkeypatch.setattr(module, '_request', lambda *a, **kw: next(pages))
    assert [r['id'] for r in module._pending('owner')] == ['one', 'two']
    monkeypatch.setattr(module, '_request', lambda *a, **kw: {'items': [{}] * 101})
    with pytest.raises(ValueError, match='exceeds'):
        module._pending('owner')


def test_pull_attachment_failure_never_imports_and_reuses_claim(monkeypatch, tmp_path):
    import hashlib
    import pytest
    module = load_module()
    ident = 'qs_' + 'a' * 32
    monkeypatch.setattr(module, 'get_hermes_home', lambda: tmp_path)
    calls = []
    def request(sender, method, path, **kw):
        calls.append((path, kw))
        if method == 'GET' and path.startswith('/transfers/'):
            return {'direction': 'request', 'target': 'mac', 'revision': 1, 'text': 'draft',
                    'files': [{'artifact_id': 'ga_' + 'b' * 32, 'filename': 'test.txt',
                               'content_hash': hashlib.sha256(b'expected').hexdigest()}]}
        if path.endswith('/claim'):
            return {'revision': 2}
        if path.startswith('/files/'):
            kw['sink'].write(b'wrong')
            return hashlib.sha256(b'wrong').hexdigest()
        raise AssertionError('must not import failed attachments')
    monkeypatch.setattr(module, '_request', request)
    for _ in range(2):
        with pytest.raises(ValueError, match='hash mismatch'):
            module._pull_one('owner', ident)
    claims = [kw['payload']['claim'] for path, kw in calls if path.endswith('/claim')]
    assert len(claims) == 2 and claims[0] == claims[1]
    assert not module._read_state('owner', ident).get('imported')


def test_desktop_recent_reads_exact_current_session(monkeypatch, tmp_path):
    module = load_module()
    seen = []
    class FakeDB:
        def __init__(self, read_only):
            assert read_only
        def get_messages(self, session, **kw):
            seen.append(session)
            return []
        def close(self):
            pass
    monkeypatch.setitem(sys.modules, 'hermes_state', types.SimpleNamespace(SessionDB=FakeDB))
    monkeypatch.setattr(module, '_owner_sender', lambda: 'owner')
    monkeypatch.setattr(module, 'get_hermes_home', lambda: tmp_path)
    assert module.push_recent_session(module.RecentBody(session_id='focused-current'))['noop']
    assert seen == ['focused-current']
