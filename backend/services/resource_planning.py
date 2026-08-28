"""Validated AI resource planning projections for QuantumWorkspace projects."""

from __future__ import annotations

import json
import random
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


def _default_scenario_twin() -> dict[str, Any]:
    return {
        "level": "L2 状态化仿真",
        "fidelity": {"data": 82, "interface": 76, "workflow": 90, "exception": 65},
        "actors": ["客户经理", "财务审批人", "交付经理", "最终客户"],
        "steps": ["客户申请", "资料校验", "信用审批", "订单创建", "库存分配", "履约开票"],
        "subagents": [
            {"id": "orchestrator", "name": "场景编排 Agent", "role": "控制步骤、分支和任务交接", "tools": ["流程状态", "事件总线"], "guardrails": ["不得调用生产写接口", "所有状态迁移必须记录证据"]},
            {"id": "finance", "name": "财务审批 Agent", "role": "执行信用、账期和风险判断", "tools": ["CRM Sandbox", "信用规则"], "guardrails": ["决策必须引用规则编号", "拒绝原因必须可解释"]},
            {"id": "delivery", "name": "交付 Agent", "role": "处理库存、拆单和交付决策", "tools": ["库存 Mock API", "ERP 模拟器"], "guardrails": ["库存不足时只能进入预设异常分支"]},
        ],
        "systems": [
            {
                "id": "erp-order-simulator", "name": "ERP 订单模拟器", "truth": "SIMULATED", "detail": "订单、审批、发票状态机", "interfaces": 6,
                "methodology": {
                    "scenario_scope": "承接信用审批后的订单创建、库存分配、履约与开票，不模拟 ERP 财务总账等无关模块。",
                    "module_reuse": "销售订单、库存预留、应收开票三个最小业务切片",
                    "data_strategy": "从用户字段字典提取客户、SKU、价格、账期；缺失值按约束生成合成数据并保留 lineage。",
                    "state_machine": ["DRAFT", "CREDIT_APPROVED", "ALLOCATED", "PARTIAL", "SHIPPED", "INVOICED", "CANCELLED"],
                    "agent_design": {"agent": "ERP 行为模拟 Agent", "objective": "依据场景事件驱动订单状态迁移并返回可解释结果", "inputs": ["客户信用结论", "订单行", "库存快照", "异常注入参数"], "tools": ["订单状态机", "规则引擎", "Mock API", "合成数据仓"], "memory": "仅保存当前仿真 run 的订单状态和证据链", "guardrails": ["禁止访问生产 ERP", "禁止生成未定义状态", "每次迁移必须输出 rule_id"]},
                    "validation": ["主链路六步全部可重放", "接口契约通过率 ≥ 95%", "库存不足/超信用/重复开票异常可复现"],
                },
                "contracts": [
                    {"method": "POST", "path": "/orders", "purpose": "创建订单"},
                    {"method": "POST", "path": "/orders/{id}/allocate", "purpose": "库存预留"},
                    {"method": "POST", "path": "/orders/{id}/invoice", "purpose": "模拟开票"},
                ],
            },
            {"id": "crm-sandbox", "name": "CRM 测试环境", "truth": "SANDBOX", "detail": "客户、联系人和历史交易", "interfaces": 4, "methodology": {"scenario_scope": "支撑客户资料与历史交易查询", "module_reuse": "客户主数据与商机历史", "data_strategy": "优先使用脱敏样本，无样本时生成分层客户画像", "state_machine": ["ACTIVE", "REVIEW", "BLOCKED"], "agent_design": {"agent": "CRM 数据代理", "objective": "返回与场景一致的客户上下文", "inputs": ["customer_id"], "tools": ["Sandbox API", "字段映射"], "memory": "只读会话缓存", "guardrails": ["PII 默认脱敏"]}, "validation": ["字段覆盖率 ≥ 90%", "查询结果可追溯"]}, "contracts": [{"method": "GET", "path": "/customers/{id}", "purpose": "查询客户"}]},
            {"id": "inventory-mock", "name": "库存 Mock API", "truth": "SIMULATED", "detail": "锁库、扣减、补货与异常", "interfaces": 5, "methodology": {"scenario_scope": "模拟可用量、锁库、扣减和跨仓调拨", "module_reuse": "库存可用量与预留模块", "data_strategy": "按 SKU/仓库/批次生成库存快照并注入缺货概率", "state_machine": ["AVAILABLE", "RESERVED", "SHORTAGE", "TRANSFER_PENDING", "DEDUCTED"], "agent_design": {"agent": "库存行为模拟 Agent", "objective": "按规则返回库存动作与异常", "inputs": ["sku", "quantity", "warehouse"], "tools": ["库存状态机", "异常注入器"], "memory": "run 级库存快照", "guardrails": ["库存不得小于零"]}, "validation": ["锁库与释放守恒", "缺货分支可重复"]}, "contracts": [{"method": "POST", "path": "/inventory/reserve", "purpose": "预留库存"}]},
            {"id": "synthetic-business-data", "name": "合成业务数据", "truth": "SYNTHETIC", "detail": "客户、商品、订单与异常样本", "interfaces": 8, "methodology": {"scenario_scope": "为所有模拟器提供一致的客户、商品、订单和异常样本", "module_reuse": "业务实体生成与关联约束", "data_strategy": "Schema 约束 + 分布参数 + 固定种子；不复制真实 PII", "state_machine": ["DRAFT", "GENERATED", "VALIDATED", "PUBLISHED"], "agent_design": {"agent": "合成数据设计 Agent", "objective": "生成满足关系和分布约束的可重放数据", "inputs": ["字段字典", "约束", "规模", "seed"], "tools": ["Schema 生成器", "质量校验器"], "memory": "数据集 manifest", "guardrails": ["禁止产生真实身份证号或联系方式"]}, "validation": ["Schema 通过率 100%", "主外键完整率 100%", "PII 扫描通过"]}, "contracts": [{"method": "POST", "path": "/datasets/generate", "purpose": "生成数据集"}]},
        ],
        "datasets": [],
    }


