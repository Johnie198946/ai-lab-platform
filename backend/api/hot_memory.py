from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.services.user_hot_memory import (
    HERMES_USER_MEMORY_MAX_CHARS,
    add_memory,
    compact_memory,
    delete_memory,
    list_memory,
    replace_memory,
    snapshot,
    MemoryOverflowError,
)

router = APIRouter(prefix="/api/v1/me/hot-memory", tags=["hot-memory"])


class HotMemoryRequest(BaseModel):
    kind: str = Field(default="general", min_length=1, max_length=40)
    content: str = Field(min_length=1, max_length=180)
    status: str = Field(default="candidate", pattern="^(candidate|confirmed)$")
    confidence: str = Field(default="medium", pattern="^(low|medium|high)$")
    source_session_id: str | None = Field(default=None, max_length=100)
    expires_at: str | None = Field(default=None, max_length=40)


class HotMemoryReplaceRequest(BaseModel):
    content: str = Field(min_length=1, max_length=180)


def _overflow(error: MemoryOverflowError) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": error.code,
            "message": str(error),
            "action": "compact_and_retry",
            "retryable": True,
            "max_chars": HERMES_USER_MEMORY_MAX_CHARS,
        },
    )


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
    try:
        item = add_memory(tenant_key, user_id, **request.model_dump())
    except MemoryOverflowError as error:
        raise _overflow(error) from error
    return item.__dict__


@router.put("/{memory_id}")
async def replace_hot_memory(memory_id: str, request: HotMemoryReplaceRequest, payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    try:
        item = replace_memory(tenant_key, user_id, memory_id, content=request.content)
    except MemoryOverflowError as error:
        raise _overflow(error) from error
    except KeyError as error:
        raise HTTPException(status_code=404, detail="memory_not_found") from error
    return item.__dict__


@router.post("/compact")
async def compact_hot_memory(payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    return {"removed": compact_memory(tenant_key, user_id), "max_chars": HERMES_USER_MEMORY_MAX_CHARS}


@router.delete("/{memory_id}")
async def remove_hot_memory(memory_id: str, payload=Depends(require_auth)):
    tenant_key, user_id = _scope(payload)
    return {"memory_id": memory_id, "deleted": delete_memory(tenant_key, user_id, memory_id)}
