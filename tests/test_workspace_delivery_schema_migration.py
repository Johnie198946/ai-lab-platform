from __future__ import annotations

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from backend.db import _migrate_workspace_delivery_contract


def test_workspace_delivery_migration_backfills_revisions_and_is_idempotent() -> None:
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "CREATE TABLE workspace_business_intakes ("
            "id VARCHAR(40) PRIMARY KEY, project_id VARCHAR(40) NOT NULL, "
            "created_at TIMESTAMP NOT NULL)"
        )
        for table in (
            "workspace_artifacts",
            "workspace_artifact_versions",
            "workspace_delivery_manifests",
        ):
            connection.exec_driver_sql(f"CREATE TABLE {table} (id VARCHAR(48) PRIMARY KEY)")
        connection.execute(
            text(
                "INSERT INTO workspace_business_intakes (id, project_id, created_at) VALUES "
                "('intake-b', 'project-a', '2026-08-30 02:00:00'), "
                "('intake-a', 'project-a', '2026-08-30 01:00:00'), "
                "('intake-c', 'project-b', '2026-08-30 01:00:00')"
            )
        )

        _migrate_workspace_delivery_contract(connection)
        _migrate_workspace_delivery_contract(connection)

        columns = {item["name"] for item in inspect(connection).get_columns("workspace_business_intakes")}
        assert "revision" in columns
        rows = connection.execute(
            text(
                "SELECT id, project_id, revision FROM workspace_business_intakes "
                "ORDER BY project_id, revision"
            )
        ).all()
        assert rows == [
            ("intake-a", "project-a", 1),
            ("intake-b", "project-a", 2),
            ("intake-c", "project-b", 1),
        ]
        with pytest.raises(IntegrityError):
            connection.execute(
                text(
                    "INSERT INTO workspace_business_intakes "
                    "(id, project_id, created_at, revision) VALUES "
                    "('intake-duplicate', 'project-a', '2026-08-30 03:00:00', 2)"
                )
            )
