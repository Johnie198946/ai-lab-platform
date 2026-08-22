#!/usr/bin/env python3
"""Repair the explicitly approved public Token Factory knowledge projection.

The migration is intentionally allow-listed.  It does not recolor every document
that mentions xFusion, because many of those pages contain tenant-private or
entitlement-gated material.  ``--apply`` creates recoverable copies before it
changes frontmatter and rolls back the batch if any target fails.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.services.knowledge_color_projection import approve_color, restore_note


PUBLIC_TOKENFACTORY_PATHS = (
    "wiki/产品/超聚变TokenFactory算力产品体系.md",
    "wiki/产品/TokenFactory.md",
)


def repair_tokenfactory_public_knowledge(
    vault: Path,
    *,
    apply_changes: bool,
    approved_by: str,
    backup_root: Path | None = None,
) -> dict[str, object]:
    vault = vault.resolve()
    targets = [(vault / relative).resolve() for relative in PUBLIC_TOKENFACTORY_PATHS]
    missing = [
        relative
        for relative, path in zip(PUBLIC_TOKENFACTORY_PATHS, targets)
        if not path.is_file() or vault not in path.parents
    ]
    if missing:
        raise FileNotFoundError("missing governed documents: " + ", ".join(missing))

    result: dict[str, object] = {
        "mode": "apply" if apply_changes else "dry-run",
        "targets": list(PUBLIC_TOKENFACTORY_PATHS),
        "security_level": "green",
        "owner_tenant": "public",
    }
    if not apply_changes:
        return result

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_root = (
        backup_root.resolve()
        if backup_root is not None
        else vault / ".governance-backups" / f"xfusion-tokenfactory-{timestamp}"
    )
    originals: list[tuple[Path, str]] = []
    changed: list[str] = []
    try:
        for relative, path in zip(PUBLIC_TOKENFACTORY_PATHS, targets):
            original = path.read_text(encoding="utf-8")
            originals.append((path, original))
            backup = backup_root / relative
            backup.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup)
            approve_color(
                vault,
                relative_path=relative,
                security_level="green",
                approved_by=approved_by,
            )
            changed.append(relative)
    except Exception:
        for path, original in originals:
            restore_note(path, original)
        raise

    result.update({"changed": changed, "backup_root": str(backup_root)})
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--approved-by", default="migration:xfusion-tokenfactory-public")
    parser.add_argument("--backup-root", type=Path)
    args = parser.parse_args()
    result = repair_tokenfactory_public_knowledge(
        args.vault,
        apply_changes=args.apply,
        approved_by=args.approved_by,
        backup_root=args.backup_root,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
