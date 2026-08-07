"""
Agent 间任务流转接口

POST   /api/tasks              — 投递任务
GET    /api/tasks/inbox        — 查某 Agent 的 inbox
GET    /api/tasks/{task_id}    — 查任务状态
PATCH  /api/tasks/{task_id}    — 更新状态
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


# ---------- Pydantic schemas ----------


class TaskCreate(BaseModel):
    from_agent: str
    to_agent: str
    task_type: str
    payload: Optional[dict[str, Any]] = None
    priority: int = 0


class TaskUpdate(BaseModel):
    status: str  # pending | in_progress | done


class TaskOut(BaseModel):
    id: int
    from_agent: str
    to_agent: str
    task_type: str
    payload: Optional[dict[str, Any]]
    status: str
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ---------- 内存队列 (demo 版，生产切 PostgreSQL) ----------

_tasks: dict[int, dict[str, Any]] = {}
_next_id: int = 1


def _now() -> str:
    return datetime.utcnow().isoformat()


@router.post("", status_code=201)
async def post_task(body: TaskCreate) -> TaskOut:
    """投递一个 Agent 间流转任务。"""
    global _next_id
    task = {
        "id": _next_id,
        "from_agent": body.from_agent,
        "to_agent": body.to_agent,
        "task_type": body.task_type,
        "payload": body.payload or {},
        "status": "pending",
        "created_at": _now(),
        "completed_at": None,
    }
    _tasks[_next_id] = task
    _next_id += 1
    return TaskOut(**task)


@router.get("/inbox")
async def inbox(
    agent: str = Query(..., description="目标 Agent 名称"),
) -> list[TaskOut]:
    """获取指定 Agent 的待处理任务列表。"""
    results = [TaskOut(**t) for t in _tasks.values() if t["to_agent"] == agent]
    return sorted(results, key=lambda x: x.created_at or "", reverse=True)


@router.get("/{task_id}")
async def get_task(task_id: int) -> TaskOut:
    """查询单个任务的状态。"""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")
    return TaskOut(**task)


@router.patch("/{task_id}")
async def update_task(task_id: int, body: TaskUpdate) -> TaskOut:
    """更新任务状态 (pending → in_progress → done)。"""
    task = _tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"task not found: {task_id}")

    allowed = {"pending", "in_progress", "done"}
    if body.status not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"invalid status: {body.status}, must be one of {allowed}",
        )

    task["status"] = body.status
    if body.status == "done":
        task["completed_at"] = _now()
    return TaskOut(**task)