def _default_model_registry() -> dict[str, Any]:
    return {
        "models": [
            {"id": "model-online-general", "name": "企业通用大模型", "delivery_mode": "ONLINE", "provider": "AI Lab Provider Router", "version": "provider-managed", "stage": "PRODUCTION", "capabilities": ["chat", "tool_calling", "structured_output"], "context_window": 128000, "endpoint": "统一推理网关 / online", "artifact_uri": "", "runtime": "Provider API", "quantization": "N/A", "hardware": "Provider managed", "linked_agents": ["场景编排 Agent", "财务审批 Agent"], "linked_datasets": ["ERP 订单模拟器 · 销售订单样本"], "evaluation": {"scenario_pass_rate": 94, "p95_latency_ms": 1420, "cost_per_million_tokens": 18.6}, "truth": "CONNECTED"},
            {"id": "model-offline-private", "name": "企业私有推理模型", "delivery_mode": "OFFLINE", "provider": "AI Lab Model Runtime", "version": "v1.3-int4", "stage": "STAGING", "capabilities": ["chat", "rag", "function_calling"], "context_window": 32768, "endpoint": "Token Factory 私有推理池", "artifact_uri": "s3://model-registry/private-model/v1.3-int4", "runtime": "vLLM-compatible", "quantization": "INT4", "hardware": "16 × 企业级推理 GPU", "linked_agents": ["交付 Agent"], "linked_datasets": ["业务异常评测集"], "evaluation": {"scenario_pass_rate": 88, "p95_latency_ms": 980, "cost_per_million_tokens": 6.4}, "truth": "PLANNED"},
        ],
        "policy": {"online_allowed": True, "offline_required_for_sensitive_data": True, "promotion_gate": "评测通过 + 安全审查 + 容量压测", "fallback": "online → offline private → rule-based degraded mode"},
    }


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
        "scenario_twin": _default_scenario_twin(),
        "model_registry": _default_model_registry(),
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
    node_configs = {}
    raw_configs = source.get("node_configs") if isinstance(source.get("node_configs"), dict) else {}
    for node_id, item in raw_configs.items():
        if (node_id not in node_ids and not str(node_id).startswith(("deploy-", "flow-"))) or not isinstance(item, dict):
            continue
        node_configs[node_id] = {
            "deployment": _text(item.get("deployment"), 120),
            "truth_status": _text(item.get("truth_status"), 24).upper() or "PLANNED",
            "resource_binding": _text(item.get("resource_binding"), 160),
            "model_binding": _text(item.get("model_binding"), 160),
            "dataset_binding": _text(item.get("dataset_binding"), 160),
            "replicas": _integer(item.get("replicas"), maximum=10_000),
            "cpu": _number(item.get("cpu"), maximum=100_000),
            "memory_gb": _number(item.get("memory_gb"), maximum=10_000_000),
            "gpu": _number(item.get("gpu"), maximum=100_000),
            "metrics": _normalize_string_list(item.get("metrics"), limit=40, item_limit=80),
            "notes": _text(item.get("notes"), 1000),
        }
    return {"nodes": nodes, "edges": edges, "node_configs": node_configs}


