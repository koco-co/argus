"""Roadmap 5.2：运行时 SQL 只读包装器及数据库断言验收。"""

from __future__ import annotations

from typing import Any

import pytest  # pyright: ignore[reportMissingImports]

from shared.assertions.db_asserts import assert_row_exists
from shared.db.readonly_client import ReadOnlyDBClient


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


class _Connection:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows = [{"id": 1}] if rows is None else rows
        self.calls: list[tuple[str, tuple[Any, ...]]] = []

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result:
        self.calls.append((sql, params))
        return _Result(self.rows)


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT 1",
        "  ( SELECT * FROM products)",
        "SHOW search_path",
        "TABLE products",
        "WITH x AS (SELECT 1) SELECT * FROM x",
        "EXPLAIN SELECT * FROM products",
    ],
)
def test_read_statements_pass(sql: str) -> None:
    conn = _Connection()
    # pi-lens-ignore: python-sql-injection
    assert ReadOnlyDBClient(conn).query(sql) == [{"id": 1}]


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO products VALUES (1)",
        "UPDATE products SET title='x'",
        "DELETE FROM products",
        "SELECT 1; DROP TABLE products",
        "WITH x AS (INSERT INTO products VALUES (1) RETURNING *) SELECT * FROM x",
        "WITH x AS (DELETE FROM products RETURNING *) SELECT * FROM x",
        "EXPLAIN ANALYZE UPDATE products SET title='x'",
        "EXPLAIN (ANALYZE true) DELETE FROM products",
        "PRAGMA table_info(products)",
        "DESCRIBE products",
    ],
)
def test_write_or_multi_statement_is_blocked(sql: str) -> None:
    conn = _Connection()
    with pytest.raises(PermissionError, match="ReadOnlyDBClient"):
        # pi-lens-ignore: python-sql-injection
        ReadOnlyDBClient(conn).query(sql)
    assert conn.calls == []


def test_with_literal_mentioning_update_fails_closed() -> None:
    with pytest.raises(PermissionError):
        ReadOnlyDBClient(_Connection()).query("WITH x AS (SELECT 'update') SELECT * FROM x")


def test_sample_db_assertion_uses_readonly_wrapper() -> None:
    client = ReadOnlyDBClient(_Connection(rows=[{"email": "guest@example.invalid"}]))
    assert_row_exists(client, "SELECT email FROM customer WHERE id = %s", ("cus_1",))


def test_sample_db_assertion_fails_for_empty_result() -> None:
    client = ReadOnlyDBClient(_Connection(rows=[]))
    with pytest.raises(AssertionError, match="未返回任何记录"):
        assert_row_exists(client, "SELECT id FROM customer WHERE id = %s", ("missing",))
