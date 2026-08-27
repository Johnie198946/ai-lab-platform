#!/usr/bin/env python3
"""Create the additive QuantumWorkspace M0 tables before application restart.

This migration is intentionally idempotent and additive. Rolling back the app
release does not require dropping these tables; older releases simply ignore
them.
"""

from __future__ import annotations

import asyncio

from backend.db import Base, engine
from backend.models.workspace import (
    WorkspaceBusinessIntake,
    WorkspaceProcessDraft,
    WorkspaceProject,
    WorkspaceTaskConversation,
    WorkspaceTaskMessage,
)

TABLES = [
    WorkspaceProject.__table__,
    WorkspaceBusinessIntake.__table__,
    WorkspaceProcessDraft.__table__,
    WorkspaceTaskConversation.__table__,
    WorkspaceTaskMessage.__table__,
]


async def migrate() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                sync_connection,
                tables=TABLES,
                checkfirst=True,
            )
        )
    print("quantum_workspace_schema=ready")


if __name__ == "__main__":
    asyncio.run(migrate())
