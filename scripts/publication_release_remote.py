#!/usr/bin/env python3
"""Release due publications on production from a trusted local Mac."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


TARGET = "admin@120.24.248.58"
OPERATOR = (
    "sudo", "-n", "docker", "compose", "-p", "ai-lab-platform",
    "-f", "/opt/ai-lab-platform/docker-compose.yml", "exec", "-T", "api",
    "python", "/app/scripts/publication_operator.py",
    "--root", "/app/data/runtime/publications",
)
STATES = ("published", "scheduled", "blocked", "failed")


def _args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--identity-file",
        default=os.environ.get(
            "AI_LAB_PUBLICATION_SSH_KEY", "~/.ssh/ai_lab_publication_ed25519"
        ),
    )
    parser.add_argument(
        "--known-hosts-file",
        default=os.environ.get(
            "AI_LAB_PUBLICATION_KNOWN_HOSTS", "~/.ssh/known_hosts"
        ),
    )
    return parser.parse_args(argv)


def _path(value: str, label: str) -> str:
    path = Path(value).expanduser().resolve()
    if not path.is_file():
        raise ValueError(f"{label} must be an existing file")
    return str(path)


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


def _json(stdout: str, label: str) -> dict:
    lines = [line for line in stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise ValueError(f"{label} returned an invalid JSON envelope")
    value = json.loads(lines[0])
    if not isinstance(value, dict) or not isinstance(value.get("result"), dict):
        raise ValueError(f"{label} returned an invalid JSON envelope")
    return value


def _command(action: str) -> str:
    return " ".join((*OPERATOR, action))


def main(argv: list[str] | None = None) -> int:
    summary = {state: 0 for state in STATES}
    summary["missing"] = 0
    release: subprocess.CompletedProcess[str] | None = None
    exit_code = 1
    try:
        args = _args(argv)
        identity = _path(args.identity_file, "identity file")
        known_hosts = _path(args.known_hosts_file, "known-hosts file")
        release = _ssh(identity, known_hosts, _command("release-due"))
        status = _ssh(identity, known_hosts, _command("status"))
        exit_code = release.returncode or status.returncode
        release_payload = _json(release.stdout, "release-due")
        status_payload = _json(status.stdout, "status")
        if release.returncode not in {0, 3} or status.returncode != 0:
            raise ValueError("remote operator command failed")
        expected_ok = release.returncode == 0
        if release_payload.get("ok") is not expected_ok:
            raise ValueError("release-due exit code disagrees with its payload")
        result = status_payload["result"]
        items, missing = result.get("items"), result.get("missing")
        if status_payload.get("ok") is not True or not isinstance(items, list) or not isinstance(missing, list):
            raise ValueError("status returned an invalid result")
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("state"), str):
                raise ValueError("status returned an invalid item")
            if item["state"] in summary:
                summary[item["state"]] += 1
        summary["missing"] = len(missing)
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError) as exc:
        summary["failed"] += 1
        print(f"publication release failed: {exc}", file=sys.stderr)
        if release is not None and release.returncode:
            exit_code = release.returncode
    print(json.dumps(summary, sort_keys=True, separators=(",", ":")))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
