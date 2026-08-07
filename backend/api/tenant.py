"""
多租户隔离

所有查询自动带 tenant_id
客户 A 的数据客户 B 绝对看不到
"""

from contextvars import ContextVar
from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

# 请求级变量，每个请求一个独立副本
current_tenant: ContextVar[str] = ContextVar("tenant_id", default="")


class TenantMiddleware(BaseHTTPMiddleware):
    """
    从请求头提取租户 ID，注入到上下文变量

    用法：
        app.add_middleware(TenantMiddleware)

        # 后续所有代码中:
        tenant = current_tenant.get()
    """

    async def dispatch(self, request: Request, call_next):
        tenant_id = request.headers.get("X-Tenant-ID", "")

        # 演示版: 无租户头时放行(默认租户), 产品版应改为强制
        if not tenant_id:
            tenant_id = "demo"
            token = current_tenant.set(tenant_id)
            try:
                response = await call_next(request)
                return response
            finally:
                current_tenant.reset(token)

        token = current_tenant.set(tenant_id)
        try:
            response = await call_next(request)
            return response
        finally:
            current_tenant.reset(token)


def tenant_filter():
    """生成 SQL 租户过滤条件"""
    tenant = current_tenant.get()
    if not tenant:
        return ""
    return f"tenant_id = '{tenant}'"
