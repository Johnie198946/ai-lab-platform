"""
FastAPI 主入口 — OpenAPI 文档配置
"""

import logging

from fastapi import FastAPI, Depends
from fastapi.openapi.utils import get_openapi
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from backend.api.errors import register_error_handlers
from backend.api.screens import router as screens_router
from backend.api.tasks import router as tasks_router
from backend.api.knowledge import router as knowledge_router
from backend.api.chat import router as chat_router
from backend.api.register import router as register_router
from backend.api.catalog import router as catalog_router
from backend.api.me import router as me_router
from backend.api.auth import require_auth, check_dev_visibility_guard
from backend.api.orchestration import router as orchestration_router

from backend.api.protocols import router as protocols_router
from backend.api.agents import router as agents_router
from backend.api.notifications import router as notifications_router
from backend.api.topology import router as topology_router
from backend.api.skills import router as skills_router
from backend.api.tenant_agents import router as tenant_agents_router
from backend.api.hermes import router as hermes_router
from backend.api.showroom import router as showroom_router
from backend.api.customer_demands import router as customer_demands_router
from backend.api.workflows import router as workflows_router
from backend.api.knowledge_policy import router as knowledge_policy_router
from backend.api.knowledge_sync import router as knowledge_sync_router
from backend.api.knowledge_actions import router as knowledge_actions_router
from backend.api.subscriptions import router as subscriptions_router
from backend.api.knowledge_publication import router as knowledge_publication_router
from backend.api.hot_memory import router as hot_memory_router
from backend.db import init_db

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动: 启动守卫 + 初始化数据库表(幂等) + 启动 Agent 调度器。"""
    # 启动守卫：JWT secret 为空 → 开发态全可见，隔离承诺不生效
    check_dev_visibility_guard()
    db_ready = True
    try:
        await init_db()
    except Exception:
        db_ready = False
        logger.exception("Database initialization failed; file-backed features remain available")
    if db_ready:
        try:
            from backend.services.workflow_migration import migrate_legacy_workflows

            await migrate_legacy_workflows()
        except Exception:
            logger.exception("Legacy workflow migration failed; continuing startup")
        try:
            from backend.api.workflows import resume_pending_planning

            await resume_pending_planning()
        except Exception:
            logger.exception("Durable planning-job recovery failed; worker will retry")
    # 启动平台 Agent 调度器(容器重启自动恢复)
    from backend.services.agent_scheduler import start_scheduler

    start_scheduler()
    from backend.services.entitlement_sync import start_entitlement_sync

    start_entitlement_sync()
    yield
    from backend.services.agent_scheduler import stop_scheduler

    stop_scheduler()
    from backend.services.entitlement_sync import stop_entitlement_sync

    await stop_entitlement_sync()


app = FastAPI(
    title="AI Lab Platform",
    description="""
## xFusion AI Lab 知识库平台 API

### 核心概念
- **知识库**: 原始材料 + 编译知识层 + knowledge_matrix 机读接口
- **编译链**: Ingest → Diff → Synth → Distill
- **Agent / Harness**: 调度 + 状态 + 日志 + policy + ledger
- **多租户知识策略**: 绿色公共知识默认可见；黄色知识由 Authen 组织套餐授权；红色知识仅所属租户可见
  （租户由 Bearer JWT 派生，不信任客户端 X-Tenant-ID 头）

### 认证
使用 Authen 统一认证，所有接口需带 `Authorization: Bearer <Authen JWT>`。
""",
    version="0.8.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 中间件（错误处理；租户已由 require_auth 从 JWT 派生，不再用 header 中间件）
register_error_handlers(app)

# ---------- 路由 ----------
# 除 /health、/api/v1/register 外均需 Authen Bearer JWT 认证
app.include_router(screens_router, dependencies=[Depends(require_auth)])
app.include_router(tasks_router, dependencies=[Depends(require_auth)])
# 知识引擎: 矩阵/检索/wiki/实体（订阅过滤）
app.include_router(knowledge_router, dependencies=[Depends(require_auth)])
# 用户笔记只同步到 raw/dialogues；编译、治理和正式存储继续由平台既有链路负责。
app.include_router(knowledge_sync_router, dependencies=[Depends(require_auth)])
app.include_router(knowledge_actions_router, dependencies=[Depends(require_auth)])
# 问答: 基于知识库的回答（订阅过滤 + 会话记录）
app.include_router(chat_router, dependencies=[Depends(require_auth)])
# 前端原型编排: 角色生成与编辑回写
app.include_router(orchestration_router, dependencies=[Depends(require_auth)])
# 注册（/register 公开；/admin/users 端点自带超管校验）
app.include_router(register_router)
# 目录 / 订阅管理 / 当前用户
app.include_router(catalog_router, dependencies=[Depends(require_auth)])
app.include_router(subscriptions_router, dependencies=[Depends(require_auth)])
app.include_router(knowledge_publication_router, dependencies=[Depends(require_auth)])
app.include_router(hot_memory_router, dependencies=[Depends(require_auth)])
app.include_router(me_router, dependencies=[Depends(require_auth)])
# Agent 协议签署
app.include_router(protocols_router, dependencies=[Depends(require_auth)])


# 挂载 Agent 调度与通知中心
app.include_router(agents_router, dependencies=[Depends(require_auth)])
app.include_router(notifications_router, dependencies=[Depends(require_auth)])
# 拓扑注册表（对话页 Agent 选择栏 + 拓扑页 DAG 同源消费）
app.include_router(topology_router, dependencies=[Depends(require_auth)])
# 租户真实技能库（挂载目录扫描·非演示数据）
app.include_router(skills_router, dependencies=[Depends(require_auth)])
# 租户 Agent 切片（基于基线 profile 的 Delta 角色扮演 · 多租户隔离）
app.include_router(tenant_agents_router, dependencies=[Depends(require_auth)])
# Hermes serve 集成（Tab 1 官方 Web 容器认证通道 · B-2-2）
app.include_router(hermes_router, dependencies=[Depends(require_auth)])
# 展厅运行态：HTTP 端点在路由内鉴权，WebSocket 使用 query token 单独验签。
app.include_router(showroom_router)
app.include_router(customer_demands_router, dependencies=[Depends(require_auth)])
# 可执行工作流：计划审批、持久执行、素材复核
app.include_router(workflows_router, dependencies=[Depends(require_auth)])
# Authen HMAC webhook + signed-capability Knowledge Gateway use their own auth.
app.include_router(knowledge_policy_router)

# ---------- 健康检查 ----------
@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.8.0"}


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
