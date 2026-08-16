"""
Agent 间任务流转接口

POST   /api/tasks              — 投递任务
GET    /api/tasks/inbox        — 查某 Agent 的 inbox
GET    /api/tasks/{task_id}    — 查任务状态
PATCH  /api/tasks/{task_id}    — 更新状态
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from backend.agents.contracts import (
    Artifact,
    HarnessPolicy,
    HarnessTask,
    TaskStatus,
    utc_now,
)

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------- Pydantic schemas ----------


class TaskCreate(BaseModel):
    task_type: str
    goal: str
    assigned_to: str
    requested_by: str = "user"
    from_agent: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list)
    read_targets: list[str] = Field(default_factory=list)
    write_targets: list[str] = Field(default_factory=list)
    priority: int = 0
    policy: HarnessPolicy = Field(default_factory=HarnessPolicy)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(BaseModel):
    status: TaskStatus | None = None
    result_summary: str | None = None
    artifacts: list[Artifact] | None = None
    next_actions: list[str] | None = None


# ---------- 内存队列 (当前单进程版，后续切 PostgreSQL) ----------

_tasks: dict[str, HarnessTask] = {}


@router.post("", status_code=201)
async def post_task(body: TaskCreate) -> HarnessTask:
    """投递一个 Agent 间流转任务。"""
    task = HarnessTask(
        task_type=body.task_type,
        goal=body.goal,
        assigned_to=body.assigned_to,
        requested_by=body.requested_by,
        from_agent=body.from_agent,
        inputs=body.inputs,
        expected_outputs=body.expected_outputs,
        read_targets=body.read_targets,
        write_targets=body.write_targets,
        priority=body.priority,
        policy=body.policy,
        metadata=body.metadata,
        status=TaskStatus.READY,
    )
    _tasks[task.task_id] = task
    return task


@router.get("/inbox")
async def inbox(
    agent: str = Query(..., description="目标 Agent 名称"),
    status: TaskStatus | None = Query(None, description="可选：按状态过滤"),
) -> list[HarnessTask]:
    """获取指定 Agent 的待处理任务列表。"""
    results = [t for t in _tasks.values() if t.assigned_to == agent]
    if status is not None:
        results = [t for t in results if t.status == status]
    return sorted(results, key=lambda x: x.created_at, reverse=True)


@router.get("/{task_id}")
async def get_task(task_id: str) -> HarnessTask:
    """查询单个任务的状态。"""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return task


@router.patch("/{task_id}")
async def update_task(task_id: str, body: TaskUpdate) -> HarnessTask:
    """更新任务状态与执行结果。"""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")

    if body.status is not None:
        task.transition(body.status)
    if (
        body.status in (TaskStatus.DONE, TaskStatus.FAILED)
        and task.completed_at is None
    ):
        task.completed_at = utc_now()
    task.with_result(
        summary=body.result_summary,
        artifacts=body.artifacts,
        next_actions=body.next_actions,
    )
    task.updated_at = utc_now()
    return task
