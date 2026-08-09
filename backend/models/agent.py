"""Agent 模型 — 云端子 Agent 注册表(对话创建·调度·管理)。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db import Base


class Agent(Base):
    """平台子 Agent: 对话创建 → 确认 → 调度 → 执行 → 汇报。

    执行经 hermes-bridge 调云端 Hermes; 汇报写 notifications 表。
    """

    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    tenant_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    mission: Mapped[str] = mapped_column(Text, nullable=False)
    # 数据源清单(JSON: [{name, url, kind}])
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # cron 表达式, 如 "0 18 * * *"
    schedule: Mapped[str] = mapped_column(
        String(64), nullable=False, default="0 18 * * *"
    )
    # 执行动作(JSON: ["collect", "ingest", "compile", "notify"])
    actions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 汇报通道: "inapp" | "feishu" | "inapp,feishu"
    channel: Mapped[str] = mapped_column(String(64), default="inapp")
    # 状态: draft(待确认) / active / paused / disabled
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # 生成的完整执行 prompt(给云端 Hermes)
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 挂载的 Hermes skills
    skills: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # 模板来源(模板库创建时记录, 如 policy-research)
    template_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    next_run_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str] = mapped_column(String(64), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
