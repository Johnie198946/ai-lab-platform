"""拓扑接口 — 基线 Agent 注册表（节点 + 边）唯一真值来源。

`GET /api/v1/topology` 返回 4 大 Agent（main/supervision/coder/knowledge）注册表拓扑，
对话页 Agent 选择栏与拓扑页 DAG 画布同源消费。运行状态统一标注「演示」。
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends

from backend.api.auth import require_auth
from backend.models.agent_registry import AGENT_EDGES, AGENT_NODES

router = APIRouter(prefix="/api/v1", tags=["topology"])


@router.get("/topology")
async def get_topology(payload=Depends(require_auth)) -> Dict[str, Any]:
    """返回基线 Agent 注册表拓扑：节点 + 边（状态标「演示」，后端无实时状态源）。"""
    return {
        # 返回浅拷贝，避免外部引用直接改动模块级常量
        "nodes": [dict(n) for n in AGENT_NODES],
        "edges": [dict(e) for e in AGENT_EDGES],
    }
