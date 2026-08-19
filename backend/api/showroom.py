"""展厅多屏运行态 API。

提供同一后端进程内的 2PC 阶段同步、WebSocket 广播与 IPD 人工评审记录。
物理展厅只有一套全局运行态；重启后安全回到站 1，前端保留离线演示兜底。
"""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import os
import re
import uuid
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
from backend.services.demand_document import (
    calculate_demand_completeness,
    extract_demand_document,
)
from backend.services.feishu import send_feishu_async
from backend.services.visitor_insight import (
    extract_visitor_insight,
    persist_visitor_wiki,
)

router = APIRouter(prefix="/api/showroom", tags=["showroom"])
CONTENT_FILE = (
    Path(__file__).resolve().parent.parent.parent
    / "config"
    / "showroom"
    / "content.yaml"
)
RUNTIME_ID = "venue"
PERSONA_SKILL_PATH = Path(
    "/root/.hermes/skills/productivity/solution-consultant-persona/SKILL.md"
)
PERSONA_MIN_VERSION = (1, 7, 0)


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
    status: Literal["active", "completed", "submitted", "archived"] | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class DemandConfirmation(BaseModel):
    demand: dict[str, Any]


class DemandExtractionRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=30_000)
    hermes_stored_session_id: str = Field(default="", max_length=200)


class DemandDraftPatch(BaseModel):
    demand: dict[str, Any] = Field(default_factory=dict)
    manual_fields: list[str] = Field(default_factory=list, max_length=20)


class SessionMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., min_length=1, max_length=12000)


class ArtifactUpdate(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    content: dict[str, Any] = Field(default_factory=dict)


class VisitorPerson(BaseModel):
    name: str = Field(default="", max_length=120)
    title: str = Field(default="", max_length=120)


class VisitorPatch(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=160)
    customer_code: str = Field(default="", max_length=24)
    visitors: list[VisitorPerson] = Field(default_factory=list, max_length=20)
    visit_type: Literal["first", "return"] = "first"
    allow_history: bool = False
    history_session_id: str = Field(default="", max_length=120)
    purpose: str = Field(default="", max_length=2000)
    focus_topics: list[str] = Field(default_factory=list, max_length=20)


class VisitorInsightRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=60_000)
    hermes_stored_session_id: str = Field(default="", max_length=200)


class FrontstageRequest(BaseModel):
    message_count: int = Field(default=0, ge=0, le=100_000)


class VisitCompleteRequest(BaseModel):
    source: str = Field(default="controller", max_length=80)


class VisitRolloverRequest(BaseModel):
    epoch: int = Field(default=0, ge=0)


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
            "active_main_session_id": "",
            "active_main_tenant_key": "",
        }
        self.switch_ready: set[int] = set()

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
SESSION_DATA_VERSION = "showroom-visitor-v17"

