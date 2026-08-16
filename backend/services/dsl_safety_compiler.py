"""
backend/services/dsl_safety_compiler.py
=======================================
声明式 DSL 语法校验、Kahn 算法有向无环图（DAG）拓扑检测与零代码执行编译器。
物理消除 eval/exec 动态执行面，保证工作流编排的安全可控与确定性执行。
"""

from __future__ import annotations
import json
from collections import deque
from typing import List, Dict, Union, Set, Any, Optional

from backend.models.tenant_agent_schema import (
    WorkflowDSLPlan,
    WorkflowDSLNode,
    WorkflowNodeType,
)


class DSLValidationError(Exception):
    """DSL 语法或节点参数非法异常"""

    def __init__(self, message: str = ""):
        self.message = message
        super().__init__(f"[DSLValidationError] {message}")


class InvalidEdgeReferenceError(Exception):
    """工作流边引用了不存在的节点异常（悬空边）"""

    def __init__(self, message: str = ""):
        self.message = message
        super().__init__(f"[InvalidEdgeReferenceError] {message}")


class CyclicDependencyError(Exception):
    """工作流存在有向环路依赖异常"""

    def __init__(self, cycle_nodes: Optional[List[str]] = None, message: str = ""):
        self.cycle_nodes = cycle_nodes or []
        msg = message or f"Cycle detected among nodes: {self.cycle_nodes}"
        self.message = msg
        super().__init__(f"[CyclicDependencyError] {msg}")


class DSLSafetyCompiler:
    """
    DSL 安全编译器
    负责将声明式 JSON/Dict 工作流编译为强类型 AST，并完成拓扑无环性验证。
    """

    ALLOWED_NODE_TYPES: Set[str] = {
        node_type.value for node_type in WorkflowNodeType
    }

    @classmethod
    def compile_and_validate(
        cls, dsl_input: Union[Dict[str, Any], str, WorkflowDSLPlan]
    ) -> WorkflowDSLPlan:
        """
        编译并校验 DSL 工作流定义：
        1. 反序列化与 Schema 结构校验
        2. 节点类型白名单硬约束校验
        3. Kahn 拓扑排序与环路检测
        """
        if isinstance(dsl_input, str):
            try:
                data = json.loads(dsl_input)
            except Exception as e:
                raise DSLValidationError(f"Invalid JSON format: {str(e)}")
        elif isinstance(dsl_input, dict):
            data = dsl_input
        elif isinstance(dsl_input, WorkflowDSLPlan):
            plan = dsl_input
            cls.check_dag_cycle_kahn(plan)
            return plan
        else:
            raise DSLValidationError(f"Unsupported DSL input type: {type(dsl_input)}")

        # 校验节点类型白名单
        raw_nodes = data.get("nodes", [])
        if not isinstance(raw_nodes, list):
            raise DSLValidationError("'nodes' field must be a list")

        for idx, node in enumerate(raw_nodes):
            if not isinstance(node, dict):
                raise DSLValidationError(f"Node at index {idx} must be a dict")
            ntype = node.get("node_type")
            if not ntype or str(ntype) not in cls.ALLOWED_NODE_TYPES:
                raise DSLValidationError(
                    f"Disallowed node_type '{ntype}' at node '{node.get('id', idx)}'. "
                    f"Allowed types: {sorted(list(cls.ALLOWED_NODE_TYPES))}"
                )

        try:
            plan = WorkflowDSLPlan(**data)
        except Exception as e:
            raise DSLValidationError(f"Schema validation failed: {str(e)}")

        # 执行 Kahn 算法 DAG 无环校验并确定执行顺序
        cls.check_dag_cycle_kahn(plan)

        return plan

    @classmethod
    def check_dag_cycle_kahn(cls, plan: WorkflowDSLPlan) -> List[str]:
        """
        基于 Kahn 算法进行 DAG 有效性验证与拓扑执行序列生成
        
        算法流程：
        1. 验证所有 edges 引用源和目标是否均在 nodes 集合中（防悬空边）；
        2. 计算所有节点的入度（In-degree）并构建邻接表；
        3. 将所有入度为 0 的起始节点入队；
        4. 依次出队并将后继节点入度减 1，入度归零则入队；
        5. 若出队节点数 != 总节点数，则判定存在环路并抛出 CyclicDependencyError；
        6. 返回合法的拓扑执行顺序 List[str]。
        """
        node_map: Dict[str, WorkflowDSLNode] = {node.id: node for node in plan.nodes}
        node_ids: Set[str] = set(node_map.keys())

        # 1. 悬空边检测 (Dangling Edge Detection)
        for edge in plan.edges:
            if edge.source not in node_ids:
                raise InvalidEdgeReferenceError(
                    f"Edge source '{edge.source}' does not exist in node definitions"
                )
            if edge.target not in node_ids:
                raise InvalidEdgeReferenceError(
                    f"Edge target '{edge.target}' does not exist in node definitions"
                )

        # 2. 构建入度表与邻接表
        in_degree: Dict[str, int] = {nid: 0 for nid in node_ids}
        adj_list: Dict[str, List[str]] = {nid: [] for nid in node_ids}

        for edge in plan.edges:
            adj_list[edge.source].append(edge.target)
            in_degree[edge.target] += 1

        # 3. 入度为 0 节点入队（排序保证确定性执行序列）
        queue: deque[str] = deque(sorted([nid for nid, deg in in_degree.items() if deg == 0]))

        execution_order: List[str] = []

        # 4. Kahn 拓扑出队迭代
        while queue:
            curr = queue.popleft()
            execution_order.append(curr)

            # 按字典序排序后继节点，保证稳定调度
            for neighbor in sorted(adj_list[curr]):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # 5. 环路判定
        if len(execution_order) != len(node_ids):
            cycle_nodes = sorted([nid for nid, deg in in_degree.items() if deg > 0])
            raise CyclicDependencyError(
                cycle_nodes=cycle_nodes,
                message=f"Cycle detected among nodes: {cycle_nodes}",
            )

        return execution_order
