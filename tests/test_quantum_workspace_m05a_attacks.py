from __future__ import annotations

import json
import sqlite3

import pytest
from sqlalchemy import create_engine, inspect, text

from backend.services.workspace_migration import (
    _ensure_card_session_registry_profile,
    migrate_workspace_schema,
)


def _snapshot(task_id: str = "shared-task") -> dict:
    return {
        "process_instance_id": "proc-legacy",
        "template_id": "ipd-product-development",
        "template_version": "1.0.0",
        "truth": "REVIEWED_CONFIGURATION",
        "status": "ACTIVE",
        "stages": [{"id": "stage-1", "name": "concept", "order": 0}],
        "tasks": [{"id": task_id, "stage_id": "stage-1", "title": "task", "status": "TODO"}],
        "gates": [{"id": "gate-1", "stage_id": "stage-1", "name": "TR1"}],
        "dependencies": [],
        "graphs": {},
    }


def test_card_session_registry_additive_profile_migration(tmp_path):
    path = tmp_path / "session-profile.db"
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE workspace_card_session_registry "
            "(id VARCHAR(48) PRIMARY KEY, title VARCHAR(240) NOT NULL)"
        )
        _ensure_card_session_registry_profile(connection)
        _ensure_card_session_registry_profile(connection)
        columns = {item["name"] for item in inspect(connection).get_columns(
            "workspace_card_session_registry"
        )}
    assert "task_profile" in columns


def _legacy_db(path, projects: list[tuple], conversations: list[tuple] = ()) -> None:
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE workspace_projects (
                id VARCHAR(40) PRIMARY KEY, tenant_key VARCHAR(64) NOT NULL,
                owner_user_id VARCHAR(64) NOT NULL, name VARCHAR(160) NOT NULL,
                goal TEXT NOT NULL, desired_outputs JSON NOT NULL,
                template_id VARCHAR(80), template_version VARCHAR(32),
                truth_mode VARCHAR(20) NOT NULL, process_revision INTEGER NOT NULL,
                process_snapshot JSON NOT NULL
            );
            CREATE TABLE workflows (id VARCHAR(48) PRIMARY KEY);
            CREATE TABLE workflow_executions (id VARCHAR(48) PRIMARY KEY);
            CREATE TABLE workspace_task_conversations (
                id VARCHAR(40) PRIMARY KEY, tenant_key VARCHAR(64) NOT NULL,
                user_id VARCHAR(64) NOT NULL, project_id VARCHAR(40) NOT NULL,
                task_id VARCHAR(40) NOT NULL, workflow_id VARCHAR(48),
                execution_id VARCHAR(48), session_id VARCHAR(100) NOT NULL,
                agent_version VARCHAR(80) NOT NULL, binding JSON NOT NULL,
                created_at DATETIME, updated_at DATETIME
            );
            """
        )
        db.executemany(
            "INSERT INTO workspace_projects VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [(*row[:10], json.dumps(row[10])) for row in projects],
        )
        db.executemany(
            "INSERT INTO workspace_task_conversations VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            conversations,
        )


def _project(project_id: str, tenant: str, owner: str, revision: int, task_id: str = "shared-task") -> tuple:
    snapshot = _snapshot(task_id) if revision else {
        "process_instance_id": None,
        "stages": [], "tasks": [], "gates": [], "dependencies": [], "graphs": {},
    }
    return (
        project_id, tenant, owner, project_id, "goal", "[]",
        "ipd-product-development", "1.0.0", "PLANNED", revision, snapshot,
    )


def test_orphan_apply_is_fail_closed_and_performs_zero_writes(tmp_path):
    path = tmp_path / "orphan.db"
    _legacy_db(
        path,
        [_project("p1", "t1", "u1", 1)],
        [("orphan", "t1", "u1", "p1", "missing", None, None, "s", "a", "{}", None, None)],
    )
    engine = create_engine(f"sqlite:///{path}")

    with pytest.raises(RuntimeError, match="orphan"):
        with engine.begin() as connection:
            migrate_workspace_schema(connection)

    with sqlite3.connect(path) as db:
        tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert "workspace_process_revisions" not in tables
        assert db.execute("SELECT count(*) FROM workspace_task_conversations").fetchone()[0] == 1


def test_normalized_task_identity_keeps_dashi_card_conversation_non_orphan(tmp_path):
    path = tmp_path / "dashi-card-anchor.db"
    _legacy_db(
        path,
        [_project("p1", "t1", "u1", 0)],
        [("card", "t1", "u1", "p1", "dashi-card", None, None, "s", "a", "{}", None, None)],
    )
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE workspace_tasks (
                id VARCHAR(40) NOT NULL,
                project_id VARCHAR(40) NOT NULL,
                tenant_key VARCHAR(64) NOT NULL,
                created_at DATETIME,
                PRIMARY KEY (project_id, id),
                FOREIGN KEY(project_id) REFERENCES workspace_projects(id) ON DELETE CASCADE
            );
            """
        )
        db.execute(
            "INSERT INTO workspace_tasks (id, project_id, tenant_key) VALUES (?, ?, ?)",
            ("dashi-card", "p1", "t1"),
        )

    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        dry_run = migrate_workspace_schema(connection, dry_run=True)
        assert dry_run["orphan_conversation_ids"] == []
        migrated = migrate_workspace_schema(connection)

    assert migrated["orphan_conversation_ids"] == []
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT count(*) FROM workspace_task_conversations WHERE id='card'"
        ).fetchone()[0] == 1


