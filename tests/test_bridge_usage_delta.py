"""Per-turn accounting at the cached Hermes agent boundary (no provider calls)."""
from __future__ import annotations

import asyncio
import os
import queue
import sys
from collections import OrderedDict
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

os.environ.setdefault("HERMES_BRIDGE_INTERNAL_TOKEN", "test-internal-token")
from scripts import hermes_bridge as bridge


class CounterAgent:
    """Matches agent_init/conversation_loop/turn_finalizer counter semantics."""
    session_id = "native-session"

    def __init__(self):
        for field in bridge._CUMULATIVE_USAGE_FIELDS:
            setattr(self, "session_" + field, 0)
        self.session_api_calls = 0
        self.fail = False
        self.wrapped = False
        self.next_usage = {
            "input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 25,
            "cache_read_tokens": 900, "cache_write_tokens": 10,
            "total_tokens": 1060, "estimated_cost_usd": 0.02,
        }

    def run_conversation(self, goal, **kwargs):
        for field, increment in self.next_usage.items():
            setattr(self, "session_" + field, getattr(self, "session_" + field) + increment)
        self.session_api_calls += 2
        if self.fail:
            raise RuntimeError("provider failed after consuming usage")
        usage = bridge._agent_usage_baseline(self)
        # Unlike the counters above, finalizer api_calls is already turn-local.
        usage.update(api_calls=2, model="test-model", provider="openai",
                     cost_status="estimated", cost_source="test-price")
        return {"final_response": "answer", **({"usage": usage} if self.wrapped else usage)}

    def close(self):
        pass


@pytest.fixture
def harness(monkeypatch, tmp_path):
    agent = CounterAgent()
    db = SimpleNamespace(get_messages=lambda sid: [], message_count=lambda sid: 0, close=lambda: None)
    sandbox = SimpleNamespace(state_db=tmp_path / "state.db")
    retained = []
    monkeypatch.setitem(sys.modules, "gateway.session_context", SimpleNamespace(declare_stateless_channel=lambda: None))
    monkeypatch.setitem(sys.modules, "hermes_constants", SimpleNamespace(
        set_hermes_home_override=lambda home: "token", reset_hermes_home_override=lambda token: None))
    monkeypatch.setattr(bridge, "_sandbox_hermes_home", lambda sandbox: tmp_path)
    monkeypatch.setattr(bridge, "_update_session_mapping", lambda *args: None)
    monkeypatch.setattr(bridge, "_AGENT_CACHE", OrderedDict())
    monkeypatch.setattr(bridge, "_AGENT_CACHE_MAX_SIZE", 2)
    original_finish = bridge._finish_cached_agent

    def build(*args, **kwargs):
        cached = bridge._take_cached_agent("user", "sig", agent.session_id)
        selected_agent, selected_db = cached[:2] if cached else (agent, db)
        return selected_agent, selected_db, {"agent_cache_key": "user", "agent_cache_signature": "sig"}

    def finish(*args, **kwargs):
        retained.append(kwargs["keep"])
        return original_finish(*args, **kwargs)

    monkeypatch.setattr(bridge, "_build_in_process_agent", build)
    monkeypatch.setattr(bridge, "_finish_cached_agent", finish)

    def run(**kwargs):
        events = queue.Queue()
        bridge._run_agent_sync("hello", "user", agent.session_id, events, [None], sandbox=sandbox, **kwargs)
        return list(events.queue)

    return agent, run, retained, sandbox


@pytest.mark.parametrize("wrapped", [False, True])
def test_cold_and_cached_turns_use_live_instance_baseline(harness, wrapped):
    agent, run, retained, _ = harness
    agent.wrapped = wrapped
    first = run()[-1]
    second = run()[-1]
    assert first["type"] == second["type"] == "done"
    for event in (first, second):
        usage = event["usage"]
        for field, increment in agent.next_usage.items():
            assert usage[field] == pytest.approx(increment)
        assert usage["api_calls"] == 2
        assert usage["budget_tokens"] == 50  # reasoning is a subset, not +25
        assert usage["usage_scope"] == "turn"
        assert usage["usage_available"] is True
    assert second["usage"]["cumulative_usage"]["total_tokens"] == 2120
    assert second["usage"]["usage_baseline"]["total_tokens"] == 1060
    assert agent.session_total_tokens == 2120  # native counters stay cumulative
    assert retained == [True, True]


def test_counter_activity_not_reported_by_previous_request_is_not_rebilled(harness):
    agent, run, _, _ = harness
    run()
    # Usage can change outside the last successful response (e.g. a failed turn).
    agent.session_total_tokens = 184970
    agent.next_usage["total_tokens"] = 235775
    usage = run()[-1]["usage"]
    assert usage["total_tokens"] == 235775
    assert usage["cumulative_usage"]["total_tokens"] == 420745
    assert usage["usage_baseline"]["total_tokens"] == 184970


def test_failure_drops_cache_and_never_poison_next_baseline(harness):
    agent, run, retained, _ = harness
    run()
    agent.fail = True
    events = run()
    assert events[-1]["type"] == "error"
    assert not any(event["type"] == "done" for event in events)
    assert retained == [True, False]
    # Even if another caller reuses the instance, the failed turn isn't rebilled.
    agent.fail = False
    assert run()[-1]["usage"]["total_tokens"] == 1060


def test_rebuilt_agent_same_session_does_not_subtract_previous_instance():
    old = CounterAgent()
    old.run_conversation("old")
    replacement = CounterAgent()
    baseline = bridge._agent_usage_baseline(replacement)
    usage = bridge._usage_delta(replacement.run_conversation("new"), baseline)
    assert usage["total_tokens"] == 1060
    assert usage["usage_baseline"]["total_tokens"] == 0


