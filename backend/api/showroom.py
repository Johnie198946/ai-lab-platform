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
from backend.services.showroom_insight import (
    EMPLOYEE_STATES,
    JOB_STAGES,
    SECTION_TYPES,
    apply_section,
    demand_fingerprint,
    empty_insight,
    empty_insight_job,
    extract_final_insight,
    extract_progress_events,
    normalize_staffing_plan,
    now_iso,
    role_catalog_payload,
    visible_insight_message,
)
from backend.services.showroom_insight_review import (
    apply_revision,
    calculate_insight_coverage,
    confirmed_version,
    create_insight_review_gate,
    create_revision,
    empty_insight_review,
    empty_insight_review_gate,
    extract_concept_review,
    extract_revision_protocol,
    field_catalog_payload,
    looks_like_revision_intent,
    materialize_missing_insight_items,
    next_draft_version,
    normalize_review,
    register_insight_tbd,
    reopen_version,
)
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


class InsightStaffingPlanRequest(BaseModel):
    plan: dict[str, Any] = Field(default_factory=dict)


class InsightProgressRequest(BaseModel):
    event_id: str = Field(..., min_length=4, max_length=160)
    kind: Literal["stage", "employee", "section"]
    stage: str = Field(default="", max_length=80)
    employee_id: str = Field(default="", max_length=80)
    employee_status: str = Field(default="", max_length=40)
    section: str = Field(default="", max_length=80)
    payload: dict[str, Any] = Field(default_factory=dict)


class InsightCompleteRequest(BaseModel):
    content: str = Field(default="", max_length=120_000)


class InsightFailureRequest(BaseModel):
    message: str = Field(default="", max_length=4000)


class InsightRevisionExtractionRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=120_000)
    job_id: str = Field(..., min_length=4, max_length=120)
    demand_hash: str = Field(..., min_length=16, max_length=128)
    base_version: str = Field(..., min_length=3, max_length=40)
    epoch: int = Field(default=0, ge=0)
    user_instruction: str = Field(default="", max_length=12_000)
    target_section: str = Field(default="", max_length=120)
    selected_text: str = Field(default="", max_length=4_000)
    expected_revision: bool = False
    request_id: str = Field(default="", max_length=160)


class InsightMutationRequest(BaseModel):
    epoch: int = Field(default=0, ge=0)
    job_id: str = Field(default="", max_length=120)
    demand_hash: str = Field(default="", max_length=128)
    base_version: str = Field(default="", max_length=40)


class InsightTbdRequest(InsightMutationRequest):
    field: str = Field(..., min_length=3, max_length=120)
    reason: str = Field(..., min_length=1, max_length=1000)
    owner: str = Field(..., min_length=1, max_length=160)
    action: str = Field(..., min_length=1, max_length=1000)
    due_at: str = Field(default="", max_length=80)


class InsightReviewCompleteRequest(InsightMutationRequest):
    content: str = Field(..., min_length=1, max_length=120_000)


class InsightReviewOverrideRequest(InsightMutationRequest):
    reason: str = Field(..., min_length=4, max_length=2000)


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
    source: str = Field(default="controller", max_length=80)


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
        "insight_stored_session_id": "",
        "backstage_skill_initialized": False,
        "frontstage_skill_initialized": False,
        "insight_skill_initialized": False,
        "backstage_skill_version": "1.7.0",
        "frontstage_skill_version": "1.7.0",
        "insight_skill_version": "1.0",
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


