#!/usr/bin/env python3
"""Release due publications on production from a trusted local Mac."""

from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo


TARGET = "deploy@120.24.248.58"
OPERATOR = (
    "sudo", "-n", "docker", "compose", "-p", "ai-lab-platform",
    "-f", "/opt/ai-lab-platform/docker-compose.yml", "exec", "-T", "api",
    "python", "/app/scripts/publication_operator.py",
    "--root", "/app/data/runtime/publications",
)
DAILY_SERIES = ("ai-history", "ai-practice")
STATES = ("draft", "staged", "scheduled", "blocked", "published", "withdrawn")
SAFE_ID = re.compile(r"^[a-z0-9][a-z0-9._:-]{1,159}$")
UNKNOWN = "unknown"
SHANGHAI = ZoneInfo("Asia/Shanghai")


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--identity-file")
    parser.add_argument("--known-hosts-file")
    parser.add_argument("--status-only", action="store_true")
    return parser.parse_args(argv)


def _secure_file(value: str, label: str, *, private: bool) -> str:
    path = Path(value).expanduser()
    try:
        info = path.stat()
    except OSError as exc:
        raise ValueError(f"{label} must be an existing secure file") from exc
    forbidden = 0o077 if private else 0o022
    if path.is_symlink() or not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) & forbidden:
        raise ValueError(f"{label} must be an owner-controlled secure file")
    return str(path.resolve())


def _trust(args: argparse.Namespace) -> tuple[str, str]:
    config_path = Path("~/.hermes/config/publication-transport.json").expanduser()
    config: dict[str, str] = {}
    identity = args.identity_file or os.environ.get("AI_LAB_PUBLICATION_SSH_KEY")
    known_hosts = args.known_hosts_file or os.environ.get("AI_LAB_PUBLICATION_KNOWN_HOSTS")
    if (not identity or not known_hosts) and config_path.exists():
        config_file = _secure_file(str(config_path), "transport config", private=True)
        value = json.loads(Path(config_file).read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or set(value) - {"identity_file", "known_hosts_file"}
            or any(not isinstance(item, str) or not item for item in value.values())
        ):
            raise ValueError("transport config must contain path-only trust settings")
        config = value
    identity = identity or config.get("identity_file", "~/.ssh/ai_lab_publication_ed25519")
    known_hosts = known_hosts or config.get("known_hosts_file", "~/.ssh/known_hosts")
    return (
        _secure_file(identity, "identity file", private=True),
        _secure_file(known_hosts, "known-hosts file", private=False),
    )


def _ssh(identity: str, known_hosts: str, command: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "ssh", "-F", "/dev/null",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-i", identity,
            "--", TARGET, command,
        ],
        text=True,
        capture_output=True,
        timeout=120,
        check=False,
    )


def _json(stdout: str, label: str) -> tuple[bool | None, dict]:
    value = json.loads(stdout)
    if not isinstance(value, dict):
        raise ValueError(f"{label} returned an invalid JSON envelope")
    ok = value.get("ok")
    if ok is not None and not isinstance(ok, bool):
        raise ValueError(f"{label} returned an invalid ok value")
    if "result" in value:
        if not isinstance(value["result"], dict) or set(value) != {"ok", "result"}:
            raise ValueError(f"{label} returned a conflicting JSON envelope")
        return ok, value["result"]
    return ok, {key: item for key, item in value.items() if key != "ok"}


