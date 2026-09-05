"""Explicit V4 schema upgrade hook; call under init_db's schema lock/transaction.

No runtime/executor lives here. New tables are registered by the contribution
model import. Existing V1 outbox rows retain their IDs and receive an empty epoch,
so no old authorization snapshot can pass the V4 result fence.
"""
from sqlalchemy import MetaData, Table, inspect, select, literal
from backend.models.knowledge_contribution import KnowledgeContributionOutbox


def migrate_knowledge_contribution_v4(connection) -> None:
    table = KnowledgeContributionOutbox.__table__
    schema = inspect(connection)
    if table.name not in schema.get_table_names():
        table.create(connection)
        return
    columns = {item["name"] for item in schema.get_columns(table.name)}
    expected = ["tenant_key", "user_id", "source_surface", "source_kind", "source_id",
                "source_revision", "content_hash", "policy_version", "authorization_epoch"]
    unique = schema.get_unique_constraints(table.name)
    if {"authorization_epoch", "source_changed_at"} <= columns and any(
        item["column_names"] == expected for item in unique
    ):
        return
    if connection.dialect.name == "sqlite":
        # SQLite cannot ALTER a table-level unique constraint. Rebuild only our
        # table, preserving every business row; caller owns the transaction.
        legacy = Table(table.name, MetaData(), autoload_with=connection)
        upgraded = table.to_metadata(MetaData(), name="knowledge_contribution_outbox_v4_upgrade")
        # Existing named indexes would collide before the old table is removed.
        for index in list(upgraded.indexes):
            upgraded.indexes.remove(index)
        upgraded.create(connection)
        fields = [col.name for col in table.columns]
        values = [legacy.c[name] if name in columns else
                  literal("" if name == "authorization_epoch" else None).label(name)
                  for name in fields]
        connection.execute(upgraded.insert().from_select(fields, select(*values)))
        legacy.drop(connection)
        connection.exec_driver_sql("ALTER TABLE knowledge_contribution_outbox_v4_upgrade RENAME TO knowledge_contribution_outbox")
        for index in table.indexes:
            index.create(connection)
        return
    if connection.dialect.name != "postgresql":
        raise RuntimeError("V4 migration supports PostgreSQL and SQLite only")
    connection.exec_driver_sql("ALTER TABLE knowledge_contribution_outbox ADD COLUMN IF NOT EXISTS authorization_epoch VARCHAR(64) NOT NULL DEFAULT ''")
    connection.exec_driver_sql("ALTER TABLE knowledge_contribution_outbox ADD COLUMN IF NOT EXISTS source_changed_at TIMESTAMP WITH TIME ZONE")
    connection.exec_driver_sql("ALTER TABLE knowledge_contribution_outbox DROP CONSTRAINT IF EXISTS uq_knowledge_contribution_source_hash_policy")
    connection.exec_driver_sql("ALTER TABLE knowledge_contribution_outbox ADD CONSTRAINT uq_knowledge_contribution_source_hash_policy UNIQUE (tenant_key, user_id, source_surface, source_kind, source_id, source_revision, content_hash, policy_version, authorization_epoch)")
