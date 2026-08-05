"""
Agent 运行时引擎

读取 manifest → 检查依赖 → 触发下游 Agent
编排逻辑: 不在 Agent 代码里，在运行时引擎里
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from backend.agents.registry import AgentRegistry, AgentMeta
from backend.agents.guard import AgentGuard
from backend.services.tokenbox import TokenBox


class AgentRuntime:
    """
    Agent 执行引擎

    流程:
    1. 读 manifest → 找上游产出
    2. 检查依赖 → 上游是否已完成？
    3. pre_check → Token预算·频率·权限
    4. 执行 Agent
    5. post_check → 输出合规验证
    6. 写 manifest → 通知下游
    """

    def __init__(self, data_dir: str = "data"):
        self.registry = AgentRegistry()
        self.guard = AgentGuard()
        self.tokenbox = TokenBox()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

    # ---------- 读上游 ----------
    async def read_manifest(self, agent_name: str) -> List[Dict]:
        """读取上游 Agent 的 manifest，找增量"""
        deps = self.registry.get_dependencies(agent_name)
        if not deps:
            return []  # 采集层 Agent 无上游

        manifest_path = self.data_dir / "manifests" / f"{agent_name}.json"
        if not manifest_path.exists():
            return []

        with open(manifest_path) as f:
            entries = json.load(f)

        # 只返回未处理的
        unprocessed = [e for e in entries if not e.get("processed")]
        return unprocessed

    # ---------- 执行 ----------
    async def run(self, agent_name: str, force: bool = False) -> Dict:
        """
        执行一个 Agent

        Args:
            agent_name: Agent 名称
            force: 是否跳过频率限制
        """
        agent = self.registry._agents.get(agent_name)
        if not agent:
            return {"error": f"Agent not found: {agent_name}"}

        # 1. 读上游
        upstream = await self.read_manifest(agent_name)
        if not upstream and not force and agent.layer != "采集":
            return {"skipped": f"No new upstream data for {agent_name}"}

        # 2. pre_check
        passed, reason = self.guard.pre_check(
            agent_name=agent.name,
            estimated_tokens=agent.token_budget,
            allowed_dirs=agent.inputs,
        )
        if not passed and not force:
            return {"blocked": reason}

        # 3. 记录运行
        self.guard.record_run(agent_name)

        # 4. 预留: 实际 Agent 执行在此处
        # result = await execute_agent_impl(agent, upstream)

        # 5. 写入输出 manifest
        await self._write_output_manifest(agent)

        return {
            "agent": agent_name,
            "status": "completed",
            "upstream_items": len(upstream),
            "time": datetime.now().isoformat(),
        }

    async def _write_output_manifest(self, agent: AgentMeta):
        """Agent 执行完后，写 manifest 通知下游"""
        manifest_path = self.data_dir / "manifests" / "_global.json"
        manifest_path.parent.mkdir(exist_ok=True)

        entry = {
            "agent": agent.name,
            "time": datetime.now().isoformat(),
            "layer": agent.layer,
            "outputs": agent.outputs,
            "processed": False,
        }

        entries = []
        if manifest_path.exists():
            with open(manifest_path) as f:
                entries = json.load(f)

        entries.append(entry)

        with open(manifest_path, "w") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    # ---------- 链式执行 ----------
    async def run_chain(self, start_agent: str) -> List[Dict]:
        """
        从指定 Agent 开始，执行整条依赖链

        例: run_chain("Horizon") → Horizon → 全量入库 → 轻量编译 → 深度编译 → 知识进化
        """
        results = []
        visited = set()
        queue = [start_agent]

        while queue:
            name = queue.pop(0)
            if name in visited:
                continue
            visited.add(name)

            result = await self.run(name)
            results.append(result)

            # 触发下游
            downstream = self.registry.get_downstream(name)
            queue.extend([d for d in downstream if d not in visited])

        return results

    # ---------- 状态 ----------
    async def status(self) -> Dict:
        """获取运行时状态概览"""
        reg = self.registry
        return {
            "total_agents": len(reg._agents),
            "by_layer": {
                layer: len(reg.list_by_layer(layer))
                for layer in ["采集", "处理", "编译", "看板", "治理"]
            },
            "tokenbox": self.tokenbox.all_summary(),
        }
