"""Out-of-process durable chat worker.

Hermes remains the only execution runtime. This worker leases persisted Runs and
invokes Hermes outside the Bridge API process, so API/SSE restarts do not kill work.
"""
from __future__ import annotations

import json
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from backend.services.knowledge_policy import KnowledgePolicy, mint_capability
from scripts.chat_run_store import DurableChatRunStore
from scripts import hermes_bridge as bridge

RUN_DB = Path(os.environ.get("HERMES_CHAT_RUN_DB", "/opt/ai-lab-platform/data/hermes_chat_runs.sqlite3"))
POLL_SECONDS = float(os.environ.get("HERMES_CHAT_WORKER_POLL", "0.5"))
MAX_PARALLEL = max(1, int(os.environ.get("HERMES_CHAT_MAX_PARALLEL_PER_USER", "3")))
MAX_WORKERS = max(2, int(os.environ.get("HERMES_CHAT_WORKER_THREADS", "8")))
WORKER_ID = f"{socket.gethostname()}:{os.getpid()}"
_run_context = threading.local()


class DurableEventSink(bridge.DurableEventQueue):
    """bridge._qput commits events; no process-local transport copy is needed."""

    def put_nowait(self, item: Any) -> None:  # noqa: ARG002
        return None


class DurableClarifyGateway:
    """Cross-process HITL resume channel backed by the same Run database."""

    def __init__(self, store: DurableChatRunStore):
        self.store = store

    def register(self, *, clarify_id: str, session_key: str, question: str,
                 choices=None, multi_select: bool = False) -> None:  # noqa: ARG002
        run_id = str(getattr(_run_context, "run_id", ""))
        if not run_id:
            raise RuntimeError("durable clarify missing run context")
        self.store.register_clarify(
            run_id=run_id,
            clarify_id=clarify_id,
            session_id=session_key,
            question=question,
            choices=list(choices or []),
            timeout_seconds=bridge.CLARIFY_TIMEOUT_SECONDS,
        )

    def wait_for_response(self, clarify_id: str, timeout: float) -> str | None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state, response = self.store.clarify_response(clarify_id)
            if state == "resolved":
                return response
            if state in {"expired", "missing"}:
                return None
            time.sleep(0.25)
        return None


def _renew_knowledge_capability(claims: dict[str, Any]) -> str | None:
    if not claims:
        return None
    scopes = frozenset(str(item) for item in claims.get("scopes") or [])
    policy = KnowledgePolicy(
        tenant_key=str(claims.get("tenant_key") or ""),
        org_id="", plan_id="", plan_status="active", wallet=frozenset(),
        entitled_yellow=frozenset(), effective_categories=scopes,
        policy_version=str(claims.get("policy_version") or "durable-run-v1"),
        entitlement_stale=False,
    )
    return mint_capability(
        policy,
        subject_id=str(claims.get("subject_id") or ""),
        entry_point="chat-durable-worker",
        requested_scopes=scopes,
        user_id=str(claims.get("user_id") or "") or None,
        sources=claims.get("sources") or ("tenant_knowledge",),
        ttl_seconds=900,
    )


def _watch_run(store: DurableChatRunStore, run_id: str, agent_holder: list[Any], done: threading.Event) -> None:
    while not done.wait(2):
        try:
            row = store.get_unchecked(run_id)
        except KeyError:
            return
        if row["status"] == "cancelled":
            agent = agent_holder[0] if agent_holder else None
            if agent is not None:
                try:
                    agent.interrupt(message="user-cancelled-durable-run")
                except Exception:
                    pass
            return
        if not store.heartbeat(run_id, WORKER_ID):
            return


def execute(store: DurableChatRunStore, run: dict[str, Any]) -> None:
    run_id = str(run["run_id"])
    bridge._chat_run_store = store
    _run_context.run_id = run_id
    payload = run.get("execution_payload") or json.loads(run.get("execution_payload_json") or "{}")
    claims = dict(payload.get("knowledge_claims") or {})
    client_claims = dict(payload.get("client_context_claims") or {})
    user_key = str(run.get("user_key") or run.get("session_id") or "")
    sandbox = bridge._tenant_sandbox_from_claims(
        subject_id=user_key,
        knowledge_claims=claims or None,
        client_claims=client_claims or None,
    )
    sink = DurableEventSink(run_id)
    agent_holder: list[Any] = [None]
    done = threading.Event()
    monitor = threading.Thread(
        target=_watch_run, args=(store, run_id, agent_holder, done), daemon=True,
        name=f"durable-watch-{run_id[:8]}",
    )
    monitor.start()
    try:
        bridge._run_agent_sync(
            str(payload.get("goal") or ""), user_key,
            bridge._hermes_session_for_request(user_key, payload.get("client_session_context")),
            sink, agent_holder, False, payload.get("agent_config"),
            _renew_knowledge_capability(claims), claims or None,
            payload.get("client_session_context"), client_claims or None, sandbox,
            bool(payload.get("knowledge_action_enabled")),
        )
        snapshot = store.get_unchecked(run_id)
        if snapshot["status"] not in {"completed", "failed", "cancelled"}:
            store.append_event(run_id, {
                "type": "error", "code": "worker_no_terminal",
                "message": "Hermes Worker 未生成终态",
            })
    except Exception as exc:
        try:
            store.append_event(run_id, {
                "type": "error", "code": "worker_exception", "message": str(exc)[:400],
            })
        except (KeyError, RuntimeError):
            pass
    finally:
        done.set()
        monitor.join(timeout=1)
        _run_context.run_id = ""


def main() -> None:
    store = DurableChatRunStore(RUN_DB)
    bridge._chat_run_store = store
    gateway = DurableClarifyGateway(store)
    bridge._get_clarify_gateway = lambda: gateway
    store.recover_after_restart()
    warmup = bridge._prewarm_bridge_agent()
    warmup.join(timeout=90)
    futures = set()
    with ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="durable-chat") as pool:
        while True:
            futures = {future for future in futures if not future.done()}
            claimed = False
            while len(futures) < MAX_WORKERS:
                run = store.claim_next(WORKER_ID, max_parallel_per_owner=MAX_PARALLEL)
                if run is None:
                    break
                futures.add(pool.submit(execute, store, run))
                claimed = True
            if not claimed:
                time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
