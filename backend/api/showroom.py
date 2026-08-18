"""展厅多屏运行态 API。

提供同一后端进程内的 2PC 阶段同步、WebSocket 广播与 IPD 人工评审记录。
物理展厅只有一套全局运行态；重启后安全回到站 1，前端保留离线演示兜底。
"""

from __future__ import annotations

import asyncio
import copy
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

import yaml
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
)
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select

from backend.api.auth import AUTHEN_JWT_ALGORITHM, AUTHEN_JWT_SECRET, require_auth
from backend.api.screens import _load_all as load_screen_configs
from backend.db import SessionLocal
from backend.models.showroom import ShowroomRuntime, ShowroomSession
from backend.services.feishu import send_feishu_async

router = APIRouter(prefix="/api/showroom", tags=["showroom"])
CONTENT_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "showroom"
    / "content.yaml"
)
RUNTIME_ID = "venue"


def _load_content() -> dict[str, Any]:
    if not CONTENT_FILE.is_file():
        return {}
    with CONTENT_FILE.open(encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


content_manifest = _load_content()


class ShowroomCommand(BaseModel):
    type: Literal["PREPARE", "COMMIT"]
    epoch: int = Field(..., ge=1)
    stage: str = Field(..., pattern=r"^station-[1-5]$")
    payload: dict[str, Any] = Field(default_factory=dict)


class ReviewSubmission(BaseModel):
    decision: Literal["approved", "changes", "rejected"]
    comment: str = Field(default="", max_length=2000)
    phase: str = Field(default="", max_length=80)
    session_id: str = Field(default="", max_length=120)


class SessionCreate(BaseModel):
    session_id: str = Field(..., min_length=4, max_length=120)
    slot: str = Field(default="main", pattern=r"^(main|[1-5])$")
    role: str = Field(default="", max_length=80)


class SessionPatch(BaseModel):
    step: int | None = Field(default=None, ge=0, le=6)
    status: Literal["active", "completed", "submitted"] | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DemandConfirmation(BaseModel):
    demand: dict[str, Any]


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=12000)


class ArtifactUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: dict[str, Any] = Field(default_factory=dict)


class ShowroomHub:
    def __init__(self) -> None:
        self.lock = asyncio.Lock()
        self.connections: dict[WebSocket, str] = {}
        self.ready_sessions: set[str] = set()
        self.state: dict[str, Any] = {
            "epoch": 0,
            "stage": "station-1",
            "payload": {},
            "reviews": {},
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            **self.state,
            "connected_clients": len(self.connections),
            "ready_clients": len(self.ready_sessions),
        }

    async def broadcast(self, message: dict[str, Any]) -> None:
        dead: list[WebSocket] = []
        for connection in list(self.connections):
            try:
                await connection.send_json(message)
            except Exception:
                dead.append(connection)
        for connection in dead:
            self.connections.pop(connection, None)


hub = ShowroomHub()
_runtime_hydrated = False


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """递归合并前端业务数据，避免局部保存覆盖整份需求或报告。"""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _initial_session_data(slot: str) -> dict[str, Any]:
    if slot == "main":
        return copy.deepcopy(content_manifest.get("default_session", {}))
    return {
        "role": "",
        "messages": [
            {
                "role": "assistant",
                "content": "请说出一个你真正想解决的业务问题，我会先帮你把需求收敛清楚。",
            }
        ],
        "demand": {
            "confirmed": False,
            "completeness": 0,
            "industry": "",
            "core_problem": "",
            "target_metric": "",
            "cycle": "",
            "users": "",
            "solution": "",
            "next_action": "",
        },
        "insight": {},
        "prototype": {},
        "artifacts": {},
        "reviews": {},
    }