def _workstation_session_id(slot: str) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"showroom-slot-{slot}-{timestamp}-{uuid.uuid4().hex[:8]}"


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
        "staffing_plan",
        "insight_job",
        "insight_review",
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
        "staffing_plan": {},
        "insight_job": {},
        "insight_review": empty_insight_review(),
        "insight_review_gate": empty_insight_review_gate(),
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
            # A workstation can be offline while the guided tour rolls over.
            # Follow the archived row's successor so reopening an old URL can
            # never revive customer content from the previous reception.
            visited = {row.session_id}
            while row.status == "archived":
                successor_id = str((row.data or {}).get("rollover_to") or "")
                if not successor_id or successor_id in visited:
                    break
                successor = await database.get(ShowroomSession, successor_id)
                if (
                    successor is None
                    or successor.tenant_key != tenant_key
                    or successor.slot != slot
                ):
                    break
                visited.add(successor_id)
                row = successor
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
                    .where(ShowroomSession.status != "archived")
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
    async with hub.lock:
        epoch = max(
            body.epoch,
            int(hub.state.get("epoch") or 0) + 1,
            int(datetime.now(timezone.utc).timestamp() * 1000),
        )

        async with SessionLocal() as database:
            requested = await database.get(ShowroomSession, session_id)
            if (
                requested is None
                or requested.tenant_key != tenant_key
                or requested.slot != "main"
            ):
                raise HTTPException(status_code=404, detail="主演示会话不存在")

            # A retried request returns the already-created successors instead
            # of producing another reception batch.
            existing_switches = (requested.data or {}).get("rollover_switches") or []
            existing_successor = str((requested.data or {}).get("rollover_to") or "")
            if requested.status == "archived" and existing_successor:
                successor = await database.get(ShowroomSession, existing_successor)
                if successor is None or successor.tenant_key != tenant_key:
                    raise HTTPException(status_code=409, detail="换场记录不完整，请人工检查")
                return {
                    "archived_session_id": session_id,
                    "session": _session_payload(successor, successor.session_id, "main"),
                    "runtime": hub.snapshot(),
                    "session_switches": existing_switches,
                }

            rows = (
                await database.execute(
                    select(ShowroomSession)
                    .where(ShowroomSession.tenant_key == tenant_key)
                    .where(ShowroomSession.status != "archived")
                    .where(ShowroomSession.slot.in_(["main", "1", "2", "3", "4", "5"]))
                    .order_by(ShowroomSession.updated_at.desc())
                )
            ).scalars()
            active_by_slot: dict[str, ShowroomSession] = {"main": requested}
            for row in rows:
                active_by_slot.setdefault(row.slot, row)

        old_session_ids = {
            row.session_id for row in active_by_slot.values() if row is not None
        }
        hub.switch_ready.clear()
        for old_session_id in old_session_ids:
            await hub.broadcast(
                {
                    "type": "SESSION_SWITCH_PREPARE",
                    "session_id": old_session_id,
                    "epoch": epoch,
                }
            )
        targets = {
            id(socket)
            for socket, client in hub.connections.items()
            if client in old_session_ids
        }
        for _ in range(20):
            if targets.issubset(hub.switch_ready):
                break
            await asyncio.sleep(0.25)

        switches: list[dict[str, str]] = []
        new_ids = {
            "main": _visit_session_id(),
            **{slot: _workstation_session_id(slot) for slot in ["1", "2", "3", "4", "5"]},
        }
        now = datetime.now(timezone.utc).isoformat()
        try:
            async with SessionLocal() as database:
                refreshed: dict[str, ShowroomSession] = {}
                for slot, row in active_by_slot.items():
                    current = await database.get(ShowroomSession, row.session_id)
                    if current is not None:
                        refreshed[slot] = current

                for slot in ["main", "1", "2", "3", "4", "5"]:
                    old = refreshed.get(slot)
                    new_id = new_ids[slot]
                    switches.append(
                        {
                            "slot": slot,
                            "old_session_id": old.session_id if old else "",
                            "new_session_id": new_id,
                        }
                    )
                    new_data = _initial_session_data(slot)
                    if slot == "main":
                        new_data["visitor"]["visit_id"] = new_id
                    database.add(
                        ShowroomSession(
                            session_id=new_id,
                            tenant_key=tenant_key,
                            slot=slot,
                            step=0,
                            status="active",
                            data=new_data,
                        )
                    )

                for slot, old in refreshed.items():
                    old.status = "archived"
                    old_data = copy.deepcopy(old.data or {})
                    old_data["rollover_to"] = new_ids[slot]
                    old_data["rollover_at"] = now
                    if slot == "main":
                        old_data["visitor"] = _merge(
                            old_data.get("visitor") or {}, {"status": "archived"}
                        )
                        old_data.setdefault("visit_completed_by", body.source)
                        old_data.setdefault("visit_completed_at", now)
                        old_data["rollover_switches"] = switches
                    old.data = old_data

                await database.commit()
                new_main = await database.get(ShowroomSession, new_ids["main"])
        except Exception:
            for old_session_id in old_session_ids:
                await hub.broadcast(
                    {
                        "type": "SESSION_SWITCH_ABORT",
                        "session_id": old_session_id,
                        "epoch": epoch,
                    }
                )
            raise

        hub.state.update(
            {
                "active_main_session_id": new_ids["main"],
                "active_main_tenant_key": tenant_key,
                "epoch": epoch,
                "stage": "station-1",
                "payload": {},
                "reviews": {},
                "updated_at": now,
            }
        )
        await _persist_runtime()
        runtime = hub.snapshot()
        for switch in switches:
            if not switch["old_session_id"]:
                continue
            await hub.broadcast(
                {
                    "type": "SESSION_SWITCH_COMMIT",
                    "session_id": switch["old_session_id"],
                    "new_session_id": switch["new_session_id"],
                    "slot": switch["slot"],
                    "session_switches": switches,
                    "epoch": epoch,
                    "state": runtime,
                }
            )
        return {
            "archived_session_id": session_id,
            "session": _session_payload(new_main, new_ids["main"], "main"),
            "runtime": runtime,
            "session_switches": switches,
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


@router.post("/sessions/{session_id}/insight/jobs")
async def start_showroom_insight_job(
    session_id: str, payload=Depends(require_auth)
) -> dict[str, Any]:
    """Create or resume the idempotent V1.7 staffing-and-insight job."""
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = data.get("demand") or {}
        if not demand.get("confirmed"):
            raise HTTPException(status_code=409, detail="请先确认需求")
        source_hash = demand_fingerprint(demand)
        current_job = copy.deepcopy(data.get("insight_job") or {})
        resumable = (
            current_job.get("source_hash") == source_hash
            and current_job.get("status")
            in {"planning", "running", "partial", "completed", "interrupted"}
        )
        if resumable:
            return {
                "resumed": True,
                "job": current_job,
                "plan": data.get("staffing_plan") or {},
                "catalog": role_catalog_payload(),
                "session": _session_payload(row, session_id, row.slot),
            }

        job_id = f"insight-{uuid.uuid4().hex[:16]}"
        job = empty_insight_job(job_id, source_hash)
        data["insight_job"] = job
        data["staffing_plan"] = {}
        data["insight"] = empty_insight()
        data["insight_review"] = empty_insight_review()
        data["insight_review_gate"] = empty_insight_review_gate()
        row.data = data
        row.step = max(row.step, 3)
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await hub.broadcast(
        {
            "type": "INSIGHT_STAGE_UPDATED",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "demand_hash": job["source_hash"],
            "job": job,
        }
    )
    return {
        "resumed": False,
        "job": job,
        "plan": {},
        "catalog": role_catalog_payload(),
        "session": session_payload,
    }


@router.put("/sessions/{session_id}/insight/jobs/{job_id}/plan")
async def save_showroom_staffing_plan(
    session_id: str,
    job_id: str,
    body: InsightStaffingPlanRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = copy.deepcopy(data.get("insight_job") or {})
        if job.get("job_id") != job_id:
            raise HTTPException(status_code=409, detail="洞察任务已切换")
        demand = data.get("demand") or {}
        source_hash = demand_fingerprint(demand)
        if source_hash != job.get("source_hash"):
            raise HTTPException(status_code=409, detail="需求已变更，请重新规划团队")
        plan = normalize_staffing_plan(
            body.plan, job_id=job_id, source_hash=source_hash, demand=demand
        )
        plan["squads"][0]["employees"][0]["status"] = "working"
        job.update(
            {
                "status": "running",
                "active_stage": "internal_research",
                "active_employee_id": "researcher",
                "updated_at": now_iso(),
                "error": "",
            }
        )

        data["staffing_plan"] = plan
        data["insight_job"] = job
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await hub.broadcast(
        {
            "type": "STAFFING_PLAN_READY",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "job_id": job_id,
            "demand_hash": job["source_hash"],
            "plan": plan,
        }
    )
    return {"plan": plan, "job": job, "session": session_payload}


@router.post("/sessions/{session_id}/insight/jobs/{job_id}/progress")
async def update_showroom_insight_progress(
    session_id: str,
    job_id: str,
    body: InsightProgressRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    broadcast_type = "INSIGHT_STAGE_UPDATED"
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = copy.deepcopy(data.get("insight_job") or {})
        if job.get("job_id") != job_id:
            raise HTTPException(status_code=409, detail="洞察任务已切换")
        if job.get("source_hash") != demand_fingerprint(data.get("demand") or {}):
            raise HTTPException(status_code=409, detail="需求指纹不匹配")
        processed = list(job.get("processed_events") or [])
        if body.event_id in processed:
            return {
                "unchanged": True,
                "job": job,
                "session": _session_payload(row, session_id, row.slot),
            }

        plan = copy.deepcopy(data.get("staffing_plan") or {})
        insight = copy.deepcopy(data.get("insight") or empty_insight())
        if body.kind == "stage":
            if body.stage not in JOB_STAGES:
                raise HTTPException(status_code=422, detail="洞察阶段无效")
            job["active_stage"] = body.stage
            if body.employee_id:
                job["active_employee_id"] = body.employee_id
        elif body.kind == "employee":
            if body.employee_status not in EMPLOYEE_STATES:
                raise HTTPException(status_code=422, detail="AI员工状态无效")
            found = False
            for squad in plan.get("squads") or []:
                for employee in squad.get("employees") or []:
                    if employee.get("employee_id") == body.employee_id:
                        employee["status"] = body.employee_status
                        found = True
            if not found:
                raise HTTPException(status_code=422, detail="AI员工不在本次项目组")
            job["active_employee_id"] = body.employee_id
            broadcast_type = "AI_EMPLOYEE_STATUS"
        else:
            if body.section not in SECTION_TYPES:
                raise HTTPException(status_code=422, detail="洞察章节无效")
            insight = apply_section(insight, body.section, body.payload)
            completed = list(job.get("completed_sections") or [])
            if body.section not in completed:
                completed.append(body.section)
            job["completed_sections"] = completed
            job["active_stage"] = (
                "ipd_handoff" if body.section == "ipd_handoff" else "writing"
            )
            broadcast_type = "INSIGHT_SECTION_COMPLETED"

        processed.append(body.event_id)
        job["processed_events"] = processed[-200:]
        job["status"] = "running"
        job["updated_at"] = now_iso()
        data["staffing_plan"] = plan
        data["insight_job"] = job
        data["insight"] = insight
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await hub.broadcast(
        {
            "type": broadcast_type,
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "job_id": job_id,
            "demand_hash": job["source_hash"],
            "job": job,
            "section": body.section,
            "employee_id": body.employee_id,
        }
    )
    return {"job": job, "session": session_payload}


@router.post("/sessions/{session_id}/insight/jobs/{job_id}/complete")
async def complete_showroom_insight_job(
    session_id: str,
    job_id: str,
    body: InsightCompleteRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = copy.deepcopy(data.get("insight_job") or {})
        if job.get("job_id") != job_id:
            raise HTTPException(status_code=409, detail="洞察任务已切换")
        insight = copy.deepcopy(data.get("insight") or empty_insight())
        for event in extract_progress_events(body.content):
            if (
                event.get("job_id") == job_id
                and event.get("kind") == "section"
                and event.get("section") in SECTION_TYPES
            ):
                insight = apply_section(
                    insight, str(event["section"]), event.get("payload") or {}
                )
                if event["section"] not in job.get("completed_sections", []):
                    job.setdefault("completed_sections", []).append(event["section"])
        final_payload = extract_final_insight(body.content) or {}
        if final_payload.get("job_id") != job_id:
            final_payload = {}
        final_sections = final_payload.get("sections") or []
        if isinstance(final_sections, dict):
            final_sections = [
                {"section": section_type, "payload": section_payload}
                for section_type, section_payload in final_sections.items()
            ]
        for section in final_sections:
            # V1.7 may emit a compact list of completed section names in the
            # final envelope because the full payloads were already delivered
            # through incremental section events. Those names are valid, but
            # they are not objects and must not break the completion callback.
            if isinstance(section, str):
                continue
            if not isinstance(section, dict):
                continue
            section_type = str(section.get("section") or section.get("type") or "")
            if section_type in SECTION_TYPES:
                insight = apply_section(insight, section_type, section.get("payload") or section)
                if section_type not in job.get("completed_sections", []):
                    job.setdefault("completed_sections", []).append(section_type)

        required = {"concept", "summary", "root_causes", "impacts", "evidence", "recommendation"}
        complete = required.issubset(set(job.get("completed_sections") or []))
        status = "completed" if complete else "partial"
        insight["status"] = status
        insight["raw_markdown"] = visible_insight_message(body.content)[:60_000]
        insight["generated_at"] = now_iso()
        insight, missing_items = materialize_missing_insight_items(insight)
        job.update(
            {
                "status": status,
                "active_stage": status,
                "active_employee_id": "",
                "updated_at": now_iso(),
                "error": "" if complete and not missing_items else f"{len(missing_items)}项内容需要在004补充或登记TBD",
            }
        )

        plan = copy.deepcopy(data.get("staffing_plan") or {})
        for squad in plan.get("squads") or []:
            squad["status"] = status
            for employee in squad.get("employees") or []:
                if employee.get("status") not in {"blocked", "failed"}:
                    employee["status"] = "done"

        artifacts = copy.deepcopy(data.get("artifacts") or {})
        artifacts["需求合理性·调研支撑"] = {
            "title": "需求合理性·调研支撑",
            "owner": "IPD-01",
            "kind": "document",
            "content": {
                "summary": insight.get("judgment") or "深度洞察已形成",
                "demand": (data.get("demand") or {}).get("core_problem", ""),
                "target": (data.get("demand") or {}).get("target_metric", ""),
                "sources": insight.get("sources") or [],
                "ipd_handoff": insight.get("ipd_handoff") or {},
            },
            "updated_at": now_iso(),
        }
        data["insight"] = insight
        data["insight_job"] = job
        data["staffing_plan"] = plan
        data["artifacts"] = artifacts
        review = normalize_review(
            data.get("insight_review"), demand=data.get("demand") or {}, job=job
        )
        review["coverage"] = calculate_insight_coverage(insight)
        data["insight_review"] = review
        row.data = data
        row.step = max(row.step, 3)
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await hub.broadcast(
        {
            "type": "INSIGHT_JOB_COMPLETED",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "job_id": job_id,
            "demand_hash": job["source_hash"],
            "job": job,
        }
    )
    return {
        "job": job,
        "insight": insight,
        "session": session_payload,
        # The browser uses this explicit list to start one bounded recovery
        # pass when a model completed the job but omitted report fields.  Do
        # not infer this from the percentage: a populated, actionable TBD is
        # a valid report value and must not trigger an automatic loop.
        "backfill_required_fields": missing_items,
    }


def _validate_insight_mutation(
    body: InsightMutationRequest,
    *,
    data: dict[str, Any],
    job: dict[str, Any],
    review: dict[str, Any],
) -> None:
    current_hash = demand_fingerprint(data.get("demand") or {})
    if body.job_id and body.job_id != str(job.get("job_id") or ""):
        raise HTTPException(status_code=409, detail="洞察任务已切换")
    if body.demand_hash and body.demand_hash != current_hash:
        raise HTTPException(status_code=409, detail="需求已变化，请刷新页面")
    if body.base_version and body.base_version != review.get("version"):
        raise HTTPException(status_code=409, detail="报告版本已更新，请刷新后重试")
    if body.epoch and body.epoch != int(hub.state.get("epoch", 0)):
        raise HTTPException(status_code=409, detail="展厅场次已切换")


async def _broadcast_insight_event(
    event_type: str,
    session_id: str,
    data: dict[str, Any],
    **details: Any,
) -> None:
    job = data.get("insight_job") or {}
    review = data.get("insight_review") or {}
    await hub.broadcast(
        {
            "type": event_type,
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "job_id": job.get("job_id", ""),
            "demand_hash": review.get("demand_hash", ""),
            "base_version": review.get("version", ""),
            "insight_review": review,
            **details,
        }
    )


@router.post("/sessions/{session_id}/insight/revisions/extract")
async def extract_showroom_insight_revision(
    session_id: str,
    body: InsightRevisionExtractionRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = data.get("demand") or {}
        job = data.get("insight_job") or {}
        insight = data.get("insight") or empty_insight()
        review = normalize_review(data.get("insight_review"), demand=demand, job=job)
        _validate_insight_mutation(
            InsightMutationRequest(
                epoch=body.epoch,
                job_id=body.job_id,
                demand_hash=body.demand_hash,
                base_version=body.base_version,
            ),
            data=data,
            job=job,
            review=review,
        )
        if review.get("status") == "confirmed":
            raise HTTPException(status_code=409, detail="已确认版本已锁定，请先发起新版本")
        expected_revision = body.expected_revision or looks_like_revision_intent(
            body.user_instruction
        )
        if body.request_id:
            existing_revision = next(
                (
                    item
                    for item in review.get("revisions") or []
                    if item.get("request_id") == body.request_id
                ),
                None,
            )
            if existing_revision:
                pending = existing_revision.get("status") == "pending"
                return {
                    "result_type": "revision_ready" if pending else "explanation",
                    "revision": existing_revision if pending else None,
                    "session": _session_payload(row, session_id, row.slot),
                    "message": (
                        "已恢复同一轮回填草案"
                        if pending
                        else "同一轮回填已处理，不重复写入"
                    ),
                }
        protocol = extract_revision_protocol(body.content)
        if not protocol:
            return {
                "result_type": "repair_required" if expected_revision else "explanation",
                "revision": None,
                "session": _session_payload(row, session_id, row.slot),
                "message": (
                    "AI已给出说明，但尚未形成可回填草案"
                    if expected_revision
                    else "本轮为解释，不修改报告"
                ),
            }
        try:
            revision = create_revision(
                protocol,
                review=review,
                insight=insight,
                job=job,
                demand=demand,
                target_section=body.target_section,
                request_id=body.request_id,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        placement_candidates = []
        for change in revision.get("changes") or []:
            alternatives = change.get("alternative_targets") or []
            if change.get("confidence", 1) < 0.7 and alternatives:
                placement_candidates.append(
                    {
                        "source_excerpt": change.get("source_excerpt") or "",
                        "recommended_field": change.get("field") or "",
                        "recommended_section": change.get("target_section") or "",
                        "confidence": change.get("confidence", 0),
                        "alternatives": alternatives,
                    }
                )
        if placement_candidates:
            return {
                "result_type": "placement_required",
                "revision": None,
                "placement_candidates": placement_candidates,
                "session": _session_payload(row, session_id, row.slot),
                "message": "AI找到了可回填内容，但需要你确认填写位置",
            }
        revisions = list(review.get("revisions") or [])
        revisions.append(revision)
        review.update(
            {
                "status": "revision_pending",
                "pending_revision_id": revision["revision_id"],
                "revisions": revisions[-50:],
                "coverage": calculate_insight_coverage(insight),
            }
        )
        data["insight_review"] = review
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_REVISION_READY", session_id, data)
    return {
        "result_type": "revision_ready",
        "revision": revision,
        "placement_candidates": [],
        "session": session_payload,
        "message": "回填草案已生成，请确认差异",
    }


@router.post("/sessions/{session_id}/insight/revisions/{revision_id}/apply")
async def apply_showroom_insight_revision(
    session_id: str,
    revision_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        revision = next(
            (item for item in review.get("revisions") or [] if item.get("revision_id") == revision_id),
            None,
        )
        if revision and revision.get("status") == "applied":
            changed_fields = [
                str(change.get("field") or "")
                for change in revision.get("changes") or []
            ]
            affected_sections = list(revision.get("affected_sections") or [])
            if (
                revision.get("target_section")
                and revision["target_section"] not in affected_sections
            ):
                affected_sections.insert(0, revision["target_section"])
            return {
                "unchanged": True,
                "revision": revision,
                "session": _session_payload(row, session_id, row.slot),
                "changed_fields": changed_fields,
                "affected_sections": affected_sections,
                "version": review.get("version", ""),
                "coverage": review.get("coverage", {}),
            }
        _validate_insight_mutation(body, data=data, job=job, review=review)
        if not revision or revision.get("status") != "pending":
            raise HTTPException(status_code=409, detail="修订草案已失效")
        if review.get("pending_revision_id") != revision_id:
            raise HTTPException(status_code=409, detail="当前已有另一份待处理修订")
        insight = apply_revision(data.get("insight") or {}, revision)
        revision["status"] = "applied"
        revision["applied_at"] = now_iso()
        review.update(
            {
                "status": "draft",
                "version": next_draft_version(str(review.get("version") or "V0.1")),
                "pending_revision_id": "",
                "coverage": calculate_insight_coverage(insight),
            }
        )
        data["insight"] = insight
        data["insight_review"] = review
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    changed_fields = [str(change.get("field") or "") for change in revision.get("changes") or []]
    affected_sections = list(revision.get("affected_sections") or [])
    if revision.get("target_section") and revision["target_section"] not in affected_sections:
        affected_sections.insert(0, revision["target_section"])
    await _broadcast_insight_event(
        "INSIGHT_REVISION_APPLIED",
        session_id,
        data,
        revision_id=revision_id,
        changed_fields=changed_fields,
        affected_sections=affected_sections,
        version=review.get("version", ""),
        coverage=review.get("coverage", {}),
    )
    return {
        "revision": revision,
        "session": session_payload,
        "changed_fields": changed_fields,
        "affected_sections": affected_sections,
        "version": review.get("version", ""),
        "coverage": review.get("coverage", {}),
    }


@router.post("/sessions/{session_id}/insight/revisions/{revision_id}/discard")
async def discard_showroom_insight_revision(
    session_id: str,
    revision_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        revision = next(
            (item for item in review.get("revisions") or [] if item.get("revision_id") == revision_id),
            None,
        )
        if not revision or revision.get("status") != "pending":
            raise HTTPException(status_code=409, detail="修订草案已失效")
        revision["status"] = "discarded"
        revision["discarded_at"] = now_iso()
        review["pending_revision_id"] = ""
        review["status"] = "draft"
        data["insight_review"] = review
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_REVISION_DISCARDED", session_id, data)
    return {"revision": revision, "session": session_payload}


def _freeze_insight_report(
    data: dict[str, Any], *, confirmed_by: str, decision: str = "approved"
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    demand = data.get("demand") or {}
    job = data.get("insight_job") or {}
    insight = data.get("insight") or {}
    review = normalize_review(data.get("insight_review"), demand=demand, job=job)
    coverage = calculate_insight_coverage(insight)
    version = confirmed_version(str(review.get("version") or "V0.1"))
    confirmed_at = now_iso()
    snapshot = {
        "version": version,
        "confirmed_by": confirmed_by,
        "confirmed_at": confirmed_at,
        "decision": decision,
        "demand_hash": demand_fingerprint(demand),
        "insight": copy.deepcopy(insight),
    }
    review.update(
        {
            "status": "confirmed",
            "version": version,
            "coverage": coverage,
            "confirmed_by": confirmed_by,
            "confirmed_at": confirmed_at,
            "snapshots": (list(review.get("snapshots") or []) + [snapshot])[-20:],
        }
    )
    artifacts = copy.deepcopy(data.get("artifacts") or {})
    concept = insight.get("concept") or {}
    artifacts["需求合理性·调研支撑"] = {
        "title": "需求合理性·调研支撑", "owner": "IPD-01", "kind": "document",
        "version": version, "frozen": True,
        "content": {"market": concept.get("market") or {}, "competition": concept.get("competition") or [], "technology": concept.get("technology") or {}, "strategic_fit": concept.get("strategic_fit") or {}, "sources": insight.get("sources") or []},
        "updated_at": confirmed_at,
    }
    artifacts["需求评审结论"] = {
        "title": "需求评审结论", "owner": "IPD-02", "kind": "document",
        "version": version, "frozen": True,
        "content": {"verdict": concept.get("verdict") or {}, "assessment": concept.get("assessment") or {}, "special_checks": concept.get("special_checks") or {}, "capability_mapping": concept.get("capability_mapping") or []},
        "updated_at": confirmed_at,
    }
    artifacts["初始产品包"] = {
        "title": "初始产品包", "owner": "IPD-02", "kind": "document",
        "version": version, "frozen": True,
        "content": {"package": concept.get("initial_product_package") or {}, "demo_slice": concept.get("demo_slice") or {}},
        "updated_at": confirmed_at,
    }
    data["insight_review"] = review
    data["artifacts"] = artifacts
    return data, review, artifacts


@router.get("/sessions/{session_id}/insight/field-catalog")
async def get_showroom_insight_field_catalog(
    session_id: str, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        return {"schema_version": "2.0", "fields": field_catalog_payload((row.data or {}).get("insight") or {})}


@router.post("/sessions/{session_id}/insight/tbds")
async def register_showroom_insight_tbd(
    session_id: str, body: InsightTbdRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        if review.get("status") == "confirmed":
            raise HTTPException(status_code=409, detail="已确认版本不能登记TBD")
        try:
            insight = register_insight_tbd(
                data.get("insight") or {}, field=body.field, reason=body.reason,
                owner=body.owner, action=body.action, due_at=body.due_at,
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        review["coverage"] = calculate_insight_coverage(insight)
        data["insight"] = insight
        data["insight_review"] = review
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_TBD_REGISTERED", session_id, data, field=body.field)
    return {"session": session_payload, "coverage": review["coverage"]}


def _concept_review_prompt(task: dict[str, Any], insight: dict[str, Any], coverage: dict[str, Any], demand_hash: str) -> str:
    return "\n".join(
        [
            "[AI_LAB_CONTROL] 当前处于004 AI概念评审会。你是Supervision评审组，只做需求合理性预审，不输出建设方案。",
            f"评审任务：{task['task_id']}",
            f"报告版本：{task['report_version']}",
            f"需求指纹：{demand_hash}",
            f"覆盖状态：{json.dumps(coverage, ensure_ascii=False)}",
            f"报告：{json.dumps(insight, ensure_ascii=False)[:80000]}",
            "请分别以明鉴（概念主审）、证源（证据核验）、守界（专项审查）完成独立检查。结论只能为approved、conditional、changes、rejected。",
            "通过或条件通过必须说明依据与条件；资料不足但已有责任人和补证动作时可conditional；没有处置的关键缺口必须changes。",
            '<!-- AI_LAB_CONCEPT_REVIEW_V1 {"decision":"approved|conditional|changes|rejected","summary":"...","conditions":[],"changes":[],"reviewer_results":[{"reviewer_id":"concept-chair","conclusion":"...","comment":"..."},{"reviewer_id":"evidence-auditor","conclusion":"...","comment":"..."},{"reviewer_id":"boundary-reviewer","conclusion":"...","comment":"..."}]} AI_LAB_CONCEPT_REVIEW_V1 -->',
        ]
    )


def _concept_review_notification(task: dict[str, Any], *, override_actor: str = "") -> tuple[str, str]:
    decision = task.get("final_decision") or {}
    title = "AI Lab 004 · 现场放行" if override_actor else "AI Lab 004 · AI概念预审"
    lines = []
    if override_actor:
        lines.append(f"操作人：{override_actor}")
    lines.extend(
        [
            f"结论：{decision.get('decision') or task.get('status') or 'unknown'}",
            f"摘要：{decision.get('summary') or '暂无摘要'}",
            f"报告版本：{task.get('report_version') or ''}",
            "后续人工联系人："
            + ", ".join(item.get("role", "") for item in task.get("human_contact_bindings") or []),
        ]
    )
    return title, "\n".join(lines)


async def _notify_insight_review_contacts(
    session_id: str,
    tenant_key: str,
    task_id: str,
    *,
    title: str,
    content: str,
) -> None:
    """Send the non-blocking Feishu notice and persist its real outcome."""
    delivered = await send_feishu_async(title, content)
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            return
        data = copy.deepcopy(row.data or {})
        task = copy.deepcopy(data.get("insight_review_gate") or {})
        if task.get("task_id") != task_id:
            return
        task["notification_status"] = "sent" if delivered else "failed"
        task["notification_updated_at"] = now_iso()
        data["insight_review_gate"] = task
        row.data = data
        await database.commit()
    await _broadcast_insight_event(
        "INSIGHT_REVIEW_NOTIFICATION_UPDATED",
        session_id,
        data,
        task=task,
    )


@router.post("/sessions/{session_id}/insight/review-tasks")
async def create_showroom_insight_review_task(
    session_id: str, body: InsightMutationRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        coverage = calculate_insight_coverage(data.get("insight") or {})
        if review.get("pending_revision_id"):
            raise HTTPException(status_code=409, detail="请先应用或放弃待处理修订")
        if not coverage.get("can_submit_review"):
            raise HTTPException(status_code=422, detail="仍有未处置缺口，请先补齐或登记为TBD")
        current = data.get("insight_review_gate") or {}
        if current.get("task_id") and current.get("report_version") == review.get("version") and current.get("status") in {"assigned", "reviewing"}:
            task = current
        else:
            task = create_insight_review_gate(
                report_version=str(review.get("version") or "V0.1"),
                assigned_by=str(payload.get("username") or payload.get("sub") or "showroom-user"),
            )
        data["insight_review_gate"] = task
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_REVIEW_ASSIGNED", session_id, data, task=task)
    return {"task": task, "review_prompt": _concept_review_prompt(task, data.get("insight") or {}, coverage, review.get("demand_hash") or ""), "session": session_payload}


@router.post("/sessions/{session_id}/insight/review-tasks/{task_id}/complete")
async def complete_showroom_insight_review_task(
    session_id: str, task_id: str, body: InsightReviewCompleteRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        task = copy.deepcopy(data.get("insight_review_gate") or empty_insight_review_gate())
        if task.get("task_id") != task_id or task.get("report_version") != review.get("version"):
            raise HTTPException(status_code=409, detail="AI评审任务已切换")
        if task.get("status") in {"approved", "conditional", "changes", "rejected"}:
            return {"task": task, "session": _session_payload(row, session_id, row.slot), "unchanged": True, "released": task.get("status") in {"approved", "conditional"}}
        try:
            decision = extract_concept_review(body.content)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
        if not decision:
            task.update({"status": "failed", "error": "AI评审结果缺少结构化结论"})
            data["insight_review_gate"] = task
            row.data = data
            await database.commit()
            raise HTTPException(status_code=422, detail=task["error"])
        by_id = {item.get("reviewer_id"): item for item in decision.get("reviewer_results") or []}
        for reviewer in task.get("ai_reviewers") or []:
            result = by_id.get(reviewer.get("reviewer_id")) or {}
            reviewer.update({"status": "done", "conclusion": result.get("conclusion") or decision["decision"], "comment": result.get("comment") or ""})
        task.update({"status": decision["decision"], "final_decision": decision, "notification_status": "queued", "error": ""})
        released = decision["decision"] in {"approved", "conditional"}
        if released:
            data, review, _ = _freeze_insight_report(data, confirmed_by=f"AI评审会 · {task['assigned_by']}", decision=decision["decision"])
            task["released_at"] = now_iso()
            row.step = max(row.step, 4)
        data["insight_review_gate"] = task
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    notification_title, notification_content = _concept_review_notification(task)
    asyncio.create_task(
        _notify_insight_review_contacts(
            session_id,
            tenant_key,
            task_id,
            title=notification_title,
            content=notification_content,
        )
    )
    await _broadcast_insight_event("INSIGHT_REVIEW_COMPLETED", session_id, data, task=task)
    if released:
        await _broadcast_insight_event("INSIGHT_REVIEW_RELEASED", session_id, data, task=task)
    else:
        await _broadcast_insight_event("INSIGHT_REVIEW_CHANGES_REQUESTED", session_id, data, task=task)
    return {"task": task, "session": session_payload, "released": released, "next_view": "screen-05" if released else "screen-04"}


@router.post("/sessions/{session_id}/insight/review-tasks/{task_id}/override")
async def override_showroom_insight_review_task(
    session_id: str, task_id: str, body: InsightReviewOverrideRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        task = copy.deepcopy(data.get("insight_review_gate") or empty_insight_review_gate())
        if task.get("task_id") != task_id:
            raise HTTPException(status_code=409, detail="AI评审任务已切换")
        actor = str(payload.get("username") or payload.get("sub") or "showroom-user")[:120]
        task.update({"status": "approved", "final_decision": {"decision": "approved", "summary": body.reason, "override": True, "reviewed_at": now_iso()}, "released_at": now_iso(), "notification_status": "queued"})
        data, review, _ = _freeze_insight_report(data, confirmed_by=f"现场放行 · {actor}", decision="override")
        data["insight_review_gate"] = task
        row.data = data
        row.step = max(row.step, 4)
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    notification_title, notification_content = _concept_review_notification(
        task, override_actor=actor
    )
    asyncio.create_task(
        _notify_insight_review_contacts(
            session_id,
            tenant_key,
            task_id,
            title=notification_title,
            content=notification_content,
        )
    )
    await _broadcast_insight_event("INSIGHT_REVIEW_RELEASED", session_id, data, task=task)
    return {"task": task, "session": session_payload, "released": True, "next_view": "screen-05"}


@router.post("/sessions/{session_id}/insight/review-tasks/{task_id}/retry")
async def retry_showroom_insight_review_task(
    session_id: str, task_id: str, body: InsightMutationRequest, payload=Depends(require_auth)
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        task = copy.deepcopy(data.get("insight_review_gate") or {})
        if task.get("task_id") != task_id:
            raise HTTPException(status_code=409, detail="AI评审任务已切换")
        task.update({"status": "assigned", "error": ""})
        for reviewer in task.get("ai_reviewers") or []:
            reviewer.update({"status": "waiting", "conclusion": "", "comment": ""})
        data["insight_review_gate"] = task
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    return {"task": task, "review_prompt": _concept_review_prompt(task, data.get("insight") or {}, calculate_insight_coverage(data.get("insight") or {}), review.get("demand_hash") or ""), "session": session_payload}


@router.post("/sessions/{session_id}/insight/review-tasks/{task_id}/notify")
async def retry_showroom_insight_review_notification(
    session_id: str,
    task_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(
            data.get("insight_review"), demand=data.get("demand") or {}, job=job
        )
        _validate_insight_mutation(body, data=data, job=job, review=review)
        task = copy.deepcopy(data.get("insight_review_gate") or {})
        if task.get("task_id") != task_id:
            raise HTTPException(status_code=409, detail="AI评审任务已切换")
        if not task.get("final_decision"):
            raise HTTPException(status_code=409, detail="AI评审尚未形成结论")
        task["notification_status"] = "queued"
        data["insight_review_gate"] = task
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    title, content = _concept_review_notification(
        task,
        override_actor=str(payload.get("username") or payload.get("sub") or "")
        if (task.get("final_decision") or {}).get("override")
        else "",
    )
    asyncio.create_task(
        _notify_insight_review_contacts(
            session_id,
            tenant_key,
            task_id,
            title=title,
            content=content,
        )
    )
    return {"task": task, "session": session_payload}


@router.post("/sessions/{session_id}/insight/confirm")
async def confirm_showroom_insight(
    session_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        demand = data.get("demand") or {}
        job = data.get("insight_job") or {}
        insight = data.get("insight") or {}
        review = normalize_review(data.get("insight_review"), demand=demand, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        coverage = calculate_insight_coverage(insight)
        if review.get("pending_revision_id"):
            raise HTTPException(status_code=409, detail="请先应用或放弃待处理修订")
        if not coverage.get("confirmable"):
            missing = [name for name, done in coverage.get("dimensions", {}).items() if not done]
            raise HTTPException(status_code=422, detail=f"洞察尚未满足确认条件：{'、'.join(missing) or '证据或TBD动作不完整'}")
        confirmed_by = str(payload.get("username") or payload.get("sub") or "showroom-user")[:120]
        data, review, artifacts = _freeze_insight_report(data, confirmed_by=confirmed_by)
        row.data = data
        row.step = max(row.step, 4)
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_CONFIRMED", session_id, data)
    return {"session": session_payload, "artifacts": artifacts, "insight_review": review}


@router.post("/sessions/{session_id}/insight/reopen")
async def reopen_showroom_insight(
    session_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        if review.get("status") != "confirmed":
            raise HTTPException(status_code=409, detail="当前报告尚未确认")
        review.update(
            {
                "status": "draft",
                "version": reopen_version(str(review.get("version") or "V1.0")),
                "confirmed_by": "",
                "confirmed_at": "",
                "pending_revision_id": "",
            }
        )
        data["insight_review"] = review
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("INSIGHT_VERSION_OPENED", session_id, data)
    return {"session": session_payload, "insight_review": review}


@router.post("/sessions/{session_id}/demand/reopen")
async def reopen_showroom_demand(
    session_id: str,
    body: InsightMutationRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    tenant_key = str(payload.get("tenant_key") or "demo")
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = data.get("insight_job") or {}
        review = normalize_review(data.get("insight_review"), demand=data.get("demand") or {}, job=job)
        _validate_insight_mutation(body, data=data, job=job, review=review)
        history = list(data.get("insight_history") or [])
        history.append(
            {
                "superseded_at": now_iso(),
                "insight": copy.deepcopy(data.get("insight") or {}),
                "insight_job": copy.deepcopy(job),
                "insight_review": {**copy.deepcopy(review), "status": "superseded"},
            }
        )
        demand = copy.deepcopy(data.get("demand") or {})
        demand["confirmed"] = False
        document = copy.deepcopy(data.get("demand_document") or {})
        if document:
            document["status"] = "draft"
        data.update(
            {
                "demand": demand,
                "demand_document": document,
                "insight_history": history[-20:],
                "insight": {},
                "insight_job": {},
                "staffing_plan": {},
                "insight_review": empty_insight_review(),
                "insight_review_gate": empty_insight_review_gate(),
            }
        )
        row.data = data
        row.step = min(row.step, 2)
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await _broadcast_insight_event("DEMAND_REOPENED", session_id, data)
    return {"session": session_payload}


async def _finish_showroom_insight_job(
    session_id: str,
    job_id: str,
    message: str,
    status: Literal["failed", "interrupted"],
    tenant_key: str,
) -> dict[str, Any]:
    async with SessionLocal() as database:
        row = await database.get(ShowroomSession, session_id)
        if row is None or row.tenant_key != tenant_key:
            raise HTTPException(status_code=404, detail="体验会话不存在")
        data = copy.deepcopy(row.data or {})
        job = copy.deepcopy(data.get("insight_job") or {})
        if job.get("job_id") != job_id:
            raise HTTPException(status_code=409, detail="洞察任务已切换")
        required = {"concept", "summary", "root_causes", "impacts", "evidence", "recommendation"}
        if status == "failed" and required.issubset(
            set(job.get("completed_sections") or [])
        ):
            # A transport/finalization failure must not overwrite a complete,
            # incrementally persisted report. Return the completed session so
            # the browser can recover without running the research twice.
            job.update(
                {
                    "status": "completed",
                    "active_stage": "completed",
                    "active_employee_id": "",
                    "updated_at": now_iso(),
                    "error": "",
                }
            )
            insight = copy.deepcopy(data.get("insight") or empty_insight())
            insight["status"] = "completed"
            plan = copy.deepcopy(data.get("staffing_plan") or {})
            for squad in plan.get("squads") or []:
                squad["status"] = "completed"
                for employee in squad.get("employees") or []:
                    employee["status"] = "done"
            data["insight_job"] = job
            data["insight"] = insight
            data["staffing_plan"] = plan
            row.data = data
            await database.commit()
            await database.refresh(row)
            return {
                "job": job,
                "session": _session_payload(row, session_id, row.slot),
            }
        active_employee_id = str(job.get("active_employee_id") or "")
        job.update(
            {
                "status": status,
                "active_stage": status,
                "active_employee_id": "",
                "updated_at": now_iso(),
                "error": message[:4000],
            }
        )
        plan = copy.deepcopy(data.get("staffing_plan") or {})
        for squad in plan.get("squads") or []:
            squad["status"] = status
            for employee in squad.get("employees") or []:
                if employee.get("employee_id") == active_employee_id:
                    employee["status"] = "failed" if status == "failed" else "waiting"
        data["insight_job"] = job
        data["staffing_plan"] = plan
        row.data = data
        await database.commit()
        await database.refresh(row)
        session_payload = _session_payload(row, session_id, row.slot)
    await hub.broadcast(
        {
            "type": "INSIGHT_JOB_FAILED" if status == "failed" else "INSIGHT_STAGE_UPDATED",
            "session_id": session_id,
            "epoch": hub.state.get("epoch", 0),
            "job_id": job_id,
            "demand_hash": job["source_hash"],
            "job": job,
        }
    )
    return {"job": job, "session": session_payload}


@router.post("/sessions/{session_id}/insight/jobs/{job_id}/fail")
async def fail_showroom_insight_job(
    session_id: str,
    job_id: str,
    body: InsightFailureRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    return await _finish_showroom_insight_job(
        session_id,
        job_id,
        body.message or "V1.7 洞察任务未完成",
        "failed",
        str(payload.get("tenant_key") or "demo"),
    )


@router.post("/sessions/{session_id}/insight/jobs/{job_id}/interrupt")
async def interrupt_showroom_insight_job(
    session_id: str,
    job_id: str,
    body: InsightFailureRequest,
    payload=Depends(require_auth),
) -> dict[str, Any]:
    return await _finish_showroom_insight_job(
        session_id,
        job_id,
        body.message or "用户已停止生成",
        "interrupted",
        str(payload.get("tenant_key") or "demo"),
    )


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
