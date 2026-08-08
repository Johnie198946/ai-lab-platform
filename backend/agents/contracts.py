"""
Agent Harness 契约

把任务对象、策略边界、产物记录收敛成统一结构，供：
1. API 投递任务
2. Runtime 执行与记账
3. 后续审计 / 回放 / 失败补偿
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    """统一生成 UTC 时间，便于日志与回放对齐。"""
    return datetime.now(timezone.utc)


class TaskStatus(StrEnum):
    """统一任务状态机。"""

    DRAFT = "draft"
    READY = "ready"
    RUNNING = "running"
    WAITING_REVIEW = "waiting_review"
    DONE = "done"
    FAILED = "failed"


class Artifact(BaseModel):
    """任务执行过程中产生的外部产物。"""

    kind: str = "file"
    uri: str
    summary: str | None = None


class HarnessPolicy(BaseModel):
    """Harness 策略边界。"""

    readable_paths: list[str] = Field(default_factory=list)
    writable_paths: list[str] = Field(default_factory=list)
    knowledge_scope: list[str] = Field(default_factory=list)
    allow_network: bool = False
    requires_review: bool = False
    max_tokens: int = 50_000


class HarnessTask(BaseModel):
    """平台统一任务对象。"""

    task_id: str = Field(default_factory=lambda: f"task-{uuid4().hex[:12]}")
    task_type: str
    goal: str
    assigned_to: str
    requested_by: str = "system"
    from_agent: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    expected_outputs: list[str] = Field(default_factory=list)
    read_targets: list[str] = Field(default_factory=list)
    write_targets: list[str] = Field(default_factory=list)
    status: TaskStatus = TaskStatus.DRAFT
    priority: int = 0
    policy: HarnessPolicy = Field(default_factory=HarnessPolicy)
    result_summary: str | None = None
    artifacts: list[Artifact] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None

    def transition(self, status: TaskStatus) -> "HarnessTask":
        """切换任务状态并刷新时间戳。"""
        self.status = status
        self.updated_at = utc_now()
        if status in (TaskStatus.DONE, TaskStatus.FAILED):
            self.completed_at = self.updated_at
        return self

    def with_result(
        self,
        *,
        summary: str | None = None,
        artifacts: list[Artifact] | None = None,
        next_actions: list[str] | None = None,
    ) -> "HarnessTask":
        """写回任务结果。"""
        if summary is not None:
            self.result_summary = summary
        if artifacts is not None:
            self.artifacts = artifacts
        if next_actions is not None:
            self.next_actions = next_actions
        self.updated_at = utc_now()
        return self