def _session_payload(
    row: ShowroomSession | None, fallback_id: str, slot: str
) -> dict[str, Any]:
    if row is None:
        return {
            "session_id": fallback_id,
            "slot": slot,
            "step": 0,
            "status": "active",
            "data": _initial_session_data(slot),
        }
    return {
        "session_id": row.session_id,
        "slot": row.slot,
        "step": row.step,
        "status": row.status,
        "data": row.data or {},
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _get_or_create_session(
    session_id: str, slot: str, tenant_key: str, role: str = ""
) -> ShowroomSession:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None:
            data = _initial_session_data(slot)
            if role:
                data["role"] = role
            row = ShowroomSession(
                session_id=session_id,
                tenant_key=tenant_key,
                slot=slot,
                data=data,
            )
            database.add(row)
            await database.commit()
            await database.refresh(row)
        elif row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        return row


async def _ensure_runtime_hydrated() -> None:
    global _runtime_hydrated
    if _runtime_hydrated:
        return
    try:
        async with SessionLocal() as database:
            row = await database.get(ShowroomRuntime, RUNTIME_ID)
            if row and row.state:
                hub.state = _merge(hub.state, row.state)
    except Exception:
        pass
    _runtime_hydrated = True


async def _persist_runtime() -> None:
    try:
        async with SessionLocal() as database:
            row = await database.get(ShowroomRuntime, RUNTIME_ID)
            state = copy.deepcopy(hub.state)
            if row is None:
                database.add(ShowroomRuntime(runtime_id=RUNTIME_ID, state=state))
            else:
                row.state = state
            await database.commit()
    except Exception:
        # 数据库不可用时仍维持进程内多屏同步，不阻断现场演示。
        pass


def _validate_websocket_token(token: str) -> dict[str, Any]:
    if not AUTHEN_JWT_SECRET:
        return {"sub": "dev", "username": "dev"}
    if not token:
        raise JWTError("missing token")
    return jwt.decode(token, AUTHEN_JWT_SECRET, algorithms=[AUTHEN_JWT_ALGORITHM])


@router.get("/state")
async def get_showroom_state(payload=Depends(require_auth)) -> dict[str, Any]:
    await _ensure_runtime_hydrated()
    return hub.snapshot()


@router.get("/bootstrap")
async def get_showroom_bootstrap(
    session_id: str = Query(..., min_length=4, max_length=120),
    slot: str = Query("main", pattern=r"^(main|[1-5])$"),
    payload=Depends(require_auth),
) -> dict[str, Any]:
    """返回前端唯一启动契约：屏幕、内容、实时状态和当前独立会话。"""
    await _ensure_runtime_hydrated()
    tenant_key = str(payload.get("tenant_key") or "demo")
    try:
        session = await _get_or_create_session(session_id, slot, tenant_key)
        session_data = _session_payload(session, session_id, slot)
    except HTTPException:
        raise
    except Exception:
        session_data = _session_payload(None, session_id, slot)

    screens = list(load_screen_configs().values())
    centers: list[dict[str, Any]] = []
    try:
        async with SessionLocal() as database:
            rows = (
                await database.execute(
                    select(ShowroomSession)
                    .where(ShowroomSession.slot.in_(["1", "2", "3", "4", "5"]))
                    .order_by(ShowroomSession.updated_at.desc())
                )
            ).scalars()
            seen: set[str] = set()
            for row in rows:
                if row.slot in seen:
                    continue
                seen.add(row.slot)
                centers.append(
                    {
                        "slot": row.slot,
                        "step": row.step,
                        "status": row.status,
                        "role": (row.data or {}).get("role", "访客"),
                        "updated_at": row.updated_at,
                    }
                )
    except Exception:
        centers = []
    knowledge: dict[str, Any] = {}
    try:
        from backend.api.knowledge import get_stats

        stats = get_stats()
        knowledge = {
            "total_md_files": stats.get("total_md_files", 0),
            "categories": stats.get("categories", {}),
            "matrix": stats.get("matrix", {}),
        }
    except Exception:
        knowledge = {"total_md_files": 0, "categories": {}, "matrix": {}}

    return {
        "contract_version": "2026-08-19",
        "screens": screens,
        "content": content_manifest,
        "runtime": hub.snapshot(),
        "session": session_data,
        "knowledge": knowledge,
        "centers": centers,
        "capabilities": {
            "chat_stream": "/api/chat/stream",
            "knowledge_search": "/api/knowledge/search",
            "review": "/api/showroom/reviews/{gate}",
            "session_write": True,
            "runtime_persistence": True,
            "feishu_configured": bool(os.environ.get("FEISHU_WEBHOOK_URL", "").strip()),
        },
    }


@router.post("/sessions")
async def create_showroom_session(
    body: SessionCreate, payload=Depends(require_auth)
) -> dict[str, Any]:
    row = await _get_or_create_session(
        body.session_id,
        body.slot,
        str(payload.get("tenant_key") or "demo"),
        body.role,
    )
    return _session_payload(row, body.session_id, body.slot)


@router.get("/sessions/{session_id}")
async def get_showroom_session(
    session_id: str, payload=Depends(require_auth)
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        return _session_payload(row, session_id, row.slot)


@router.patch("/sessions/{session_id}")
async def update_showroom_session(
    session_id: str, body: SessionPatch, payload=Depends(require_auth)
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        if body.step is not None:
            row.step = body.step
        if body.status is not None:
            row.status = body.status
        if body.data:
            row.data = _merge(row.data or {}, body.data)
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.post("/sessions/{session_id}/messages")
async def append_showroom_message(
    session_id: str, body: SessionMessage, payload=Depends(require_auth)
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        messages = list(data.get("messages", []))
        messages.append(
            {
                "role": body.role,
                "content": body.content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )
        data["messages"] = messages[-50:]
        row.data = data
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.post("/sessions/{session_id}/demand/confirm")
async def confirm_showroom_demand(
    session_id: str, body: DemandConfirmation, payload=Depends(require_auth)
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        demand = _merge((row.data or {}).get("demand", {}), body.demand)
        demand["confirmed"] = True
        demand["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        data = _merge(row.data or {}, {"demand": demand})
        row.data = data
        row.step = max(row.step, 2)
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.post("/sessions/{session_id}/insight/generate")
async def generate_showroom_insight(
    session_id: str, payload=Depends(require_auth)
) -> dict[str, Any]:
    """基于已确认需求检索真实知识库，生成带来源的结构化洞察。"""
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = data.get("demand", {})
        if not demand.get("confirmed"):
            raise HTTPException(status_code=409, detail="请先确认需求")

        query = " ".join(
            part
            for part in [
                str(demand.get("industry", "")),
                str(demand.get("core_problem", "")),
                str(demand.get("solution", "")),
            ]
            if part
        )[:200]
        documents: list[dict[str, Any]] = []
        try:
            from backend.api.knowledge import search

            documents = search(query or "业务效率", limit=8).get("docs", [])
        except Exception:
            documents = []

        insight = _merge(
            copy.deepcopy(
                content_manifest.get("default_session", {}).get("insight", {})
            ),
            data.get("insight", {}),
        )
        if documents:
            insight["evidence"] = [
                [
                    document.get("title") or document.get("path") or "知识条目",
                    document.get("snippet") or "命中当前需求关键词",
                    "知识库命中",
                    "已检索",
                ]
                for document in documents[:6]
            ]
        insight["sources"] = [
            {
                "path": document.get("path", ""),
                "title": document.get("title", ""),
                "score": document.get("score", 0),
            }
            for document in documents
        ]
        insight["query"] = query
        insight["generated_at"] = datetime.now(timezone.utc).isoformat()
        data["insight"] = insight
        row.data = data
        row.step = max(row.step, 3)
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.post("/sessions/{session_id}/ipd/{phase_index}/generate")
async def generate_showroom_ipd_artifacts(
    session_id: str,
    phase_index: int,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    """按后端 IPD 清单生成阶段交付件索引并绑定当前需求与证据。"""
    phases = content_manifest.get("ipd_phases", [])
    if phase_index < 0 or phase_index >= len(phases):
        raise HTTPException(status_code=422, detail="IPD 阶段无效")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = data.get("demand", {})
        if not demand.get("confirmed"):
            raise HTTPException(status_code=409, detail="请先确认需求")
        artifacts = dict(data.get("artifacts", {}))
        manifest = content_manifest.get("artifacts", {})
        phase = phases[phase_index]
        now = datetime.now(timezone.utc).isoformat()
        for title in phase.get("outputs", []):
            definition = manifest.get(title, {})
            artifacts[title] = {
                "title": title,
                "owner": definition.get("owner", ""),
                "kind": definition.get("kind", "document"),
                "content": {
                    "summary": definition.get("summary", ""),
                    "demand": demand.get("core_problem", ""),
                    "target": demand.get("target_metric", ""),
                    "sources": data.get("insight", {}).get("sources", []),
                },
                "updated_at": now,
            }
        data["artifacts"] = artifacts
        data["ipd_phase"] = phase_index
        row.data = data
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.put("/sessions/{session_id}/artifacts/{artifact_key}")
async def upsert_showroom_artifact(
    session_id: str,
    artifact_key: str,
    body: ArtifactUpdate,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        artifacts = dict(data.get("artifacts", {}))
        artifacts[artifact_key] = {
            "title": body.title,
            "content": body.content,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        data["artifacts"] = artifacts
        row.data = data
        await database.commit()
        await database.refresh(row)
        return artifacts[artifact_key]


@router.post("/commands")
async def apply_showroom_command(
    command: ShowroomCommand,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_runtime_hydrated()
    async with hub.lock:
        current_epoch = int(hub.state["epoch"])
        if command.epoch < current_epoch:
            raise HTTPException(status_code=409, detail="陈旧 epoch 已被丢弃")

        if command.type == "PREPARE":
            hub.ready_sessions.clear()
            message = {
                "type": "PREPARE",
                "epoch": command.epoch,
                "stage": command.stage,
                "payload": command.payload,
                "state": hub.snapshot(),
            }
        else:
            hub.state.update(
                {
                    "epoch": command.epoch,
                    "stage": command.stage,
                    "payload": command.payload,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            message = {
                "type": "COMMIT",
                "epoch": command.epoch,
                "stage": command.stage,
                "payload": command.payload,
                "state": hub.snapshot(),
            }
        await hub.broadcast(message)
        await _persist_runtime()
        return hub.snapshot()


@router.post("/reviews/{gate}")
async def submit_showroom_review(
    gate: str,
    submission: ReviewSubmission,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    await _ensure_runtime_hydrated()
    normalized_gate = gate.strip().upper()
    if not normalized_gate or len(normalized_gate) > 12:
        raise HTTPException(status_code=422, detail="评审关口格式无效")
    if submission.decision != "approved" and not submission.comment.strip():
        raise HTTPException(status_code=422, detail="修改或拒绝必须填写审批意见")

    reviewer = payload.get("username") or payload.get("sub") or "unknown"
    record = {
        "decision": submission.decision,
        "comment": submission.comment.strip(),
        "phase": submission.phase,
        "session_id": submission.session_id,
        "reviewer": reviewer,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    async with hub.lock:
        hub.state["reviews"][normalized_gate] = record
        hub.state["updated_at"] = record["reviewed_at"]
        message = {
            "type": "REVIEW",
            "gate": normalized_gate,
            "record": record,
            "state": hub.snapshot(),
        }
        await hub.broadcast(message)
        await _persist_runtime()

    if submission.session_id:
        try:
            async with SessionLocal() as database:
                session = await database.get(ShowroomSession, submission.session_id)
                if session is not None and session.tenant_key == str(
                    payload.get("tenant_key") or "demo"
                ):
                    session.data = _merge(
                        session.data or {}, {"reviews": {normalized_gate: record}}
                    )
                    await database.commit()
        except Exception:
            pass

    asyncio.create_task(
        send_feishu_async(
            f"AI Lab IPD · {normalized_gate} 人工评审",
            "\n".join(
                [
                    f"阶段：{submission.phase or '未指定'}",
                    f"结论：{submission.decision}",
                    f"审批人：{reviewer}",
                    f"意见：{submission.comment.strip() or '通过'}",
                ]
            ),
        )
    )
    return hub.snapshot()


@router.websocket("/ws")
async def showroom_websocket(
    websocket: WebSocket,
    token: str = "",
    session_id: str = "",
) -> None:
    try:
        _validate_websocket_token(token)
    except JWTError:
        await websocket.close(code=4401, reason="invalid token")
        return

    await websocket.accept()
    client_id = session_id.strip()[:120] or f"screen-{id(websocket)}"
    hub.connections[websocket] = client_id
    await websocket.send_json({"type": "STATE", "state": hub.snapshot()})
    try:
        while True:
            try:
                message = await asyncio.wait_for(websocket.receive_json(), timeout=25)
            except asyncio.TimeoutError:
                await websocket.send_json({"type": "PING"})
                continue
            is_ready = message.get("type") == "READY"
            epoch_is_current = int(message.get("epoch", -1)) >= int(
                hub.state["epoch"]
            )
            if is_ready and epoch_is_current:
                hub.ready_sessions.add(client_id)
            elif message.get("type") == "PONG":
                continue
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.connections.pop(websocket, None)
        hub.ready_sessions.discard(client_id)
