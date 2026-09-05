"""Single entry point for source adapters: durable outbox plus Hermes scheduling."""
from __future__ import annotations

import logging
from typing import Any

from backend.services.knowledge_contribution import ContributionCandidate, enqueue_contribution
from backend.services.knowledge_pipeline import submit_compile
from backend.services.knowledge_pipeline_supervisor import run_db_path
from scripts.chat_run_store import DurableChatRunStore

logger = logging.getLogger(__name__)


async def enqueue_and_schedule(
    candidate: ContributionCandidate, *, source_content: str,
) -> dict[str, Any] | None:
    """Never make private source persistence depend on contribution success."""
    event = await enqueue_contribution(candidate)
    if event is None:
        return None
    return await schedule_event(event, source_content=source_content)


async def schedule_event(event: dict[str, Any], *, source_content: str) -> dict[str, Any]:
    try:
        run = await submit_compile(
            DurableChatRunStore(run_db_path()),
            event_id=event["event_id"], content=source_content,
        )
        return {**event, "schedule_status": "scheduled", "run_id": run["run_id"]}
    except Exception as exc:
        logger.exception("Contribution scheduling deferred: %s", event["event_id"])
        return {**event, "schedule_status": "pending", "schedule_error": str(exc)[:160]}
