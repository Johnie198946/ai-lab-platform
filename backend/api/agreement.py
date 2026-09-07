"""Public agreement text, authenticated acceptance, and the business-route gate."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.agreement import UserAgreementAcceptance
from backend.services.agreement_authorization import project_acceptance, CURRENT_VERSION, CONTRIBUTION_VERSION, utc

router = APIRouter(tags=["agreement"])
CURRENT_AGREEMENT_VERSION = CURRENT_VERSION
CURRENT_AGREEMENT_LOCALE = "zh-CN"
CURRENT_AGREEMENT_UPDATED_AT = datetime(2026, 9, 6, tzinfo=timezone.utc)
CURRENT_IOS_CLIENT_CONTRACT = "ios-unified-agreement-v1"

_SECTIONS = [
    {
        "id": "service",
        "title": "用户服务协议",
        "clauses": [
            "您在使用本服务前，应仔细阅读并同意本协议全部条款，并依法、诚信使用服务。",
            "您应提供真实、准确、完整的注册信息，妥善保管账号，并对账号下的操作与内容承担相应责任。",
            "服务功能、可用范围和限制以产品实际提供为准；我们会依法保障服务安全与连续性。",
        ],
    },
    {
        "id": "privacy",
        "title": "隐私保护条款",
        "clauses": [
            "我们仅在提供、维护和改进服务所必需的范围内依法收集、使用和保护个人信息，并采取访问控制、加密及审计等安全措施。",
            "个人信息依适用法律和实现处理目的所需期限保存；账号删除申请完成后，依法删除或匿名化，但法律另有保存要求的除外。",
            "未经您的授权，我们不会向无关第三方提供个人信息；法定义务、保护安全或您另行授权的情形除外。",
        ],
    },
    {
        "id": "knowledge-contribution",
        "title": "知识共建协议",
        "clauses": [
            "知识共建仅适用于您接受本版本协议后新建或修改的内容，不回填或追溯处理此前的历史内容。",
            "在权限与安全策略范围内，我们可对适用内容进行整理、分析、展示和推荐，以改进知识组织、检索与服务质量；这些边界不等于转让内容权利。",
            "内容不会因本协议而未经授权自动公开；对外发布仍须遵循独立的权限、审核和发布流程。",
            "知识共建处理同样受数据安全、保存期限、账号删除和适用法律约束。协议版本更新时，旧确认失效，您须阅读并重新确认后方可继续受保护业务。",
        ],
    },
]


class AgreementAcceptanceBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agreement_version: str = Field(min_length=1, max_length=96)
    idempotency_key: UUID
    source: Literal["ios", "web"] = "ios"


def _document() -> dict:
    return {
        "version": CURRENT_AGREEMENT_VERSION,
        "title": "服务协议",
        "updated_at": CURRENT_AGREEMENT_UPDATED_AT.isoformat().replace("+00:00", "Z"),
        "sections": _SECTIONS,
    }


def _etag() -> str:
    canonical = json.dumps(_document(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return '"' + hashlib.sha256(canonical.encode()).hexdigest() + '"'


def _user_id(payload: dict) -> str:
    user_id = str(payload.get("user_id") or payload.get("sub") or "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail={"code": "authenticated_user_required"})
    return user_id


@router.get("/api/v1/legal/agreement", response_model=dict)
async def get_agreement(
    response: Response,
    locale: str = CURRENT_AGREEMENT_LOCALE,
    if_none_match: str | None = Header(default=None),
) -> dict | Response:
    if locale != CURRENT_AGREEMENT_LOCALE:
        raise HTTPException(status_code=404, detail={"code": "agreement_locale_unavailable"})
    etag = _etag()
    response.headers["ETag"] = etag
    if if_none_match:
        candidates = {value.strip().removeprefix("W/") for value in if_none_match.split(",")}
        if "*" in candidates or etag in candidates:
            return Response(status_code=304, headers={"ETag": etag})
    return _document()


@router.get("/api/v1/me/agreement-acceptance")
async def get_acceptance(payload: dict = Depends(require_auth)) -> dict:
    user_id = _user_id(payload)
    async with SessionLocal() as db:
        row = await db.scalar(
            select(UserAgreementAcceptance)
            .where(
                UserAgreementAcceptance.user_id == user_id,
                UserAgreementAcceptance.agreement_version == CURRENT_AGREEMENT_VERSION,
            )
        )
    return {
        "agreement_version": row.agreement_version if row else None,
        "accepted_at": row.accepted_at if row else None,
    }


@router.put("/api/v1/me/agreement-acceptance")
async def put_acceptance(
    body: AgreementAcceptanceBody, payload: dict = Depends(require_auth)
) -> dict:
    user_id = _user_id(payload)
    key = str(body.idempotency_key)
    # One transaction: acceptance + both contribution prerequisites. A failed
    # projection cannot leave an apparently successful acceptance behind.
    for attempt in range(3):
        async with SessionLocal() as db:
            try:
                existing = await db.scalar(select(UserAgreementAcceptance).where(
                    UserAgreementAcceptance.user_id == user_id,
                    UserAgreementAcceptance.idempotency_key == key,
                ))
                if existing and existing.agreement_version != body.agreement_version:
                    raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
                if body.agreement_version != CURRENT_AGREEMENT_VERSION:
                    raise HTTPException(status_code=409, detail={
                        "code": "agreement_version_outdated", "current_version": CURRENT_AGREEMENT_VERSION,
                    })
                if not existing:
                    existing = await db.scalar(select(UserAgreementAcceptance).where(
                        UserAgreementAcceptance.user_id == user_id,
                        UserAgreementAcceptance.agreement_version == body.agreement_version,
                    ))
                if not existing:
                    existing = UserAgreementAcceptance(
                        user_id=user_id, agreement_version=body.agreement_version,
                        locale=CURRENT_AGREEMENT_LOCALE, source=body.source, idempotency_key=key,
                    )
                    db.add(existing)
                    await db.flush()
                report = await project_acceptance(
                    db, acceptance=existing, tenant_key=str(payload.get("tenant_key") or ""),
                )
                if report["status"] != "ready":
                    raise HTTPException(status_code=409, detail={
                        "code": "agreement_authorization_conflict", "reason": report["status"],
                    })
                await db.commit()
                return {"agreement_version": existing.agreement_version, "accepted_at": existing.accepted_at}
            except IntegrityError:
                await db.rollback()
                if attempt == 2:
                    raise
            except ValueError as exc:
                raise HTTPException(status_code=409, detail={
                    "code": "agreement_authorization_conflict", "reason": str(exc),
                }) from exc
    raise RuntimeError("acceptance retry exhausted")


async def require_current_agreement(
    payload: dict = Depends(require_auth),
    client_contract: str | None = Header(default=None, alias="X-Client-Contract"),
) -> dict:
    # Neither legacy JWTs, headers nor rollout environment can waive consent.
    # This is deliberately a DB read on every protected request, not a JWT claim.
    user_id = _user_id(payload)
    async with SessionLocal() as db:
        accepted = await db.scalar(select(UserAgreementAcceptance).where(
            UserAgreementAcceptance.user_id == user_id,
            UserAgreementAcceptance.agreement_version == CURRENT_AGREEMENT_VERSION,
            UserAgreementAcceptance.accepted_at <= datetime.now(timezone.utc),
        ))
        if accepted is not None:
            from backend.models.knowledge_contribution import (
                KnowledgeContributionPolicy as Policy, KnowledgeContributionUserConsent as Consent,
            )
            tenant = str(payload.get("tenant_key") or "")
            policy = await db.get(Policy, tenant)
            consent = await db.get(Consent, (tenant, user_id))
            if (policy is not None and not policy.enabled) or (consent is not None and not consent.participation_enabled):
                raise HTTPException(status_code=428, detail={
                    "code": "agreement_participation_withdrawn", "current_version": CURRENT_AGREEMENT_VERSION,
                })
            now = datetime.now(timezone.utc)
            if (policy is None or consent is None
                    or policy.agreement_version != CONTRIBUTION_VERSION or policy.historical_backfill
                    or not policy.effective_at or utc(policy.effective_at) > now
                    or consent.service_agreement_version != CONTRIBUTION_VERSION
                    or not consent.participation_effective_at
                    or not (utc(accepted.accepted_at) <= utc(consent.participation_effective_at) <= now)):
                raise HTTPException(status_code=428, detail={
                    "code": "agreement_authorization_required", "current_version": CURRENT_AGREEMENT_VERSION,
                })
    if accepted is None:
        raise HTTPException(status_code=428, detail={
            "code": "agreement_required",
            "current_version": CURRENT_AGREEMENT_VERSION,
        })
    return payload
