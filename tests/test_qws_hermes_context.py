import json
import queue
import sys
import types

import pytest
from fastapi import HTTPException

from backend.services.client_context_capability import (
    QWSBusinessContextDenied,
    context_digest,
    mint_client_context_capability,
    mint_qws_business_context_capability,
    verify_qws_business_context_capability,
)
import scripts.hermes_bridge as bridge


def _business_context() -> dict:
    snapshot = {
        "project_overview": {"name": "QWS continuity"},
        "task": {"qws_task_id": "task-1", "status": "in_progress"},
    }
    return {
        "session_id": "task-session-1",
        "revision": 3,
        "context_hash": context_digest(snapshot),
        "snapshot": snapshot,
    }


def _qws_token(context: dict) -> str:
    return mint_qws_business_context_capability(
        tenant_key="tenant-a",
        user_id="user-a",
        session_id="t123456789abc-u123456789abc-main_agent-task-session-1",
        request_id="request-1234",
        policy_version="policy-v1",
        context_hash=context_digest(context),
    )


def test_qws_business_context_has_a_dedicated_signed_audience() -> None:
    context = _business_context()
    claims = verify_qws_business_context_capability(_qws_token(context))
    assert claims["aud"] == "hermes-qws-business-context"
    assert claims["context_hash"] == context_digest(context)

    client_token = mint_client_context_capability(
        tenant_key="tenant-a",
        user_id="user-a",
        session_id="t123456789abc-u123456789abc-main_agent-task-session-1",
        request_id="request-1234",
        policy_version="policy-v1",
        context_hash=context_digest(context),
    )
    with pytest.raises(QWSBusinessContextDenied):
        verify_qws_business_context_capability(client_token)


def test_bridge_rejects_tampered_qws_business_context() -> None:
    context = _business_context()
    token = _qws_token(context)
    claims = bridge._validated_qws_business_context_claims(
        token,
        context,
        subject_id="t123456789abc-u123456789abc-main_agent-task-session-1",
        request_id="request-1234",
        policy_version="policy-v1",
    )
    assert claims and claims["tenant_key"] == "tenant-a"

    tampered = json.loads(json.dumps(context))
    tampered["snapshot"]["task"]["status"] = "done"
    with pytest.raises(HTTPException) as exc_info:
        bridge._validated_qws_business_context_claims(
            token,
            tampered,
            subject_id="t123456789abc-u123456789abc-main_agent-task-session-1",
            request_id="request-1234",
            policy_version="policy-v1",
        )
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail == "qws_business_context_denied"


def test_qws_facts_are_not_rendered_as_conversation_messages(monkeypatch) -> None:
    context = _business_context()
    monkeypatch.setattr(bridge, "_resolve_hermes_session", lambda _user_id: "hermes-native-session")

    assert bridge._hermes_session_for_request("stable-qws-session", None) == "hermes-native-session"
    goal = bridge._with_qws_business_context("按照刚才第二种方案继续", context)
    assert "[QWS_REQUEST_SCOPED_BUSINESS_CONTEXT]" in goal
    assert "Hermes SessionDB is the only source of prior user/assistant turns" in goal
    assert '"qws_task_id":"task-1"' in goal
    assert goal.endswith("按照刚才第二种方案继续")


def test_bridge_exposes_qws_facts_ephemerally_but_persists_clean_turn(
    monkeypatch, tmp_path
) -> None:
    observed: dict[str, object] = {}

    gateway = types.ModuleType("gateway")
    gateway.__path__ = []
    session_context = types.ModuleType("gateway.session_context")
    session_context.declare_stateless_channel = lambda: None
    monkeypatch.setitem(sys.modules, "gateway", gateway)
    monkeypatch.setitem(sys.modules, "gateway.session_context", session_context)

    class FakeAgent:
        session_id = "hermes-native-session"

        def run_conversation(self, model_goal, *, persist_user_message=None):
            observed["model_goal"] = model_goal
            observed["persist_user_message"] = persist_user_message
            return {"final_response": "done"}

        def close(self):
            return None

    class FakeSessionDB:
        def close(self):
            return None

    monkeypatch.setattr(
        bridge,
        "_build_in_process_agent",
        lambda *_args, **_kwargs: (FakeAgent(), FakeSessionDB(), {"triage": None}),
    )
    monkeypatch.setattr(bridge, "_update_session_mapping", lambda *_args: None)

    events: queue.Queue = queue.Queue()
    bridge._run_agent_sync(
        "按照刚才第二种方案继续",
        "stable-qws-session",
        "hermes-native-session",
        events,
        [None],
        sandbox=types.SimpleNamespace(state_db=tmp_path / "state.db"),
        qws_business_context=_business_context(),
    )

    assert "[QWS_REQUEST_SCOPED_BUSINESS_CONTEXT]" in str(observed["model_goal"])
    assert '"qws_task_id":"task-1"' in str(observed["model_goal"])
    assert observed["persist_user_message"] == "按照刚才第二种方案继续"
    assert "QWS_REQUEST_SCOPED_BUSINESS_CONTEXT" not in str(
        observed["persist_user_message"]
    )
