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

engine = create_async_engine(DATABASE_URL, pool_pre_ping=True, pool_size=5)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db() -> None:
    """启动时建表（幂等）。"""
    import backend.models.tenant  # noqa: F401  (注册模型到 metadata)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session():
    """FastAPI 依赖: 异步会话。"""
    async with SessionLocal() as session:
        yield session
