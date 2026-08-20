"""Durable server-side producer and projector for Showroom IPD0 insight.

Hermes Bridge owns execution.  The browser only observes the validated projection
stored on ``ShowroomSession``; chat messages are never accepted as report data.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.showroom import ShowroomInsightExecution, ShowroomSession
from backend.models.workflow import (
    WorkflowArtifact,
    WorkflowDefinition,
    WorkflowExecution,
    WorkflowNodeRun,
    WorkflowPlanVersion,
)
from backend.services.dsl_safety_compiler import DSLSafetyCompiler
from backend.services.showroom_insight import (
    apply_section,
    default_staffing_plan,
    empty_insight,
    normalize_staffing_plan,
    now_iso,
)
from backend.services.showroom_insight_review import (
    calculate_insight_coverage,
    empty_insight_review,
    empty_insight_review_gate,
    materialize_missing_insight_items,
)
from backend.services.workflow_artifacts import run_root

SCHEMA = "AI_LAB_INSIGHT_DOCUMENT_V2"
NODE_IDS = (
    "staffing-plan", "evidence-research", "market-insight",
    "requirement-analysis", "supervision-review", "output-format",
)
SECTION_KEYS = (
    "summary", "root_causes", "impacts", "evidence", "recommendation",
    "ipd_handoff", "concept",
)
CONCEPT_KEYS = (
    "demand_trace", "customer_user", "market", "competition", "technology",
    "strategic_fit", "capability_mapping", "assessment", "special_checks",
    "knowledge_status", "verdict", "initial_product_package", "demo_slice",
)
STATUS_VALUES = {"verified", "inferred", "tbd", "not_applicable"}
NODE_EMPLOYEES = {
    "staffing-plan": [],
    "evidence-research": ["researcher"],
    "market-insight": ["industry-analyst"],
    "requirement-analysis": ["product-manager"],
    "supervision-review": ["evidence-reviewer"],
    "output-format": [],
}
NODE_STAGE = {
    "staffing-plan": "planning",
    "evidence-research": "internal_research",
    "market-insight": "analysis",
    "requirement-analysis": "ipd_handoff",
    "supervision-review": "reviewing",
    "output-format": "writing",
}


def _id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("\0".join(parts).encode()).hexdigest()[:24]
    return f"{prefix}_{digest}"[:48]


def _artifact_schema_prompt(run_id: str, demand_hash: str) -> str:
    return (
        "只输出一个JSON对象，不要Markdown代码围栏或解释。schema必须为"
        f"{SCHEMA}，run_id必须为{run_id}，demand_hash必须为{demand_hash}。"
        "sections必须包含summary、root_causes、impacts、evidence、recommendation、"
        "ipd_handoff、concept；concept必须包含demand_trace、customer_user、market、"
        "competition、technology、strategic_fit、capability_mapping、assessment、"
        "special_checks、knowledge_status、verdict、initial_product_package、demo_slice。"
        "每个业务字段必须标记verified/inferred/tbd/not_applicable；tbd必须包含"
        "reason、owner、action。sources包含title、url或path、date、confidence。"
        "不得输出完整建设方案，不得虚构来源。"
    )


def build_dsl(run_id: str, demand_hash: str, demand: dict[str, Any]) -> dict[str, Any]:
    requirement = json.dumps(demand, ensure_ascii=False, sort_keys=True)[:24_000]
    nodes = [
        {"id": "staffing-plan", "node_type": "PROMPT_TRANSFORM", "name": "V1.7组建AI项目组", "parameters": {
            "agent_id": "main_agent", "max_tokens": 2500,
            "instruction": "使用solution-consultant-persona V1.7理解任务；仅规划researcher、industry-analyst、product-manager、evidence-reviewer四角色的具体task。只输出JSON对象，包含mission和squads，不要Markdown。已确认需求：" + requirement,
        }},
        {"id": "evidence-research", "node_type": "KNOWLEDGE_RETRIEVAL", "name": "证据研究", "parameters": {
            "agent_id": "knowledge", "max_tokens": 9000,
            "instruction": "优先检索授权内部Wiki；不足时才使用公开网络。整理事实、来源、日期、置信度、相反证据和缺口。不得把推断冒充事实。",
        }},
        {"id": "market-insight", "node_type": "LLM_INFERENCE", "name": "IPD-01市场洞察", "parameters": {
            "agent_id": "main_agent", "skill_id": "ipd-01-market-insight", "max_tokens": 12000,
            "instruction": "调用已安装ipd-01-market-insight，形成客户价值、市场政策、竞争替代、技术趋势、根因、影响；保留证据引用。",
        }},
        {"id": "requirement-analysis", "node_type": "LLM_INFERENCE", "name": "IPD-02需求分析", "parameters": {
            "agent_id": "main_agent", "skill_id": "ipd-02-requirement-analysis", "max_tokens": 12000,
            "instruction": "调用已安装ipd-02-requirement-analysis，形成战略边界、能力映射、采纳判断、专项检查、初始产品包和001最小实践切片；不要给完整建设方案。",
        }},
        {"id": "supervision-review", "node_type": "FILTER_PASS", "name": "Supervision证据核验", "parameters": {
            "agent_id": "supervision", "max_tokens": 7000,
            "instruction": "核验事实/推断/TBD分类、来源、相反证据及网络安全/可靠性/节能/功能性能四类专项检查。未知项必须给责任人与补证动作。",
        }},
        {"id": "output-format", "node_type": "OUTPUT_FORMAT", "name": "结构化报告回填", "parameters": {
            "agent_id": "main_agent", "max_tokens": 16000,
            "instruction": _artifact_schema_prompt(run_id, demand_hash),
            "output_format": SCHEMA,
        }},
    ]
    edges = [
        {"source": NODE_IDS[index], "target": NODE_IDS[index + 1]}
        for index in range(len(NODE_IDS) - 1)
    ]
    return {"plan_id": _id("sidp", run_id), "name": "Showroom IPD0洞察", "version": "2.0.0", "nodes": nodes, "edges": edges}


async def ensure_execution(
    db: AsyncSession, *, session: ShowroomSession, demand_hash: str, epoch: int,
) -> tuple[ShowroomInsightExecution, bool]:
    existing = (
        await db.execute(select(ShowroomInsightExecution).where(
            ShowroomInsightExecution.tenant_key == session.tenant_key,
            ShowroomInsightExecution.session_id == session.session_id,
            ShowroomInsightExecution.epoch == epoch,
            ShowroomInsightExecution.demand_hash == demand_hash,
        ))
    ).scalar_one_or_none()
    if existing:
        return existing, True

    job_id = _id("sij", session.tenant_key, session.session_id, str(epoch), demand_hash)
    workflow_id = _id("swf", job_id)
    plan_id = _id("swp", job_id)
    execution_id = _id("swe", job_id)
    demand = copy.deepcopy((session.data or {}).get("demand") or {})
    dsl = build_dsl(execution_id, demand_hash, demand)
    compiled = DSLSafetyCompiler.compile_and_validate(dsl)
    workflow = WorkflowDefinition(
        id=workflow_id, tenant_key=session.tenant_key, created_by="showroom-system",
        title=f"Showroom IPD0 · {session.session_id}"[:160],
        description="服务端持久化生产003.5至004深度洞察",
        desired_output=SCHEMA, status="ready", active_plan_id=plan_id,
        requirements_snapshot={"session_id": session.session_id, "epoch": epoch, "demand_hash": demand_hash, "demand": demand},
    )
    plan = WorkflowPlanVersion(
        id=plan_id, workflow_id=workflow_id, version=1,
        dsl=compiled.model_dump(mode="json"), goal=f"基于已确认需求生产IPD0洞察：{demand.get('core_problem') or ''}",
        deliverable=SCHEMA, allow_network=True, max_tokens=58500,
        estimated_tokens=58500, knowledge_scope=[], validation_errors=[],
    )
    execution = WorkflowExecution(
        id=execution_id, workflow_id=workflow_id, plan_id=plan_id,
        tenant_key=session.tenant_key, status="queued", token_budget=58500,
        idempotency_key=f"showroom-insight:{session.tenant_key}:{session.session_id}:{epoch}:{demand_hash}",
    )
    # These objects are intentionally built from deterministic foreign-key IDs rather
    # than ORM relationship assignment.  Flush each dependency boundary explicitly:
    # SQLite normally leaves FK enforcement disabled and masked this ordering bug,
    # while PostgreSQL correctly rejected execution-before-plan with a 500.
    db.add(workflow)
    await db.flush()
    db.add(plan)
    await db.flush()
    db.add(execution)
    await db.flush()
    order = DSLSafetyCompiler.check_dag_cycle_kahn(compiled)
    node_map = {node.id: node for node in compiled.nodes}
    for position, node_id in enumerate(order):
        node = node_map[node_id]
        db.add(WorkflowNodeRun(
            id=_id("swn", execution_id, node_id), execution_id=execution_id,
            node_id=node_id, node_type=node.node_type.value, name=node.name or node_id,
            agent_id=str(node.parameters.get("agent_id") or "main_agent"),
            position=position, max_tokens=int(node.parameters.get("max_tokens") or 4000),
            input_refs=[edge.source for edge in compiled.edges if edge.target == node_id],
        ))
    binding = ShowroomInsightExecution(
        job_id=job_id, session_id=session.session_id, tenant_key=session.tenant_key,
        epoch=epoch, demand_hash=demand_hash, execution_id=execution_id, status="queued",
    )
    db.add(binding)
    data = copy.deepcopy(session.data or {})
    legacy = copy.deepcopy(data.get("insight_job") or {})
    if legacy and not legacy.get("execution_id"):
        legacy["status"] = "superseded"
        legacy["superseded_at"] = now_iso()
        data.setdefault("insight_execution_history", []).append(legacy)
        old_insight = copy.deepcopy(data.get("insight") or {})
        if old_insight:
            data.setdefault("insight_history", []).append({
                "superseded_at": now_iso(),
                "reason": "migrated_to_server_execution_v2",
                "insight": old_insight,
                "insight_job": legacy,
            })
    job = {
        "job_id": job_id, "execution_id": execution_id, "demand_hash": demand_hash,
        "source_hash": demand_hash, "status": "queued", "active_node": "staffing-plan",
        "active_stage": "planning", "active_employee_id": "",
        "completed_sections": [], "node_statuses": {node: "pending" for node in NODE_IDS},
        "attempt": 0, "artifact_hash": "", "started_at": now_iso(), "updated_at": now_iso(), "error": "",
    }
    data.update({
        "insight_job": job,
        "staffing_plan": default_staffing_plan(job_id, demand_hash, demand),
        "insight": empty_insight(),
        "insight_review": empty_insight_review(),
        "insight_review_gate": empty_insight_review_gate(),
    })
    session.data = data
    session.step = max(session.step, 3)
    await db.flush()
    return binding, False


def _parse_json(content: str) -> dict[str, Any]:
    text = (content or "").strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", text, re.I)
    if fenced:
        text = fenced.group(1).strip()
    value = json.loads(text)
    if not isinstance(value, dict):
        raise ValueError("洞察Artifact必须是JSON对象")
    return value


def _walk_status(value: Any, path: str = "sections") -> None:
    if isinstance(value, dict):
        if "status" in value:
            status = str(value.get("status") or "")
            if status not in STATUS_VALUES:
                raise ValueError(f"{path}.status无效")
            if status == "tbd" and not all(str(value.get(key) or "").strip() for key in ("reason", "owner", "action")):
                raise ValueError(f"{path}的TBD缺少reason/owner/action")
        for key, child in value.items():
            _walk_status(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _walk_status(child, f"{path}[{index}]")


def validate_document(value: dict[str, Any], *, execution_id: str, demand_hash: str) -> dict[str, Any]:
    if value.get("schema") != SCHEMA:
        raise ValueError("洞察Artifact schema不匹配")
    if value.get("run_id") != execution_id or value.get("demand_hash") != demand_hash:
        raise ValueError("洞察Artifact执行或需求指纹不匹配")
    sections = value.get("sections")
    if not isinstance(sections, dict) or any(key not in sections for key in SECTION_KEYS):
        raise ValueError("洞察Artifact缺少七个顶层章节")
    concept = sections.get("concept")
    if not isinstance(concept, dict) or any(key not in concept for key in CONCEPT_KEYS):
        raise ValueError("洞察Artifact缺少概念阶段字段")
    for key in CONCEPT_KEYS:
        if not isinstance(concept.get(key), dict) or concept[key].get("status") not in STATUS_VALUES:
            raise ValueError(f"洞察Artifact concept.{key}缺少有效状态")
    sources = value.get("sources") or []
    if not isinstance(sources, list):
        raise ValueError("sources必须是列表")
    for source in sources:
        if not isinstance(source, dict) or not (str(source.get("url") or "").startswith(("http://", "https://")) or str(source.get("path") or "").startswith(("wiki/", "tenants/"))):
            raise ValueError("洞察来源路径无效")
    _walk_status(sections)
    return value


def document_to_insight(document: dict[str, Any]) -> dict[str, Any]:
    sections = document["sections"]
    insight = empty_insight()
    for section in SECTION_KEYS:
        payload = sections[section]
        if section == "summary" and isinstance(payload, dict):
            normalized = payload
        elif section == "root_causes":
            normalized = payload if isinstance(payload, dict) else {"causes": payload}
        elif section == "impacts":
            normalized = payload if isinstance(payload, dict) else {"impacts": payload}
        elif section == "evidence":
            normalized = payload if isinstance(payload, dict) else {"evidence": payload}
        elif section == "recommendation":
            normalized = payload if isinstance(payload, dict) else {"recommendation": str(payload)}
        else:
            normalized = payload if isinstance(payload, dict) else {}
        insight = apply_section(insight, section, normalized)
    insight["sources"] = copy.deepcopy(document.get("sources") or insight.get("sources") or [])
    insight["warnings"] = [str(item)[:1000] for item in (document.get("warnings") or [])[:30]]
    insight["schema"] = SCHEMA
    insight["run_id"] = document["run_id"]
    insight["demand_hash"] = document["demand_hash"]
    insight["status"] = "completed"
    insight["generated_at"] = now_iso()
    insight, _ = materialize_missing_insight_items(insight)
    return insight


async def project_execution(db: AsyncSession, execution_id: str) -> dict[str, Any] | None:
    binding = (
        await db.execute(select(ShowroomInsightExecution).where(ShowroomInsightExecution.execution_id == execution_id))
    ).scalar_one_or_none()
    if binding is None:
        return None
    execution = await db.get(WorkflowExecution, execution_id)
    session = await db.get(ShowroomSession, binding.session_id)
    if execution is None or session is None or session.tenant_key != binding.tenant_key:
        return None
    data = copy.deepcopy(session.data or {})
    if binding.demand_hash != str((data.get("insight_job") or {}).get("demand_hash") or (data.get("insight_job") or {}).get("source_hash") or ""):
        binding.status = "superseded"
        return None
    nodes = list((await db.execute(select(WorkflowNodeRun).where(WorkflowNodeRun.execution_id == execution_id).order_by(WorkflowNodeRun.position))).scalars())
    statuses = {node.node_id: node.status for node in nodes}
    active = next((node for node in nodes if node.status in {"running", "failed"}), None)
    plan = copy.deepcopy(data.get("staffing_plan") or {})
    staffing_node = next((node for node in nodes if node.node_id == "staffing-plan"), None)
    if staffing_node is not None and staffing_node.status == "succeeded":
        staffing_artifact = (
            await db.execute(
                select(WorkflowArtifact)
                .where(
                    WorkflowArtifact.execution_id == execution_id,
                    WorkflowArtifact.node_run_id == staffing_node.id,
                )
                .order_by(WorkflowArtifact.created_at.desc())
            )
        ).scalars().first()
        if staffing_artifact is not None:
            try:
                staffing_content = (run_root(execution) / Path(staffing_artifact.relative_path)).read_text(encoding="utf-8")
                plan = normalize_staffing_plan(
                    _parse_json(staffing_content), job_id=binding.job_id,
                    source_hash=binding.demand_hash,
                    demand=copy.deepcopy(data.get("demand") or {}),
                )
            except (OSError, ValueError, json.JSONDecodeError):
                # The controlled fallback stays authoritative when V1.7 returns
                # prose or an invalid role. Execution may continue safely.
                pass
    for squad in plan.get("squads") or []:
        for employee in squad.get("employees") or []:
            related = [node for node, employee_ids in NODE_EMPLOYEES.items() if employee.get("employee_id") in employee_ids]
            related_statuses = [statuses.get(node, "pending") for node in related]
            employee["status"] = "failed" if "failed" in related_statuses else "working" if "running" in related_statuses else "done" if related_statuses and all(item == "succeeded" for item in related_statuses) else "waiting"
        squad["status"] = "failed" if "failed" in statuses.values() else "completed" if all(statuses.get(node) == "succeeded" for node in NODE_IDS) else "running"
    job = copy.deepcopy(data.get("insight_job") or {})
    job.update({
        "execution_id": execution_id, "node_statuses": statuses,
        "active_node": active.node_id if active else "",
        "active_stage": NODE_STAGE.get(active.node_id, "completed" if execution.status == "awaiting_review" else "queued") if active else ("completed" if execution.status == "awaiting_review" else "queued"),
        "active_employee_id": (NODE_EMPLOYEES.get(active.node_id) or [""])[0] if active else "",
        "attempt": sum(node.attempt for node in nodes), "updated_at": now_iso(),
        "error": str(execution.error_message or ""),
    })
    completed_sections: list[str] = []
    if statuses.get("market-insight") == "succeeded":
        completed_sections.extend(["root_causes", "impacts", "evidence"])
    if statuses.get("requirement-analysis") == "succeeded":
        completed_sections.extend(["recommendation", "ipd_handoff"])
    if statuses.get("output-format") == "succeeded":
        completed_sections = list(SECTION_KEYS)
    job["completed_sections"] = completed_sections
    job["status"] = "failed" if execution.status == "failed" else "running"

    if execution.status == "awaiting_review" and statuses.get("output-format") == "succeeded":
        output_node = next(node for node in nodes if node.node_id == "output-format")
        artifacts = list((await db.execute(select(WorkflowArtifact).where(WorkflowArtifact.execution_id == execution_id, WorkflowArtifact.node_run_id == output_node.id).order_by(WorkflowArtifact.created_at.desc()))).scalars())
        if artifacts:
            artifact = artifacts[0]
            try:
                content = (run_root(execution) / Path(artifact.relative_path)).read_text(encoding="utf-8")
                document = validate_document(_parse_json(content), execution_id=execution_id, demand_hash=binding.demand_hash)
                insight = document_to_insight(document)
                data["insight"] = insight
                job.update({"status": "completed", "active_stage": "completed", "active_node": "", "active_employee_id": "", "completed_sections": list(SECTION_KEYS), "artifact_hash": artifact.content_hash, "error": ""})
                binding.status = "completed"
                binding.artifact_hash = artifact.content_hash
                binding.error_message = ""
                review = copy.deepcopy(data.get("insight_review") or empty_insight_review())
                review.update({"status": "draft", "version": review.get("version") or "V0.1", "demand_hash": binding.demand_hash, "source_job_id": binding.job_id, "coverage": calculate_insight_coverage(insight)})
                data["insight_review"] = review
            except Exception as exc:
                binding.format_attempt += 1
                binding.status = "partial" if binding.format_attempt <= 2 else "failed"
                binding.error_message = f"结构化回填失败：{str(exc)[:1000]}"
                job.update({"status": binding.status, "active_stage": "writing", "error": binding.error_message})
                if binding.format_attempt <= 2:
                    from backend.services.workflow_executor import retry_remote

                    await retry_remote(execution_id, "output-format")
                    output_node.status = "pending"
                    output_node.error_message = None
                    execution.status = "queued"
        else:
            binding.format_attempt += 1
            binding.status = "partial" if binding.format_attempt <= 2 else "failed"
            binding.error_message = "output-format未产生Artifact"
            job.update({"status": binding.status, "active_stage": "writing", "error": binding.error_message})
            if binding.format_attempt <= 2:
                from backend.services.workflow_executor import retry_remote

                await retry_remote(execution_id, "output-format")
                output_node.status = "pending"
                execution.status = "queued"
    else:
        binding.status = job["status"]
    data["staffing_plan"] = plan
    data["insight_job"] = job
    session.data = data
    await db.flush()
    return {"session_id": session.session_id, "job": job, "plan": plan}