def _status(stdout: str, returncode: int, label: str = "status") -> dict:
    ok, result = _json(stdout, label)
    if returncode != 0 or ok is not True:
        raise ValueError(f"{label} command failed")
    items, missing = result.get("items"), result.get("missing")
    if not isinstance(items, list) or not isinstance(missing, list):
        raise ValueError(f"{label} returned an invalid result")
    edition_ids: set[str] = set()
    published_ids: set[str] = set()
    for item in items:
        if (
            not isinstance(item, dict)
            or any(not _valid_id(item.get(key)) for key in ("edition_id", "publication_id", "series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("state") not in STATES
            or not isinstance(item.get("edition"), int)
            or isinstance(item.get("edition"), bool)
            or item["edition"] < 1
            or not isinstance(item.get("blocked_reasons", []), list)
            or any(not isinstance(reason, str) or not reason for reason in item.get("blocked_reasons", []))
        ):
            raise ValueError(f"{label} returned an invalid item")
        if item["edition_id"] in edition_ids:
            raise ValueError(f"{label} returned duplicate edition IDs")
        edition_ids.add(item["edition_id"])
        if item["state"] == "published":
            if item["publication_id"] in published_ids:
                raise ValueError(f"{label} returned conflicting published editions")
            published_ids.add(item["publication_id"])
    for item in missing:
        if (
            not isinstance(item, dict)
            or not _valid_id(item.get("series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("status") not in {"missing", "overdue_missing", *(f"overdue_{state}" for state in STATES)}
        ):
            raise ValueError(f"{label} returned an invalid missing issue")
    return result


def _release(stdout: str, returncode: int) -> dict:
    ok, result = _json(stdout, "release-due")
    expected_status = {0: "ok", 3: "attention_required"}.get(returncode)
    if expected_status is None:
        raise ValueError("release-due command failed")
    if ok is not None and ok != (returncode == 0):
        raise ValueError("release-due exit code disagrees with its envelope")
    if result.get("status") != expected_status:
        raise ValueError("release-due exit code disagrees with its status")
    if any(not isinstance(result.get(key), list) for key in ("released", "blocked", "superseded", "missing")):
        raise ValueError("release-due returned an invalid result")
    released, blocked, superseded, missing = (result[key] for key in ("released", "blocked", "superseded", "missing"))
    blocked_ids = [item.get("edition_id") if isinstance(item, dict) and isinstance(item.get("edition_id"), str) else None for item in blocked]
    if (
        any(not _valid_id(item) for item in [*released, *superseded])
        or len(set(released)) != len(released)
        or len(set(superseded)) != len(superseded)
        or len(set(blocked_ids)) != len(blocked)
        or set(released) & set(superseded)
        or set(released) & set(blocked_ids)
        or set(superseded) & set(blocked_ids)
        or any(
            not isinstance(item, dict)
            or not _valid_id(item.get("edition_id"))
            or not isinstance(item.get("reasons"), list)
            or not item["reasons"]
            or any(not isinstance(reason, str) or not reason for reason in item["reasons"])
            for item in blocked
        )
        or any(
            not isinstance(item, dict)
            or not _valid_id(item.get("series_id"))
            or not _valid_date(item.get("issue_date"))
            or item.get("status") not in {"missing", "overdue_missing", *(f"overdue_{state}" for state in STATES)}
            for item in missing
        )
        or not _valid_datetime(result.get("at"))
    ):
        raise ValueError("release-due returned an invalid result")
    overdue = any(item["status"].startswith("overdue_") for item in missing)
    if (returncode == 0 and (blocked or overdue)) or (returncode == 3 and not (blocked or overdue)):
        raise ValueError("release-due returned a contradictory result")
    return result


def _valid_id(value: object) -> bool:
    return isinstance(value, str) and SAFE_ID.fullmatch(value) is not None


def _valid_date(value: object) -> bool:
    try:
        return isinstance(value, str) and date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _valid_datetime(value: object) -> bool:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else None
        return parsed is not None and parsed.tzinfo is not None and parsed.utcoffset() is not None
    except ValueError:
        return False


def _command(action: str) -> str:
    return " ".join((*OPERATOR, action))


def _today() -> str:
    return datetime.now(SHANGHAI).date().isoformat()


def _summary(status: dict | None = None, before: dict | None = None) -> dict:
    day = _today()
    if status is None:
        return {
            "issues": {"blocked": UNKNOWN, "missing": UNKNOWN},
            "observed_published_publication_id_delta": UNKNOWN,
            "released_edition_ids": UNKNOWN,
            "today": {
                "date": day, "expected": len(DAILY_SERIES), "published": UNKNOWN,
                "by_series": {series: UNKNOWN for series in DAILY_SERIES},
            },
            "totals": {**{state: UNKNOWN for state in STATES}, "missing": UNKNOWN},
        }
    items, missing = status["items"], status["missing"]
    totals = {state: sum(item["state"] == state for item in items) for state in STATES}
    totals["missing"] = len(missing)
    published = {
        series: len({
            item["publication_id"] for item in items
            if item.get("state") == "published" and item.get("issue_date") == day and item.get("series_id") == series
        })
        for series in DAILY_SERIES
    }
    before_ids = {
        item["publication_id"] for item in (before or {}).get("items", []) if item.get("state") == "published"
    }
    after_ids = {item["publication_id"] for item in items if item.get("state") == "published"}
    return {
        "issues": {
            "blocked": [
                {
                    "publication_id": item["publication_id"],
                    "series_id": item["series_id"],
                    "issue_date": item["issue_date"],
                    "state": item["state"],
                    "blocked_reasons": item.get("blocked_reasons", []),
                }
                for item in items if item.get("state") in {"blocked", "failed"}
            ],
            "missing": [
                {key: item[key] for key in ("series_id", "issue_date", "status")}
                for item in missing
            ],
        },
        "observed_published_publication_id_delta": sorted(after_ids - before_ids) if before is not None else UNKNOWN,
        "released_edition_ids": UNKNOWN,
        "today": {"date": day, "expected": len(DAILY_SERIES), "published": sum(published.values()), "by_series": published},
        "totals": totals,
    }


def _attention(summary: dict) -> bool:
    totals = summary["totals"]
    return bool(totals["blocked"] or totals["missing"] or any(count != 1 for count in summary["today"]["by_series"].values()))


def main(argv: list[str] | None = None) -> int:
    summary = _summary()
    exit_code = 1
    errors: list[Exception] = []
    try:
        args = _args(argv)
        identity, known_hosts = _trust(args)
        if args.status_only:
            post_status = _ssh(identity, known_hosts, _command("status"))
            exit_code = post_status.returncode
            status = _status(post_status.stdout, post_status.returncode)
            summary = _summary(status)
            summary["released_edition_ids"] = []
        else:
            pre_status = _ssh(identity, known_hosts, _command("status"))
            exit_code = pre_status.returncode or 1
            before = _status(pre_status.stdout, pre_status.returncode, "pre-release status")
            release = None
            try:
                release = _ssh(identity, known_hosts, _command("release-due"))
                exit_code = release.returncode
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(exc)
            try:
                post_status = _ssh(identity, known_hosts, _command("status"))
                if not exit_code and post_status.returncode:
                    exit_code = post_status.returncode
                status = _status(post_status.stdout, post_status.returncode)
                summary = _summary(status, before)
            except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
                errors.append(exc)
            if release is not None:
                try:
                    receipt = _release(release.stdout, release.returncode)
                    summary["released_edition_ids"] = sorted(receipt["released"])
                except (ValueError, json.JSONDecodeError) as exc:
                    errors.append(exc)
            if errors and not exit_code:
                exit_code = 1
        if summary["totals"]["published"] != UNKNOWN and _attention(summary):
            exit_code = exit_code or 3
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        errors.append(exc)
        exit_code = exit_code or 1
    for exc in errors:
        print(f"publication release failed: {exc}", file=sys.stderr)
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
