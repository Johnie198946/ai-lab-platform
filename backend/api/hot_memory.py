"""Authenticated façade for the user sandbox's native Hermes memory."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.api.auth import require_auth
from backend.api.chat import _resolve_chat_policy
from backend.services.hermes_sandbox_catalog import (
    add_native_memory,
    delete_native_memory,
    fetch_native_memory,
    replace_native_memory,
)

router = APIRouter(prefix="/api/v1/me/memory", tags=["memory"])


class MemoryWriteRequest(BaseModel):
    target: str = Field(pattern="^(user|memory)$")
    content: str = Field(min_length=1, max_length=2_200)


class MemoryReplaceRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_200)


def _user_id(payload: dict[str, Any]) -> str:
    return str(payload.get("user_id") or payload.get("sub") or "anonymous")


def _bridge_error(exc: Exception) -> HTTPException:
    response = getattr(exc, "response", None)
    if isinstance(exc, httpx.HTTPStatusError) and response is not None:
        try:
            detail = response.json().get("detail")
        except (ValueError, AttributeError):
            detail = None
        if response.status_code in {404, 409}:
            return HTTPException(status_code=response.status_code, detail=detail)
    return HTTPException(status_code=502, detail="Hermes memory unavailable")


@router.get("")
async def get_memory(payload: dict[str, Any] = Depends(require_auth)):
    try:
        return await fetch_native_memory(
            await _resolve_chat_policy(payload), user_id=_user_id(payload)
        )
    except Exception as exc:
        raise _bridge_error(exc) from exc


@router.post("")
async def create_memory(
    request: MemoryWriteRequest,
    payload: dict[str, Any] = Depends(require_auth),
):
    try:
        return await add_native_memory(
            await _resolve_chat_policy(payload),
            user_id=_user_id(payload),
            target=request.target,
            content=request.content,
        )
    except Exception as exc:
        raise _bridge_error(exc) from exc


@router.put("/{memory_id}")
async def replace_memory(
    memory_id: str,
    request: MemoryReplaceRequest,
    payload: dict[str, Any] = Depends(require_auth),
):
    try:
        return await replace_native_memory(
            await _resolve_chat_policy(payload),
            user_id=_user_id(payload),
            memory_id=memory_id,
            content=request.content,
        )
    except Exception as exc:
        raise _bridge_error(exc) from exc


@router.delete("/{memory_id}")
async def remove_memory(
    memory_id: str,
    payload: dict[str, Any] = Depends(require_auth),
):
    try:
        return await delete_native_memory(
            await _resolve_chat_policy(payload),
            user_id=_user_id(payload),
            memory_id=memory_id,
        )
    except Exception as exc:
        raise _bridge_error(exc) from exc
