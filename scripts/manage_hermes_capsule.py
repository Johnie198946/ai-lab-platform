#!/usr/bin/env python3
"""Backup or restore one hashed Hermes user-state capsule."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.services.tenant_hermes_sandbox import (
    backup_sandbox_capsule,
    ensure_tenant_sandbox,
    namespace,
    restore_sandbox_capsule,
    sandbox_root,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("backup", "restore"))
    parser.add_argument("--tenant-key", required=True)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--generation", required=True, type=int)
    parser.add_argument("--root", type=Path, default=None)
    args = parser.parse_args(argv)
    root = args.root or sandbox_root()
    tenant_ns, user_ns = namespace(args.tenant_key), namespace(args.user_id)
    if args.action == "backup":
        result = backup_sandbox_capsule(
            ensure_tenant_sandbox(
                tenant_key=args.tenant_key, user_id=args.user_id, root=root,
            ),
            args.archive,
            generation=args.generation,
        )
    else:
        destination = root / "tenants" / tenant_ns / "users" / user_ns
        destination.parent.mkdir(parents=True, exist_ok=True)
        result = restore_sandbox_capsule(
            args.archive,
            destination,
            tenant_namespace=tenant_ns,
            user_namespace=user_ns,
            expected_generation=args.generation,
        )
    print(json.dumps({
        "status": "ok",
        "action": args.action,
        "generation": result["generation"],
        "files": len(result["files"]),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