def test_existing_sqlite_conversation_workflow_and_execution_orphans_fail_closed(
    tmp_path,
):
    path = tmp_path / "workflow-execution-orphans.db"
    _legacy_db(
        path,
        [_project("p1", "t1", "u1", 1)],
        [
            (
                "orphan-workflow",
                "t1",
                "u1",
                "p1",
                "shared-task",
                "missing-workflow",
                None,
                "s1",
                "a",
                "{}",
                None,
                None,
            ),
            (
                "orphan-execution",
                "t1",
                "u1",
                "p1",
                "shared-task",
                None,
                "missing-execution",
                "s2",
                "a",
                "{}",
                None,
                None,
            ),
        ],
    )
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        before = db.execute(
            "SELECT id, workflow_id, execution_id FROM workspace_task_conversations "
            "ORDER BY id"
        ).fetchall()

    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        dry_run = migrate_workspace_schema(connection, dry_run=True)
    assert dry_run["orphan_conversation_references"] == [
        "orphan-execution.execution_id=missing-execution",
        "orphan-workflow.workflow_id=missing-workflow",
    ]

    with pytest.raises(RuntimeError, match="orphan.*workflow_id=missing-workflow"):
        with engine.begin() as connection:
            migrate_workspace_schema(connection)

    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='workspace_task_conversations'"
        ).fetchone() is not None
        assert db.execute(
            "SELECT id, workflow_id, execution_id FROM workspace_task_conversations "
            "ORDER BY id"
        ).fetchall() == before
        assert db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' "
            "AND name='workspace_process_revisions'"
        ).fetchone() is None


def test_migration_backfills_revision_zero_config_owner_and_real_conversation_fks(tmp_path):
    path = tmp_path / "valid.db"
    _legacy_db(
        path,
        [_project("p0", "t1", "owner0", 0), _project("p1", "t1", "owner1", 1)],
        [("valid", "t1", "owner1", "p1", "shared-task", None, None, "s", "a", "{}", None, None)],
    )
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        report = migrate_workspace_schema(connection)
        assert connection.exec_driver_sql("PRAGMA foreign_keys").scalar_one() == 1
        fks = inspect(connection).get_foreign_keys("workspace_task_conversations")
        targets = {(tuple(fk["constrained_columns"]), fk["referred_table"]) for fk in fks}
        assert (("project_id", "task_id"), "workspace_tasks") in targets
        assert (("workflow_id",), "workflows") in targets
        assert (("execution_id",), "workflow_executions") in targets
        assert report["projects_scanned"] == 2

    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM workspace_project_config_revisions").fetchone()[0] == 2
        assert db.execute("SELECT count(*) FROM workspace_project_members WHERE role='owner'").fetchone()[0] == 2
        db.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO workspace_task_conversations "
                "(id,tenant_key,user_id,project_id,task_id,session_id,agent_version,binding) "
                "VALUES ('bad','t1','u','p0','shared-task','s','a','{}')"
            )


def test_project_scoped_task_identity_prevents_cross_project_same_id_linkage(tmp_path):
    path = tmp_path / "composite.db"
    _legacy_db(path, [_project("p1", "t1", "u1", 1), _project("p2", "t2", "u2", 1)])
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        migrate_workspace_schema(connection)

    with sqlite3.connect(path) as db:
        tasks = db.execute(
            "SELECT project_id,id,tenant_key FROM workspace_tasks ORDER BY project_id"
        ).fetchall()
        links = db.execute(
            "SELECT r.project_id,tr.task_project_id,tr.task_id "
            "FROM workspace_task_revisions tr JOIN workspace_process_revisions r "
            "ON r.id=tr.process_revision_id ORDER BY r.project_id"
        ).fetchall()
    assert tasks == [("p1", "shared-task", "t1"), ("p2", "shared-task", "t2")]
    assert links == [("p1", "p1", "shared-task"), ("p2", "p2", "shared-task")]


def test_normalized_fk_closure_and_revision_rows_are_db_immutable(tmp_path):
    path = tmp_path / "closure.db"
    _legacy_db(path, [_project("p1", "t1", "u1", 1)])
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        migrate_workspace_schema(connection)
        inspector = inspect(connection)
        task_fks = inspector.get_foreign_keys("workspace_task_revisions")
        gate_fks = inspector.get_foreign_keys("workspace_gates")
        dep_fks = inspector.get_foreign_keys("workspace_task_dependencies")
        decision_fks = inspector.get_foreign_keys("workspace_approval_decisions")
        assert any(fk["referred_table"] == "workspace_stages" for fk in task_fks)
        assert any(fk["referred_table"] == "workspace_stages" for fk in gate_fks)
        assert sum(fk["referred_table"] == "workspace_task_revisions" for fk in dep_fks) == 2
        assert any(fk["referred_table"] == "workspace_process_revisions" for fk in decision_fks)
        assert any(fk["referred_table"] == "workspace_gates" for fk in decision_fks)

    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys=ON")
        process_id = db.execute("SELECT id FROM workspace_process_revisions").fetchone()[0]
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(
                "UPDATE workspace_process_revisions SET canonical_hash=? WHERE id=?",
                ("0" * 64, process_id),
            )
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute("DELETE FROM workspace_process_revisions WHERE id=?", (process_id,))
