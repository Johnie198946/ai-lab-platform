from __future__ import annotations

from dataclasses import dataclass

import backend.db as database_module


class _Schema:
    def __init__(self, column_type: str) -> None:
        self.column_type = column_type

    def get_table_names(self) -> list[str]:
        return ["showroom_insight_executions"]

    def get_columns(self, table: str) -> list[dict[str, object]]:
        assert table == "showroom_insight_executions"
        return [{"name": "epoch", "type": self.column_type}]


@dataclass
class _Dialect:
    name: str = "postgresql"


class _Connection:
    def __init__(self) -> None:
        self.dialect = _Dialect()
        self.statements: list[str] = []

    def exec_driver_sql(self, statement: str) -> None:
        self.statements.append(statement)


def test_existing_integer_epoch_is_widened(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(database_module, "inspect", lambda _: _Schema("INTEGER"))

    database_module._migrate_showroom_epoch_bigint(connection)

    assert connection.statements == [
        "ALTER TABLE showroom_insight_executions "
        "ALTER COLUMN epoch TYPE BIGINT USING epoch::BIGINT"
    ]


def test_existing_bigint_epoch_is_left_unchanged(monkeypatch) -> None:
    connection = _Connection()
    monkeypatch.setattr(database_module, "inspect", lambda _: _Schema("BIGINT"))

    database_module._migrate_showroom_epoch_bigint(connection)

    assert connection.statements == []
