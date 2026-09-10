from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

import pytest


DAY = "2026-09-10"


def _module():
    path = Path(__file__).parents[1] / "scripts" / "publication_release_remote.py"
    spec = importlib.util.spec_from_file_location("publication_release_remote", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module._today = lambda: DAY
    return module


def _files(tmp_path: Path) -> tuple[Path, Path]:
    identity, known_hosts = tmp_path / "key", tmp_path / "known_hosts"
    identity.write_text("path-only fixture", encoding="utf-8")
    known_hosts.write_text("pinned fixture", encoding="utf-8")
    identity.chmod(0o600)
    known_hosts.chmod(0o600)
    return identity, known_hosts


def _item(publication_id: str, series_id: str, day: str, state: str, reasons=(), *, edition=1, edition_id=None):
    return {
        "edition_id": edition_id or f"edition-{publication_id}-{edition}",
        "publication_id": publication_id,
        "series_id": series_id,
        "issue_date": day,
        "edition": edition,
        "state": state,
        "blocked_reasons": list(reasons),
        "body": "must never be emitted",
        "content_hash": "private-metadata",
    }


def _status(items=(), missing=(), *, wrapped=True, pretty=False):
    result = {"items": list(items), "missing": list(missing)}
    payload = {"ok": True, "result": result} if wrapped else {"ok": True, **result, "counts": {"ignored": 1}}
    return subprocess.CompletedProcess([], 0, json.dumps(payload, indent=2 if pretty else None) + "\n", "")


def _release(code=0, *, wrapped=True, **changes):
    result = {
        "status": "ok" if code == 0 else "attention_required",
        "released": ["edition-new"] if code == 3 else [],
        "blocked": [{"edition_id": "edition-blocked", "reasons": ["review_missing"]}] if code == 3 else [],
        "missing": [{
            "series_id": "ai-practice", "series_title": "Practice",
            "issue_date": DAY, "status": "overdue_missing",
        }] if code == 3 else [],
        "superseded": [],
        "at": "2026-09-10T12:00:00+08:00",
    }
    result.update(changes)
    payload = {"ok": code == 0, "result": result} if wrapped else result
    return subprocess.CompletedProcess([], code, json.dumps(payload) + "\n", "")


def _run(module, monkeypatch, replies):
    calls = []
    iterator = iter(replies)

    def run(*args, **kwargs):
        calls.append((args[0], kwargs))
        reply = next(iterator)
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(module.subprocess, "run", run)
    return calls


def test_release_uses_secure_fixed_contract_and_reports_new_and_today_counts(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    historical = _item("historical", "ai-history", "2026-09-08", "published")
    history = _item("today-history", "ai-history", DAY, "published")
    practice = _item("today-practice", "ai-practice", DAY, "published")
    calls = _run(module, monkeypatch, [
        _status([historical]),
        _release(released=[history["edition_id"], practice["edition_id"]]),
        _status([historical, history, practice], wrapped=False, pretty=True),
    ])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["observed_published_publication_id_delta"] == ["today-history", "today-practice"]
    assert summary["released_edition_ids"] == [history["edition_id"], practice["edition_id"]]
    assert summary["today"] == {
        "date": DAY, "expected": 2, "published": 2,
        "by_series": {"ai-history": 1, "ai-practice": 1},
    }
    assert summary["totals"] == {
        "blocked": 0, "draft": 0, "missing": 0, "published": 3,
        "scheduled": 0, "staged": 0, "withdrawn": 0,
    }
    assert "must never be emitted" not in json.dumps(summary)
    assert "private-metadata" not in json.dumps(summary)
    assert [call[0][-1].rsplit(" ", 1)[-1] for call in calls] == ["status", "release-due", "status"]
    for args, kwargs in calls:
        assert args[:3] == ["ssh", "-F", "/dev/null"]
        assert "BatchMode=yes" in args and "IdentitiesOnly=yes" in args and "StrictHostKeyChecking=yes" in args
        assert f"UserKnownHostsFile={known_hosts.resolve()}" in args
        assert args[args.index("-i") + 1] == str(identity.resolve())
        assert args[-2] == "deploy@120.24.248.58"
        assert "root@" not in " ".join(args) and "admin@" not in " ".join(args)
        assert kwargs["capture_output"] is True and kwargs["check"] is False
    assert "path-only fixture" not in " ".join(calls[0][0])


def test_partial_attention_exit3_accepts_result_only_release_and_preserves_raw_issues(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    blocked = _item("blocked", "ai-practice", DAY, "blocked", ["review_missing_or_hash_mismatch"])
    missing = [{"series_id": "ai-practice", "issue_date": DAY, "status": "overdue_blocked"}]
    calls = _run(module, monkeypatch, [_status([]), _release(3, wrapped=False), _status([_item("new", "ai-history", DAY, "published"), blocked], missing)])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 3
    summary = json.loads(capsys.readouterr().out)
    assert len(calls) == 3
    assert summary["observed_published_publication_id_delta"] == ["new"]
    assert summary["released_edition_ids"] == ["edition-new"]
    assert summary["issues"]["blocked"] == [{
        "publication_id": "blocked", "series_id": "ai-practice", "issue_date": DAY,
        "state": "blocked", "blocked_reasons": ["review_missing_or_hash_mismatch"],
    }]
    assert summary["issues"]["missing"] == missing


def test_release_zero_with_blocked_or_missing_status_fails_attention(monkeypatch, tmp_path):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    blocked = _item("blocked", "anthropic-originals", "2026-01-20", "blocked", ["review_missing"])
    missing = [{"series_id": "ai-practice", "issue_date": DAY, "status": "overdue_missing"}]
    _run(module, monkeypatch, [_status([]), _release(0), _status([blocked], missing)])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 3


def test_status_only_never_calls_release_due(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    calls = _run(module, monkeypatch, [_status([
        _item("history", "ai-history", DAY, "published"),
        _item("practice", "ai-practice", DAY, "published"),
    ])])

    assert module.main(["--status-only", "--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    assert len(calls) == 1 and calls[0][0][-1].endswith(" status")
    summary = json.loads(capsys.readouterr().out)
    assert summary["observed_published_publication_id_delta"] == "unknown"
    assert summary["released_edition_ids"] == []


def test_default_path_only_config_is_used_and_must_be_restrictive(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    config = tmp_path / ".hermes/config/publication-transport.json"
    config.parent.mkdir(parents=True)
    config.write_text(json.dumps({"identity_file": str(identity), "known_hosts_file": str(known_hosts)}), encoding="utf-8")
    config.chmod(0o600)
    monkeypatch.setenv("HOME", str(tmp_path))
    calls = _run(module, monkeypatch, [_status([
        _item("history", "ai-history", DAY, "published"), _item("practice", "ai-practice", DAY, "published")
    ])])

    assert module.main(["--status-only"]) == 0
    assert calls[0][0][calls[0][0].index("-i") + 1] == str(identity.resolve())
    config.chmod(0o644)
    calls.clear()
    assert module.main(["--status-only"]) == 1
    assert calls == []
    assert "owner-controlled secure file" in capsys.readouterr().err


def test_missing_trust_files_fail_closed_before_ssh(monkeypatch, tmp_path, capsys):
    module = _module()
    calls = _run(module, monkeypatch, [])

    assert module.main([
        "--identity-file", str(tmp_path / "missing-key"),
        "--known-hosts-file", str(tmp_path / "missing-hosts"),
    ]) == 1
    captured = capsys.readouterr()
    assert "must be an existing secure file" in captured.err
    assert calls == []
    assert set(json.loads(captured.out)["totals"].values()) == {"unknown"}


@pytest.mark.parametrize("release_stdout", [
    "not-json\n",
    json.dumps({"ok": True, "result": {"status": "ok"}, "status": "attention_required"}) + "\n",
    json.dumps({"ok": False, "result": {"status": "ok", "released": [], "blocked": [], "missing": []}}) + "\n",
])
def test_malformed_or_conflicting_release_fails_closed(monkeypatch, tmp_path, release_stdout):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    invalid = subprocess.CompletedProcess([], 0, release_stdout, "")
    calls = _run(module, monkeypatch, [_status([]), invalid, _status([])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 1
    assert len(calls) == 3


def test_arbitrary_nonzero_release_is_never_swallowed_and_still_reads_status(monkeypatch, tmp_path):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    failed = subprocess.CompletedProcess([], 2, "not-json\n", "")
    calls = _run(module, monkeypatch, [_status([]), failed, _status([])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 2
    assert len(calls) == 3 and calls[-1][0][-1].endswith(" status")


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("release-due", 120),
    OSError("transport unavailable"),
])
def test_release_transport_failure_still_reads_and_reports_post_status(monkeypatch, tmp_path, capsys, failure):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history = _item("history", "ai-history", DAY, "published")
    practice = _item("practice", "ai-practice", DAY, "published")
    calls = _run(module, monkeypatch, [_status([]), failure, _status([history, practice])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 1
    summary = json.loads(capsys.readouterr().out)
    assert len(calls) == 3 and calls[-1][0][-1].endswith(" status")
    assert summary["totals"]["published"] == 2
    assert summary["observed_published_publication_id_delta"] == ["history", "practice"]
    assert summary["released_edition_ids"] == "unknown"


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired("status", 120),
    OSError("readback unavailable"),
])
def test_release_exit3_survives_failed_post_status_and_reports_unknown(monkeypatch, tmp_path, capsys, failure):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    calls = _run(module, monkeypatch, [_status([]), _release(3), failure])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 3
    summary = json.loads(capsys.readouterr().out)
    assert len(calls) == 3
    assert set(summary["totals"].values()) == {"unknown"}
    assert summary["released_edition_ids"] == ["edition-new"]


def test_malformed_release_keeps_truthful_post_status_totals(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history = _item("history", "ai-history", DAY, "published")
    practice = _item("practice", "ai-practice", DAY, "published")
    malformed = subprocess.CompletedProcess([], 2, "not-json\n", "private stderr")
    _run(module, monkeypatch, [_status([]), malformed, _status([history, practice])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 2
    summary = json.loads(capsys.readouterr().out)
    assert summary["totals"]["published"] == 2
    assert summary["observed_published_publication_id_delta"] == ["history", "practice"]
    assert summary["released_edition_ids"] == "unknown"


@pytest.mark.parametrize("change", [
    {"state": "NOT_A_STATE"},
    {"publication_id": ""},
    {"edition_id": ""},
    {"issue_date": "2026-99-10"},
])
def test_invalid_status_semantics_prevent_release(monkeypatch, tmp_path, capsys, change):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    invalid = {**_item("history", "ai-history", DAY, "published"), **change}
    calls = _run(module, monkeypatch, [_status([invalid])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 1
    assert len(calls) == 1 and calls[0][0][-1].endswith(" status")
    assert set(json.loads(capsys.readouterr().out)["totals"].values()) == {"unknown"}


def test_duplicate_editions_and_conflicting_published_rows_are_rejected(monkeypatch, tmp_path):
    module = _module()
    duplicate = _item("history", "ai-history", DAY, "published")
    with pytest.raises(ValueError, match="duplicate edition IDs"):
        module._status(_status([duplicate, duplicate]).stdout, 0)
    with pytest.raises(ValueError, match="conflicting published editions"):
        module._status(_status([
            duplicate,
            _item("history", "ai-history", DAY, "published", edition=2),
        ]).stdout, 0)


def test_historical_withdrawn_edition_may_share_publication_id(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history_old = _item("history", "ai-history", DAY, "withdrawn", edition=1)
    history_new = _item("history", "ai-history", DAY, "published", edition=2)
    practice = _item("practice", "ai-practice", DAY, "published")
    _run(module, monkeypatch, [_status([history_old, history_new, practice])])

    assert module.main(["--status-only", "--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["totals"]["withdrawn"] == 1
    assert summary["totals"]["published"] == 2


def test_daily_series_requires_exactly_one_each_not_aggregate_two(monkeypatch, tmp_path):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    _run(module, monkeypatch, [_status([
        _item("history-one", "ai-history", DAY, "published"),
        _item("history-two", "ai-history", DAY, "published"),
    ])])

    assert module.main(["--status-only", "--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 3


@pytest.mark.parametrize("contradiction", [
    {"blocked": [{"edition_id": "edition-blocked", "reasons": ["review_missing"]}]},
    {"missing": [{"series_id": "ai-practice", "series_title": "Practice", "issue_date": DAY, "status": "overdue_missing"}]},
])
def test_success_release_rejects_blocked_or_overdue_missing(monkeypatch, tmp_path, contradiction):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history = _item("history", "ai-history", DAY, "published")
    practice = _item("practice", "ai-practice", DAY, "published")
    _run(module, monkeypatch, [_status([]), _release(**contradiction), _status([history, practice])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 1


def test_success_release_allows_nonoverdue_missing(monkeypatch, tmp_path):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history = _item("history", "ai-history", DAY, "published")
    practice = _item("practice", "ai-practice", DAY, "published")
    missing = [{"series_id": "ai-practice", "series_title": "Practice", "issue_date": DAY, "status": "missing"}]
    _run(module, monkeypatch, [_status([]), _release(missing=missing), _status([history, practice])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0


@pytest.mark.parametrize("change", [
    {"released": [""]},
    {"released": ["edition-same", "edition-same"]},
    {"released": ["edition-same"], "superseded": ["edition-same"]},
    {"blocked": [
        {"edition_id": "edition-same", "reasons": ["review_missing"]},
        {"edition_id": "edition-same", "reasons": ["rights_expired"]},
    ]},
])
def test_release_receipt_rejects_empty_duplicate_or_conflicting_edition_ids(change):
    module = _module()
    with pytest.raises(ValueError, match="invalid result"):
        module._release(_release(**change).stdout, 0)


def test_authoritative_release_editions_are_separate_from_observed_publication_delta(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    old = _item("history", "ai-history", DAY, "published", edition=1)
    upgraded = _item("history", "ai-history", DAY, "published", edition=2)
    withdrawn = {**old, "state": "withdrawn"}
    practice = _item("practice", "ai-practice", DAY, "published")
    _run(module, monkeypatch, [
        _status([old, practice]),
        _release(released=[upgraded["edition_id"]]),
        _status([withdrawn, upgraded, practice]),
    ])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["released_edition_ids"] == [upgraded["edition_id"]]
    assert summary["observed_published_publication_id_delta"] == []


def test_observed_delta_is_not_attributed_to_empty_release_receipt(monkeypatch, tmp_path, capsys):
    module = _module()
    identity, known_hosts = _files(tmp_path)
    history = _item("history", "ai-history", DAY, "published")
    practice = _item("practice", "ai-practice", DAY, "published")
    _run(module, monkeypatch, [_status([]), _release(), _status([history, practice])])

    assert module.main(["--identity-file", str(identity), "--known-hosts-file", str(known_hosts)]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["released_edition_ids"] == []
    assert summary["observed_published_publication_id_delta"] == ["history", "practice"]