LEGACY_MESSAGES = [
    {
        "role": "assistant",
        "content": (
            "您提到“换模慢”。更影响经营结果的是停机时间、良品率，还是订单交付周期？"
        ),
    },
    {
        "role": "user",
        "content": "主要是停机。现在换一次模具要 45 分钟，老师傅经验也很难复制。",
    },
    {"role": "assistant", "content": "如果三个月内完成第一阶段，您希望达到什么结果？"},
    {"role": "user", "content": "先降到 20 分钟以内，让新员工也能按标准完成。"},
]
LEGACY_DEMAND = {
    "confirmed": False,
    "completeness": 86,
    "industry": "制造业",
    "core_problem": "换模依赖老师傅经验，停机时间长且标准难以复制",
    "target_metric": "45 分钟 → 20 分钟内",
    "cycle": "12 周",
    "users": "班组长 / 新员工",
    "solution": "换模辅助工作台",
    "next_action": "采集一条典型产线的 20 次换模过程，建立动作基线",
}
LEGACY_PROTOTYPE = {
    "title": "换模辅助工作台 V1",
    "goal": "通过步骤引导和实时计时，将换模过程标准化",
    "target_time": "20:00",
    "elapsed": "06:42",
    "progress": 33,
}
LEGACY_INSIGHT = {
    "title": "不是“换模慢”，而是经验没有成为组织能力。",
    "judgment": "经验隐性化是首要根因",
    "gap": "25 min",
    "recommendation": "先验证 1 条产线",
    "causes": [
        {"title": "经验隐性化", "detail": "关键动作仅掌握在老师傅手中"},
        {"title": "过程不可见", "detail": "没有步骤耗时与异常数据"},
        {"title": "反馈未闭环", "detail": "换模结束后缺少结构化复盘"},
    ],
    "impacts": [
        {"label": "产线停机损失", "score": 92},
        {"label": "人员培养周期", "score": 76},
        {"label": "交付稳定性", "score": 62},
        {"label": "质量追溯成本", "score": 54},
    ],
    "evidence": [
        ["现场访谈", "关键动作依赖老师傅口授", "高", "已验证"],
        ["换模记录", "平均耗时 45 分钟", "中高", "已采集"],
        ["步骤级数据", "尚无统一埋点与异常分类", "—", "待补齐"],
        ["新员工测试", "独立完成率尚未量化", "低", "待验证"],
    ],
}


def _empty_demand() -> dict[str, Any]:
    return {
        "confirmed": False,
        "completeness": 0,
        "industry": "",
        "core_problem": "",
        "target_metric": "",
        "cycle": "",
        "users": "",
        "solution": "",
        "next_action": "",
        "facts": [],
        "non_goals": [],
        "constraints": [],
        "acceptance_criteria": [],
        "solution_directions": [],
    }


def _empty_demand_interview() -> dict[str, Any]:
    return {
        "status": "collecting",
        "followup_count": 0,
        "dimensions": {
            "business_scene": "",
            "user_role": "",
            "current_blocker": "",
            "target_outcome": "",
        },
        "missing": [
            "business_scene",
            "user_role",
            "current_blocker",
            "target_outcome",
        ],
        "policy_version": "1.7.0",
    }


def _empty_hermes_sessions() -> dict[str, Any]:
    return {
        "backstage_stored_session_id": "",
        "frontstage_stored_session_id": "",
        "backstage_skill_initialized": False,
        "frontstage_skill_initialized": False,
        "backstage_skill_version": "1.7.0",
        "frontstage_skill_version": "1.7.0",
    }


def _skill_details(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
        match = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
        metadata = yaml.safe_load(match.group(1)) if match else {}
        return {
            "name": str((metadata or {}).get("name") or "").strip(),
            "version": str((metadata or {}).get("version") or "").strip(),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        }
    except Exception:
        return {"name": "", "version": "", "sha256": ""}


def _persona_metadata() -> dict[str, Any]:
    path = Path(os.environ.get("SHOWROOM_PERSONA_SKILL_PATH", str(PERSONA_SKILL_PATH)))
    formal = _skill_details(path)
    version, digest = formal["version"], formal["sha256"]
    skills_root = next((parent for parent in path.parents if parent.name == "skills"), None)
    all_skill_files = (
        sorted(skills_root.rglob("SKILL.md"))
        if skills_root and skills_root.is_dir()
        else ([path] if path.is_file() else [])
    )
    candidate_meta = []
    for candidate in all_skill_files:
        details = _skill_details(candidate)
        if candidate == path or details["name"] == "solution-consultant-persona":
            candidate_meta.append({"path": str(candidate), **details})
    parts = tuple(int(part) for part in re.findall(r"\d+", version)[:3])
    normalized = parts + (0,) * (3 - len(parts))
    duplicate_count = max(0, len(candidate_meta) - 1)
    return {
        "name": "solution-consultant-persona",
        "version": version,
        "disk_version": version,
        "resolved_version": version if duplicate_count == 0 else "",
        "sha256": digest,
        "available": path.is_file(),
        "compatible": normalized >= PERSONA_MIN_VERSION and duplicate_count == 0,
        "path": str(path),
        "minimum_version": "1.7.0",
        "duplicate_count": duplicate_count,
        "candidates": candidate_meta,
    }


def _empty_visitor() -> dict[str, Any]:
    return {
        "visit_id": "",
        "customer_code": "",
        "company_name": "",
        "visitors": [],
        "visit_type": "first",
        "allow_history": False,
        "history_session_id": "",
        "purpose": "",
        "focus_topics": [],
        "status": "preparing",
    }


def _empty_customer_insight() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "status": "idle",
        "summary": {},
        "sources": [],
        "warnings": [],
        "public_wiki_slug": "",
        "private_record_path": "",
        "source_hash": "",
        "updated_at": "",
    }


