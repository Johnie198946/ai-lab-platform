from __future__ import annotations

import asyncio
import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ..auth import AuthContext
from ..domain import RunManifest


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=20000)
    request_id: str | None = Field(default=None, min_length=8, max_length=100)
    session_id: str | None = Field(default=None, max_length=100)
    agent_id: str | None = Field(default=None, max_length=80)
    skill_id: str | None = Field(default=None, max_length=120)


class ChatRuntime:
    def __init__(self, settings, repository, sandboxes, runner):
        self.settings = settings
        self.repository = repository
        self.sandboxes = sandboxes
        self.runner = runner

    def create(self, request: ChatRequest, auth: AuthContext) -> tuple[RunManifest, object]:
        version = "v1"
        sandbox = self.sandboxes.provision(auth.tenant_id, self.settings.hermes_template, "hermes-main", version)
        manifest = RunManifest.now(
            run_id=f"run_{uuid4().hex}",
            tenant_id=auth.tenant_id,
            sandbox_id=sandbox.sandbox_id,
            template_id="hermes-main",
            template_version=version,
            session_id=request.session_id or f"sess_{uuid4().hex}",
            agent_id=request.agent_id or "main_agent",
            allowed_skills=(request.skill_id,) if request.skill_id else (),
            knowledge_scope=("public", auth.tenant_id),
            allow_network=False,
            allow_local_files=False,
        )
        self.repository.create(manifest, request.question)
        return manifest, sandbox


def build_router(runtime: ChatRuntime, auth_dependency) -> APIRouter:
    router = APIRouter(prefix="/api/chat", tags=["chat"])

    @router.post("/stream")
    async def stream(request: ChatRequest, auth: AuthContext = Depends(auth_dependency)):
        manifest, sandbox = runtime.create(request, auth)
        asyncio.create_task(runtime.runner.start(manifest, request.question, sandbox))

        async def body():
            created = {"run_id": manifest.run_id, "session_id": manifest.session_id}
            yield _sse("run.created", created)
            sequence = 0
            while True:
                events = runtime.repository.events(manifest.run_id, sequence)
                for event in events:
                    sequence = event.sequence
                    yield _sse(event.event_type, {"sequence": event.sequence, **event.payload})
                current = runtime.repository.get(manifest.run_id, auth.tenant_id)
                if current and current["status"] in {"completed", "failed", "cancelled"}:
                    break
                await asyncio.sleep(0.25)

        return StreamingResponse(body(), media_type="text/event-stream")

    @router.get("/status/{session_id}")
    async def status(session_id: str, auth: AuthContext = Depends(auth_dependency)):
        candidates = []
        for run_id in _run_ids_for_session(runtime, session_id, auth.tenant_id):
            run = runtime.repository.get(run_id, auth.tenant_id)
            if run:
                candidates.append(run)
        if not candidates:
            raise HTTPException(status_code=404, detail="session not found")
        current = candidates[-1]
        return {**current, "events": [event.__dict__ for event in runtime.repository.events(current["run_id"])]}

    @router.post("/stream/cancel")
    async def cancel(payload: dict, auth: AuthContext = Depends(auth_dependency)):
        run_id = str(payload.get("run_id", ""))
        run = runtime.repository.get(run_id, auth.tenant_id)
        if not run:
            raise HTTPException(status_code=404, detail="run not found")
        await runtime.runner.cancel(run_id, auth.tenant_id)
        return {"run_id": run_id, "status": "cancelled"}

    @router.post("")
    async def chat(request: ChatRequest, auth: AuthContext = Depends(auth_dependency)):
        manifest, sandbox = runtime.create(request, auth)
        await runtime.runner.start(manifest, request.question, sandbox)
        events = runtime.repository.events(manifest.run_id)
        answer = next((event.payload.get("answer", "") for event in reversed(events) if event.event_type == "run.completed"), "")
        return {"question": request.question, "answer": answer, "session_id": manifest.session_id}

    return router


def _run_ids_for_session(runtime: ChatRuntime, session_id: str, tenant_id: str) -> list[str]:
    import sqlite3

    with sqlite3.connect(runtime.repository.path) as connection:
        rows = connection.execute("SELECT run_id FROM runs WHERE session_id=? AND tenant_id=? ORDER BY created_at", (session_id, tenant_id)).fetchall()
    return [row[0] for row in rows]


def _sse(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