def _normalize_string_list(value: Any, *, limit: int = 40, item_limit: int = 500) -> list[str]:
    return [_text(item, item_limit) for item in value if _text(item, item_limit)][:limit] if isinstance(value, list) else []


def _normalize_model_registry(value: Any) -> dict[str, Any]:
    default = _default_model_registry()
    source = value if isinstance(value, dict) else {}
    models = []
    for index, item in enumerate(source.get("models") if isinstance(source.get("models"), list) else default["models"]):
        if not isinstance(item, dict):
            continue
        fallback = default["models"][min(index, len(default["models"]) - 1)]
        evaluation = item.get("evaluation") if isinstance(item.get("evaluation"), dict) else {}
        models.append({
            "id": _text(item.get("id"), 80) or fallback["id"],
            "name": _text(item.get("name"), 160) or fallback["name"],
            "delivery_mode": _text(item.get("delivery_mode"), 16).upper() or fallback["delivery_mode"],
            "provider": _text(item.get("provider"), 120) or fallback["provider"],
            "version": _text(item.get("version"), 80) or fallback["version"],
            "stage": _text(item.get("stage"), 24).upper() or "CANDIDATE",
            "capabilities": _normalize_string_list(item.get("capabilities"), limit=40, item_limit=80) or fallback["capabilities"],
            "context_window": _integer(item.get("context_window"), maximum=10_000_000),
            "endpoint": _text(item.get("endpoint"), 300),
            "artifact_uri": _text(item.get("artifact_uri"), 1000),
            "runtime": _text(item.get("runtime"), 160),
            "quantization": _text(item.get("quantization"), 80),
            "hardware": _text(item.get("hardware"), 300),
            "linked_agents": _normalize_string_list(item.get("linked_agents"), limit=40, item_limit=160),
            "linked_datasets": _normalize_string_list(item.get("linked_datasets"), limit=40, item_limit=160),
            "evaluation": {
                "scenario_pass_rate": _number(evaluation.get("scenario_pass_rate"), maximum=100),
                "p95_latency_ms": _number(evaluation.get("p95_latency_ms"), maximum=10_000_000),
                "cost_per_million_tokens": _number(evaluation.get("cost_per_million_tokens"), maximum=10_000_000),
            },
            "truth": _text(item.get("truth"), 24).upper() or "PLANNED",
        })
        if len(models) >= 100:
            break
    policy = source.get("policy") if isinstance(source.get("policy"), dict) else default["policy"]
    return {"models": models or default["models"], "policy": {
        "online_allowed": bool(policy.get("online_allowed", True)),
        "offline_required_for_sensitive_data": bool(policy.get("offline_required_for_sensitive_data", True)),
        "promotion_gate": _text(policy.get("promotion_gate"), 500) or default["policy"]["promotion_gate"],
        "fallback": _text(policy.get("fallback"), 500) or default["policy"]["fallback"],
    }}