def _visit_session_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"visit-{timestamp}-{uuid.uuid4().hex[:8]}"


def _customer_code(company_name: str) -> str:
    digest = int.from_bytes(company_name.encode("utf-8"), "little", signed=False) % 1000
    return f"C{digest:03d}"


def _migrate_legacy_session_data(
    raw: dict[str, Any] | None,
) -> tuple[dict[str, Any], bool]:
    """Remove only the exact legacy showroom seed while preserving real edits."""
    data = copy.deepcopy(raw or {})
    changed = False
    messages = list(data.get("messages") or [])
    legacy_count = len(LEGACY_MESSAGES)
    if len(messages) >= legacy_count and messages[:legacy_count] == LEGACY_MESSAGES:
        data["messages"] = messages[len(LEGACY_MESSAGES) :]
        changed = True
    if data.get("demand") == LEGACY_DEMAND:
        data["demand"] = _empty_demand()
        changed = True
    if data.get("insight") == LEGACY_INSIGHT:
        data["insight"] = {}
        changed = True
    if data.get("prototype") == LEGACY_PROTOTYPE:
        data["prototype"] = {}
        changed = True
    if changed and data.get("role") == "业务负责人":
        data["role"] = ""
    if data.get("schema_version") != SESSION_DATA_VERSION:
        data["schema_version"] = SESSION_DATA_VERSION
        changed = True
    defaults = _initial_session_data("main")
    for key in (
        "visitor",
        "customer_insight",
        "hermes_sessions",
        "demand_interview",
        "host_greeting_initialized",
        "frontstage_started",
        "frontstage_message_offset",
        "persona_skill_version",
    ):
        if key not in data:
            data[key] = copy.deepcopy(defaults[key])
            changed = True
    hermes_sessions = _merge(
        _empty_hermes_sessions(), data.get("hermes_sessions") or {}
    )
    legacy_stored_id = str(data.get("hermes_stored_session_id") or "").strip()
    if legacy_stored_id and not hermes_sessions.get("backstage_stored_session_id"):
        hermes_sessions["backstage_stored_session_id"] = legacy_stored_id
        hermes_sessions["backstage_skill_initialized"] = bool(
            data.get("hermes_skill_initialized")
        )
    if hermes_sessions != data.get("hermes_sessions"):
        data["hermes_sessions"] = hermes_sessions
        changed = True
    return data, changed


def _merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    """递归合并前端业务数据，避免局部保存覆盖整份需求或报告。"""
    result = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)
    return result


DEMAND_STATE_PATTERN = re.compile(
    r"<!--\s*AI_LAB_DEMAND_STATE_V1\s*(\{[\s\S]*?\})\s*AI_LAB_DEMAND_STATE_V1\s*-->",
    re.IGNORECASE,
)
DEMAND_DIMENSIONS = (
    "business_scene",
    "user_role",
    "current_blocker",
    "target_outcome",
)


