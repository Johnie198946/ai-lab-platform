#!/usr/bin/env python3
"""Pull a frozen cloud complaint digest, send via local Hermes, then ACK."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import hmac
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any

DEFAULT_TARGET = "feedback-digest@120.24.248.58"
LOCK_PATH = os.path.expanduser("~/.hermes/run/local-feedback-digest.lock")


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def _remote(command: list[str]) -> dict[str, Any]:
    remote_command = "feedback-digest " + " ".join(
        shlex.quote(part) for part in command
    )
    proc = subprocess.run(
        [
            "ssh",
            "-o", "BatchMode=yes",
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=yes",
            "--", DEFAULT_TARGET, remote_command,
        ],
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"remote digest command failed ({proc.returncode})")
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("remote digest command returned no JSON")
    return json.loads(lines[-1])


def main() -> int:
    args = _args()
    os.makedirs(os.path.dirname(LOCK_PATH), mode=0o700, exist_ok=True)
    lock = open(LOCK_PATH, "a+", encoding="utf-8")
    try:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return 0
    prepared = _remote(["prepare"])
    status = prepared.get("status")
    if status in {"empty", "delivered", "too_early", "locked"}:
        return 0
    if status != "prepared":
        raise RuntimeError(f"unexpected prepare status: {status}")
    digest_id = str(prepared.get("digest_id") or "")
    payload_hash = str(prepared.get("payload_hash") or "")
    content = str(prepared.get("content") or "")
    title = str(prepared.get("title") or "产品抱怨日报")
    if not re.fullmatch(r"feedback-\d{4}-\d{2}-\d{2}", digest_id):
        raise RuntimeError("invalid digest ID from cloud")
    if not re.fullmatch(r"[0-9a-f]{64}", payload_hash):
        raise RuntimeError("invalid payload hash from cloud")
    if not content or digest_id not in content:
        raise RuntimeError("invalid digest payload from cloud")
    actual_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(actual_hash, payload_hash):
        raise RuntimeError("digest payload hash mismatch")
    if args.dry_run:
        print(json.dumps(prepared, ensure_ascii=False))
        return 0
    hermes = shutil.which("hermes")
    if not hermes:
        raise RuntimeError("hermes CLI not found")
    sent = subprocess.run(
        [hermes, "send", "--to", "feishu", "--subject", title, "--file", "-", "--json"],
        input=content,
        text=True,
        capture_output=True,
        timeout=90,
        check=False,
    )
    try:
        send_result = json.loads(sent.stdout)
    except (TypeError, json.JSONDecodeError):
        send_result = {}
    if sent.returncode != 0 or send_result.get("success") is not True:
        raise RuntimeError("local Hermes Feishu delivery failed")
    acknowledged = _remote(["ack", digest_id, payload_hash])
    if acknowledged.get("status") != "delivered":
        raise RuntimeError(f"cloud ACK failed: {acknowledged.get('status')}")
    print(f"DELIVERED {digest_id}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"feedback digest delivery error: {exc}", file=sys.stderr)
        raise SystemExit(1)
