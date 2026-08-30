"""Public phone and OAuth login facade for Web and iOS clients.

Provider credentials remain in Authen.  This service owns OAuth state, tenant
provisioning and one-time ticket exchange so JWTs never appear in redirect URLs.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import delete, select

from backend.api.register import _issue_jwt, _provision_tenant
from backend.db import SessionLocal
from backend.models.external_auth import ExternalAuthFlow


router = APIRouter(prefix="/api/v1/auth", tags=["external-auth"])

AUTHEN_BASE = os.environ.get("AUTHEN_BASE", "http://host.docker.internal:8001").rstrip("/")
SUPPORTED_PROVIDERS = {"wechat", "alipay"}
FLOW_TTL = timedelta(minutes=10)
TICKET_TTL = timedelta(minutes=5)
PHONE_RE = re.compile(r"^\+861[3-9]\d{9}$")


class PhoneRequest(BaseModel):
    phone: str


class PhoneLoginRequest(PhoneRequest):
    code: str


class TicketRequest(BaseModel):
    ticket: str


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_phone(value: str) -> str:
    compact = re.sub(r"[\s-]", "", value.strip())
    if compact.startswith("0086"):
        compact = "+86" + compact[4:]
    elif compact.startswith("86") and len(compact) == 13:
        compact = "+" + compact
    elif len(compact) == 11:
        compact = "+86" + compact
    if not PHONE_RE.fullmatch(compact):
        raise HTTPException(status_code=422, detail="请输入有效的中国大陆手机号")
    return compact


def _provider_callback(provider: str) -> str:
    public_base = os.environ.get("AUTH_PUBLIC_BASE_URL", "").strip().rstrip("/")
    if not public_base.startswith("https://"):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="第三方登录需要配置 HTTPS 公网回调地址",
        )
    return f"{public_base}/api/v1/auth/oauth/{provider}/callback"


def _return_url(client: str) -> str:
    if client == "web":
        configured = os.environ.get("AUTH_WEB_RETURN_URL", "").strip()
        if configured:
            return configured
        public_base = os.environ.get("AUTH_PUBLIC_BASE_URL", "").strip().rstrip("/")
        if public_base:
            return f"{public_base}/login"
    elif client == "ios":
        return os.environ.get("AUTH_IOS_RETURN_URL", "quantum://oauth/callback").strip()
    raise HTTPException(status_code=422, detail="不支持的登录客户端")


def _append_query(url: str, **values: str) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(values)
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


async def _authen_request(method: str, path: str, **kwargs) -> dict:
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.request(method, f"{AUTHEN_BASE}{path}", **kwargs)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="认证服务暂不可用") from exc
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail")
        except ValueError:
            detail = None
        raise HTTPException(
            status_code=response.status_code,
            detail=detail or "认证服务请求失败",
        )
    return response.json()


def _session_payload(
    user_id: str, tenant_key: str, *, is_new_user: bool = False,
    auth_method: str = "interactive",
) -> dict:
    token = _issue_jwt(user_id, auth_method=auth_method)
    if not token:
        raise HTTPException(status_code=503, detail="平台登录签名尚未配置")
    return {
        "success": True,
        "token": token,
        "access_token": token,
        "user_id": user_id,
        "tenant_key": tenant_key,
        "is_new_user": is_new_user,
    }


@router.get("/capabilities")
async def capabilities():
    try:
        data = await _authen_request("GET", "/api/v1/auth/capabilities")
    except HTTPException:
        data = {
            "phone": {"enabled": False},
            "oauth": {
                "wechat": {"enabled": False},
                "alipay": {"enabled": False},
            },
        }
    https_ready = os.environ.get("AUTH_PUBLIC_BASE_URL", "").strip().startswith(
        "https://"
    )
    for provider in SUPPORTED_PROVIDERS:
        provider_data = data.setdefault("oauth", {}).setdefault(provider, {})
        provider_data["enabled"] = bool(provider_data.get("enabled") and https_ready)
    return data


@router.post("/phone/send-code")
async def send_phone_code(body: PhoneRequest):
    phone = _normalize_phone(body.phone)
    await _authen_request("POST", "/api/v1/auth/send-sms", json={"phone": phone})
    return {"success": True, "message": "验证码已发送"}


@router.post("/phone/login")
async def phone_login(body: PhoneLoginRequest):
    phone = _normalize_phone(body.phone)
    if not re.fullmatch(r"\d{6}", body.code.strip()):
        raise HTTPException(status_code=422, detail="请输入 6 位短信验证码")
    payload = await _authen_request(
        "POST",
        "/api/v1/auth/login/phone-code",
        json={"phone": phone, "code": body.code.strip()},
    )
    user_id = str(payload.get("user", {}).get("id", ""))
    if not user_id:
        raise HTTPException(status_code=502, detail="认证服务未返回用户标识")
    tenant_key = await _provision_tenant(user_id)
    return _session_payload(
        user_id, tenant_key, is_new_user=bool(payload.get("is_new_user")),
        auth_method="sms",
    )


@router.get("/oauth/{provider}/start")
async def oauth_start(provider: str, client: str = Query("web")):
    if provider not in SUPPORTED_PROVIDERS:
        raise HTTPException(status_code=404, detail="不支持的第三方登录方式")
    callback = _provider_callback(provider)
    return_url = _return_url(client)
    raw_state = secrets.token_urlsafe(32)
    flow = ExternalAuthFlow(
        id=secrets.token_hex(16),
        provider=provider,
        client=client,
        return_url=return_url,
        state_hash=_digest(raw_state),
        expires_at=_utcnow() + FLOW_TTL,
    )
    async with SessionLocal() as db:
        await db.execute(delete(ExternalAuthFlow).where(ExternalAuthFlow.expires_at < _utcnow()))
        db.add(flow)
        await db.commit()
    auth = await _authen_request(
        "GET",
        f"/api/v1/auth/oauth/{provider}/authorize",
        params={"redirect_uri": callback, "state": raw_state},
    )
    return {"authorization_url": auth["authorization_url"]}


@router.get("/oauth/{provider}/callback")
async def oauth_callback(provider: str, request: Request):
    raw_state = request.query_params.get("state", "")
    code = request.query_params.get("code") or request.query_params.get("auth_code")
    if provider not in SUPPORTED_PROVIDERS or not raw_state:
        raise HTTPException(status_code=400, detail="无效的第三方登录回调")

    async with SessionLocal() as db:
        flow = (
            await db.execute(
                select(ExternalAuthFlow)
                .where(ExternalAuthFlow.state_hash == _digest(raw_state))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            flow is None
            or flow.provider != provider
            or flow.state_consumed_at is not None
            or flow.expires_at <= _utcnow()
        ):
            raise HTTPException(status_code=400, detail="登录状态无效或已过期")
        flow.state_consumed_at = _utcnow()
        await db.commit()

    if not code:
        error_url = _append_query(flow.return_url, oauth_error="authorization_cancelled")
        return RedirectResponse(error_url, status_code=303)

    callback = _provider_callback(provider)
    try:
        payload = await _authen_request(
            "POST",
            f"/api/v1/auth/oauth/{provider}",
            json={"code": code, "redirect_uri": callback},
        )
        user_id = str(payload.get("user", {}).get("id", ""))
        if not user_id:
            raise HTTPException(status_code=502, detail="认证服务未返回用户标识")
        await _provision_tenant(user_id)
    except HTTPException:
        return RedirectResponse(
            _append_query(flow.return_url, oauth_error="provider_exchange_failed"),
            status_code=303,
        )

    raw_ticket = secrets.token_urlsafe(32)
    async with SessionLocal() as db:
        locked = (
            await db.execute(
                select(ExternalAuthFlow)
                .where(ExternalAuthFlow.id == flow.id)
                .with_for_update()
            )
        ).scalar_one()
        locked.user_id = user_id
        locked.ticket_hash = _digest(raw_ticket)
        locked.expires_at = _utcnow() + TICKET_TTL
        await db.commit()
    return RedirectResponse(
        _append_query(flow.return_url, oauth_ticket=raw_ticket), status_code=303
    )


@router.post("/oauth/complete")
async def oauth_complete(body: TicketRequest):
    async with SessionLocal() as db:
        flow = (
            await db.execute(
                select(ExternalAuthFlow)
                .where(ExternalAuthFlow.ticket_hash == _digest(body.ticket))
                .with_for_update()
            )
        ).scalar_one_or_none()
        if (
            flow is None
            or not flow.user_id
            or flow.ticket_consumed_at is not None
            or flow.expires_at <= _utcnow()
        ):
            raise HTTPException(status_code=401, detail="登录票据无效或已过期")
        flow.ticket_consumed_at = _utcnow()
        user_id = flow.user_id
        await db.commit()
    tenant_key = await _provision_tenant(user_id)
    return _session_payload(user_id, tenant_key, auth_method="oauth")