def _extract_demand_interview_state(
    content: str, current: dict[str, Any] | None = None
) -> tuple[dict[str, Any], bool]:
    state = _merge(_empty_demand_interview(), current or {})
    match = DEMAND_STATE_PATTERN.search(content)
    if not match:
        return state, False
    try:
        payload = json.loads(match.group(1))
    except (TypeError, ValueError):
        return state, False
    supplied = payload.get("dimensions") if isinstance(payload, dict) else {}
    dimensions = copy.deepcopy(state["dimensions"])
    if isinstance(supplied, dict):
        for key in DEMAND_DIMENSIONS:
            value = str(supplied.get(key) or "").strip()[:2_000]
            if value:
                dimensions[key] = value
    state["dimensions"] = dimensions
    state["followup_count"] = min(3, int(state.get("followup_count") or 0) + 1)
    state["missing"] = [key for key in DEMAND_DIMENSIONS if not dimensions.get(key)]
    requested_status = str(payload.get("status") or "").strip()
    if not state["missing"]:
        state["status"] = "ready"
    elif state["followup_count"] >= 3:
        state["status"] = "draft"
    elif requested_status in {"collecting", "ready", "draft"}:
        state["status"] = requested_status
    state["policy_version"] = "1.7.0"
    return state, True


def _initial_session_data(slot: str) -> dict[str, Any]:
    data = {
        "role": "",
        "messages": [],
        "demand": _empty_demand(),
        "demand_document": {},
        "insight": {},
        "prototype": {},
        "artifacts": {},
        "reviews": {},
        "schema_version": SESSION_DATA_VERSION,
    }
    if slot == "main":
        data.update(
            {
                "visitor": _empty_visitor(),
                "customer_insight": _empty_customer_insight(),
                "hermes_sessions": _empty_hermes_sessions(),
                "demand_interview": _empty_demand_interview(),
                "hermes_stored_session_id": "",
                "hermes_skill_initialized": False,
                "host_greeting_initialized": False,
                "frontstage_started": False,
                "frontstage_message_offset": 0,
                "persona_skill_version": _persona_metadata()["version"],
            }
        )
    return data


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
        else:
            migrated, changed = _migrate_legacy_session_data(row.data)
            if changed:
                row.data = migrated
                await database.commit()
                await database.refresh(row)
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


