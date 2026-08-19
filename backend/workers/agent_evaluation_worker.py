from __future__ import annotations

import asyncio

from backend.services.agent_evaluation import worker_loop


if __name__ == "__main__":
    asyncio.run(worker_loop())
