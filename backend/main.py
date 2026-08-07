"""
FastAPI 主入口 — OpenAPI 文档配置
"""

from fastapi import FastAPI, Depends
from fastapi.openapi.utils import get_openapi
from contextlib import asynccontextmanager
from backend.api.errors import register_error_handlers
from backend.api.screens import router as screens_router
from backend.api.tasks import router as tasks_router
from backend.api.knowledge import router as knowledge_router
from backend.api.chat import router as chat_router
from backend.api.register import router as register_router
from backend.api.catalog import router as catalog_router
from backend.api.me import router as me_router
from backend.api.auth import require_auth
from backend.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动: 初始化数据库表（幂等）。"""
    try:
        await init_db()
    except Exception:
        # DB 不可用时不阻塞启动（知识库文件驱动功能仍可用）
        pass
    yield


app = FastAPI(
    title="AI Lab Platform",
    description="""
## xFusion AI Lab 知识库平台 API

### 核心概念
- **知识库**: 原始文章 + 来源卡片 + 专题档案
- **编译链**: Ingest → Diff → Synth → Distill
- **Agent**: 调度 + 状态 + 日志
- **多租户（订阅制）**: 每个用户默认空知识库，订阅知识分类后可见；超管可见全部
  （租户由 Bearer JWT 派生，不信任客户端 X-Tenant-ID 头）

### 认证
使用 Authen 统一认证，所有接口需带 `Authorization: Bearer <Authen JWT>`。
""",
    version="0.7.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 中间件（错误处理；租户已由 require_auth 从 JWT 派生，不再用 header 中间件）
register_error_handlers(app)

# ---------- 路由 ----------
# 除 /health、/api/v1/register 外均需 Authen Bearer JWT 认证
app.include_router(screens_router, dependencies=[Depends(require_auth)])
app.include_router(tasks_router, dependencies=[Depends(require_auth)])
# 知识引擎: 矩阵/检索/wiki/实体（订阅过滤）
app.include_router(knowledge_router, dependencies=[Depends(require_auth)])
# 问答: 基于知识库的回答（订阅过滤 + 会话记录）
app.include_router(chat_router, dependencies=[Depends(require_auth)])
# 注册（/register 公开；/admin/users 端点自带超管校验）
app.include_router(register_router)
# 目录 / 订阅管理 / 当前用户
app.include_router(catalog_router, dependencies=[Depends(require_auth)])
app.include_router(me_router, dependencies=[Depends(require_auth)])


# ---------- 健康检查 ----------
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.7.0"}


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