def _normalize_scenario_twin(value: Any) -> dict[str, Any]:
    default = _default_scenario_twin()
    source = value if isinstance(value, dict) else {}
    fidelity_source = source.get("fidelity") if isinstance(source.get("fidelity"), dict) else {}
    fidelity = {}
    for key, score in default["fidelity"].items():
        normalized_score = _integer(fidelity_source.get(key), maximum=100)
        fidelity[key] = normalized_score if normalized_score is not None else score
    subagents = []
    for index, item in enumerate(source.get("subagents") if isinstance(source.get("subagents"), list) else default["subagents"]):
        if not isinstance(item, dict):
            continue
        fallback = default["subagents"][min(index, len(default["subagents"]) - 1)]
        subagents.append({
            "id": _text(item.get("id"), 80) or fallback["id"],
            "name": _text(item.get("name"), 160) or fallback["name"],
            "role": _text(item.get("role"), 800) or fallback["role"],
            "tools": _normalize_string_list(item.get("tools"), limit=20, item_limit=120) or fallback["tools"],
            "guardrails": _normalize_string_list(item.get("guardrails"), limit=20, item_limit=300) or fallback["guardrails"],
        })
        if len(subagents) >= 20:
            break
    systems = []
    source_systems = source.get("systems") if isinstance(source.get("systems"), list) else default["systems"]
    for index, item in enumerate(source_systems):
        if not isinstance(item, dict):
            continue
        fallback = default["systems"][min(index, len(default["systems"]) - 1)]
        method = item.get("methodology") if isinstance(item.get("methodology"), dict) else {}
        fallback_method = fallback["methodology"]
        agent = method.get("agent_design") if isinstance(method.get("agent_design"), dict) else {}
        fallback_agent = fallback_method["agent_design"]
        contracts = []
        for contract in item.get("contracts") if isinstance(item.get("contracts"), list) else fallback.get("contracts", []):
            if isinstance(contract, dict):
                contracts.append({"method": _text(contract.get("method"), 12).upper() or "GET", "path": _text(contract.get("path"), 240), "purpose": _text(contract.get("purpose"), 300)})
            if len(contracts) >= 30:
                break
        systems.append({
            "id": _text(item.get("id"), 80) or fallback["id"],
            "name": _text(item.get("name"), 160) or fallback["name"],
            "truth": _text(item.get("truth"), 24).upper() or fallback["truth"],
            "detail": _text(item.get("detail"), 500) or fallback["detail"],
            "interfaces": _integer(item.get("interfaces"), maximum=1000) if _integer(item.get("interfaces"), maximum=1000) is not None else fallback["interfaces"],
            "methodology": {
                "scenario_scope": _text(method.get("scenario_scope"), 1500) or fallback_method["scenario_scope"],
                "module_reuse": _text(method.get("module_reuse"), 800) or fallback_method["module_reuse"],
                "data_strategy": _text(method.get("data_strategy"), 1500) or fallback_method["data_strategy"],
                "state_machine": _normalize_string_list(method.get("state_machine"), limit=30, item_limit=80) or fallback_method["state_machine"],
                "agent_design": {
                    "agent": _text(agent.get("agent"), 160) or fallback_agent["agent"],
                    "objective": _text(agent.get("objective"), 1000) or fallback_agent["objective"],
                    "inputs": _normalize_string_list(agent.get("inputs"), limit=30, item_limit=160) or fallback_agent["inputs"],
                    "tools": _normalize_string_list(agent.get("tools"), limit=30, item_limit=160) or fallback_agent["tools"],
                    "memory": _text(agent.get("memory"), 500) or fallback_agent["memory"],
                    "guardrails": _normalize_string_list(agent.get("guardrails"), limit=30, item_limit=300) or fallback_agent["guardrails"],
                },
                "validation": _normalize_string_list(method.get("validation"), limit=30, item_limit=300) or fallback_method["validation"],
            },
            "contracts": contracts,
        })
        if len(systems) >= 30:
            break
    datasets = []
    for index, item in enumerate(source.get("datasets") if isinstance(source.get("datasets"), list) else []):
        if not isinstance(item, dict):
            continue
        schema = item.get("schema") if isinstance(item.get("schema"), list) else []
        rows = item.get("sample_rows") if isinstance(item.get("sample_rows"), list) else []
        datasets.append({
            "id": _text(item.get("id"), 100) or f"dataset-{index + 1}",
            "simulator_id": _text(item.get("simulator_id"), 80),
            "name": _text(item.get("name"), 160) or f"模拟数据集 {index + 1}",
            "truth": "SYNTHETIC",
            "status": _text(item.get("status"), 32).upper() or "GENERATED",
            "row_count": _integer(item.get("row_count"), maximum=1_000_000) or len(rows),
            "seed": _integer(item.get("seed"), maximum=2_147_483_647) or 1,
            "generated_at": _text(item.get("generated_at"), 80) or None,
            "schema": [{"name": _text(field.get("name"), 80), "type": _text(field.get("type"), 40), "description": _text(field.get("description"), 300)} for field in schema[:40] if isinstance(field, dict)],
            "sample_rows": [{_text(key, 80): _text(cell, 300) for key, cell in row.items()} for row in rows[:50] if isinstance(row, dict)],
            "quality": {key: _number(score, maximum=100) for key, score in (item.get("quality") if isinstance(item.get("quality"), dict) else {}).items()},
            "lineage": _text(item.get("lineage"), 1000),
        })
        if len(datasets) >= 50:
            break
    return {
        "level": _text(source.get("level"), 120) or default["level"],
        "fidelity": fidelity,
        "actors": _normalize_string_list(source.get("actors"), limit=40, item_limit=160) or default["actors"],
        "steps": _normalize_string_list(source.get("steps"), limit=40, item_limit=160) or default["steps"],
        "subagents": subagents or default["subagents"],
        "systems": systems or default["systems"],
        "datasets": datasets,
    }


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
        "scenario_twin": _normalize_scenario_twin(source.get("scenario_twin")),
        "model_registry": _normalize_model_registry(source.get("model_registry")),
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
        "JSON 必须包含 scenario_twin、model_registry、systems、infrastructure、runtime、sla、token_factory、topology、assumptions。",
        "scenario_twin 必须描述 actors、steps、subagents、systems、datasets；每个模拟 system 必须包含 methodology（scenario_scope、module_reuse、data_strategy、state_machine、agent_design、validation）和 contracts。",
        "模拟设计只覆盖当前需求使用的最小业务切片，必须明确真实/脱敏/SANDBOX/SIMULATED/SYNTHETIC 边界，不得声称复刻完整生产系统。",
        "infrastructure 包含 ecs(count,v_cpu,memory_gb)、storage(system_disk_gb,data_disk_gb,object_storage_gb)、hyperconverged_nodes(count,profile)、gpu(model,count,memory_gb)、network(bandwidth_mbps)。",
        "runtime 包含 microservices、containers、queues、ontology、agents(count,concurrency)、inference(service,provider,model,replicas)。",
        "model_registry.models 必须同时覆盖 ONLINE 与 OFFLINE，包含 provider、version、stage、capabilities、endpoint/artifact_uri、runtime、hardware、linked_agents、linked_datasets、evaluation 与 truth。",
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


