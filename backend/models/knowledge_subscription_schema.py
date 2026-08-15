"""
backend/models/knowledge_subscription_schema.py
===============================================
红黄绿知识分级、五维隔离元数据、订阅生命周期与 Merkle DAG 溯源模型。
"""

from __future__ import annotations
import time
import hashlib
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class SecurityLevel(str, Enum):
    """
    知识安全分级枚举（红黄绿三色分级标准）
    - RED: 🔴 绝密私有（核心IP、企业机密、私人对话资产），物理隔离，禁止外流与跨租户订阅
    - YELLOW: 🟡 受限共享（高阶方法论、脱敏案例库），需租户申请 + Master Admin 审批授权
    - GREEN: 🟢 公开通用（行业标准、开源架构、公共百科/工具库），全员按需一键自由订阅
    """
    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


class DomainEnum(str, Enum):
    """业务领域枚举"""
    AUDIT = "audit"
    FINANCE = "finance"
    TOKENOPS = "tokenops"
    MANUFACTURING = "manufacturing"
    HEALTHCARE = "healthcare"
    GENERAL = "general"


class SubscriptionStatus(str, Enum):
    """知识订阅生命周期状态"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class KnowledgeItemMetadata(BaseModel):
    """
    知识条目五维隔离与安全元数据模型
    """
    id: str = Field(..., description="知识条目唯一 ID")
    title: str = Field(..., description="知识条目标题")
    domain: str = Field(default="general", description="所属领域 (audit/finance/manufacturing/healthcare/tokenops/general)")
    tenant: str = Field(default="public", description="归属租户 (public 为全局共享，具体 tenant_id 为私有)")
    task_id: Optional[str] = Field(default=None, description="产出该知识的任务 ID（防同域历史任务串扰）")
    security_level: SecurityLevel = Field(default=SecurityLevel.GREEN, description="红黄绿安全等级")
    subscribers: List[str] = Field(default_factory=list, description="授权订阅租户白名单列表")
    lineage_hash: Optional[str] = Field(default=None, description="SHA256 因果血缘与内容摘要")
    upstream_ids: List[str] = Field(default_factory=list, description="上游依赖知识 ID 列表")
    created_at: float = Field(default_factory=time.time, description="创建时间戳")

    def compute_lineage_hash(self, raw_content: str = "") -> str:
        """根据条目属性与上游依赖计算 Merkle 血缘 SHA256 摘要"""
        upstream_repr = ",".join(sorted(self.upstream_ids))
        content_seed = f"{self.id}:{self.domain}:{self.tenant}:{self.security_level}:{upstream_repr}:{raw_content}"
        digest = hashlib.sha256(content_seed.encode("utf-8")).hexdigest()
        self.lineage_hash = digest
        return digest


class KnowledgeSubscriptionRecord(BaseModel):
    """
    黄色受限知识订阅申请与生命周期流转记录
    """
    subscription_id: str = Field(..., description="订阅申请单唯一 ID")
    tenant_id: str = Field(..., description="申请租户 ID")
    knowledge_id: str = Field(..., description="目标黄色知识条目 ID")
    status: SubscriptionStatus = Field(default=SubscriptionStatus.PENDING, description="当前审批状态")
    applied_at: float = Field(default_factory=time.time, description="申请提交时间戳")
    approved_by: Optional[str] = Field(default=None, description="审批人（必须为 Master Admin）")
    approved_at: Optional[float] = Field(default=None, description="审批处理时间戳")
    reason: Optional[str] = Field(default=None, description="申请理由或拒绝原因")


class MerkleDAGNode(BaseModel):
    """
    知识因果溯源 Merkle DAG 节点
    支持防投毒校验与端到端溯源。
    """
    node_id: str = Field(..., description="DAG 节点唯一标识（通常对应 knowledge_id）")
    data_hash: str = Field(..., description="本节点内容数据 SHA256")
    parent_hashes: List[str] = Field(default_factory=list, description="父节点哈希列表")
    timestamp: float = Field(default_factory=time.time, description="节点建立时间戳")

    def calculate_merkle_hash(self) -> str:
        """计算当前 Merkle DAG 节点的整体指纹"""
        parents_str = "|".join(sorted(self.parent_hashes))
        payload = f"{self.node_id}:{self.data_hash}:{parents_str}:{self.timestamp}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
