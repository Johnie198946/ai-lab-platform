"""RED tests for the AI Chief Architect vertical slice."""

from datetime import datetime, timedelta, timezone
import asyncio
import inspect

import pytest


def test_dynamic_clarification_uses_bridge_http_and_honest_failure(monkeypatch):
    from backend.services import clarification_planner

    calls = []

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "question", "question": "Which evidence?", "dimension": "evidence", "source": "hermes", "truth": "LIVE", "simulation": False}

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response()

    monkeypatch.setattr(clarification_planner.httpx, "AsyncClient", lambda **_: Client())
    result = asyncio.run(clarification_planner.request_bridge_clarification(
        "Build a plan", [], tenant_id="tenant-a", workflow_id="wf-a"
    ))
    assert result["source"] == "hermes"
    assert result["question"] == "Which evidence?"
    assert calls and calls[0][0].endswith("/v1/workflows/clarify")
    assert calls[0][1]["json"]["tenant_id"] == "tenant-a"
    assert calls[0][1]["json"]["workflow_id"] == "wf-a"


def test_dynamic_clarification_bridge_failure_is_not_fixed_question(monkeypatch):
    from backend.services import clarification_planner

    class Client:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise TimeoutError("bridge down")

    monkeypatch.setattr(clarification_planner.httpx, "AsyncClient", lambda **_: Client())
    result = asyncio.run(clarification_planner.request_bridge_clarification(
        "Need a plan", [], tenant_id="tenant-a", workflow_id="wf-a"
    ))
    assert result == {
        "status": "ERROR",
        "question": "大架构师暂时未连接，请稍后重试。",
        "dimension": "connection",
        "source": "fallback",
        "truth": "UNCONNECTED",
        "simulation": True,
    }


def test_clarification_bridge_token_and_schema_fail_closed(monkeypatch):
    from fastapi import HTTPException
    from pydantic import ValidationError
    from scripts import hermes_bridge

    monkeypatch.setattr(hermes_bridge, "HERMES_BRIDGE_INTERNAL_TOKEN", "")
    with pytest.raises(HTTPException) as missing:
        hermes_bridge._require_internal_strict(None)
    assert missing.value.status_code == 503

    monkeypatch.setattr(hermes_bridge, "HERMES_BRIDGE_INTERNAL_TOKEN", "server-secret")
    with pytest.raises(HTTPException) as invalid:
        hermes_bridge._require_internal_strict("wrong-secret")
    assert invalid.value.status_code == 401
    hermes_bridge._require_internal_strict("server-secret")

    hermes_bridge._clarification_last_run.clear()
    hermes_bridge._reserve_clarification_slot("tenant-a")
    with pytest.raises(HTTPException) as limited:
        hermes_bridge._reserve_clarification_slot("tenant-a")
    assert limited.value.status_code == 429

    with pytest.raises(ValidationError):
        hermes_bridge.ClarificationDecision.model_validate(
            {"status": "READY", "question": None, "dimension": None, "extra": True}
        )
    with pytest.raises(ValidationError):
        hermes_bridge.ClarificationDecision.model_validate(
            {"status": "question", "question": "x" * 501, "dimension": "goal"}
        )


def test_clarification_runner_declares_zero_tool_and_zero_context_boundary():
    from scripts import hermes_bridge

    source = inspect.getsource(hermes_bridge._run_clarification_in_process)
    assert 'enabled_toolsets=no_toolsets' in source
    assert 'get_tool_definitions(enabled_toolsets=no_toolsets' in source
    assert 'skip_context_files=True' in source
    assert 'skip_memory=True' in source
    assert 'max_iterations=1' in source



def test_capability_projection_expires_from_server_facts():
    from backend.services.capability_projection import project_capability

    now = datetime.now(timezone.utc)
    assert project_capability(connected=True, checked_at=now, ttl_seconds=300, now=now)["status"] == "CONNECTED"
    assert project_capability(connected=True, checked_at=now - timedelta(seconds=301), ttl_seconds=300, now=now)["status"] == "UNCONNECTED"
    assert project_capability(connected=False, checked_at=now, ttl_seconds=300, now=now)["status"] == "UNCONNECTED"


def test_plan_capability_uses_server_compile_facts_only():
    from backend.services.capability_projection import project_plan_capability

    now = datetime.now(timezone.utc)
    fresh = project_plan_capability(
        compiler_status="compiled",
        checked_at=now,
        ttl_seconds=300,
        now=now,
    )
    stale = project_plan_capability(
        compiler_status="compiled",
        checked_at=now - timedelta(seconds=301),
        ttl_seconds=300,
        now=now,
    )
    assert fresh["status"] == "CONNECTED"
    assert stale["status"] == "UNCONNECTED"