def generate_simulation_dataset(plan: dict[str, Any], simulator_id: str, *, row_count: int, seed: int) -> dict[str, Any]:
    """Create deterministic, inspectable synthetic preview data; never copies production records."""
    twin = _normalize_scenario_twin(plan.get("scenario_twin"))
    simulator = next((item for item in twin["systems"] if item["id"] == simulator_id), None)
    if simulator is None:
        raise ValueError("simulation component does not exist")
    rng = random.Random(seed)
    sample_size = min(max(row_count, 1), 20)
    if simulator_id == "erp-order-simulator":
        schema = [
            {"name": "order_id", "type": "string", "description": "模拟销售订单编号"},
            {"name": "customer_id", "type": "string", "description": "合成客户标识"},
            {"name": "sku", "type": "string", "description": "合成商品编码"},
            {"name": "quantity", "type": "integer", "description": "订购数量"},
            {"name": "amount_cny", "type": "decimal", "description": "订单含税金额"},
            {"name": "state", "type": "enum", "description": "订单状态机状态"},
            {"name": "rule_id", "type": "string", "description": "触发状态迁移的规则证据"},
        ]
        states = simulator["methodology"]["state_machine"]
        rows = [{
            "order_id": f"SIM-SO-{seed % 10000:04d}-{index + 1:03d}",
            "customer_id": f"SYN-C-{rng.randint(1000, 9999)}",
            "sku": f"SKU-{rng.randint(100, 999)}",
            "quantity": rng.randint(1, 20),
            "amount_cny": f"{rng.randint(8, 180) * 100:.2f}",
            "state": states[rng.randrange(len(states))],
            "rule_id": f"ERP-R-{rng.randint(1, 12):02d}",
        } for index in range(sample_size)]
        entity = "销售订单"
    else:
        schema = [
            {"name": "record_id", "type": "string", "description": "合成记录标识"},
            {"name": "scenario_step", "type": "string", "description": "关联业务步骤"},
            {"name": "status", "type": "enum", "description": "模拟状态"},
            {"name": "evidence", "type": "string", "description": "生成规则证据"},
        ]
        states = simulator["methodology"]["state_machine"]
        steps = twin["steps"]
        rows = [{"record_id": f"SYN-{simulator_id[:8].upper()}-{index + 1:03d}", "scenario_step": steps[rng.randrange(len(steps))], "status": states[rng.randrange(len(states))], "evidence": f"seed:{seed}/rule:{rng.randint(1, 20)}"} for index in range(sample_size)]
        entity = simulator["detail"]
    return {
        "id": f"dataset-{simulator_id}-{seed}",
        "simulator_id": simulator_id,
        "name": f"{simulator['name']} · {entity}样本",
        "truth": "SYNTHETIC",
        "status": "VALIDATED",
        "row_count": row_count,
        "seed": seed,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "schema": schema,
        "sample_rows": rows,
        "quality": {"schema_validity": 100, "referential_integrity": 100, "pii_safety": 100, "scenario_coverage": 84},
        "lineage": f"由 {simulator['name']} methodology + 场景步骤 + seed={seed} 确定性生成；未读取生产数据。",
    }


