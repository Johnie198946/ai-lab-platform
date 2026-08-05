"""
FastAPI 主入口 — OpenAPI 文档配置
"""

from fastapi import FastAPI
from fastapi.openapi.utils import get_openapi
from backend.api.errors import register_error_handlers
from backend.api.tenant import TenantMiddleware

app = FastAPI(
    title="AI Lab Platform",
    description="""
## xFusion AI Lab 知识库平台 API

### 核心概念
- **知识库**: 原始文章 + 来源卡片 + 专题档案
- **编译链**: Ingest → Diff → Synth → Distill
- **Agent**: 调度 + 状态 + 日志
- **多租户**: 所有请求需带 `X-Tenant-ID` 头

### 认证
使用 Authen 统一认证，所有接口需带 `Authorization: Bearer <token>`
    """,
    version="0.1.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json",
)

# 中间件
register_error_handlers(app)
app.add_middleware(TenantMiddleware)


# ---------- 健康检查 ----------
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# 自动生成 OpenAPI schema
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
    )
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
