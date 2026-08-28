"""Validated AI resource planning projections for QuantumWorkspace projects."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from typing import Any


def _text(value: Any, limit: int = 500) -> str:
    return str(value or "").strip()[:limit]


def _number(value: Any, *, minimum: float = 0, maximum: float = 10_000_000) -> float | None:
    if value in (None, "", "待压测", "待确认"):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return max(minimum, min(maximum, result))


def _integer(value: Any, *, minimum: int = 0, maximum: int = 1_000_000) -> int | None:
    result = _number(value, minimum=minimum, maximum=maximum)
    return int(result) if result is not None else None


def build_resource_plan_skeleton(project: Any, process: dict[str, Any]) -> dict[str, Any]:
    stages = process.get("stages") or []
    return {
        "schema_version": "1.0",
        "source_status": "UNCONFIGURED",
        "generated_by": None,
        "updated_at": None,
        "scenario": {
            "name": _text(getattr(project, "name", ""), 160),
            "goal": _text(getattr(project, "goal", ""), 4000),
            "desired_outputs": list(getattr(project, "desired_outputs", None) or [])[:40],
        },
        "systems": [
            {
                "id": f"system-{index + 1}",
                "name": _text(stage.get("name"), 120),
                "role": "待 AI 根据场景拆解",
                "deployment": "待配置",
                "replicas": None,
            }
            for index, stage in enumerate(stages)
        ],
        "infrastructure": {
            "ecs": {"count": None, "v_cpu": None, "memory_gb": None},
            "storage": {"system_disk_gb": None, "data_disk_gb": None, "object_storage_gb": None},
            "hyperconverged_nodes": {"count": None, "profile": "待配置"},
            "gpu": {"model": "待选型", "count": None, "memory_gb": None},
            "network": {"bandwidth_mbps": None},
        },
        "runtime": {
            "microservices": None,
            "containers": None,
            "queues": None,
            "ontology": "待建模",
            "agents": {"count": None, "concurrency": None},
            "inference": {"service": "待配置", "provider": "待选择", "model": "待选择", "replicas": None},
        },
        "sla": {
            "p95_latency_ms": None,
            "throughput_rps": None,
            "availability": "待定义",
            "target_monthly_cost_cny": None,
            "acceleration": "待评估",
        },
        "token_factory": {
            "status": "UNCONNECTED",
            "product_mapping": "待映射",
            "token_peak_per_minute": None,
            "monthly_token_estimate": None,
            "capacity_unit": "待 Token Factory 接口确认",
            "evidence": "需要业务压测与 Token Factory 产品目录作为选型证据。",
        },
        "topology": {"nodes": [], "edges": []},
        "assumptions": ["当前尚未生成资源方案；所有数量字段必须经业务基线或压测确认。"],
    }


def _normalize_systems(value: Any) -> list[dict[str, Any]]:
    systems = []
    for index, item in enumerate(value if isinstance(value, list) else []):
        if not isinstance(item, dict):
            continue
        systems.append({
            "id": _text(item.get("id"), 80) or f"system-{index + 1}",
            "name": _text(item.get("name"), 160) or f"系统 {index + 1}",
            "role": _text(item.get("role"), 500),
            "deployment": _text(item.get("deployment"), 120) or "待配置",
            "replicas": _integer(item.get("replicas"), maximum=10_000),
        })
        if len(systems) >= 40:
            break
    return systems


def _normalize_topology(value: Any, systems: list[dict[str, Any]]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    nodes = []
    for index, item in enumerate(source.get("nodes") if isinstance(source.get("nodes"), list) else []):
        if not isinstance(item, dict):
            continue
        nodes.append({
            "id": _text(item.get("id"), 80) or f"node-{index + 1}",
            "label": _text(item.get("label"), 160) or f"节点 {index + 1}",
            "type": _text(item.get("type"), 40) or "service",
            "status": _text(item.get("status"), 32) or "PLANNED",
        })
        if len(nodes) >= 80:
            break
    if not nodes:
        nodes = [{"id": "scenario", "label": "用户场景", "type": "scenario", "status": "PLANNED"}]
        nodes.extend({"id": item["id"], "label": item["name"], "type": "system", "status": "PLANNED"} for item in systems)
    node_ids = {item["id"] for item in nodes}
    edges = []
    for index, item in enumerate(source.get("edges") if isinstance(source.get("edges"), list) else []):
        if not isinstance(item, dict):
            continue
        source_id, target_id = _text(item.get("source"), 80), _text(item.get("target"), 80)
        if source_id in node_ids and target_id in node_ids:
            edges.append({"id": _text(item.get("id"), 80) or f"edge-{index + 1}", "source": source_id, "target": target_id})
        if len(edges) >= 160:
            break
    if not edges and "scenario" in node_ids:
        edges = [{"id": f"scenario-{item['id']}", "source": "scenario", "target": item["id"]} for item in systems]
    return {"nodes": nodes, "edges": edges}


def normalize_resource_plan(candidate: Any, project: Any, process: dict[str, Any], *, generated_by: str) -> dict[str, Any]:
    source = candidate if isinstance(candidate, dict) else {}
    skeleton = build_resource_plan_skeleton(project, process)
    systems = _normalize_systems(source.get("systems")) or skeleton["systems"]
    infrastructure = source.get("infrastructure") if isinstance(source.get("infrastructure"), dict) else {}
    ecs = infrastructure.get("ecs") if isinstance(infrastructure.get("ecs"), dict) else {}
    storage = infrastructure.get("storage") if isinstance(infrastructure.get("storage"), dict) else {}
    hci = infrastructure.get("hyperconverged_nodes") if isinstance(infrastructure.get("hyperconverged_nodes"), dict) else {}
    gpu = infrastructure.get("gpu") if isinstance(infrastructure.get("gpu"), dict) else {}
    network = infrastructure.get("network") if isinstance(infrastructure.get("network"), dict) else {}
    runtime = source.get("runtime") if isinstance(source.get("runtime"), dict) else {}
    agents = runtime.get("agents") if isinstance(runtime.get("agents"), dict) else {}
    inference = runtime.get("inference") if isinstance(runtime.get("inference"), dict) else {}
    sla = source.get("sla") if isinstance(source.get("sla"), dict) else {}
    token_factory = source.get("token_factory") if isinstance(source.get("token_factory"), dict) else {}
    assumptions = [_text(item, 500) for item in source.get("assumptions", []) if _text(item, 500)][:20]
    return {
        **skeleton,
        "source_status": "AI_PROPOSED" if generated_by == "hermes" else "USER_CONFIGURED",
        "generated_by": generated_by,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "systems": systems,
        "infrastructure": {
            "ecs": {"count": _integer(ecs.get("count")), "v_cpu": _integer(ecs.get("v_cpu")), "memory_gb": _integer(ecs.get("memory_gb"))},
            "storage": {
                "system_disk_gb": _integer(storage.get("system_disk_gb")),
                "data_disk_gb": _integer(storage.get("data_disk_gb")),
                "object_storage_gb": _integer(storage.get("object_storage_gb")),
            },
            "hyperconverged_nodes": {"count": _integer(hci.get("count")), "profile": _text(hci.get("profile"), 160) or "待配置"},
            "gpu": {"model": _text(gpu.get("model"), 120) or "待选型", "count": _integer(gpu.get("count")), "memory_gb": _integer(gpu.get("memory_gb"))},
            "network": {"bandwidth_mbps": _integer(network.get("bandwidth_mbps"))},
        },
        "runtime": {
            "microservices": _integer(runtime.get("microservices")),
            "containers": _integer(runtime.get("containers")),
            "queues": _integer(runtime.get("queues")),
            "ontology": _text(runtime.get("ontology"), 1000) or "待建模",
            "agents": {"count": _integer(agents.get("count")), "concurrency": _integer(agents.get("concurrency"))},
            "inference": {
                "service": _text(inference.get("service"), 160) or "待配置",
                "provider": _text(inference.get("provider"), 120) or "待选择",
                "model": _text(inference.get("model"), 160) or "待选择",
                "replicas": _integer(inference.get("replicas")),
            },
        },
        "sla": {
            "p95_latency_ms": _integer(sla.get("p95_latency_ms")),
            "throughput_rps": _number(sla.get("throughput_rps")),
            "availability": _text(sla.get("availability"), 40) or "待定义",
            "target_monthly_cost_cny": _number(sla.get("target_monthly_cost_cny")),
            "acceleration": _text(sla.get("acceleration"), 500) or "待评估",
        },
        "token_factory": {
            "status": "UNCONNECTED",
            "product_mapping": _text(token_factory.get("product_mapping"), 500) or "待映射",
            "token_peak_per_minute": _integer(token_factory.get("token_peak_per_minute")),
            "monthly_token_estimate": _integer(token_factory.get("monthly_token_estimate")),
            "capacity_unit": _text(token_factory.get("capacity_unit"), 160) or "待 Token Factory 接口确认",
            "evidence": _text(token_factory.get("evidence"), 1000) or skeleton["token_factory"]["evidence"],
        },
        "topology": _normalize_topology(source.get("topology"), systems),
        "assumptions": assumptions or skeleton["assumptions"],
    }


def build_resource_recommendation_prompt(project: Any, process: dict[str, Any], constraints: str = "") -> str:
    tasks = [{"title": item.get("title"), "summary": item.get("summary"), "role": item.get("assignee_role")} for item in (process.get("tasks") or [])]
    return "\n".join([
        "你是企业 AI 基础设施解决方案架构师。请基于已确认项目场景生成可编辑的资源配置建议。",
        "只输出一个 JSON 对象，不要 Markdown、解释或代码围栏。",
        "没有业务基线时允许给出带假设的建议值，但必须在 assumptions 中说明，禁止声称已经部署或已经连接。",
        "token_factory.status 必须为 UNCONNECTED；映射只是建议，不得冒充超聚变产品接口返回。",
        "JSON 必须包含 systems、infrastructure、runtime、sla、token_factory、topology、assumptions。",
        "infrastructure 包含 ecs(count,v_cpu,memory_gb)、storage(system_disk_gb,data_disk_gb,object_storage_gb)、hyperconverged_nodes(count,profile)、gpu(model,count,memory_gb)、network(bandwidth_mbps)。",
        "runtime 包含 microservices、containers、queues、ontology、agents(count,concurrency)、inference(service,provider,model,replicas)。",
        "sla 包含 p95_latency_ms、throughput_rps、availability、target_monthly_cost_cny、acceleration。",
        "topology.nodes 每项包含 id,label,type,status；topology.edges 每项包含 id,source,target。",
        f"项目名称：{getattr(project, 'name', '')}",
        f"项目目标：{getattr(project, 'goal', '')}",
        f"期望成果：{json.dumps(getattr(project, 'desired_outputs', None) or [], ensure_ascii=False)}",
        f"流程任务：{json.dumps(tasks, ensure_ascii=False)}",
        f"用户补充约束：{_text(constraints, 4000) or '无'}",
    ])


def extract_resource_plan_json(answer: str) -> dict[str, Any]:
    value = answer.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", value, re.I)
    if fenced:
        value = fenced.group(1)
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("Hermes did not return a JSON resource plan")
        parsed = json.loads(value[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("Hermes resource plan must be a JSON object")
    return parsed


def build_resource_monitoring(executions: list[Any]) -> dict[str, Any]:
    if not executions:
        return {
            "source_status": "UNCONNECTED",
            "active_executions": 0,
            "total_executions": 0,
            "tokens_used": 0,
            "estimated_cost_usd": 0,
            "average_progress": 0,
            "executions": [],
        }
    active = {"queued", "running", "awaiting_review"}
    rows = [{
        "id": item.id,
        "workflow_id": item.workflow_id,
        "status": item.status,
        "progress": item.progress,
        "tokens_used": item.token_used,
        "estimated_cost_usd": float(item.estimated_cost_usd or 0),
        "provider": item.provider_used,
        "model": item.model_used,
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    } for item in executions]
    return {
        "source_status": "LIVE",
        "active_executions": sum(1 for item in executions if item.status in active),
        "total_executions": len(executions),
        "tokens_used": sum(item.token_used or 0 for item in executions),
        "estimated_cost_usd": round(sum(float(item.estimated_cost_usd or 0) for item in executions), 6),
        "average_progress": round(sum(item.progress or 0 for item in executions) / len(executions)),
        "executions": rows,
    }
