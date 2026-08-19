"""
平台数据库层 — 异步 SQLAlchemy（asyncpg）

表: tenant_mappings / knowledge_subscriptions / knowledge_catalog /
     tenant_sessions / tenant_usage
启动时自动建表（init_db）。
"""

from __future__ import annotations

import os

from sqlalchemy import inspect
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
    import backend.models.workflow  # noqa: F401  (注册持久工作流模型)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.run_sync(_migrate_workflow_v2_columns)
        await conn.run_sync(_migrate_knowledge_policy_v2_columns)


def _migrate_workflow_v2_columns(connection) -> None:
    """Additive migration for deployments that already have V1 workflow tables.

    The project intentionally has no destructive startup migrations.  New installs are
    handled by ``create_all``; existing installs only receive nullable/defaulted telemetry
    and Hermes resume columns.
    """
    schema = inspect(connection)
    tables = set(schema.get_table_names())
    if "workflow_executions" not in tables:
        return
    dialect = connection.dialect.name
    float_type = "DOUBLE PRECISION" if dialect == "postgresql" else "REAL"
    execution_columns = {
        "input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
        "api_calls": "INTEGER NOT NULL DEFAULT 0",
        "estimated_cost_usd": f"{float_type} NOT NULL DEFAULT 0",
        "model_used": "VARCHAR(120) NOT NULL DEFAULT ''",
        "provider_used": "VARCHAR(80) NOT NULL DEFAULT ''",
        "route_reason": "VARCHAR(500) NOT NULL DEFAULT ''",
        "idempotency_key": "VARCHAR(160)",
        "hermes_session_id": "VARCHAR(120)",
        "bridge_event_seq": "INTEGER NOT NULL DEFAULT 0",
    }
    existing = {item["name"] for item in schema.get_columns("workflow_executions")}
    for name, definition in execution_columns.items():
        if name not in existing:
            connection.exec_driver_sql(
                f'ALTER TABLE workflow_executions ADD COLUMN "{name}" {definition}'
            )
    connection.exec_driver_sql(
        "UPDATE workflow_executions SET idempotency_key = "
        "'legacy:' || id WHERE idempotency_key IS NULL"
    )
    connection.exec_driver_sql(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_workflow_executions_idempotency_key "
        "ON workflow_executions (idempotency_key)"
    )

    if "workflow_node_runs" not in tables:
        return
    node_columns = {
        "input_tokens": "INTEGER NOT NULL DEFAULT 0",
        "output_tokens": "INTEGER NOT NULL DEFAULT 0",
        "reasoning_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cache_read_tokens": "INTEGER NOT NULL DEFAULT 0",
        "cache_write_tokens": "INTEGER NOT NULL DEFAULT 0",
        "api_calls": "INTEGER NOT NULL DEFAULT 0",
        "estimated_cost_usd": f"{float_type} NOT NULL DEFAULT 0",
        "model_used": "VARCHAR(120) NOT NULL DEFAULT ''",
        "provider_used": "VARCHAR(80) NOT NULL DEFAULT ''",
    }
    existing_nodes = {item["name"] for item in schema.get_columns("workflow_node_runs")}
    for name, definition in node_columns.items():
        if name not in existing_nodes:
            connection.exec_driver_sql(
                f'ALTER TABLE workflow_node_runs ADD COLUMN "{name}" {definition}'
            )


def _migrate_knowledge_policy_v2_columns(connection) -> None:
    """Additive migration for the catalog-to-policy V2 transition."""
    schema = inspect(connection)
    if "knowledge_catalog" not in set(schema.get_table_names()):
        return
    existing = {item["name"] for item in schema.get_columns("knowledge_catalog")}
    columns = {
        "security_level": "VARCHAR(16) NOT NULL DEFAULT 'green'",
        "owner_tenant": "VARCHAR(64) NOT NULL DEFAULT 'public'",
        "entitlement_key": "VARCHAR(128) NOT NULL DEFAULT ''",
        "is_active": "BOOLEAN NOT NULL DEFAULT TRUE",
    }
    for name, definition in columns.items():
        if name not in existing:
            connection.exec_driver_sql(
                f'ALTER TABLE knowledge_catalog ADD COLUMN "{name}" {definition}'
            )
    if "tenant_entitlement_snapshots" in set(schema.get_table_names()):
        snapshot_columns = {
            item["name"] for item in schema.get_columns("tenant_entitlement_snapshots")
        }
        if "last_event_id" not in snapshot_columns:
            connection.exec_driver_sql(
                "ALTER TABLE tenant_entitlement_snapshots "
                "ADD COLUMN last_event_id VARCHAR(255) NOT NULL DEFAULT ''"
            )


async def get_session():
    """FastAPI 依赖: 异步会话。"""
    async with SessionLocal() as session:
        yield session
