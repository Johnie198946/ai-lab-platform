"""Fail-closed M0.5A schema migration and deterministic legacy backfill."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from sqlalchemy import inspect, select, text

from backend.db import Base, canonical_plan_hash
from backend.models.workspace import (
    WorkspaceApprovalDecision,
    WorkspaceAuditEvent,
    WorkspaceGate,
    WorkspaceGateApprover,
    WorkspaceProcessRevision,
    WorkspaceProjectApprover,
    WorkspaceProjectConfigRevision,
    WorkspaceProjectMember,
    WorkspaceStage,
    WorkspaceTask,
    WorkspaceTaskConversation,
    WorkspaceTaskDependency,
    WorkspaceTaskMessage,
    WorkspaceTaskRevision,
)

M05A_TABLES = [
    WorkspaceProjectConfigRevision.__table__,
    WorkspaceProcessRevision.__table__,
    WorkspaceStage.__table__,
    WorkspaceTask.__table__,
    WorkspaceTaskRevision.__table__,
    WorkspaceGate.__table__,
    WorkspaceTaskDependency.__table__,
    WorkspaceProjectMember.__table__,
    WorkspaceProjectApprover.__table__,
    WorkspaceGateApprover.__table__,
    WorkspaceApprovalDecision.__table__,
    WorkspaceAuditEvent.__table__,
]

IMMUTABLE_TABLES = (
    "workspace_project_config_revisions",
    "workspace_process_revisions",
    "workspace_stages",
    "workspace_task_revisions",
    "workspace_gates",
    "workspace_task_dependencies",
)

CONVERSATION_FK_NAMES = {
    "fk_workspace_conversation_project_task",
    "workspace_task_conversations_workflow_id_fkey",
    "workspace_task_conversations_execution_id_fkey",
}


def _json(value: Any) -> Any:
    return json.loads(value) if isinstance(value, str) else value


def _stable_id(prefix: str, *parts: object) -> str:
    digest = sha256(":".join(str(part) for part in parts).encode()).hexdigest()[:32]
    return f"{prefix}_{digest}"


def _legacy_rows(connection) -> list[dict[str, Any]]:
    if "workspace_projects" not in set(inspect(connection).get_table_names()):
        return []
    return list(
        connection.execute(
            text(
                "SELECT id, tenant_key, owner_user_id, name, goal, desired_outputs, template_id, "
                "template_version, truth_mode, process_revision, process_snapshot "
                "FROM workspace_projects"
            )
        ).mappings()
    )


def _orphan_conversations(
    connection, projects: list[dict[str, Any]]
) -> tuple[list[str], list[str]]:
    if "workspace_task_conversations" not in set(inspect(connection).get_table_names()):
        return [], []
    task_ids_by_project = {
        str(row["id"]): {
            str(task["id"])
            for task in (_json(row["process_snapshot"]) or {}).get("tasks", [])
        }
        for row in projects
    }
    tables = set(inspect(connection).get_table_names())
    workflow_ids = (
        {
            str(row["id"])
            for row in connection.execute(text("SELECT id FROM workflows")).mappings()
        }
        if "workflows" in tables
        else set()
    )
    execution_ids = (
        {
            str(row["id"])
            for row in connection.execute(
                text("SELECT id FROM workflow_executions")
            ).mappings()
        }
        if "workflow_executions" in tables
        else set()
    )
    orphan_ids: set[str] = set()
    orphan_references: list[str] = []
    conversation_columns = {
        column["name"]
        for column in inspect(connection).get_columns("workspace_task_conversations")
    }
    selected_columns = ["id", "project_id", "task_id"] + [
        column for column in ("workflow_id", "execution_id")
        if column in conversation_columns
    ]
    select_sql = ", ".join(selected_columns)
    for row in connection.execute(
        text(f"SELECT {select_sql} FROM workspace_task_conversations")
    ).mappings():
        row = dict(row)
        row.setdefault("workflow_id", None)
        row.setdefault("execution_id", None)
        conversation_id = str(row["id"])
        if str(row["task_id"]) not in task_ids_by_project.get(str(row["project_id"]), set()):
            orphan_ids.add(conversation_id)
        for column, parent_ids in (
            ("workflow_id", workflow_ids),
            ("execution_id", execution_ids),
        ):
            value = row[column]
            if value is not None and str(value) not in parent_ids:
                orphan_ids.add(conversation_id)
                orphan_references.append(
                    f"{conversation_id}.{column}={value}"
                )
    return sorted(orphan_ids), sorted(orphan_references)


def _already_backfilled(connection) -> set[tuple[str, int]]:
    if "workspace_process_revisions" not in set(inspect(connection).get_table_names()):
        return set()
    return {
        (str(row.project_id), int(row.revision))
        for row in connection.execute(
            select(WorkspaceProcessRevision.project_id, WorkspaceProcessRevision.revision)
        )
    }


def _copy_common_columns(connection, source: str, target: str, table) -> None:
    source_columns = {item["name"] for item in inspect(connection).get_columns(source)}
    columns = [column for column in table.columns if column.name in source_columns]
    expressions = [
        (
            f'COALESCE("{column.name}", CURRENT_TIMESTAMP)'
            if column.name in {"created_at", "updated_at"}
            else f'"{column.name}"'
        )
        for column in columns
    ]
    # Legacy conversation rows predate identity/binding fields.  Fill them with
    # deterministic, non-authorizing values rather than dropping the rows.
    if table.name == "workspace_task_conversations":
        for name, expression in (
            ("tenant_key", "(SELECT tenant_key FROM workspace_projects WHERE id = workspace_task_conversations_m05a_old.project_id)"),
            ("user_id", "'legacy'"),
            ("session_id", "'legacy:' || id"),
            ("agent_version", "'legacy'"),
            ("binding", "'{}'"),
        ):
            if name not in source_columns:
                column = table.c[name]
                columns.append(column)
                expressions.append(expression)
    quoted = ", ".join(f'"{column.name}"' for column in columns)
    expression_sql = ", ".join(expressions)
    connection.exec_driver_sql(
        f'INSERT INTO "{target}" ({quoted}) SELECT {expression_sql} FROM "{source}"'
    )


def _rebuild_sqlite_conversations(connection) -> None:
    tables = set(inspect(connection).get_table_names())
    if "workspace_task_conversations" not in tables:
        WorkspaceTaskConversation.__table__.create(connection, checkfirst=True)
        return
    current = inspect(connection).get_foreign_keys("workspace_task_conversations")
    targets = {(tuple(fk["constrained_columns"]), fk["referred_table"]) for fk in current}
    required = {
        (("project_id", "task_id"), "workspace_tasks"),
        (("workflow_id",), "workflows"),
        (("execution_id",), "workflow_executions"),
    }
    if required <= targets:
        return

    has_messages = "workspace_task_messages" in tables
    if has_messages:
        connection.exec_driver_sql(
            "ALTER TABLE workspace_task_messages RENAME TO workspace_task_messages_m05a_old"
        )
    connection.exec_driver_sql(
        "ALTER TABLE workspace_task_conversations RENAME TO workspace_task_conversations_m05a_old"
    )
    WorkspaceTaskConversation.__table__.create(connection)
    _copy_common_columns(
        connection,
        "workspace_task_conversations_m05a_old",
        "workspace_task_conversations",
        WorkspaceTaskConversation.__table__,
    )
    if has_messages:
        WorkspaceTaskMessage.__table__.create(connection)
        _copy_common_columns(
            connection,
            "workspace_task_messages_m05a_old",
            "workspace_task_messages",
            WorkspaceTaskMessage.__table__,
        )
        connection.exec_driver_sql("DROP TABLE workspace_task_messages_m05a_old")
    connection.exec_driver_sql("DROP TABLE workspace_task_conversations_m05a_old")


def _postgres_add_fk(connection, name: str, ddl: str) -> None:
    names = {
        fk.get("name")
        for fk in inspect(connection).get_foreign_keys("workspace_task_conversations")
    }
    if name not in names:
        connection.exec_driver_sql(
            f'ALTER TABLE workspace_task_conversations ADD CONSTRAINT "{name}" {ddl}'
        )


def _alter_postgres_conversations(connection) -> None:
    _postgres_add_fk(
        connection,
        "fk_workspace_conversation_project_task",
        "FOREIGN KEY (project_id, task_id) REFERENCES workspace_tasks (project_id, id) ON DELETE RESTRICT",
    )
    _postgres_add_fk(
        connection,
        "workspace_task_conversations_workflow_id_fkey",
        "FOREIGN KEY (workflow_id) REFERENCES workflows (id) ON DELETE RESTRICT",
    )
    _postgres_add_fk(
        connection,
        "workspace_task_conversations_execution_id_fkey",
        "FOREIGN KEY (execution_id) REFERENCES workflow_executions (id) ON DELETE RESTRICT",
    )


def _verify_conversation_fks(connection) -> None:
    targets = {
        (tuple(fk["constrained_columns"]), fk["referred_table"])
        for fk in inspect(connection).get_foreign_keys("workspace_task_conversations")
    }
    required = {
        (("project_id", "task_id"), "workspace_tasks"),
        (("workflow_id",), "workflows"),
        (("execution_id",), "workflow_executions"),
    }
    if not required <= targets:
        raise RuntimeError(f"conversation foreign-key verification failed: {required - targets}")


def _install_immutable_guards(connection) -> None:
    dialect = connection.dialect.name
    if dialect == "sqlite":
        for table in IMMUTABLE_TABLES:
            for operation in ("UPDATE", "DELETE"):
                trigger = f"trg_{table}_immutable_{operation.lower()}"
                connection.exec_driver_sql(
                    f'CREATE TRIGGER IF NOT EXISTS "{trigger}" BEFORE {operation} ON "{table}" '
                    f"BEGIN SELECT RAISE(ABORT, '{table} is immutable'); END"
                )
        return
    if dialect == "postgresql":
        connection.exec_driver_sql(
            """
            CREATE OR REPLACE FUNCTION workspace_reject_immutable_revision()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RAISE EXCEPTION '% is immutable', TG_TABLE_NAME USING ERRCODE = 'integrity_constraint_violation'; END;
            $$
            """
        )
        for table in IMMUTABLE_TABLES:
            trigger = f"trg_{table}_immutable"
            connection.exec_driver_sql(f'DROP TRIGGER IF EXISTS "{trigger}" ON "{table}"')
            connection.exec_driver_sql(
                f'CREATE TRIGGER "{trigger}" BEFORE UPDATE OR DELETE ON "{table}" '
                "FOR EACH ROW EXECUTE FUNCTION workspace_reject_immutable_revision()"
            )


def _backfill_project_config_and_owner(connection, row: dict[str, Any]) -> str:
    project_id = str(row["id"])
    config = {
        "name": row["name"],
        "goal": row["goal"],
        "desired_outputs": _json(row["desired_outputs"]) or [],
        "template_id": row["template_id"],
        "template_version": row["template_version"],
        "truth_mode": row["truth_mode"],
    }
    config_id = _stable_id("cfgrev", project_id, 1)
    if connection.execute(
        select(WorkspaceProjectConfigRevision.id).where(
            WorkspaceProjectConfigRevision.project_id == project_id,
            WorkspaceProjectConfigRevision.revision == 1,
        )
    ).scalar_one_or_none() is None:
        connection.execute(
            WorkspaceProjectConfigRevision.__table__.insert().values(
                id=config_id,
                project_id=project_id,
                revision=1,
                canonical_hash=canonical_plan_hash(config),
                snapshot=config,
            )
        )
    owner_member_id = _stable_id("member", project_id, row["owner_user_id"])
    if connection.execute(
        select(WorkspaceProjectMember.id).where(
            WorkspaceProjectMember.project_id == project_id,
            WorkspaceProjectMember.user_id == row["owner_user_id"],
        )
    ).scalar_one_or_none() is None:
        connection.execute(
            WorkspaceProjectMember.__table__.insert().values(
                id=owner_member_id,
                tenant_key=row["tenant_key"],
                project_id=project_id,
                user_id=row["owner_user_id"],
                request_id=f"legacy-owner:{project_id}",
                role="owner",
                scopes=["project:read", "project:write"],
                status="ACTIVE",
            )
        )
    return config_id


def _backfill_process(connection, row: dict[str, Any], config_id: str) -> None:
    project_id = str(row["id"])
    revision = int(row["process_revision"])
    process = _json(row["process_snapshot"]) or {}
    process_id = _stable_id("procrev", project_id, revision)
    connection.execute(
        WorkspaceProcessRevision.__table__.insert().values(
            id=process_id,
            project_id=project_id,
            config_revision_id=config_id,
            revision=revision,
            canonical_hash=canonical_plan_hash(process),
            legacy_snapshot=process,
        )
    )
    for task in process.get("tasks", []):
        task_id = str(task["id"])
        if connection.execute(
            select(WorkspaceTask.id).where(
                WorkspaceTask.project_id == project_id,
                WorkspaceTask.id == task_id,
            )
        ).scalar_one_or_none() is None:
            connection.execute(
                WorkspaceTask.__table__.insert().values(
                    id=task_id,
                    project_id=project_id,
                    tenant_key=row["tenant_key"],
                )
            )
    for position, stage in enumerate(process.get("stages", [])):
        connection.execute(
            WorkspaceStage.__table__.insert().values(
                id=_stable_id("stagefact", process_id, position),
                process_revision_id=process_id,
                stage_id=stage["id"],
                position=position,
                facts=stage,
            )
        )
    for position, task in enumerate(process.get("tasks", [])):
        connection.execute(
            WorkspaceTaskRevision.__table__.insert().values(
                id=_stable_id("taskfact", process_id, position),
                process_revision_id=process_id,
                task_project_id=project_id,
                task_id=task["id"],
                stage_id=task["stage_id"],
                position=position,
                facts=task,
            )
        )
    for position, gate in enumerate(process.get("gates", [])):
        connection.execute(
            WorkspaceGate.__table__.insert().values(
                id=_stable_id("gatefact", process_id, position),
                process_revision_id=process_id,
                gate_id=gate["id"],
                stage_id=gate["stage_id"],
                position=position,
                facts=gate,
            )
        )
    for position, dependency in enumerate(process.get("dependencies", [])):
        connection.execute(
            WorkspaceTaskDependency.__table__.insert().values(
                id=_stable_id("dependency", process_id, position),
                process_revision_id=process_id,
                project_id=project_id,
                from_task_id=dependency["from_task_id"],
                to_task_id=dependency["to_task_id"],
                position=position,
            )
        )


def migrate_workspace_schema(
    connection,
    *,
    dry_run: bool = False,
    fail_after_backfill: bool = False,
) -> dict[str, Any]:
    """Migrate inside the caller transaction; orphan references block every write."""
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
    projects = _legacy_rows(connection)
    orphans, orphan_references = _orphan_conversations(connection, projects)
    existing = _already_backfilled(connection)
    pending = [
        row
        for row in projects
        if int(row["process_revision"] or 0) > 0
        and (str(row["id"]), int(row["process_revision"])) not in existing
    ]
    report = {
        "dry_run": dry_run,
        "projects_scanned": len(projects),
        "projects_to_backfill": len(pending),
        "orphan_conversation_ids": orphans,
        "orphan_conversation_references": orphan_references,
        "revisions_written": 0,
    }
    if dry_run:
        return report
    if orphans:
        details = orphan_references or [f"conversation_id={conversation_id}" for conversation_id in orphans]
        raise RuntimeError(
            "orphan task conversations block migration: " + ", ".join(details)
        )

    Base.metadata.create_all(connection, tables=M05A_TABLES, checkfirst=True)
    for row in projects:
        config_id = _backfill_project_config_and_owner(connection, row)
        key = (str(row["id"]), int(row["process_revision"] or 0))
        if int(row["process_revision"] or 0) > 0 and key not in existing:
            _backfill_process(connection, row, config_id)
            report["revisions_written"] += 1

    if connection.dialect.name == "sqlite":
        _rebuild_sqlite_conversations(connection)
    elif connection.dialect.name == "postgresql":
        _alter_postgres_conversations(connection)
    else:
        raise RuntimeError(f"unsupported migration dialect: {connection.dialect.name}")
    _verify_conversation_fks(connection)
    _install_immutable_guards(connection)

    if fail_after_backfill:
        raise RuntimeError("injected migration failure")
    return report
