"""Server-owned dynamic clarification through the Hermes Bridge."""

import os
from collections.abc import Sequence
from typing import Any

import httpx


HERMES_BRIDGE_URL = os.environ.get("HERMES_BRIDGE_URL", "http://host.docker.internal:9118/v1/chat")
HERMES_BRIDGE_INTERNAL_TOKEN = os.environ.get("HERMES_BRIDGE_INTERNAL_TOKEN", "")
BRIDGE_TIMEOUT_SECONDS = float(os.environ.get("HERMES_CLARIFICATION_TIMEOUT", "65"))


def _honest_fallback() -> dict[str, Any]:
    return {
        "status": "ERROR",
        "question": "大架构师暂时未连接，请稍后重试。",
        "dimension": "connection",
        "source": "fallback",
        "truth": "UNCONNECTED",
        "simulation": True,
    }


def bridge_base_url() -> str:
    base = HERMES_BRIDGE_URL.rstrip("/")
    return base[: -len("/v1/chat")] if base.endswith("/v1/chat") else base


def _validate_bridge_payload(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return _honest_fallback()
    status = str(raw.get("status") or "").upper()
    if status == "READY":
        return {"status": "READY", "source": "hermes", "truth": "LIVE", "simulation": False, "usage": raw.get("usage") or {}}
    question = raw.get("question")
    if status != "QUESTION" or not isinstance(question, str) or not question.strip():
        return _honest_fallback()
    if raw.get("source") != "hermes" or raw.get("truth") != "LIVE" or raw.get("simulation") is not False:
        return _honest_fallback()
    return {
        "status": "question",
        "question": question.strip(),
        "dimension": str(raw.get("dimension") or "missing requirement"),
        "source": "hermes",
        "truth": "LIVE",
        "simulation": False,
        "usage": raw.get("usage") or {},
    }


async def request_bridge_clarification(
    goal: str,
    transcript: Sequence[dict[str, Any]],
    *,
    tenant_id: str,
    workflow_id: str,
) -> dict[str, Any]:
    """Call the protected structured bridge endpoint; never masquerade as model output."""
    headers = {"X-Hermes-Internal-Token": HERMES_BRIDGE_INTERNAL_TOKEN} if HERMES_BRIDGE_INTERNAL_TOKEN else {}
    try:
        async with httpx.AsyncClient(timeout=BRIDGE_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{bridge_base_url()}/v1/workflows/clarify",
                headers=headers,
                json={
                    "tenant_id": tenant_id,
                    "workflow_id": workflow_id,
                    "goal": goal[:12000],
                    "transcript": list(transcript)[-12:],
                },
            )
            response.raise_for_status()
            return _validate_bridge_payload(response.json())
    except Exception:
        return _honest_fallback()

