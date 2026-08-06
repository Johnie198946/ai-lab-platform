"""
Agent 运行时引擎

读取 manifest → 检查依赖 → 触发下游 Agent
编排逻辑: 不在 Agent 代码里，在运行时引擎里
"""

import asyncio
import json
import os
import subprocess
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
    1. 读 manifest → 找上游产出 (asyncio.gather 并行)
    2. 检查依赖 → 上游是否已完成？
    3. pre_check → Token预算·动态退避·权限
    4. 执行 Agent (Subprocess/Task 引擎闭环)
    5. post_check → 输出合规验证
    6. 写 manifest → 通知下游
    """

    def __init__(self, data_dir: str = "data"):
        self.registry = AgentRegistry()
        self.guard = AgentGuard()
        self.tokenbox = TokenBox()
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)

    # ---------- 读上游 (并发并行机制) ----------
    async def _read_single_dep_manifest(self, dep_name: str) -> List[Dict]:
        """读取单个依赖 Agent 的 manifest"""
        manifest_path = self.data_dir / "manifests" / f"{dep_name}.json"
        if not manifest_path.exists():
            return []
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            return [e for e in entries if not e.get("processed")]
        except Exception:
            return []

    async def read_manifest(self, agent_name: str) -> List[Dict]:
        """异步并行读取所有上游 Agent 的 manifest，合并找增量"""
        deps = self.registry.get_dependencies(agent_name)
        if not deps:
            return []  # 采集层 Agent 无上游

        # asyncio.gather 并行并发检查多依赖上游
        tasks = [self._read_single_dep_manifest(d) for d in deps]
        results = await asyncio.gather(*tasks)
        combined = []
        for r in results:
            combined.extend(r)
        return combined

    # ---------- 实际 Agent 执行器闭环 ----------
    async def _execute_agent_impl(
        self, agent: AgentMeta, upstream_items: List[Dict]
    ) -> Dict:
        """真实 Agent 执行器闭环 (支持脚本文档构建与编译)"""
        # 针对知识编译与矩阵更新，触发 knowledge_matrix 逻辑
        if agent.name in ["全量入库", "轻量编译", "深度编译"]:
            try:
                script_path = (
                    "/Users/dengzhaoyu/Desktop/AI Lab/ai-lab-platform/"
                    "scripts/build_knowledge_matrix.py"
                )
                cmd = ["python3", script_path]
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                return {
                    "exit_code": proc.returncode,
                    "stdout": stdout.decode().strip(),
                    "stderr": stderr.decode().strip()
                }
            except Exception as e:
                return {"error": str(e)}

        return {"status": "executed", "items_processed": len(upstream_items)}

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

        # 1. 并行读上游
        upstream = await self.read_manifest(agent_name)
        if not upstream and not force and agent.layer != "采集":
            return {"skipped": f"No new upstream data for {agent_name}"}

        # 2. pre_check (含动态退避)
        passed, reason = self.guard.pre_check(
            agent_name=agent.name,
            estimated_tokens=agent.token_budget,
            allowed_dirs=agent.inputs,
        )
        if not passed and not force:
            return {"blocked": reason}

        # 3. 真实 Agent 执行闭环
        exec_res = await self._execute_agent_impl(agent, upstream)

        if exec_res.get("exit_code", 0) != 0 and "error" in exec_res:
            self.guard.record_failure(agent_name)
            return {"agent": agent_name, "status": "failed", "details": exec_res}

        # 4. 成功记录与退避重置
        self.guard.record_success(agent_name)

        # 5. 写入输出 manifest
        await self._write_output_manifest(agent)

        return {
            "agent": agent_name,
            "status": "completed",
            "upstream_items": len(upstream),
            "exec_details": exec_res,
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
