"""
多租户上下文 — 订阅制逻辑隔离

租户从 JWT 派生（require_auth 写入），不再信任客户端 X-Tenant-ID 头。
- current_tenant: 当前请求的 tenant_key
- current_visibility: None = 全部可见（超管）；frozenset[str] = 已订阅分类集合
"""

from __future__ import annotations

from contextvars import ContextVar
from typing import FrozenSet, Optional

current_tenant: ContextVar[str] = ContextVar("tenant_id", default="")
current_visibility: ContextVar[Optional[FrozenSet[str]]] = ContextVar(
    "visibility", default=None
)


def tenant_filter(column: str = "tenant_id") -> str:
    """生成 SQL 租户过滤条件（供后续租户维数据查询使用）。"""
    t = current_tenant.get()
    if not t:
        return "1=1"
    return f"{column} = '{t}'"
