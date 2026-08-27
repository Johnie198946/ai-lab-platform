"""
backend/services/tenant_isolation_middleware.py
===============================================
多租户上下文提取器与 ABAC 数据库/向量 Pre-filter 生成器。
实现零外部 Web 框架强绑定的纯 Python 轻量级中间件与内存匹配引擎。
"""

from __future__ import annotations
import json
from typing import Dict, Any, Optional, Tuple, Union, List

from backend.models.tenant_agent_schema import TenantContext, TenantRole
from backend.models.knowledge_subscription_schema import (
    KnowledgeItemMetadata,
    SecurityLevel,
)


class TenantContextExtractor:
    """
    租户安全上下文提取器
    支持从 JWT Payload Claims 或 HTTP Headers 中安全反序列化 TenantContext。
    """

    @staticmethod
    def from_jwt_claims(claims: Dict[str, Any]) -> TenantContext:
        """
        从 JWT Claims 字典中提取租户上下文
        """
        tenant_id = claims.get("tenant_id") or claims.get("tid") or claims.get("tenant")
        user_id = claims.get("user_id") or claims.get("uid") or claims.get("sub")

        if not tenant_id:
            raise ValueError("JWT claims must contain 'tenant_id', 'tid', or 'tenant'")
        if not user_id:
            raise ValueError("JWT claims must contain 'user_id', 'uid', or 'sub'")

        raw_role = claims.get("role") or claims.get("user_role") or "tenant_member"
        try:
            role = TenantRole(str(raw_role).lower())
        except ValueError:
            role = TenantRole.TENANT_MEMBER

        raw_permissions = claims.get("permissions", [])
        if isinstance(raw_permissions, str):
            permissions = [p.strip() for p in raw_permissions.split(",") if p.strip()]
        elif isinstance(raw_permissions, list):
            permissions = [str(p) for p in raw_permissions]
        else:
            permissions = []

        return TenantContext(
            tenant_id=str(tenant_id),
            user_id=str(user_id),
            role=role,
            permissions=permissions,
        )

    @staticmethod
    def from_headers(headers: Dict[str, Any]) -> TenantContext:
        """
        从 HTTP 请求头中提取租户上下文（大小写不敏感）
        """
        norm_headers = {str(k).lower(): str(v) for k, v in headers.items()}

        tenant_id = (
            norm_headers.get("x-tenant-id")
            or norm_headers.get("tenant-id")
            or norm_headers.get("tenant_id")
        )
        user_id = (
            norm_headers.get("x-user-id")
            or norm_headers.get("user-id")
            or norm_headers.get("user_id")
        )

        if not tenant_id:
            raise ValueError("Headers must contain 'X-Tenant-ID'")
        if not user_id:
            raise ValueError("Headers must contain 'X-User-ID'")

        raw_role = (
            norm_headers.get("x-user-role")
            or norm_headers.get("user-role")
            or norm_headers.get("role")
            or "tenant_member"
        )
        try:
            role = TenantRole(raw_role.lower())
        except ValueError:
            role = TenantRole.TENANT_MEMBER

        raw_perm = norm_headers.get("x-permissions") or norm_headers.get("permissions")
        permissions: List[str] = []
        if raw_perm:
            try:
                parsed = json.loads(raw_perm)
                if isinstance(parsed, list):
                    permissions = [str(p) for p in parsed]
                else:
                    permissions = [str(raw_perm)]
            except Exception:
                permissions = [p.strip() for p in raw_perm.split(",") if p.strip()]

        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            permissions=permissions,
        )


class ABACPreFilterGenerator:
    """
    ABAC (Attribute-Based Access Control) 检索预过滤器生成器
    实现数据库/向量库 Pre-filter 表达式生成与内存中知识可见性断言判定。
    """

    @staticmethod
    def build_sql_filter(
        context: TenantContext,
        domain: Optional[str] = None,
        dialect: str = "postgresql",
    ) -> Tuple[str, Dict[str, Any]]:
        """
        生成带有参数化绑定的 SQL WHERE 过滤子句与参数字典

        支持两种 SQL 方言：
        - dialect="postgresql" (默认):
          ((tenant = :current_tenant) OR (tenant = 'public' AND (security_level = 'green' OR :current_tenant = ANY(subscribers))))
        - dialect="sqlite":
          ((tenant = :current_tenant) OR (tenant = 'public' AND (security_level = 'green' OR EXISTS (SELECT 1 FROM json_each(subscribers) WHERE value = :current_tenant))))
        """
        params: Dict[str, Any] = {"current_tenant": context.tenant_id}

        if context.is_master_admin:
            # Master Admin 具备全局穿透视野
            tenant_clause = "(1 = 1)"
        else:
            dialect_lower = dialect.lower().strip()
            if dialect_lower == "sqlite":
                tenant_clause = (
                    "((tenant = :current_tenant) OR "
                    "(tenant = 'public' AND (security_level = 'green' OR "
                    "EXISTS (SELECT 1 FROM json_each(subscribers) WHERE value = :current_tenant))))"
                )
            else:  # postgresql (default)
                tenant_clause = (
                    "((tenant = :current_tenant) OR "
                    "(tenant = 'public' AND (security_level = 'green' OR :current_tenant = ANY(subscribers))))"
                )

        if domain and domain.strip():
            domain_clause = "(domain = :req_domain OR domain = 'general')"
            params["req_domain"] = domain.strip()
            full_sql = f"{tenant_clause} AND {domain_clause}"
        else:
            full_sql = tenant_clause

        return full_sql, params

    @classmethod
    def matches_in_memory(
        cls,
        context: TenantContext,
        item: Union[KnowledgeItemMetadata, Dict[str, Any]],
        domain: Optional[str] = None,
    ) -> bool:
        """
        内存中断言判定单条知识是否对当前租户上下文可见。
        包含 Fail-Safe 降级逻辑：缺失标签条目自动回退为 public / general / green。
        """
        # 1. 规范化元数据
        if isinstance(item, KnowledgeItemMetadata):
            item_tenant = item.tenant or "public"
            item_domain = item.domain or "general"
            item_sec_level = item.security_level or SecurityLevel.GREEN
            item_subscribers = item.subscribers or []
        elif isinstance(item, dict):
            item_tenant = item.get("tenant") or "public"
            item_domain = item.get("domain") or "general"
            raw_sec = item.get("security_level") or "green"
            try:
                item_sec_level = SecurityLevel(str(raw_sec).lower())
            except ValueError:
                item_sec_level = SecurityLevel.GREEN
            item_subscribers = item.get("subscribers") or []
        else:
            return False

        # 2. 领域 (Domain) 过滤判定
        if domain and domain.strip():
            req_dom = domain.strip().lower()
            if item_domain.lower() != req_dom and item_domain.lower() != "general":
                return False

        # 3. 租户与安全等级 (Tenant & Security Level) 过滤判定
        if context.is_master_admin:
            return True

        # (a) 属于当前租户的私有知识
        if item_tenant == context.tenant_id:
            return True

        # (b) 属于公共知识池 (tenant == 'public')
        if item_tenant == "public":
            if item_sec_level == SecurityLevel.GREEN:
                return True
            if item_sec_level == SecurityLevel.YELLOW:
                # 黄色受限知识必须在已授权订阅者列表中
                return context.tenant_id in item_subscribers
            if item_sec_level == SecurityLevel.RED:
                # 红色公共知识（异常定级）仅 Master 可见，普通租户恒不可见
                return False

        # (c) 其他租户私有知识，绝对不可见
        return False
