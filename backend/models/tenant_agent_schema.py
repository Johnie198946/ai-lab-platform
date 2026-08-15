"""
backend/models/tenant_agent_schema.py
=====================================
多租户 Agent 切片与声明式 DSL Schema 定义。
遵循零代码攻击面与严格类型校验规范。
"""

from __future__ import annotations
from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator, model_validator


class TenantRole(str, Enum):
    """租户用户角色枚举"""
    MASTER_ADMIN = "master_admin"
    TENANT_ADMIN = "tenant_admin"
    TENANT_MEMBER = "tenant_member"
    GUEST = "guest"


class TenantContext(BaseModel):
    """
    多租户安全上下文对象
    贯穿整个请求生命周期，由中间件解析生成并注入调用栈。
    """
    tenant_id: str = Field(..., description="租户唯一标识符 (例如 'tenant_alpha', 'master')")
    user_id: str = Field(..., description="用户唯一标识符")
    role: TenantRole = Field(default=TenantRole.TENANT_MEMBER, description="用户在当前租户下的角色")
    permissions: List[str] = Field(default_factory=list, description="细粒度权限列表")

    @property
    def is_master_admin(self) -> bool:
        """判定当前上下文是否具备平台级超级管理员（Master Admin）特权"""
        return (
            self.role == TenantRole.MASTER_ADMIN
            or self.tenant_id in ("master", "tenant_0", "admin")
        )


class BaseAgentSlice(BaseModel):
    """
    平台只读基线 Agent 切片（Base Slices）
    例如 Main, Supervision, Coder 等核心智能体，代码与系统 Prompt 物理不可变。
    """
    base_agent_id: str = Field(..., description="基线 Agent 标识符 (如 'main', 'supervision', 'coder')")
    name: str = Field(..., description="基线 Agent 名称")
    immutable_system_prompt: str = Field(..., description="平台级不可变核心 System Prompt")
    allowed_tools: List[str] = Field(default_factory=list, description="允许调用的工具白名单")
    version: str = Field(default="1.0.0", description="基线切片版本号")


class TenantAgentDelta(BaseModel):
    """
    租户私有声明式 Delta 配置
    租户仅可在基线之上零代码覆盖元数据与追加私有 Prompt，严禁修改底层代码与执行面。
    """
    tenant_id: str = Field(..., description="归属租户 ID")
    base_agent_id: str = Field(..., description="继承的目标基线 Agent ID")
    custom_name: Optional[str] = Field(default=None, description="租户自定义名称")
    custom_avatar: Optional[str] = Field(default=None, description="租户自定义头像 URL 或标识")
    private_prompt_delta: str = Field(default="", description="租户私有业务 Prompt 增量")
    subscribed_knowledge_packs: List[str] = Field(default_factory=list, description="挂载的已订阅知识包 ID 列表")
    is_active: bool = Field(default=True, description="切片是否启用")


class TenantAgentConfig(BaseModel):
    """
    合成后的运行时只读 Agent 切片配置
    由 BaseAgentSlice 与 TenantAgentDelta 组装而成。
    """
    tenant_id: str
    base_agent_id: str
    effective_name: str
    effective_avatar: Optional[str] = None
    effective_prompt: str
    allowed_tools: List[str] = Field(default_factory=list)
    subscribed_knowledge_packs: List[str] = Field(default_factory=list)
    is_active: bool = True
    version: str = "1.0.0"

    @classmethod
    def from_slice_and_delta(
        cls, base: BaseAgentSlice, delta: TenantAgentDelta
    ) -> TenantAgentConfig:
        """从基线切片与租户增量合成运行时配置"""
        if base.base_agent_id != delta.base_agent_id:
            raise ValueError(
                f"Base agent ID mismatch: base '{base.base_agent_id}' vs delta '{delta.base_agent_id}'"
            )

        effective_name = delta.custom_name if delta.custom_name else base.name
        effective_avatar = delta.custom_avatar

        if delta.private_prompt_delta.strip():
            effective_prompt = (
                f"{base.immutable_system_prompt}\n\n"
                f"[Tenant Context: {delta.tenant_id}]\n"
                f"{delta.private_prompt_delta.strip()}"
            )
        else:
            effective_prompt = base.immutable_system_prompt

        return cls(
            tenant_id=delta.tenant_id,
            base_agent_id=base.base_agent_id,
            effective_name=effective_name,
            effective_avatar=effective_avatar,
            effective_prompt=effective_prompt,
            allowed_tools=list(base.allowed_tools),
            subscribed_knowledge_packs=list(delta.subscribed_knowledge_packs),
            is_active=delta.is_active,
            version=base.version,
        )


class WorkflowNodeType(str, Enum):
    """合法工作流节点类型白名单"""
    LLM_INFERENCE = "LLM_INFERENCE"
    KNOWLEDGE_RETRIEVAL = "KNOWLEDGE_RETRIEVAL"
    PROMPT_TRANSFORM = "PROMPT_TRANSFORM"
    FILTER_PASS = "FILTER_PASS"
    AGGREGATION = "AGGREGATION"
    OUTPUT_FORMAT = "OUTPUT_FORMAT"


class WorkflowDSLNode(BaseModel):
    """工作流 DSL 节点定义"""
    id: str = Field(..., description="节点唯一标识符")
    node_type: WorkflowNodeType = Field(..., description="节点类型（必须在白名单内）")
    name: Optional[str] = Field(default=None, description="节点可读名称")
    parameters: Dict[str, Any] = Field(default_factory=dict, description="节点参数配置")

    @field_validator("parameters")
    @classmethod
    def validate_node_parameters(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """校验节点参数安全边界"""
        if "temperature" in v:
            temp = float(v["temperature"])
            if temp < 0.0 or temp > 2.0:
                raise ValueError(f"Parameter 'temperature' must be in range [0.0, 2.0], got {temp}")
        if "max_tokens" in v:
            tokens = int(v["max_tokens"])
            if tokens <= 0 or tokens > 128000:
                raise ValueError(f"Parameter 'max_tokens' must be in range (0, 128000], got {tokens}")
        return v


class WorkflowDSLEdge(BaseModel):
    """工作流 DSL 有向边定义"""
    source: str = Field(..., description="源节点 ID")
    target: str = Field(..., description="目标节点 ID")
    condition: Optional[str] = Field(default=None, description="转移条件描述（纯声明式）")


class WorkflowDSLPlan(BaseModel):
    """
    声明式工作流编排计划 AST 模型
    零代码执行面，所有调度完全基于数据驱动。
    """
    plan_id: str = Field(..., description="工作流唯一标识符")
    name: str = Field(default="", description="工作流名称")
    nodes: List[WorkflowDSLNode] = Field(default_factory=list, description="工作流节点列表")
    edges: List[WorkflowDSLEdge] = Field(default_factory=list, description="工作流有向依赖边列表")
    version: str = Field(default="1.0.0", description="DSL 格式版本")
