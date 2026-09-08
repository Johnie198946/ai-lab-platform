from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path


def _module():
    path = Path(__file__).parents[1] / "scripts" / "publication_release_remote.py"
    spec = importlib.util.spec_from_file_location("publication_release_remote", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _files(tmp_path: Path) -> tuple[Path, Path]:
    identity, known_hosts = tmp_path / "key", tmp_path / "known_hosts"
    identity.write_text("path-only fixture", encoding="utf-8")
    known_hosts.write_text("pinned fixture", encoding="utf-8")
    return identity, known_hosts


def test_remote_release_uses_fixed_secure_contract_and_reports_totals(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    calls = []
    replies = iter(
        [
            subprocess.CompletedProcess([], 0, '{"ok":true,"result":{"status":"ok"}}\n', ""),
            subprocess.CompletedProcess(
                [], 0,
                json.dumps({"ok": True, "result": {"items": [
                    {"state": "published"}, {"state": "published"},
                    {"state": "scheduled"}, {"state": "blocked"},
                    {"state": "failed"}, {"state": "withdrawn"},
                ], "missing": [{"series_id": "ai-history"}]}}) + "\n",
                "",
            ),
        ]
    )

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return next(replies)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    assert capsys.readouterr().out == '{"blocked":1,"failed":1,"missing":1,"published":2,"scheduled":1}\n'
    assert len(calls) == 2
    for args, kwargs in calls:
        assert args[:3] == ["ssh", "-F", "/dev/null"]
        assert ["-o", "BatchMode=yes"] == args[3:5]
        assert "IdentitiesOnly=yes" in args and "StrictHostKeyChecking=yes" in args
        assert f"UserKnownHostsFile={known_hosts.resolve()}" in args
        assert args[args.index("-i") + 1] == str(identity.resolve())
        assert args[-2] == "admin@120.24.248.58"
        assert "root@" not in " ".join(args)
        assert "sudo -n docker compose -p ai-lab-platform -f /opt/ai-lab-platform/docker-compose.yml" in args[-1]
        assert "python /app/scripts/publication_operator.py --root /app/data/runtime/publications" in args[-1]
        assert kwargs["capture_output"] is True and kwargs["check"] is False
    assert calls[0][0][-1].endswith(" release-due")
    assert calls[1][0][-1].endswith(" status")
    assert "path-only fixture" not in " ".join(calls[0][0])


def test_attention_exit_is_preserved_after_status_readback(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    replies = iter([
        subprocess.CompletedProcess([], 3, '{"ok":false,"result":{"status":"attention_required"}}\n', ""),
        subprocess.CompletedProcess([], 0, '{"ok":true,"result":{"items":[{"state":"blocked"}],"missing":[{}]}}\n', ""),
    ])
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: calls.append(args) or next(replies))

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 3
    assert len(calls) == 2
    assert capsys.readouterr().out == '{"blocked":1,"failed":0,"missing":1,"published":0,"scheduled":0}\n'


def test_missing_trust_files_fail_closed_before_ssh(monkeypatch, tmp_path, capsys):
    module = _module()
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: calls.append(args))

    assert module.main([
        "--identity-file", str(tmp_path / "missing-key"),
        "--known-hosts-file", str(tmp_path / "missing-hosts"),
    ]) == 1
    captured = capsys.readouterr()
    assert captured.out == '{"blocked":0,"failed":1,"missing":0,"published":0,"scheduled":0}\n'
    assert "must be an existing file" in captured.err
    assert calls == []


def test_malformed_release_preserves_its_exit_code_and_still_reads_status(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    replies = iter([
        subprocess.CompletedProcess([], 2, "not-json\n", ""),
        subprocess.CompletedProcess([], 0, '{"ok":true,"result":{"items":[],"missing":[]}}\n', ""),
    ])
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda *args, **kwargs: calls.append(args) or next(replies))

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 2
    assert len(calls) == 2
    assert json.loads(capsys.readouterr().out)["failed"] == 1
