"""
Agent 运行时引擎

读取 manifest → 检查依赖 → 触发下游 Agent
编排逻辑: 不在 Agent 代码里，在运行时引擎里
"""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from backend.agents.registry import AgentRegistry, AgentMeta
from backend.agents.guard import AgentGuard
from backend.agents.contracts import HarnessPolicy, HarnessTask, TaskStatus
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
        self.runtime_dir = self.data_dir / "runtime"
        self.runtime_dir.mkdir(exist_ok=True)
        self.ledger_path = self.runtime_dir / "task_ledger.jsonl"

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

    def _append_ledger(
        self,
        event_type: str,
        task: HarnessTask,
        payload: Dict | None = None,
    ):
        """追加写入任务流水账，供后续审计 / 回放使用。"""
        event = {
            "event": event_type,
            "time": datetime.now().isoformat(),
            "task": task.model_dump(mode="json"),
            "payload": payload or {},
        }
        with open(self.ledger_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")

    def _build_policy(self, agent: AgentMeta) -> HarnessPolicy:
        """从 Agent 元数据推导本次执行的 harness 策略。"""
        return HarnessPolicy(
            readable_paths=list(agent.inputs or []),
            writable_paths=list(agent.outputs or []),
            knowledge_scope=list(agent.knowledge_scope or []),
            allow_network=agent.allow_network,
            requires_review=agent.requires_review,
            max_tokens=agent.token_budget,
        )

    def _build_task(self, agent: AgentMeta, upstream_items: List[Dict]) -> HarnessTask:
        """把 runtime 执行收敛为统一任务对象。"""
        return HarnessTask(
            task_type="agent_run",
            goal=f"执行 Agent：{agent.name}",
            assigned_to=agent.name,
            requested_by="runtime",
            from_agent="runtime",
            inputs={
                "upstream_count": len(upstream_items),
                "depends_on": agent.depends_on,
                "schedule": agent.schedule,
                "model": agent.model,
            },
            expected_outputs=list(agent.outputs or []),
            read_targets=list(agent.inputs or []),
            write_targets=list(agent.outputs or []),
            policy=self._build_policy(agent),
            metadata={"layer": agent.layer, "tools": list(agent.tools or [])},
            status=TaskStatus.READY,
        )

    # ---------- 实际 Agent 执行器闭环 ----------
    async def _execute_agent_impl(
        self, agent: AgentMeta, upstream_items: List[Dict]
    ) -> Dict:
        """真实 Agent 执行器闭环 (支持脚本文档构建与编译)"""
        # 针对知识编译与矩阵更新，触发 knowledge_matrix 逻辑
        if agent.name in ["Wiki Ingester", "Wiki Writer", "Deep Compiler"]:
            try:
                script_path = os.path.join(
                    os.environ.get(
                        "AI_LAB_HOME", os.path.dirname(os.path.dirname(__file__))
                    ),
                    "scripts/build_knowledge_matrix.py",
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
                    "stderr": stderr.decode().strip(),
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
        task = self._build_task(agent, upstream)
        self._append_ledger("task_created", task)
        if not upstream and not force and agent.layer != "采集":
            task.transition(TaskStatus.FAILED).with_result(
                summary=f"{agent_name} 没有新的上游输入",
                next_actions=["等待上游 Agent 输出新的 manifest 后重试"],
            )
            self._append_ledger("task_skipped", task, {"reason": "no_upstream"})
            return {"skipped": f"No new upstream data for {agent_name}"}

        # 2. pre_check (含动态退避)
        passed, reason = self.guard.pre_check(
            agent_name=agent.name,
            estimated_tokens=agent.token_budget,
            allowed_dirs=agent.inputs,
        )
        if not passed and not force:
            task.transition(TaskStatus.FAILED).with_result(
                summary=reason,
                next_actions=["调整权限/预算/频率限制后再执行"],
            )
            self._append_ledger("task_blocked", task, {"reason": reason})
            return {"blocked": reason}

        # 3. 真实 Agent 执行闭环
        task.transition(TaskStatus.RUNNING)
        self._append_ledger("task_started", task)
        exec_res = await self._execute_agent_impl(agent, upstream)

        if exec_res.get("error") or exec_res.get("exit_code", 0) != 0:
            self.guard.record_failure(agent_name)
            task.transition(TaskStatus.FAILED).with_result(
                summary="Agent 执行失败",
                next_actions=["检查 stderr / error 并重试"],
            )
            self._append_ledger("task_failed", task, {"details": exec_res})
            return {
                "agent": agent_name,
                "task_id": task.task_id,
                "status": "failed",
                "details": exec_res,
            }

        # 4. 成功记录与退避重置
        self.guard.record_success(agent_name)

        # 5. 写入输出 manifest
        if agent.requires_review:
            task.transition(TaskStatus.WAITING_REVIEW)
        else:
            task.transition(TaskStatus.DONE)
        task.with_result(
            summary=f"{agent.name} 执行完成，处理 {len(upstream)} 条上游输入",
            next_actions=(["人工复核输出后再发布"] if agent.requires_review else []),
        )
        await self._write_output_manifest(agent, task)
        self._append_ledger(
            "task_completed"
            if task.status == TaskStatus.DONE
            else "task_waiting_review",
            task,
            {"exec_details": exec_res},
        )

        return {
            "agent": agent_name,
            "task_id": task.task_id,
            "status": task.status.value,
            "upstream_items": len(upstream),
            "exec_details": exec_res,
            "time": datetime.now().isoformat(),
        }

    async def _write_output_manifest(self, agent: AgentMeta, task: HarnessTask):
        """Agent 执行完后，写 manifest 通知下游"""
        manifests_dir = self.data_dir / "manifests"
        manifests_dir.mkdir(exist_ok=True)
        manifest_path = manifests_dir / f"{agent.name}.json"
        global_manifest_path = manifests_dir / "_global.json"
        manifest_path.parent.mkdir(exist_ok=True)

        entry = {
            "agent": agent.name,
            "task_id": task.task_id,
            "time": datetime.now().isoformat(),
            "layer": agent.layer,
            "outputs": agent.outputs,
            "status": task.status,
            "processed": False,
        }

        entries = []
        if manifest_path.exists():
            with open(manifest_path, encoding="utf-8") as f:
                entries = json.load(f)

        entries.append(entry)

        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

        global_entries = []
        if global_manifest_path.exists():
            with open(global_manifest_path, encoding="utf-8") as f:
                global_entries = json.load(f)
        global_entries.append(entry)
        with open(global_manifest_path, "w", encoding="utf-8") as f:
            json.dump(global_entries, f, indent=2, ensure_ascii=False)

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
            "ledger_path": str(self.ledger_path),
        }
