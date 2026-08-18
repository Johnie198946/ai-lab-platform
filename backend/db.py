"""
平台数据库层 — 异步 SQLAlchemy（asyncpg）

表: tenant_mappings / knowledge_subscriptions / knowledge_catalog /
     tenant_sessions / tenant_usage
启动时自动建表（init_db）。
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://ailab:ailab_dev@localhost:5432/ai_lab",
)

_engine_kwargs: dict = {"pool_pre_ping": True}
if not DATABASE_URL.startswith("sqlite"):
    _engine_kwargs["pool_size"] = 5

engine = create_async_engine(DATABASE_URL, **_engine_kwargs)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """启动时建表(幂等)。"""
    import backend.models.tenant  # noqa: F401  (注册模型到 metadata)
    import backend.models.protocol  # noqa: F401  (注册协议模型)
    import backend.models.agent  # noqa: F401  (注册子 Agent 模型)
    import backend.models.notification  # noqa: F401  (注册通知模型)
    import backend.models.tenant_agent  # noqa: F401  (注册租户 Agent 切片模型)
    import backend.models.showroom  # noqa: F401  (注册共创体验中心会话模型)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """FastAPI 依赖: 异步会话。"""
    async with SessionLocal() as session:
        yield session