def test_counter_reset_is_nonnegative_and_auditable():
    usage = bridge._usage_delta(
        {"total_tokens": 50, "output_tokens": 10, "estimated_cost_usd": 0.01, "api_calls": 1},
        {"total_tokens": 100, "output_tokens": 30, "estimated_cost_usd": 0.05},
    )
    assert usage["total_tokens"] == 50
    assert usage["estimated_cost_usd"] == 0.01
    assert usage["usage_available"] is False
    assert set(usage["usage_counter_resets"]) == {"total_tokens", "output_tokens", "estimated_cost_usd"}
    assert usage["api_calls"] == 1


def test_missing_usage_stays_unavailable_and_normalization_is_idempotent():
    missing = bridge._usage_delta({"api_calls": 0}, {"total_tokens": 100})
    assert missing["usage_available"] is False
    assert missing["total_tokens"] == 0
    assert bridge._usage_delta(missing) == missing
    agent = CounterAgent()
    before = bridge._agent_usage_baseline(agent)
    usage = bridge._usage_delta(agent.run_conversation("turn"), before)
    assert bridge._usage_delta(usage, {"total_tokens": 999}) == usage
    assert bridge._accumulate_usage({}, usage) == usage


def test_signed_nonstream_chat_returns_same_turn_delta(harness, monkeypatch):
    agent, run, _, sandbox = harness
    run()
    monkeypatch.setattr(bridge, "_require_internal_strict", lambda token: None)
    monkeypatch.setattr(bridge, "_validated_knowledge_claims", lambda *args, **kwargs: {"tenant_key": "t", "user_id": "u"})
    monkeypatch.setattr(bridge, "_validated_client_context_claims", lambda *args, **kwargs: None)
    monkeypatch.setattr(bridge, "_validated_qws_business_context_claims", lambda *args, **kwargs: None)
    monkeypatch.setattr(bridge, "_tenant_sandbox_from_claims", lambda **kwargs: sandbox)
    monkeypatch.setattr(bridge, "_resolve_hermes_session", lambda user: agent.session_id)
    monkeypatch.setattr(bridge, "_mark_consumed", lambda *args: None)

    @asynccontextmanager
    async def admitted():
        yield

    monkeypatch.setattr(bridge, "_admit_request", admitted)
    monkeypatch.setattr(bridge, "_get_user_lock", lambda user: asyncio.Lock())
    result = asyncio.run(bridge.chat(bridge.GoalRequest(goal="hello", session_id="user"), "token"))
    assert result["usage"]["total_tokens"] == 1060
    assert result["usage"]["cumulative_usage"]["total_tokens"] == 2120


@pytest.mark.parametrize("entrypoint", ["workflow", "clarification"])
def test_other_in_process_entrypoints_snapshot_before_execution(monkeypatch, tmp_path, entrypoint):
    agent = CounterAgent()
    agent.run_conversation("prior work")
    db = SimpleNamespace(close=lambda: None)
    monkeypatch.setitem(sys.modules, "run_agent", SimpleNamespace(AIAgent=lambda **kwargs: agent))
    monkeypatch.setitem(sys.modules, "model_tools", SimpleNamespace(get_tool_definitions=lambda **kwargs: []))
    monkeypatch.setitem(sys.modules, "agent.runtime_cwd", SimpleNamespace(set_session_cwd=lambda cwd: None))
    monkeypatch.setattr(bridge, "_get_cached_config", lambda: {"model": "test-model"})
    monkeypatch.setattr(bridge, "_get_cached_runtime", lambda cfg: {})
    monkeypatch.setattr(bridge, "_get_cached_fallback", lambda cfg: None)
    monkeypatch.setattr(bridge, "_cache_request_overrides", lambda *args: {})
    monkeypatch.setattr(bridge, "_ensure_tenant_skill_tool_registered", lambda: None)
    monkeypatch.setattr(bridge, "_create_sandbox_session_db", lambda sandbox: db)
    monkeypatch.setattr(bridge, "_create_thread_local_session_db", lambda: db)
    if entrypoint == "workflow":
        reply, sid, usage = bridge._run_workflow_node_in_process(
            "hello", {"node_type": "LLM_INFERENCE", "parameters": {"max_tokens": 1000}},
            sandbox=SimpleNamespace(root=tmp_path),
        )
        assert sid == agent.session_id
    else:
        reply, usage = bridge._run_clarification_in_process("hello")
    assert reply == "answer"
    assert usage["total_tokens"] == 1060
    assert usage["usage_baseline"]["total_tokens"] == 1060
    assert usage["api_calls"] == 2
    assert bridge._usage_delta(usage) == usage


def test_postprocessing_guard_retains_completed_usage(harness, monkeypatch):
    agent, run, _, _ = harness
    original = agent.run_conversation
    def guarded(*args, **kwargs):
        result = original(*args, **kwargs)
        bridge._client_context_tool_context.value = {}
        return result
    monkeypatch.setattr(agent, "run_conversation", guarded)
    monkeypatch.setattr(bridge, "_is_note_draft_request", lambda goal: True)
    errors = [event for event in run(knowledge_action_enabled=True) if event["type"] == "error"]
    assert errors[-1]["code"] == "knowledge_action_missing"
    assert errors[-1]["usage"]["total_tokens"] == 1060
    assert errors[-1]["usage"]["usage_scope"] == "turn"


def test_execution_error_retains_confirmed_counter_delta(harness):
    agent, run, _, _ = harness
    run()
    agent.fail = True
    errors = [event for event in run() if event["type"] == "error"]
    assert errors[-1]["usage"]["total_tokens"] == 1060
    assert errors[-1]["usage"]["usage_scope"] == "turn"
