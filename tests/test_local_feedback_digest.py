from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest


def _module():
    path = Path(__file__).parents[1] / "scripts" / "local_feedback_digest.py"
    spec = importlib.util.spec_from_file_location("local_feedback_digest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _prepared(hash_override: str | None = None) -> dict:
    content = "Digest ID: feedback-2026-08-29\n\n新增抱怨：1 条"
    return {
        "status": "prepared",
        "title": "产品抱怨日报 · 2026-08-29",
        "content": content,
        "payload_hash": hash_override or hashlib.sha256(content.encode()).hexdigest(),
        "digest_id": "feedback-2026-08-29",
    }


def test_local_worker_sends_with_hermes_then_acks(monkeypatch, tmp_path):
    module = _module()
    prepared = _prepared()
    calls: list[tuple[list[str], str | None]] = []

    def fake_run(args, **kwargs):
        calls.append((list(args), kwargs.get("input")))
        if args[0] == "ssh" and " prepare" in args[-1]:
            return subprocess.CompletedProcess(args, 0, json.dumps(prepared), "")
        if args[0] == "/usr/local/bin/hermes":
            return subprocess.CompletedProcess(args, 0, '{"success":true}', "")
        if args[0] == "ssh" and " ack " in args[-1]:
            return subprocess.CompletedProcess(
                args, 0, '{"status":"delivered","digest_id":"feedback-2026-08-29"}', ""
            )
        raise AssertionError(args)

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/local/bin/hermes")
    monkeypatch.setattr(module, "LOCK_PATH", str(tmp_path / "digest.lock"))
    monkeypatch.setattr(sys, "argv", ["local_feedback_digest.py"])
    assert module.main() == 0
    assert calls[0][0][calls[0][0].index("-i") + 1] == module.IDENTITY_PATH
    assert calls[0][0][-3:] == ["--", module.DEFAULT_TARGET, "feedback-digest prepare"]
    assert calls[1][0][1:4] == ["send", "--to", "feishu"]
    assert calls[1][1] == prepared["content"]
    assert "feedback-2026-08-29" in calls[2][0][-1]
    assert prepared["payload_hash"] in calls[2][0][-1]


def test_local_worker_never_acks_failed_feishu_send(monkeypatch, tmp_path):
    module = _module()
    prepared = _prepared()
    ssh_calls = 0

    def fake_run(args, **kwargs):
        nonlocal ssh_calls
        if args[0] == "ssh":
            ssh_calls += 1
            return subprocess.CompletedProcess(args, 0, json.dumps(prepared), "")
        return subprocess.CompletedProcess(args, 1, "", "failed")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/local/bin/hermes")
    monkeypatch.setattr(module, "LOCK_PATH", str(tmp_path / "digest.lock"))
    monkeypatch.setattr(sys, "argv", ["local_feedback_digest.py"])
    with pytest.raises(RuntimeError, match="delivery failed"):
        module.main()
    assert ssh_calls == 1


def test_local_worker_rejects_payload_hash_mismatch_before_send(monkeypatch, tmp_path):
    module = _module()
    prepared = _prepared("a" * 64)
    calls = []

    def fake_run(args, **kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args, 0, json.dumps(prepared), "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module, "LOCK_PATH", str(tmp_path / "digest.lock"))
    monkeypatch.setattr(sys, "argv", ["local_feedback_digest.py"])
    with pytest.raises(RuntimeError, match="hash mismatch"):
        module.main()
    assert len(calls) == 1


def test_forced_command_rejects_arbitrary_remote_shell():
    script = Path(__file__).parents[1] / "scripts" / "feedback_digest_forced_command.sh"
    env = dict(os.environ, SSH_ORIGINAL_COMMAND="cat /etc/shadow")
    result = subprocess.run(["/bin/sh", str(script)], env=env, text=True, capture_output=True)
    assert result.returncode == 64
    assert "denied" in result.stderr


def test_local_worker_never_acks_ambiguous_zero_exit(monkeypatch, tmp_path):
    module = _module()
    prepared = _prepared()
    ssh_calls = 0

    def fake_run(args, **kwargs):
        nonlocal ssh_calls
        if args[0] == "ssh":
            ssh_calls += 1
            return subprocess.CompletedProcess(args, 0, json.dumps(prepared), "")
        return subprocess.CompletedProcess(args, 0, '{"success":false}', "")

    monkeypatch.setattr(module.subprocess, "run", fake_run)
    monkeypatch.setattr(module.shutil, "which", lambda _name: "/usr/local/bin/hermes")
    monkeypatch.setattr(module, "LOCK_PATH", str(tmp_path / "digest.lock"))
    monkeypatch.setattr(sys, "argv", ["local_feedback_digest.py"])
    with pytest.raises(RuntimeError, match="delivery failed"):
        module.main()
    assert ssh_calls == 1


@pytest.mark.parametrize(
    "original_command",
    [
        "uname -a",
        "feedback-digest ack feedback-2026-08-29 abc;id",
        "feedback-digest prepare extra",
    ],
)
def test_forced_command_rejects_everything_outside_prepare_and_exact_ack(original_command):
    script = Path(__file__).parents[1] / "scripts" / "feedback_digest_forced_command.sh"
    env = {"PATH": "/usr/bin:/bin", "SSH_ORIGINAL_COMMAND": original_command}
    result = subprocess.run(["/bin/sh", str(script)], env=env, capture_output=True, text=True)
    assert result.returncode == 64
    assert "denied" in result.stderr or not result.stdout
