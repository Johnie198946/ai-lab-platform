"""Entrypoint: ``python -m backend.workers.workflow_planning_worker``."""

import asyncio

from backend.services.workflow_planning import worker_loop


if __name__ == "__main__":
    asyncio.run(worker_loop())
