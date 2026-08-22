"""Independent CustomerDemand API used by the S3/S4 Showroom journey."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from backend.api.auth import require_auth
from backend.db import SessionLocal
from backend.models.customer_demand import CustomerDemand

router = APIRouter(prefix="/api/v1/demands", tags=["customer-demands"])

ShortItem = Annotated[str, Field(min_length=1, max_length=500)]


class DemandCreate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_text: str = Field(..., min_length=1, max_length=12000)
    business_scene: str = Field(default="", max_length=500)
    overall_goal: str = Field(default="", max_length=1000)
    stakeholders: list[ShortItem] = Field(default_factory=list, max_length=50)
    requirement_items: list[ShortItem] = Field(default_factory=list, max_length=100)
    conflict_notes: list[ShortItem] = Field(default_factory=list, max_length=50)
    constraints: list[ShortItem] = Field(default_factory=list, max_length=50)
    acceptance_criteria: list[ShortItem] = Field(default_factory=list, max_length=50)
    showroom_session_id: str | None = Field(default=None, max_length=120)


class DemandPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_text: str | None = Field(default=None, min_length=1, max_length=12000)
    business_scene: str | None = Field(default=None, max_length=500)
    overall_goal: str | None = Field(default=None, max_length=1000)
    stakeholders: list[ShortItem] | None = Field(default=None, max_length=50)
    requirement_items: list[ShortItem] | None = Field(default=None, max_length=100)
    conflict_notes: list[ShortItem] | None = Field(default=None, max_length=50)
    constraints: list[ShortItem] | None = Field(default=None, max_length=50)
    acceptance_criteria: list[ShortItem] | None = Field(default=None, max_length=50)
    expected_version: int = Field(..., ge=1)


class DemandConfirm(BaseModel):
    model_config = ConfigDict(extra="ignore")

    expected_version: int = Field(..., ge=1)


def _identity(payload: dict[str, Any]) -> tuple[str, str]:
    tenant = str(payload.get("tenant_key") or "")
    user = str(payload.get("user_id") or payload.get("sub") or "")
    if tenant == "demo" and not user:
        user = str(payload.get("username") or "dev")
    if not tenant or not user:
        raise HTTPException(status_code=401, detail="认证身份缺少租户或用户")
    return tenant, user


def _source_hash(text: str) -> str:
    return hashlib.sha256(text.strip().encode("utf-8")).hexdigest()


def _serialize(row: CustomerDemand) -> dict[str, Any]:
    return {
        "demand_id": row.demand_id, "tenant_key": row.tenant_key, "created_by": row.created_by,
        "source_text": row.source_text, "source_hash": row.source_hash,
        "business_scene": row.business_scene, "overall_goal": row.overall_goal,
        "stakeholders": row.stakeholders, "requirement_items": row.requirement_items,
        "conflict_notes": row.conflict_notes, "constraints": row.constraints,
        "acceptance_criteria": row.acceptance_criteria, "status": row.status,
        "version": row.version, "showroom_session_id": row.showroom_session_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "confirmed_at": row.confirmed_at.isoformat() if row.confirmed_at else None,
    }


async def _owned(demand_id: str, payload: dict[str, Any], db) -> CustomerDemand:
    tenant, _ = _identity(payload)
    row = (await db.execute(select(CustomerDemand).where(
        CustomerDemand.demand_id == demand_id, CustomerDemand.tenant_key == tenant
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="需求不存在")
    return row


@router.post("", status_code=201)
async def create_demand(body: DemandCreate, payload: dict[str, Any] = Depends(require_auth)):
    tenant, user = _identity(payload)
    source_hash = _source_hash(body.source_text)
    async with SessionLocal() as db:
        existing = (await db.execute(select(CustomerDemand).where(
            CustomerDemand.tenant_key == tenant, CustomerDemand.source_hash == source_hash
        ))).scalar_one_or_none()
        if existing is not None:
            return _serialize(existing)
        row = CustomerDemand(
            demand_id="dmd_" + uuid.uuid4().hex[:20], tenant_key=tenant, created_by=user,
            source_text=body.source_text.strip(), source_hash=source_hash,
            **body.model_dump(exclude={"source_text"}),
        )
        db.add(row)
        try:
            await db.commit()
        except IntegrityError:
            await db.rollback()
            existing = (await db.execute(select(CustomerDemand).where(
                CustomerDemand.tenant_key == tenant, CustomerDemand.source_hash == source_hash
            ))).scalar_one()
            return _serialize(existing)
        await db.refresh(row)
        return _serialize(row)


@router.get("/{demand_id}")
async def get_demand(demand_id: str, payload: dict[str, Any] = Depends(require_auth)):
    async with SessionLocal() as db:
        return _serialize(await _owned(demand_id, payload, db))


@router.patch("/{demand_id}")
async def patch_demand(demand_id: str, body: DemandPatch, payload: dict[str, Any] = Depends(require_auth)):
    async with SessionLocal() as db:
        row = await _owned(demand_id, payload, db)
        changes = body.model_dump(exclude_none=True)
        expected_version = changes.pop("expected_version")
        values = {
            key: value.strip() if key == "source_text" else value
            for key, value in changes.items()
        }
        if "source_text" in changes:
            values["source_hash"] = _source_hash(values["source_text"])
        values["version"] = expected_version + 1
        try:
            result = await db.execute(
                update(CustomerDemand)
                .where(
                    CustomerDemand.demand_id == demand_id,
                    CustomerDemand.tenant_key == row.tenant_key,
                    CustomerDemand.status == "draft",
                    CustomerDemand.version == expected_version,
                )
                .values(**values)
            )
            if result.rowcount != 1:
                await db.rollback()
                raise HTTPException(status_code=409, detail="需求版本已变更或已确认")
            await db.commit()
        except IntegrityError as error:
            await db.rollback()
            if "source_hash" in str(error).lower() or "ix_customer_demands_tenant_source_hash" in str(error):
                raise HTTPException(status_code=409, detail="source_hash 已被其他需求占用") from error
            raise
        await db.refresh(row)
        return _serialize(row)


@router.post("/{demand_id}/confirm")
async def confirm_demand(
    demand_id: str,
    body: DemandConfirm,
    payload: dict[str, Any] = Depends(require_auth),
):
    async with SessionLocal() as db:
        row = await _owned(demand_id, payload, db)
        result = await db.execute(
            update(CustomerDemand)
            .where(
                CustomerDemand.demand_id == demand_id,
                CustomerDemand.tenant_key == row.tenant_key,
                CustomerDemand.status == "draft",
                CustomerDemand.version == body.expected_version,
            )
            .values(
                status="confirmed",
                confirmed_at=datetime.now(timezone.utc),
                version=body.expected_version + 1,
            )
        )
        if result.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="需求版本已变更或已确认")
        await db.commit()
        await db.refresh(row)
        return _serialize(row)
