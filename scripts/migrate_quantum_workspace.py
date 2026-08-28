#!/usr/bin/env python3
"""Additive QuantumWorkspace M0.5A migration with dry-run/orphan reporting."""

from __future__ import annotations

import argparse
import asyncio
import json

from backend.db import engine
from backend.services.workspace_migration import migrate_workspace_schema


async def migrate(*, dry_run: bool = False) -> dict:
    async with engine.begin() as connection:
        report = await connection.run_sync(
            lambda sync_connection: migrate_workspace_schema(
                sync_connection,
                dry_run=dry_run,
            )
        )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="scan legacy projects/orphan references without schema or data writes",
    )
    args = parser.parse_args()
    asyncio.run(migrate(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
