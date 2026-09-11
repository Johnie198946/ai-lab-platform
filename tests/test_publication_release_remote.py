"""No live SSH; verify the legacy issuer plus opt-in fail-closed relay."""
import json
import subprocess

import pytest
from scripts import publication_release_remote as release
from scripts import publication_editorial_remote as editorial


@pytest.mark.parametrize("parser", [release._status, release._release])
@pytest.mark.parametrize("code", [1, 2, 255])
def test_transport_error_is_checked_before_json(parser, code):
    with pytest.raises(ValueError, match=f"command failed.*{code}"):
        parser("", code)


def fake_transport(monkeypatch):
    monkeypatch.delenv("AI_LAB_PUBLICATION_EDITORIAL_ROOT", raising=False)
    monkeypatch.setattr(release, "_trust", lambda _: ("TEST-ONLY", "TEST-ONLY"))
    calls = []
    def ssh(identity, hosts, command):
        action = command.split()[-1]
        calls.append(action)
        if action == "status":
            result = {"items": [], "missing": []}
        else:
            result = {"status": "ok", "released": [], "blocked": [], "superseded": [], "missing": [], "at": "2026-09-11T12:00:00+08:00"}
        return subprocess.CompletedProcess([], 0, json.dumps({"ok": True, "result": result}), "")
    monkeypatch.setattr(release, "_ssh", ssh)
    return calls


def test_legacy_no_config_never_calls_editorial(monkeypatch, capsys):
    calls = fake_transport(monkeypatch)
    monkeypatch.setattr(editorial, "finalize", lambda *a: pytest.fail("legacy must not finalize"))
    assert release.main([]) == 3  # No synthetic daily editions in this fixture.
    assert calls == ["status", "release-due", "status"]
    assert json.loads(capsys.readouterr().out)["released_edition_ids"] == []


def test_opt_in_finalizes_before_any_release(monkeypatch):
    calls = fake_transport(monkeypatch)
    monkeypatch.setattr(editorial, "finalize", lambda *a: calls.append("finalize") or {"items": []})
    assert release.main(["--editorial-root", "/TEST-ONLY"]) == 3
    assert calls == ["finalize", "status", "release-due", "status"]


def test_opt_in_error_prevents_release_and_reports_unknown(monkeypatch, capsys):
    calls = fake_transport(monkeypatch)
    def fail(*a): raise ValueError("TEST readback missing")
    monkeypatch.setattr(editorial, "finalize", fail)
    monkeypatch.setenv("AI_LAB_PUBLICATION_EDITORIAL_ROOT", "/TEST-ONLY")
    assert release.main([]) == 1
    assert calls == []
    output = capsys.readouterr()
    assert "readback missing" in output.err
    assert json.loads(output.out)["released_edition_ids"] == "unknown"


def test_status_only_never_finalizes_even_if_configured(monkeypatch):
    calls = fake_transport(monkeypatch)
    monkeypatch.setattr(editorial, "finalize", lambda *a: pytest.fail("status-only must not write"))
    assert release.main(["--status-only", "--editorial-root", "/TEST-ONLY"]) == 3
    assert calls == ["status"]
