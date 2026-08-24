from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services.user_hot_memory import (
    HERMES_USER_MEMORY_MAX_CHARS,
    add_memory,
    delete_memory,
    list_memory,
    snapshot,
)

router = APIRouter(prefix="/api/v1/me/hot-memory", tags=["hot-memory"])


class HotMemoryRequest(BaseModel):
    kind: str = Field(default="general", min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=180)
    status: str = Field(default="candidate", pattern="^(candidate|confirmed)$")
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    source_session_id: str | None = Field(default=None, max_length=100)
    expires_at: str | None = Field(default=None, max_length=40)


def _scope(payload: dict) -> tuple[str, str]:
    return (
        str(payload.get("tenant_key") or "public"),
        str(payload.get("user_id") or payload.get("sub") or "anonymous"),
    )


@router.get("")
async def get_hot_memory(payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    return {"max_chars": HERMES_USER_MEMORY_MAX_CHARS, "items": [item.__dict__ for item in list_memory(tenant_key, user_id)]}


@router.get("/snapshot")
async def get_hot_memory_snapshot(payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    return {"max_chars": HERMES_USER_MEMORY_MAX_CHARS, "frozen": "session_start", "content": snapshot(tenant_key, user_id)}


@router.post("")
async def create_hot_memory(request: HotMemoryRequest, payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    item = add_memory(tenant_key, user_id, **request.model_dump())
    return item.__dict__


@router.delete("/{memory_id}")
async def remove_hot_memory(memory_id: str, payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    return {"memory_id": memory_id, "deleted": delete_memory(tenant_key, user_id, memory_id)}