def build_resource_context_chat_prompt(
    plan: dict[str, Any],
    *,
    context_id: str,
    context_title: str,
    question: str,
    monitoring: dict[str, Any] | None = None,
) -> str:
    safe_plan = normalize_resource_plan(plan, type("Project", (), {"name": "", "goal": "", "desired_outputs": []})(), {}, generated_by="user")
    scenario_twin = safe_plan.get("scenario_twin") or {}
    context_map = {
        "scenario": safe_plan.get("scenario"), "scenario-twin": safe_plan.get("scenario_twin"),
        "simulation": safe_plan.get("scenario_twin"), "systems": safe_plan.get("systems"),
        "infrastructure": safe_plan.get("infrastructure"), "runtime": safe_plan.get("runtime"),
        "sla": safe_plan.get("sla"), "token-factory": safe_plan.get("token_factory"),
        "datasets": {
            "datasets": scenario_twin.get("datasets") or [],
            "systems": scenario_twin.get("systems") or [],
        },
        "model-registry": safe_plan.get("model_registry"),
        "topology-node": {
            "topology": safe_plan.get("topology"),
            "infrastructure": safe_plan.get("infrastructure"),
            "runtime": safe_plan.get("runtime"),
            "model_registry": safe_plan.get("model_registry"),
        },
        "monitoring": monitoring or {"source_status": "UNCONNECTED"},
    }
    context = context_map.get(context_id, {"title": context_title})
    return "\n".join([
        "你是 AI Resource 工作台的上下文助手。请只围绕当前卡片回答，先给结论，再给依据和可执行建议。",
        "必须区分 REAL、SANDBOX、SIMULATED、SYNTHETIC、PLANNED、UNCONNECTED；不得把规划或模拟数据描述成生产事实。",
        f"当前卡片：{_text(context_title, 160)} ({_text(context_id, 80)})",
        f"卡片上下文：{json.dumps(context, ensure_ascii=False)[:12000]}",
        f"用户问题：{_text(question, 12000)}",
    ])


