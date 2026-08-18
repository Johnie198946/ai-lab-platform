"""展厅多屏运行态 API。

提供同一后端进程内的 2PC 阶段同步、WebSocket 广播与 IPD 人工评审记录。
物理展厅只有一套全局运行态；重启后安全回到站 1，前端保留离线演示兜底。
"""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from jose import JWTError, jwt
from pydantic import BaseModel, Field

from backend.api.auth import AUTHEN_JWT_ALGORITHM, AUTHEN_JWT_SECRET, require_auth
from backend.services.feishu import send_feishu_async

router = APIRouter(prefix="/api/showroom", tags=["showroom"])


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


def _validate_websocket_token(token: str) -> dict[str, Any]:
    if not AUTHEN_JWT_SECRET:
        return {"sub": "dev", "username": "dev"}
    if not token:
        raise JWTError("missing token")
    return jwt.decode(token, AUTHEN_JWT_SECRET, algorithms=[AUTHEN_JWT_ALGORITHM])


@router.get("/state")
async def get_showroom_state(payload=Depends(require_auth)) -> dict[str, Any]:
    return hub.snapshot()


@router.post("/commands")
async def apply_showroom_command(
    command: ShowroomCommand,
    payload=Depends(require_auth),
) -> dict[str, Any]:
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
        return hub.snapshot()


@router.post("/reviews/{gate}")
async def submit_showroom_review(
    gate: str,
    submission: ReviewSubmission,
    payload=Depends(require_auth),
) -> dict[str, Any]:
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
