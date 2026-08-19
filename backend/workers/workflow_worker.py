"""Entrypoint: ``python -m backend.workers.workflow_worker``."""

import asyncio

from backend.services.workflow_executor import worker_loop


if __name__ == "__main__":
    asyncio.run(worker_loop())