def build_resource_monitoring(executions: list[Any], plan: dict[str, Any] | None = None, tasks: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    safe_plan = plan if isinstance(plan, dict) else {}
    infra, runtime = safe_plan.get("infrastructure") or {}, safe_plan.get("runtime") or {}
    ecs, storage = infra.get("ecs") or {}, infra.get("storage") or {}
    gpu, network, hci = infra.get("gpu") or {}, infra.get("network") or {}, infra.get("hyperconverged_nodes") or {}
    agents, inference = runtime.get("agents") or {}, runtime.get("inference") or {}
    datasets = (safe_plan.get("scenario_twin") or {}).get("datasets") or []
    models = (safe_plan.get("model_registry") or {}).get("models") or []
    resource_inventory = [
        {"key": "ecs", "category": "计算", "label": "ECS", "configured": f"{ecs.get('count') or 0} 台 / {ecs.get('v_cpu') or 0} vCPU / {ecs.get('memory_gb') or 0} GB", "metrics": ["cpu_utilization", "memory_utilization", "instance_health"]},
        {"key": "hci", "category": "计算", "label": "超融合节点", "configured": f"{hci.get('count') or 0} 节点 · {hci.get('profile') or '待配置'}", "metrics": ["node_health", "cpu_utilization", "storage_latency"]},
        {"key": "gpu", "category": "加速", "label": "GPU", "configured": f"{gpu.get('count') or 0} × {gpu.get('model') or '待选型'} / {gpu.get('memory_gb') or 0} GB", "metrics": ["gpu_utilization", "gpu_memory_utilization", "temperature", "power"]},
        {"key": "storage", "category": "存储", "label": "块与对象存储", "configured": f"系统 {storage.get('system_disk_gb') or 0} GB · 数据 {storage.get('data_disk_gb') or 0} GB · 对象 {storage.get('object_storage_gb') or 0} GB", "metrics": ["capacity_used", "iops", "throughput", "latency"]},
        {"key": "network", "category": "网络", "label": "业务带宽", "configured": f"{network.get('bandwidth_mbps') or 0} Mbps", "metrics": ["bandwidth_used", "packet_loss", "p95_rtt"]},
        {"key": "runtime", "category": "AI Runtime", "label": "服务与队列", "configured": f"{runtime.get('microservices') or 0} 微服务 · {runtime.get('containers') or 0} 容器 · {runtime.get('queues') or 0} 队列", "metrics": ["replica_health", "request_rate", "queue_depth", "error_rate"]},
        {"key": "agents", "category": "AI Runtime", "label": "Agent", "configured": f"{agents.get('count') or 0} 个 · 并发 {agents.get('concurrency') or 0}", "metrics": ["active_agents", "tool_success_rate", "turn_latency", "token_rate"]},
        {"key": "inference", "category": "模型", "label": "推理服务", "configured": f"{inference.get('service') or '待配置'} · {inference.get('model') or '待选择'} · {inference.get('replicas') or 0} 副本", "metrics": ["ttft", "tpot", "tokens_per_second", "p95_latency", "error_rate"]},
        {"key": "datasets", "category": "数据", "label": "模拟数据集", "configured": f"{len(datasets)} 个 · {sum(item.get('row_count') or 0 for item in datasets)} 行", "metrics": ["row_count", "quality_score", "freshness", "generation_failures"]},
        {"key": "models", "category": "模型", "label": "模型仓库", "configured": f"{len(models)} 个版本 · ONLINE {sum(1 for item in models if item.get('delivery_mode') == 'ONLINE')} / OFFLINE {sum(1 for item in models if item.get('delivery_mode') == 'OFFLINE')}", "metrics": ["scenario_pass_rate", "serving_health", "drift", "cost_per_million_tokens"]},
    ]
    empty = {
            "source_status": "UNCONNECTED",
            "active_executions": 0,
            "total_executions": 0,
            "tokens_used": 0,
            "estimated_cost_usd": 0,
            "average_progress": 0,
            "executions": [],
            "resource_inventory": resource_inventory,
            "task_bindings": [{"task_id": item.get("id"), "title": item.get("title"), "workflow_id": item.get("workflow_id"), "monitoring_scope": ["execution", "agent", "model", "resource"]} for item in (tasks or [])],
        }
    if not executions:
        return empty
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
        "resource_inventory": resource_inventory,
        "task_bindings": empty["task_bindings"],
    }