async def _active_main_session(tenant_key: str) -> ShowroomSession:
    """Return the tenant's single current guided-tour session."""
    await _ensure_runtime_hydrated()
    session_id = str(hub.state.get("active_main_session_id") or "")
    owner = str(hub.state.get("active_main_tenant_key") or "")
    if session_id and owner == tenant_key:
        async with SessionLocal() as database:
            row = await database.get(ShowroomSession, session_id)
            if (
                row is not None
                and row.tenant_key == tenant_key
                and row.status != "archived"
            ):
                return row

    metadata = _persona_metadata()
    if not metadata["compatible"]:
        duplicate_detail = (
            f"；检测到 {metadata['duplicate_count']} 份同名副本，已阻止不确定解析"
            if metadata.get("duplicate_count")
            else ""
        )
        raise HTTPException(
            status_code=503,
            detail=(
                "主演示要求 solution-consultant-persona >= 1.7.0，当前版本："
                f"{metadata['version'] or '未安装'}{duplicate_detail}"
            ),
        )
    session_id = _visit_session_id()
    row = await _get_or_create_session(session_id, "main", tenant_key)
    data = copy.deepcopy(row.data or {})
    data["visitor"]["visit_id"] = session_id
    data["persona_skill_version"] = metadata["version"]
    async with SessionLocal() as database:
        stored = await database.get(ShowroomSession, session_id)
        stored.data = data
        await database.commit()
        await database.refresh(stored)
        row = stored
    hub.state["active_main_session_id"] = session_id
    hub.state["active_main_tenant_key"] = tenant_key
    hub.state["updated_at"] = datetime.now(timezone.utc).isoformat()
    await _persist_runtime()
    return row


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
        session = (
            await _active_main_session(tenant_key)
            if slot == "main"
            else await _get_or_create_session(session_id, slot, tenant_key)
        )
        session_id = session.session_id
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

    persona = _persona_metadata()
    return {
        "contract_version": "2026-08-19",
        "screens": screens,
        "content": content_manifest,
        "runtime": hub.snapshot(),
        "session": session_data,
        "active_main_session_id": hub.state.get("active_main_session_id", ""),
        "visitor": session_data.get("data", {}).get("visitor", {}),
        "persona_skill": persona,
        "knowledge": knowledge,
        "centers": centers,
        "capabilities": {
            "chat_stream": "/api/chat/stream",
            "hermes_gateway": "/api/ws",
            "hermes_serve_token": "/api/v1/hermes/serve-token",
            "knowledge_search": "/api/knowledge/search",
            "review": "/api/showroom/reviews/{gate}",
            "session_write": True,
            "runtime_persistence": True,
            "visitor_insight": True,
            "wiki_write": True,
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


@router.post("/visits")
async def create_showroom_visit(payload=Depends(require_auth)) -> dict[str, Any]:
    metadata = _persona_metadata()
    if not metadata["compatible"]:
        raise HTTPException(status_code=503, detail="拟人 V1.7 技能未安装或版本过低")
    tenant_key = str(payload.get("tenant_key") or "demo")
    row = await _active_main_session(tenant_key)
    return _session_payload(row, row.session_id, "main")


@router.patch("/visits/{session_id}/visitor")
async def update_showroom_visitor(
    session_id: str, body: VisitorPatch, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key or row.slot != "main":
            raise HTTPException(status_code=404, detail="主演示会话不存在")
        company_name = body.company_name.strip()
        if not company_name or any(char in company_name for char in "<>\x00"):
            raise HTTPException(status_code=422, detail="公司名称格式无效")
        if body.allow_history and body.visit_type != "return":
            raise HTTPException(status_code=422, detail="首次来访不能读取历史 Session")
        if body.allow_history:
            historical = await database.get(ShowroomSession, body.history_session_id)
            if (
                historical is None
                or historical.tenant_key != tenant_key
                or historical.status != "archived"
            ):
                raise HTTPException(
                    status_code=422, detail="请指定同租户已归档的精确历史 Session"
                )
        visitor = _merge(_empty_visitor(), body.model_dump())
        visitor["visit_id"] = (row.data or {}).get("visitor", {}).get(
            "visit_id"
        ) or session_id
        visitor["customer_code"] = body.customer_code.strip() or _customer_code(
            company_name
        )
        visitor["focus_topics"] = [
            str(item).strip()[:160] for item in body.focus_topics if str(item).strip()
        ]
        visitor["status"] = "researching"
        data = copy.deepcopy(row.data or {})
        data["visitor"] = visitor
        data["customer_insight"] = _merge(
            _empty_customer_insight(), {"status": "running"}
        )
        row.data = data
        await database.commit()
        await database.refresh(row)
    message = {
        "type": "VISITOR_UPDATED",
        "session_id": session_id,
        "epoch": hub.state.get("epoch", 0),
        "visitor": visitor,
    }
    await hub.broadcast(message)
    return _session_payload(row, session_id, "main")


@router.post("/visits/{session_id}/insight/extract")
async def extract_showroom_visitor_insight(
    session_id: str, body: VisitorInsightRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key or row.slot != "main":
            raise HTTPException(status_code=404, detail="主演示会话不存在")
        data = copy.deepcopy(row.data or {})
        stored_id = str(
            (data.get("hermes_sessions") or {}).get("backstage_stored_session_id")
            or data.get("hermes_stored_session_id")
            or ""
        )
        if (
            stored_id
            and body.hermes_stored_session_id
            and stored_id != body.hermes_stored_session_id
        ):
            raise HTTPException(status_code=409, detail="Hermes 会话与当前接待不匹配")
        extraction = extract_visitor_insight(body.content)
        if not extraction.get("recognized"):
            return {
                "recognized": False,
                "reason": extraction.get("reason"),
                "session": _session_payload(row, session_id, "main"),
            }
        current = data.get("customer_insight") or {}
        if current.get("source_hash") == extraction["source_hash"]:
            return {
                "recognized": True,
                "unchanged": True,
                "session": _session_payload(row, session_id, "main"),
            }
        insight = _merge(_empty_customer_insight(), extraction)
        insight.pop("raw_content", None)
        paths = persist_visitor_wiki(
            tenant_key=tenant_key, visitor=data.get("visitor") or {}, insight=insight
        )
        insight.update(paths)
        insight["status"] = "completed" if insight.get("sources") else "partial"
        insight["updated_at"] = datetime.now(timezone.utc).isoformat()
        data["customer_insight"] = insight
        data["visitor"] = _merge(data.get("visitor") or {}, {"status": "ready"})
        row.data = data
        await database.commit()
        await database.refresh(row)
    try:
        from backend.api.knowledge import _matrix

        _matrix.cache_clear()
    except Exception:
        pass
    await hub.broadcast(
        {
            "type": "INSIGHT_UPDATED",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "customer_insight": insight,
        }
    )
    return {"recognized": True, "session": _session_payload(row, session_id, "main")}


@router.post("/visits/{session_id}/frontstage")
async def activate_showroom_frontstage(
    session_id: str, body: FrontstageRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key or row.slot != "main":
            raise HTTPException(status_code=404, detail="主演示会话不存在")
        data = copy.deepcopy(row.data or {})
        visitor = data.get("visitor") or {}
        if not visitor.get("company_name"):
            raise HTTPException(status_code=409, detail="主控台尚未录入来访客户")
        if visitor.get("visit_type") == "first" and visitor.get("allow_history"):
            raise HTTPException(status_code=422, detail="首次来访禁止读取历史 Session")
        data["frontstage_message_offset"] = max(
            int(data.get("frontstage_message_offset") or 0), body.message_count
        )
        data["frontstage_started"] = True
        data["visitor"] = _merge(visitor, {"status": "in_tour"})
        row.data = data
        await database.commit()
        await database.refresh(row)
    insight = data.get("customer_insight") or {}
    paths = [
        path
        for path in [
            insight.get("public_wiki_slug"),
            insight.get("private_record_path"),
        ]
        if path
    ]
    context = "\n".join(
        [
            "当前模式：frontstage（站 3 需求问诊）。",
            "当前来访客户："
            f"{visitor.get('customer_code')} · {visitor.get('company_name')}",
            f"访问目的：{visitor.get('purpose') or '未录入'}",
            f"关注方向：{'、'.join(visitor.get('focus_topics') or []) or '未录入'}",
            f"仅允许读取这些背景路径：{', '.join(paths) or '暂无已核验背景'}",
            "请静默读取允许的背景，自然欢迎客户并进入需求问诊。禁止复述后台洞察，禁止声称提前研究过贵司。",
            "严格收敛业务场景、用户角色、当前阻碍、目标结果；最多追问三轮，第三轮必须用TBD补齐并输出需求确认单。",
            "站3禁止输出完整方案。需求确认后引导进入屏幕04深度洞察，再到屏幕05/06完成001 IPD实践。",
        ]
    )
    return {
        "session": _session_payload(row, session_id, "main"),
        "station_context": context,
    }


@router.post("/visits/{session_id}/complete")
async def complete_showroom_visit(
    session_id: str, body: VisitCompleteRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key or row.slot != "main":
            raise HTTPException(status_code=404, detail="主演示会话不存在")
        data = copy.deepcopy(row.data or {})
        data["visitor"] = _merge(
            data.get("visitor") or {}, {"status": "awaiting_rollover"}
        )
        data["visit_completed_by"] = body.source
        data["visit_completed_at"] = datetime.now(timezone.utc).isoformat()
        row.data = data
        await database.commit()
        await database.refresh(row)
    await hub.broadcast(
        {
            "type": "VISIT_COMPLETE",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "visitor": data.get("visitor"),
            "wiki": data.get("customer_insight"),
        }
    )
    return _session_payload(row, session_id, "main")


@router.post("/visits/{session_id}/rollover")
async def rollover_showroom_visit(
    session_id: str, body: VisitRolloverRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    epoch = max(
        body.epoch,
        int(hub.state.get("epoch") or 0) + 1,
        int(datetime.now(timezone.utc).timestamp() * 1000),
    )
    hub.switch_ready.clear()
    await hub.broadcast(
        {"type": "SESSION_SWITCH_PREPARE", "session_id": session_id, "epoch": epoch}
    )
    targets = {
        id(socket) for socket, client in hub.connections.items() if client == session_id
    }
    for _ in range(20):
        if targets.issubset(hub.switch_ready):
            break
        await asyncio.sleep(0.25)
    async with SessionLocal() as database:
        old = await database.get(ShowroomSession, session_id)
        if old is None or old.tenant_key != tenant_key or old.slot != "main":
            raise HTTPException(status_code=404, detail="主演示会话不存在")
        old.status = "archived"
        old_data = copy.deepcopy(old.data or {})
        old_data["visitor"] = _merge(
            old_data.get("visitor") or {}, {"status": "archived"}
        )
        old.data = old_data
        new_id = _visit_session_id()
        new_data = _initial_session_data("main")
        new_data["visitor"]["visit_id"] = new_id
        database.add(
            ShowroomSession(
                session_id=new_id, tenant_key=tenant_key, slot="main", data=new_data
            )
        )
        await database.commit()
        new = await database.get(ShowroomSession, new_id)
    hub.state.update(
        {
            "active_main_session_id": new_id,
            "active_main_tenant_key": tenant_key,
            "epoch": epoch,
            "stage": "station-1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    await _persist_runtime()
    await hub.broadcast(
        {
            "type": "SESSION_SWITCH_COMMIT",
            "session_id": session_id,
            "new_session_id": new_id,
            "epoch": epoch,
            "state": hub.snapshot(),
        }
    )
    return {
        "archived_session_id": session_id,
        "session": _session_payload(new, new_id, "main"),
        "runtime": hub.snapshot(),
    }


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
        document = copy.deepcopy((row.data or {}).get("demand_document") or {})
        if document:
            document["status"] = "confirmed"
            document["confirmed_at"] = demand["confirmed_at"]
        data = _merge(
            row.data or {},
            {
                "demand": demand,
                "demand_document": document,
                "demand_interview": _merge(
                    (row.data or {}).get("demand_interview") or _empty_demand_interview(),
                    {"status": "confirmed", "missing": []},
                ),
            },
        )
        row.data = data
        row.step = max(row.step, 2)
        await database.commit()
        await database.refresh(row)
        return _session_payload(row, session_id, row.slot)


@router.post("/sessions/{session_id}/demand/extract")
async def extract_showroom_demand(
    session_id: str,
    body: DemandExtractionRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    """Recognize a completed Hermes confirmation sheet and persist a draft."""
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")

        data = copy.deepcopy(row.data or {})
        stored_id = str(
            (data.get("hermes_sessions") or {}).get("frontstage_stored_session_id")
            or data.get("hermes_stored_session_id")
            or ""
        ).strip()
        requested_stored_id = body.hermes_stored_session_id.strip()
        if stored_id and requested_stored_id and stored_id != requested_stored_id:
            raise HTTPException(
                status_code=409, detail="Hermes 会话与当前体验会话不匹配"
            )

        interview, state_recognized = _extract_demand_interview_state(
            body.content, data.get("demand_interview")
        )
        if state_recognized:
            data["demand_interview"] = interview

        extraction = extract_demand_document(body.content)
        if not extraction["recognized"]:
            if state_recognized:
                row.data = data
                await database.commit()
                await database.refresh(row)
            return {
                "recognized": False,
                "state_recognized": state_recognized,
                "demand_interview": interview,
                "reason": extraction["reason"],
                "session": _session_payload(row, session_id, row.slot),
            }

        current_demand = copy.deepcopy(data.get("demand") or _empty_demand())
        current_document = copy.deepcopy(data.get("demand_document") or {})
        if (
            current_demand.get("confirmed")
            or current_document.get("status") == "confirmed"
        ):
            return {
                "recognized": True,
                "locked": True,
                "session": _session_payload(row, session_id, row.slot),
            }
        if current_document.get("source_hash") == extraction["source_hash"]:
            return {
                "recognized": True,
                "unchanged": True,
                "session": _session_payload(row, session_id, row.slot),
            }

        manual_fields = {
            str(field)
            for field in current_document.get("manual_fields") or []
            if isinstance(field, str)
        }
        demand = _merge(_empty_demand(), extraction["demand"])
        for field in manual_fields:
            if field in current_demand:
                demand[field] = copy.deepcopy(current_demand[field])
        demand["completeness"] = calculate_demand_completeness(demand)
        demand["confirmed"] = False

        document = extraction["demand_document"]
        document["manual_fields"] = sorted(manual_fields)
        interview["status"] = "draft"
        interview["missing"] = []
        row.data = _merge(
            data,
            {
                "demand": demand,
                "demand_document": document,
                "demand_interview": interview,
            },
        )
        await database.commit()
        await database.refresh(row)
        return {
            "recognized": True,
            "session": _session_payload(row, session_id, row.slot),
        }


@router.patch("/sessions/{session_id}/demand/draft")
async def update_showroom_demand_draft(
    session_id: str,
    body: DemandDraftPatch,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    """Persist explicit human overrides without confirming the demand."""
    editable_fields = {
        "industry",
        "core_problem",
        "target_metric",
        "cycle",
        "users",
        "solution",
        "next_action",
    }
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != str(payload.get("tenant_key") or "demo"):
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = copy.deepcopy(data.get("demand") or _empty_demand())
        if demand.get("confirmed"):
            raise HTTPException(status_code=409, detail="已确认需求不可被自动草稿覆盖")

        changed_fields = {
            field for field in body.manual_fields if field in editable_fields
        }
        for field in changed_fields:
            if field in body.demand:
                demand[field] = str(body.demand[field] or "").strip()[:2_000]
        demand["completeness"] = calculate_demand_completeness(demand)

        document = copy.deepcopy(data.get("demand_document") or {})
        manual_fields = {str(field) for field in document.get("manual_fields") or []}
        document["manual_fields"] = sorted(manual_fields | changed_fields)
        row.data = _merge(
            data,
            {"demand": demand, "demand_document": document},
        )
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

        core_problem = str(demand.get("core_problem") or "").strip()
        insight = _merge(
            {
                "title": (
                    f"围绕“{core_problem}”的需求洞察" if core_problem else "需求洞察"
                ),
                "judgment": (
                    "等待知识证据补齐" if not documents else "已形成首轮知识证据"
                ),
                "gap": str(demand.get("target_metric") or ""),
                "recommendation": str(demand.get("next_action") or ""),
                "causes": [],
                "impacts": [],
                "evidence": [],
            },
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
            epoch_is_current = int(message.get("epoch", -1)) >= int(hub.state["epoch"])
            if is_ready and epoch_is_current:
                hub.ready_sessions.add(client_id)
            elif message.get("type") == "SESSION_SWITCH_READY":
                if message.get("session_id") == client_id:
                    hub.switch_ready.add(id(websocket))
            elif message.get("type") == "PONG":
                continue
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        hub.connections.pop(websocket, None)
        hub.ready_sessions.discard(client_id)
